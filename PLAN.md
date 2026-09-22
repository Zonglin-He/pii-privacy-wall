# Implementation plan and completion record

Updated: 2026-09-22.

## Selected scope

The assignment permits completing one service. The user prioritized speed and a route requiring no LLM API, then authorized implementation. Service 1 / AI-1 was selected.

Subsequent requirements: the user records the video; the application UI and submission documentation must be English; the interface should use a modern, minimal visual design.

## Architecture decisions

- Python/FastAPI and a single local service; static HTML/CSS/JavaScript frontend.
- SQLite with separately stored encryption key and Fernet-encrypted token mappings.
- Deterministic regex/context heuristics for seven PII types; no downloaded NER model.
- TXT/pasted-text support first; no PDF/DOCX/OCR.
- Real loopback HTTP transport for both completion and embedding wrappers.
- One gateway enforcing preflight checks, no raw fallback, no cloud endpoint.
- Code-point span mapping for safe original/masked highlighting.
- Current-session authorization for restoration; no full mapping endpoint.
- English sidebar workspace, neutral surfaces, restrained blue accent, responsive layout.

## Milestones

| Stage | Deliverable | State |
| --- | --- | --- |
| P0 | Read source, select scope, create project directory and initial plan | Complete |
| P1 | Seven detectors, fixtures, stable tokens, overlap resolution | Complete |
| P2 | Encrypted mappings, session isolation, exact restoration | Complete |
| P3 | Completion/embedding wrappers and real HTTP receiver verification | Complete |
| P4 | English UI, upload, highlighting, request viewer, responsive browser checks | Complete |
| P5 | Automated tests, documentation, demo guide, source submission package | See VALIDATION.md and output directory |
| Video | Final demonstration recording | User-owned, per explicit instruction |

## Acceptance evidence

The executable tests, browser smoke workflow and screenshots are documented in VALIDATION.md. The scope and limitations are documented in MASKER_LIMITATIONS.md.

Do not claim production certification, universal PII recall, legal review, real third-party model integration, or completion of Service 2/3. The original assignment is preserved unchanged in docs/AI Tasks.md.
