# Masker limitations

## Supported input

UTF-8 TXT and pasted text, up to 100,000 Unicode code points and 2,000 replacement spans. Primary coverage is English financial documents with explicit labels and common US formats.

| Type | Supported detection |
| --- | --- |
| Person | Title-case names following Client, Name, Customer, Account holder, Beneficiary, Agreement for, Prepared for, Dear, Mr., Ms., or Mrs.; repeated detected names elsewhere |
| Email | Common local-part and domain formats |
| Phone | Common North American formats; labeled international numbers |
| SSN | 3-2-4 grouping, or nine digits following an SSN label |
| Account | Account/Acct labels or a supported prefixed identifier |
| Address | Address-labeled line content and common US street-address patterns |
| Amount | Dollar/USD amounts preceded in the same local context by ownership language and a person/account cue |

## Known limitations

1. There is no general-purpose NER model. Unlabeled names, single names, all-uppercase/lowercase names, Chinese names, and many international naming conventions can be missed.
2. Unlabeled international phone numbers, non-US addresses, IBANs, passport numbers, dates of birth and device identifiers are not comprehensively covered.
3. Title-case organization names after a person label may be false positives. Address-label detection can mask extra line content. SSN/phone-like numbers can be false positives.
4. Dollar-amount ownership uses local heuristics, not full semantic understanding. Cross-sentence references can be missed; a nearby ownership cue can also create a false positive.
5. NFKC and removal of Unicode formatting characters cover fullwidth digits and some zero-width hiding. They do not solve all Cyrillic/Greek homoglyphs, transliteration or visual deception.
6. The input detector does not decode arbitrary Base64, URL escapes, HTML entities, archives or compressed data. The outbound encoding check only searches representations of already detected values.
7. PDF, DOCX, spreadsheets, images, scanned text and hidden headers/footers are outside this implementation. Renaming a binary file to .txt does not add parsing support.
8. Exact repeated original values share a token. Different original spellings or capitalization may receive different tokens to preserve lossless restoration.
9. Text that says “ignore instructions” has no execution authority: the detector is deterministic and does not invoke an LLM.
10. Only fixture-level correctness is established. There is no representative population accuracy benchmark or universal recall guarantee.

## Interpreting “verified”

A successful outbound check means that, for that particular request through this application, none of the detected original values or covered encoded representations appeared in the checked request data.

This does **not** establish that the document contains no remaining PII. An undetected value may remain in the masked text, database or developer viewer. Do not treat this prototype as the sole protection for actual client records.

The receiver reads the HTTP body as raw bytes. Request lines and headers are reconstructed after HTTP parsing for inspection; this is not an operating-system packet capture. The body digest is SHA-256 of the exact received body.

## Storage and security boundaries

- Original uploads are not stored as files. Detected values are stored in an encrypted mapping; the mapping and masked text together reconstruct the source.
- Plaintext exists temporarily in memory, the input field and authorized restore view.
- The encryption key is outside the database/project, but the application process can access both. This does not defend against compromise of the local account or administrator privileges.
- The payload viewer is opt-in and never displays the mapping or internal receiver key. Undetected sensitive values may still be present in the masked payload.
- Sessions are local-demo capabilities, not enterprise identity. Cookies are HttpOnly and SameSite=Strict. Secure cookies are not enabled on this loopback HTTP deployment.
- Remote deployment would require TLS, real authentication, operational controls and a new security review.
- Sessions expire after eight hours and disappear on server restart. Old database records are not made available to a new session.
- Replacing a document in the UI deletes the previous current record. There is no background retention cleanup, key rotation or full audit platform.
- Delete uses SQLite secure_delete. It is not a guarantee of forensic erasure from SSD blocks, OS caches or backups.
- The default launcher binds only to loopback and disables access logs. Custom launch configurations can change these properties.
- The outbound target is the application's loopback receiver. This is not an operating-system network firewall and does not constrain unrelated processes.

## Failure behavior

Detection failure, invalid spans, mapping decryption failure, known-PII preflight failure and transport timeout block the operation. There is no fallback that sends raw input. Error responses use fixed codes rather than source content or third-party exception messages.

Adding a model provider, parser, new user-controlled field, or a new outbound path requires fresh leakage tests. Existing tests do not automatically validate those future changes.
