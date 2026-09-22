"""Build a source-only submission; runtime databases and keys are never included."""

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "README.md",
    "PLAN.md",
    "MASKER_LIMITATIONS.md",
    "VALIDATION.md",
    "pyproject.toml",
    "uv.lock",
    ".gitignore",
    "run.py",
]
DIRECTORIES = ["app", "fixtures", "tests", "scripts", "docs"]
EVIDENCE = [
    "output/test-results.xml",
    "output/test-results.txt",
    "output/browser-results.txt",
    "output/playwright/desktop-empty.png",
    "output/playwright/desktop-verified.png",
    "output/playwright/mobile-verified.png",
]


def package():
    paths = [ROOT / item for item in FILES + EVIDENCE]
    for directory in DIRECTORIES:
        paths.extend(
            path
            for path in (ROOT / directory).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
    manifest = {}
    destination = ROOT / "output" / "privacy-wall-submission.zip"
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            relative = path.relative_to(ROOT).as_posix()
            if not path.is_file():
                raise FileNotFoundError(relative)
            data = path.read_bytes()
            if (
                path.suffix in {".key", ".sqlite3", ".db"}
                or ".local" in path.parts
                or ".venv" in path.parts
            ):
                raise ValueError("runtime_file_in_submission")
            archive.writestr("privacy-wall/" + relative, data)
            manifest[relative] = hashlib.sha256(data).hexdigest()
        archive.writestr("privacy-wall/MANIFEST.json", json.dumps(manifest, indent=2))
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        for relative, digest in manifest.items():
            assert hashlib.sha256(archive.read("privacy-wall/" + relative)).hexdigest() == digest
    print(
        json.dumps(
            {
                "archive": str(destination),
                "files": len(manifest) + 1,
                "bytes": destination.stat().st_size,
                "integrity": "PASS",
            }
        )
    )


if __name__ == "__main__":
    package()
