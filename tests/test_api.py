import base64
import json
import logging
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.masking import mask
from app.outbound import assert_no_known_pii

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HEADERS = {"X-Privacy-Wall": "1"}


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "data", tmp_path / "keys", dev_viewer=True)
    with TestClient(app, headers=HEADERS) as client:
        assert client.post("/api/session").status_code == 200
        yield client


def upload(client, text=None):
    if text is None:
        text = (FIXTURES / "mixed.txt").read_text(encoding="utf-8")
    response = client.post("/api/documents", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def test_mask_restore_no_mapping_and_headers(client):
    text = (FIXTURES / "mixed.txt").read_text(encoding="utf-8")
    document = upload(client, text)
    assert "mapping" not in document
    assert "Jane Smith" not in json.dumps(document)
    response = client.post(f"/api/documents/{document['document_id']}/restore")
    assert response.json()["text"] == text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["offset_unit"] == "unicode_code_point"
    assert "default-src 'self'" in response.headers["content-security-policy"]


@pytest.mark.parametrize("operation", ["complete", "embed"])
def test_actual_serialized_http_request_has_no_known_raw_pii(client, operation):
    document = upload(client)
    response = client.post(f"/api/documents/{document['document_id']}/send/{operation}")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["verified"] is True
    assert result["transport"] == "HTTP / 127.0.0.1"
    assert result["checked_entity_count"] == 9
    assert result["mode"] == "local_mock"
    payload = result["serialized_body"]
    assert "[CLIENT_1]" in payload
    for raw in [
        "Jane Smith",
        "jane.smith@example.test",
        "987-65-4321",
        "AC-99120",
        "$125,000.00",
        "123 Maple",
    ]:
        assert raw not in payload
    assert "mapping" not in payload
    assert "filename" not in payload
    assert not client.app.state.receiver.captures


def test_wrong_session_cannot_restore_send_or_delete(client):
    document = upload(client)
    client.cookies.clear()
    assert client.post("/api/session").status_code == 200
    for path in ["restore", "send/complete", "send/embed"]:
        assert client.post(f"/api/documents/{document['document_id']}/{path}").status_code == 404
    assert client.delete(f"/api/documents/{document['document_id']}").status_code == 404


def test_unauthenticated_and_cross_origin_requests_blocked(client):
    client.cookies.clear()
    assert client.post("/api/documents", json={"text": "hello"}).status_code == 401
    assert client.post("/api/session", headers={"Origin": "https://attacker.invalid"}).status_code == 403
    assert client.post("/api/session", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/api/session", headers={"X-Privacy-Wall": ""}).status_code == 403
    assert client.get("/api/health", headers={"Host": "attacker.invalid"}).status_code == 400


def test_storage_encrypted_and_delete(client):
    document = upload(client)
    db_bytes = client.app.state.vault.path.read_bytes()
    for value in [b"Jane Smith", b"987-65-4321", b"AC-99120", b"jane.smith@example.test"]:
        assert value not in db_bytes
    assert b"[CLIENT_1]" in db_bytes
    assert client.delete(f"/api/documents/{document['document_id']}").json() == {"deleted": True}
    assert client.post(f"/api/documents/{document['document_id']}/restore").status_code == 404


def test_upload_txt_bom_unicode_and_crlf(client):
    text = "边界 🔒\r\nClient: Jane Smith\r\nSSN: 123-45-6789\r\n"
    response = client.post(
        "/api/documents/upload",
        content=b"\xef\xbb\xbf" + text.encode(),
        headers={"X-File-Extension": ".txt"},
    )
    assert response.status_code == 200
    doc_id = response.json()["document_id"]
    assert client.post(f"/api/documents/{doc_id}/restore").json()["text"] == text
    assert (
        client.post(
            "/api/documents/upload", content=b"%PDF", headers={"X-File-Extension": ".pdf"}
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/api/documents/upload", content=b"\xff", headers={"X-File-Extension": ".txt"}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "payload",
    [{"text": "ok", "metadata": "Jane Smith"}, {"text": ["Jane Smith"]}, ["Jane Smith"], {"text": ""}],
)
def test_invalid_input_never_echoes_pii(client, payload):
    response = client.post("/api/documents", json=payload)
    assert response.status_code == 422
    assert "Jane Smith" not in response.text


def test_payload_size_limit(client):
    response = client.post("/api/documents", content=b"x" * 800001)
    assert response.status_code == 413


def test_mask_failure_fails_closed(client, monkeypatch, caplog):
    def fail(_):
        raise RuntimeError("secret Jane Smith 123-45-6789")

    monkeypatch.setattr("app.main.mask", fail)
    with caplog.at_level(logging.INFO):
        response = client.post("/api/documents", json={"text": "Client: Jane Smith"})
    assert response.status_code == 500
    assert "Jane Smith" not in response.text + caplog.text
    assert "123-45-6789" not in caplog.text
    assert not client.app.state.receiver.captures


def test_logs_do_not_contain_raw_pii_on_success_or_network_failure(client, monkeypatch, caplog):
    def fail(*_, **__):
        raise httpx.TimeoutException("secret Jane Smith 123-45-6789")

    with caplog.at_level(logging.INFO):
        document = upload(client)
        gateway = client.app.state.gateway
        original = gateway.complete

        def unavailable(*args):
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(httpx.Client, "send", fail)
                return original(*args)

        monkeypatch.setattr(gateway, "complete", unavailable)
        response = client.post(f"/api/documents/{document['document_id']}/send/complete")
    assert response.status_code == 502
    for raw in ["Jane Smith", "123-45-6789", "987-65-4321", "jane.smith@example.test"]:
        assert raw not in caplog.text + response.text
    assert not client.app.state.receiver.captures


def test_preflight_catches_raw_and_encoded_values():
    document = mask("Client: Jane Smith\nEmail: jane@example.test")
    for value in [
        "Jane Smith",
        quote("Jane Smith"),
        base64.b64encode(b"Jane Smith").decode(),
        "jane@example.test",
    ]:
        with pytest.raises(ValueError, match="outbound_pii_blocked"):
            assert_no_known_pii(value.encode(), document)


def test_tampered_masked_cache_is_blocked_before_socket(client, monkeypatch):
    document = upload(client)
    real_get = client.app.state.vault.get

    def tampered(*args):
        result = real_get(*args)
        result["masked_text"] += " Jane Smith"
        return result

    monkeypatch.setattr(client.app.state.vault, "get", tampered)
    response = client.post(f"/api/documents/{document['document_id']}/send/complete")
    assert response.status_code == 502
    assert not client.app.state.receiver.captures


def test_viewer_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("PII_DEV_VIEWER", raising=False)
    with TestClient(create_app(tmp_path / "data", tmp_path / "keys"), headers=HEADERS) as client:
        assert client.post("/api/session").json()["dev_viewer"] is False
        doc = upload(client)
        result = client.post(f"/api/documents/{doc['document_id']}/send/embed").json()
        assert result["verified"]
        assert "captured_payload" not in result
        assert "serialized_body" not in result
