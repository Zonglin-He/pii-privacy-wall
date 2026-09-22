# Validation report

Date: 2026-09-22. Platform: Windows, Python 3.13.5. Dependencies: uv.lock.

## Automated checks

Command: `uv run --frozen pytest -q --junitxml=output/test-results.xml`

**44 passed, 0 failed, 14.11 seconds.** Two upstream test-library deprecation warnings remain: Starlette's httpx TestClient adapter and the AnyIO BlockingPortal alias. They are recorded in the log and are not runtime test failures.

Evidence: [JUnit XML](output/test-results.xml), [test output](output/test-results.txt).

Additional checks: `uv run --frozen ruff check .` passed; `node --check app/static/app.js` passed.

| Area | Verified behavior |
| --- | --- |
| Seven types | Synthetic agreement: 9 occurrences, all 7 categories |
| Stable tokens | Three Jane Smith mentions share one token |
| Negative controls | S&P 500, return percentages and public pricing survive; clean fixture unchanged |
| Exact restoration | Original text reconstructed character-for-character, including Unicode/CRLF tests |
| Span safety | Overlaps, existing tokens, fullwidth digits, zero-width email and emoji offsets |
| HTTP transport | Real loopback socket sends both completion and embedding requests; received body and headers checked |
| Encoding guard | Known raw, JSON, URL, HTML and Base64 representations inspected by the guard |
| Isolation | Another session cannot restore, send or delete a document |
| Storage | Known fixture PII absent as plaintext in the database; masked tokens are present |
| Failure paths | Detector exceptions, tampered masked cache, transport timeout and invalid input do not send a raw fallback |
| Logging | Tested success and failure logs/responses exclude fixture PII |
| Defaults | Payload viewer disabled unless explicitly enabled |

## Browser acceptance

Command: `npx --yes --package @playwright/cli playwright-cli -s=privacy-wall run-code --filename scripts/browser_smoke.js --raw`

**13 acceptance categories passed; zero captured browser page errors.** The actual browser interacted with the live application, including a real TXT file-input upload.

Checks: seven types, stable tokens, exact restore, completion HTTP, embedding HTTP, masked clipboard, clean control, Unicode highlights, source HTML rendered as inert text, TXT upload, mobile layout, deletion and no localStorage/sessionStorage records.

Clipboard comparison normalizes CRLF/LF because Windows changes clipboard newline representation. Source restoration tests remain exact and do not normalize text.

Evidence: [machine-readable browser result](output/browser-results.txt).

Screenshots, all using synthetic data:

- [Desktop: verified workflow](output/playwright/desktop-verified.png) — 1440 × 1080 viewport, full-page capture.
- [Desktop: empty workspace](output/playwright/desktop-empty.png).
- [Mobile: masked document](output/playwright/mobile-verified.png) — 390 × 844 viewport, no horizontal overflow.

Visual review confirmed readable side-by-side documents, token highlights, request inspection, empty states and a stacked mobile layout. UI strings and submission documentation are English. The Unicode fixture deliberately retains fullwidth digits for testing.

## Runtime and delivery checks

- Local health endpoint returned `status: ok`, `mode: local_only`, `external_ai: false`.
- Windows ACL readback showed only the current-user grant on the data and key directories.
- The application server's error log was empty after the browser workflow.
- Original assignment copy retained its SHA-256: `83B4E413CFBA4B23317CF1A3714F68ADF0817C5CBA30D1C6AF17E0B4BC268155`.
- Source package builder uses an explicit allowlist, rejects database/key/runtime paths, and verifies archive contents against an embedded SHA-256 manifest.
- Video recording is explicitly delegated to the user. No video was recorded by the agent.

## What this does not prove

These are deterministic fixture and integration checks, not a population-level precision/recall benchmark. They do not prove arbitrary-document PII recall, production certification, legal compliance, real cloud-provider SDK compatibility, or support for Service 2/3. See [MASKER_LIMITATIONS.md](MASKER_LIMITATIONS.md).
