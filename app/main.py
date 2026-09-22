import asyncio
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.masking import mask, restore
from app.outbound import LocalReceiver, MaskedLlmClient
from app.storage import Vault

ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger("privacy_wall")
COOKIE = "privacy_session"
TTL = 8 * 60 * 60


def create_app(data_dir=None, key_dir=None, dev_viewer=None):
    data_dir = Path(data_dir or ROOT / ".local" / "data")
    key_dir = Path(
        key_dir
        or Path(os.getenv("LOCALAPPDATA", str(Path.home() / ".local"))) / "PIIPrivacyWall" / "keys"
    )
    viewer = dev_viewer if dev_viewer is not None else os.getenv("PII_DEV_VIEWER") == "1"
    sessions = {}

    @asynccontextmanager
    async def lifespan(app):
        app.state.vault = Vault(data_dir, key_dir)
        app.state.receiver = LocalReceiver()
        app.state.gateway = MaskedLlmClient(app.state.vault, app.state.receiver)
        yield
        app.state.receiver.close()

    app = FastAPI(
        title="PII Privacy Wall", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def security(request, call_next):
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
            if (origin and origin != expected) or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "cross_origin_blocked"}, status_code=403)
            if request.method != "GET" and request.headers.get("x-privacy-wall") != "1":
                return JSONResponse({"detail": "request_header_required"}, status_code=403)
        try:
            response = await call_next(request)
        except Exception:
            # No exception repr, request body, filename, PII or mapping in logs.
            LOG.error("request_failed")
            response = JSONResponse({"detail": "request_failed"}, status_code=500)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            }
        )
        return response

    def owner(request):
        token = request.cookies.get(COOKIE)
        if not token or sessions.get(token, 0) < time.time():
            raise HTTPException(401, "session_required")
        return token

    def read_document(request, document_id):
        try:
            return app.state.vault.get(owner(request), document_id)
        except KeyError:
            raise HTTPException(404, "document_not_found") from None

    async def bounded_body(request, maximum=800_000):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > maximum:
                raise HTTPException(413, "document_too_large")
        return bytes(body)

    async def save_document(request, text):
        session = owner(request)
        started = time.perf_counter()
        try:
            document = await asyncio.to_thread(mask, text)
        except ValueError:
            raise HTTPException(422, "invalid_document_or_too_many_entities") from None
        result = await asyncio.to_thread(app.state.vault.save, session, document)
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
        LOG.info(
            "document_masked id=%s entity_count=%d",
            result["document_id"],
            sum(result["counts"].values()),
        )
        return result

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "local_only", "external_ai": False}

    @app.post("/api/session")
    def session(request: Request):
        now = time.time()
        for expired in [key for key, expiry in sessions.items() if expiry < now]:
            del sessions[expired]
        token = request.cookies.get(COOKIE)
        if token not in sessions:
            if len(sessions) >= 1000:
                raise HTTPException(429, "session_limit")
            token = secrets.token_urlsafe(32)
        sessions[token] = now + TTL
        response = JSONResponse({"mode": "local_only", "dev_viewer": viewer})
        response.set_cookie(COOKIE, token, max_age=TTL, httponly=True, samesite="strict", path="/")
        return response

    @app.get("/api/samples/{sample}")
    def sample(sample: str, request: Request):
        owner(request)
        choices = {"mixed": "mixed.txt", "clean": "clean.txt", "edge": "edge.txt"}
        if sample not in choices:
            raise HTTPException(404, "sample_not_found")
        return {
            "text": (ROOT / "fixtures" / choices[sample]).read_text(encoding="utf-8"),
            "synthetic": True,
        }

    @app.post("/api/documents")
    async def documents(request: Request):
        owner(request)
        try:
            payload = json.loads(await bounded_body(request))
        except (ValueError, UnicodeError):
            raise HTTPException(422, "invalid_json") from None
        if (
            not isinstance(payload, dict)
            or set(payload) != {"text"}
            or not isinstance(payload["text"], str)
        ):
            raise HTTPException(422, "expected_text_only")
        return await save_document(request, payload["text"])

    @app.post("/api/documents/upload")
    async def upload(request: Request):
        owner(request)
        if request.headers.get("x-file-extension", "").lower() != ".txt":
            raise HTTPException(415, "txt_only")
        try:
            text = (await bounded_body(request, 400_000)).decode("utf-8-sig")
        except UnicodeError:
            raise HTTPException(422, "utf8_required") from None
        return await save_document(request, text)

    @app.post("/api/documents/{document_id}/restore")
    def rehydrate(document_id: str, request: Request):
        document = read_document(request, document_id)
        return {
            "text": restore(document),
            "spans": document["spans"],
            "offset_unit": "unicode_code_point",
        }

    @app.post("/api/documents/{document_id}/send/{operation}")
    def send(document_id: str, operation: str, request: Request):
        session = owner(request)
        if operation not in {"complete", "embed"}:
            raise HTTPException(404, "operation_not_found")
        try:
            result = getattr(app.state.gateway, operation)(session, document_id)
        except KeyError:
            raise HTTPException(404, "document_not_found") from None
        except Exception:
            LOG.warning("outbound_blocked_or_unavailable")
            raise HTTPException(502, "outbound_blocked_or_unavailable") from None
        if not viewer:
            result.pop("captured_payload")
            result.pop("serialized_body")
        return result

    @app.delete("/api/documents/{document_id}")
    def delete(document_id: str, request: Request):
        if not app.state.vault.delete(owner(request), document_id):
            raise HTTPException(404, "document_not_found")
        return {"deleted": True}

    @app.get("/")
    def index():
        return FileResponse(ROOT / "app" / "static" / "index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")
    return app
