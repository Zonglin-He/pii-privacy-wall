# Privacy Wall

A local implementation of **Service 1 / AI-1: PII Masking & Security**. Detect personal information, replace it with stable tokens, inspect real serialized HTTP requests, and restore the original in an authorized browser session.

**No API key. No external LLM or embedding calls.** The completion and embedding targets are local HTTP mock receivers. They verify the privacy boundary; they do not perform AI inference or compliance review.

## Run

On this machine, the environment is already installed:

~~~powershell
Set-Location 'C:\PyCharm Project\pii-privacy-wall'
.\.venv\Scripts\python.exe run.py --dev-viewer
~~~

Open **http://127.0.0.1:8765**. If the application is already running, open the URL directly.

For a fresh checkout, install Python 3.11+ and uv, then:

~~~powershell
uv sync --frozen
uv run --frozen python run.py --dev-viewer
~~~

The initial dependency installation may use the network. Application operation does not require internet access, model downloads, Node.js, or API credentials. Dependencies are locked in uv.lock.

The payload viewer is **disabled by default**. Enable it explicitly with --dev-viewer for the demonstration. Use --port 8766 if you need a different port. The launcher binds only to 127.0.0.1. Press Ctrl+C to stop a foreground instance.

## Try the workflow

1. Choose **Agreement**, upload a UTF-8 TXT file, or paste document text.
2. Select **Mask document**. The synthetic agreement produces **9 occurrences across 7 entity types**. All three instances of Jane Smith use the same token.
3. Select **Test completion** and **Test embedding**. The summary should show **2 / 2 verified**.
4. In developer mode, inspect the captured JSON body and SHA-256 digest. Detected names, SSNs, accounts and personal amounts should not appear as raw values.
5. Select **Restore original** to check exact text reconstruction and entity highlights.
6. Try **Clean control** for false-positive checks and **Edge cases** for fullwidth numbers, overlapping entities, existing placeholders and inert HTML.
7. Select **Delete document** to remove the current record and clear the workspace.

The English interface supports desktop and mobile layouts. It uses no CDN fonts, scripts, telemetry, or third-party assets.

## Architecture

~~~text
Browser -> local API -> detector -> overlap resolver -> stable token mapper
                                            |
                           masked text + encrypted mapping in SQLite
                                            |
                       MaskedLlmClient.complete() / embed()
                                            |
                   preflight validation -> loopback HTTP receiver
                                            |
                    captured-body and header checks -> viewer

Authorized restore -> decrypt mapping -> reconstruct source -> safe text rendering
~~~

| File | Responsibility |
| --- | --- |
| app/masking.py | Seven entity types, normalization view, overlap resolution, stable tokens, reversible spans |
| app/storage.py | SQLite, Fernet-encrypted mappings, document/session isolation, deletion |
| app/outbound.py | Both outbound entry points, preflight checks, actual loopback HTTP transport, receiver verification |
| app/main.py | Session and document APIs, bounded uploads, origin checks, safe error responses |
| app/static/ | English responsive UI, document highlighting, upload, restore and request viewer |
| fixtures/ | Synthetic mixed, clean and adversarial examples |
| tests/ | Detector and HTTP integration tests |
| scripts/browser_smoke.js | Repeatable browser acceptance workflow |

## Privacy controls

- Seven types: person names, email, phone, address, SSN, account number, and person-associated dollar amounts.
- Repeated exact entity values share a token within one document. Documents do not share mappings.
- Existing source placeholders are protected as literal spans, preventing accidental rehydration.
- All offsets are Unicode code points. Browser rendering uses code-point arrays rather than incorrect UTF-16 slicing.
- Mapping encryption uses Fernet from cryptography. No custom cryptographic algorithm.
- The key is stored outside the project at %LOCALAPPDATA%\PIIPrivacyWall\keys\vault.key on Windows. The database is in .local/data/documents.sqlite3.
- Windows ACLs restrict the key and data directories to the current user SID. POSIX uses directory mode 0700 and key mode 0600.
- Uploaded files and original file names are not persisted. The upload path sends raw TXT content, not the source filename.
- Cookies are HttpOnly and SameSite=Strict. Origin and request-header checks block cross-origin mutations.
- Restore responses use Cache-Control: no-store. Source text and mappings are not saved in localStorage or sessionStorage.
- Application logs contain IDs/counts/error codes, not source text. The launcher disables access logging.
- Detection, decryption and transport failures do not trigger raw-text fallback requests.
- The receiver is loopback-only, authenticated internally, and created by the application. Environment proxies and redirects are disabled.

Session lifetime is eight hours and session state is in process memory. Restarting the server invalidates previous browser sessions. Older records are not reassigned to a new session. This is a local demo, not a durable document-management platform.

## Tests

~~~powershell
uv run --frozen pytest -q --junitxml=output/test-results.xml
uv run --frozen ruff check .
~~~

The integration tests open a real local HTTP socket and inspect the received body. They also check parsed receiver headers, known raw values, and selected encoded representations. They are not limited to inspecting a Python object before serialization.

Browser verification uses Playwright CLI, which is optional and not needed to run the application:

~~~powershell
npx --yes --package @playwright/cli playwright-cli -s=privacy-wall open http://127.0.0.1:8765 --headed
npx --yes --package @playwright/cli playwright-cli -s=privacy-wall run-code --filename scripts/browser_smoke.js
~~~

Read [VALIDATION.md](VALIDATION.md) for verified results, [MASKER_LIMITATIONS.md](MASKER_LIMITATIONS.md) for coverage limits, and [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) for the recording sequence. Video recording is handled by the user.

## Scope

This submission implements Service 1 only. It does not implement legal compliance decisions, semantic disclosure checking, precedent retrieval, PDFs, DOCX, OCR, or a real cloud-model adapter.

**A passed request check means detected entities were not found in that request. It is not proof that every possible PII entity was detected.** Use the included synthetic fixtures for demonstrations.

The original assignment is preserved in [docs/AI Tasks.md](docs/AI%20Tasks.md). Technical references: [Fernet](https://cryptography.io/en/latest/fernet/) and [FastAPI](https://fastapi.tiangolo.com/).
