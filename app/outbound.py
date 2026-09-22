"""One outbound path, backed by a real loopback HTTP receiver, never a cloud API."""

import base64
import hashlib
import html
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, quote_plus

import httpx


def assert_no_known_pii(wire: bytes, document: dict):
    """Bounded assertion about detected entities, not an arbitrary-PII detector."""
    for span in document["spans"]:
        if span["kind"] == "LITERAL":
            continue
        raw = document["mapping"][span["token"]]
        representations = {
            raw,
            json.dumps(raw, ensure_ascii=True)[1:-1],
            quote(raw, safe=""),
            quote_plus(raw),
            html.escape(raw),
            base64.b64encode(raw.encode()).decode(),
        }
        if any(value.encode() in wire for value in representations if value):
            raise ValueError("outbound_pii_blocked")


class LocalReceiver:
    def __init__(self):
        self.secret = secrets.token_urlsafe(32)
        self.captures = {}
        self.lock = threading.Lock()
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                if self.headers.get("X-Receiver-Key") != receiver.secret or self.path not in {
                    "/complete",
                    "/embed",
                }:
                    self.send_error(403)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 800_000:
                    self.send_error(413)
                    return
                body = self.rfile.read(length)
                capture_id = self.headers.get("X-Capture-Id", "")
                # Keep exact serialized request bytes for verification; don't log them.
                raw = self.requestline.encode() + b"\r\n" + self.headers.as_bytes() + b"\r\n" + body
                with receiver.lock:
                    receiver.captures[capture_id] = (body, raw)
                response = json.dumps(
                    {"mode": "local_mock", "received_bytes": len(body), "operation": self.path[1:]}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class MaskedLlmClient:
    def __init__(self, vault, receiver: LocalReceiver):
        self.vault = vault
        self.receiver = receiver

    def complete(self, owner, document_id):
        return self._send(owner, document_id, "complete")

    def embed(self, owner, document_id):
        return self._send(owner, document_id, "embed")

    def _send(self, owner, document_id, operation):
        document = self.vault.get(owner, document_id)
        payload = {"model": "local-mock-no-llm", "document_id": document_id}
        if operation == "complete":
            payload["messages"] = [{"role": "user", "content": document["masked_text"]}]
        else:
            payload["input"] = document["masked_text"]
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
        assert_no_known_pii(body, document)  # Fail closed BEFORE the socket call.
        capture_id = secrets.token_hex(16)
        try:
            with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
                request = client.build_request(
                    "POST",
                    f"{self.receiver.url}/{operation}",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Receiver-Key": self.receiver.secret,
                        "X-Capture-Id": capture_id,
                    },
                )
                assert_no_known_pii(str(request.headers).encode() + request.content, document)
                response = client.send(request)
                response.raise_for_status()
            with self.receiver.lock:
                captured_body, wire = self.receiver.captures.pop(capture_id)
            assert_no_known_pii(wire, document)
            if captured_body != body:
                raise ValueError("capture_mismatch")
            return {
                "mode": "local_mock",
                "operation": operation,
                "verified": True,
                "scope": "detected_entities_only",
                "checked_entity_count": sum(document["counts"].values()),
                "body_bytes": len(captured_body),
                "body_sha256": hashlib.sha256(captured_body).hexdigest(),
                "transport": "HTTP / 127.0.0.1",
                "captured_payload": json.loads(captured_body),
                "serialized_body": captured_body.decode("ascii"),
            }
        finally:
            with self.receiver.lock:
                self.receiver.captures.pop(capture_id, None)
