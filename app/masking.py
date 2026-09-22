"""Deterministic, context-limited detector with reversible character spans.

Offsets are Python Unicode code points, never JavaScript UTF-16 indices.
Normalization is a detection view only; reconstruction retains original bytes/text.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass

VERSION = "heuristics-1.0"
TYPES = ("CLIENT", "EMAIL", "PHONE", "ADDRESS", "SSN", "ACCOUNT", "AMOUNT")
TOKEN = re.compile(r"\[[A-Z]+_\d+\]")


@dataclass(frozen=True)
class Entity:
    start: int
    end: int
    kind: str
    source: str
    priority: int


def detection_view(text: str):
    chars, positions = [], []
    for index, char in enumerate(text):
        if unicodedata.category(char) == "Cf":
            continue
        for normalized in unicodedata.normalize("NFKC", char):
            chars.append(normalized)
            positions.append(index)
    return "".join(chars), positions


def detect(text: str) -> list[Entity]:
    view, positions = detection_view(text)
    candidates: list[Entity] = []

    def add(start, end, kind, source, priority):
        if start < end:
            candidates.append(Entity(positions[start], positions[end - 1] + 1, kind, source, priority))

    def scan(pattern, kind, source, priority, group=0, flags=re.I):
        for match in re.finditer(pattern, view, flags):
            add(*match.span(group), kind, source, priority)

    scan(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?!\w)", "EMAIL", "email-format", 100)
    scan(r"(?<!\d)\d{3}[- ]\d{2}[- ]\d{4}(?!\d)", "SSN", "ssn-format", 100)
    scan(r"\bSSN\s*[:#]?\s*(\d{9})(?!\d)", "SSN", "ssn-label", 100, 1)
    scan(
        r"(?<!\w)(?:\+?1[-. ]?)?(?:\(\d{3}\)|\d{3})[-. ]?\d{3}[-. ]?\d{4}(?!\d)",
        "PHONE",
        "north-american-phone",
        80,
    )
    scan(
        r"\b(?:phone|mobile|tel(?:ephone)?)\s*:\s*(\+?\d[\d ().-]{6,}\d)", "PHONE", "phone-label", 85, 1
    )
    scan(
        r"\b(?:account|acct)(?:[ ]+(?:number|no\.?))?[ ]*[:#]?[ ]*((?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{3,})\b",
        "ACCOUNT",
        "account-label",
        95,
        1,
    )
    scan(r"(?<!\w)#([A-Z]{1,5}-\d{3,})\b", "ACCOUNT", "account-prefix", 95, 1)
    scan(
        r"\b(?:address|resides at|mailing address)\s*:[ \t]*([^\n;]+)", "ADDRESS", "address-label", 90, 1
    )
    scan(
        r"\b\d{1,6}[ ]+(?:[\w.'-]+[ ]+){1,5}(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Boulevard|Blvd)\b\.?"
        r"(?:[ ]+(?:Apt|Suite|Unit)[ ]*[\w-]+)?(?:,[ ]*[A-Za-z .'-]+,[ ]*[A-Z]{2}[ ]+\d{5}(?:-\d{4})?)?",
        "ADDRESS",
        "us-street-address",
        90,
    )

    word = r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+(?:['’-][A-ZÀ-ÖØ-Þ]?[a-zà-öø-ÿ]+)?"
    name = rf"{word}(?:[ ]+{word}){{1,3}}"
    # Match labels case-insensitively, names case-sensitively; don't cross newlines.
    pattern = rf"(?i:\b(?:client(?: name)?|customer(?: name)?|name|account holder|beneficiary)[ ]*:[ ]*|\b(?:agreement for|prepared for|dear|Mr\.|Ms\.|Mrs\.)[ ]+)({name})"
    known_names = set()
    for match in re.finditer(pattern, view):
        start, end = match.span(1)
        add(start, end, "CLIENT", "name-context", 60)
        known_names.add(match.group(1))
    for value in known_names:
        scan(r"(?<!\w)" + re.escape(value) + r"(?!\w)", "CLIENT", "document-name-repeat", 60)

    # Dollar amounts only in the same local clause as an ownership cue AND a person/account cue.
    for match in re.finditer(r"(?:\$|\bUSD[ ]*)\d[\d,]*(?:\.\d{2})?", view):
        left = (
            max(
                view.rfind("\n", 0, match.start()),
                view.rfind(";", 0, match.start()),
                view.rfind(". ", 0, match.start()),
            )
            + 1
        )
        context = view[max(left, match.start() - 180) : match.start()]
        owner = re.search(
            r"\b(?:balance|holds?|owns?|assets?|deposit(?:ed)?|portfolio|net worth)\b", context, re.I
        )
        identity = re.search(r"\b(?:client|customer|account|acct)\b", context, re.I) or any(
            re.search(re.escape(value), context, re.I) for value in known_names
        )
        if owner and identity:
            add(*match.span(), "AMOUNT", "personal-amount-context", 70)

    # Reserve source placeholders as literal segments; later restoration is span-based.
    for match in TOKEN.finditer(text):
        candidates.append(Entity(*match.span(), "LITERAL", "source-placeholder", 110))

    accepted: list[Entity] = []
    for candidate in sorted(candidates, key=lambda e: (-e.priority, -(e.end - e.start), e.start)):
        if not any(candidate.start < item.end and candidate.end > item.start for item in accepted):
            accepted.append(candidate)
    return sorted(accepted, key=lambda e: e.start)


def mask(text: str) -> dict:
    if not text.strip() or len(text) > 100_000 or "\x00" in text:
        raise ValueError("invalid_document")
    entities = detect(text)
    if len(entities) > 2000:
        raise ValueError("too_many_entities")
    used = set(TOKEN.findall(text))
    counters, mapping, lookup, spans, chunks = Counter(), {}, {}, [], []
    cursor, masked_cursor = 0, 0
    for entity in entities:
        value = text[entity.start : entity.end]
        key = (entity.kind, value)
        if key not in lookup:
            while True:
                counters[entity.kind] += 1
                token = f"[{entity.kind}_{counters[entity.kind]}]"
                if token not in used:
                    break
            used.add(token)
            lookup[key] = token
            mapping[token] = value
        token = lookup[key]
        prefix = text[cursor : entity.start]
        chunks.extend([prefix, token])
        masked_cursor += len(prefix)
        spans.append(
            {
                **asdict(entity),
                "token": token,
                "masked_start": masked_cursor,
                "masked_end": masked_cursor + len(token),
            }
        )
        masked_cursor += len(token)
        cursor = entity.end
    chunks.append(text[cursor:])
    return {
        "masked_text": "".join(chunks),
        "spans": spans,
        "mapping": mapping,
        "counts": dict(Counter(e.kind for e in entities if e.kind != "LITERAL")),
        "detector_version": VERSION,
    }


def restore(document: dict) -> str:
    text, cursor, chunks = document["masked_text"], 0, []
    for span in document["spans"]:
        if text[span["masked_start"] : span["masked_end"]] != span["token"]:
            raise ValueError("invalid_span")
        chunks.extend([text[cursor : span["masked_start"]], document["mapping"][span["token"]]])
        cursor = span["masked_end"]
    chunks.append(text[cursor:])
    return "".join(chunks)
