# Demo recording guide

Record the video yourself using the synthetic fixtures. Suggested duration: 3–4 minutes. No API credentials are needed.

## Start

~~~powershell
Set-Location 'C:\PyCharm Project\pii-privacy-wall'
.\.venv\Scripts\python.exe run.py --dev-viewer
~~~

Open http://127.0.0.1:8765. If the application is already running, just open the page.

## Recording sequence

| Time | Action | Explain |
| --- | --- | --- |
| 0:00–0:20 | Show the workspace | Service 1, local processing, no cloud-model API |
| 0:20–0:55 | Agreement → Mask document | Nine occurrences, seven types; repeated names share tokens; S&P 500, 18% and the public subscription price are preserved |
| 0:55–1:35 | Test completion, inspect the request, then Test embedding | Actual local HTTP transport; both wrappers enforce masking; show 2 / 2 verified |
| 1:35–2:00 | Restore original, then Masked | Session-authorized reconstruction and correct highlights |
| 2:00–2:25 | Clean control → Mask document | Zero detected entities; no modification to the control text |
| 2:25–2:55 | Edge cases → Mask document → Restore original | Fullwidth SSN, overlapping name/address, pre-existing placeholder, inert HTML |
| 2:55–3:20 | Upload fixtures/mixed.txt → Mask document | Demonstrate the actual file-input path, not only preset samples |
| 3:20–3:50 | Show validation report or test run | Request bytes, session isolation, encryption and safe logs; acknowledge heuristic coverage limits |

## Suggested introduction

This is the Service 1 PII masking application. It runs locally without an LLM API key. It detects seven categories of personal information, replaces repeated entities with stable document-scoped tokens, and stores the mapping encrypted on the server. Both completion and embedding requests go through the same masking gateway. A local HTTP receiver captures the actual serialized request body so we can verify that detected personal values were not transmitted. Authorized rendering restores the original text and its highlights. This is a heuristic prototype: it verifies detected entities, not universal PII coverage.

## Accurate claims

- The recipient is a local mock receiver, not OpenAI or Gemini.
- This implements Service 1, not all three assignment services.
- Passing tests does not establish zero leakage for arbitrary documents.
- Request verification is not a legal compliance decision.
- Use synthetic documents, not actual client information.
