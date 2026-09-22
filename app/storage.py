"""Encrypted mapping vault; no raw source document or filename is persisted."""

import hashlib
import json
import os
import sqlite3
import subprocess
import uuid
from pathlib import Path

from cryptography.fernet import Fernet


def restrict_directory(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        # Restrict BOTH the key directory and the data directory, inherited by new files.
        identity = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True)
        sid = identity.strip().split(",")[-1].strip('"')
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"],
            check=True,
            capture_output=True,
        )
    else:
        path.chmod(0o700)


class Vault:
    def __init__(self, data_dir: Path, key_dir: Path):
        restrict_directory(data_dir)
        restrict_directory(key_dir)
        key_file = key_dir / "vault.key"
        if not key_file.exists():
            try:
                with key_file.open("xb") as handle:
                    handle.write(Fernet.generate_key())
            except FileExistsError:
                pass
            if os.name != "nt":
                key_file.chmod(0o600)
        self.cipher = Fernet(key_file.read_bytes())
        self.path = data_dir / "documents.sqlite3"
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, owner TEXT NOT NULL, "
                "public TEXT NOT NULL, secret BLOB NOT NULL)"
            )

    def connect(self):
        return sqlite3.connect(self.path)

    @staticmethod
    def owner_hash(owner):
        return hashlib.sha256(owner.encode()).hexdigest()

    def save(self, owner: str, document: dict):
        document_id = str(uuid.uuid4())
        public = {key: value for key, value in document.items() if key != "mapping"}
        public["document_id"] = document_id
        secret = self.cipher.encrypt(json.dumps(document["mapping"], ensure_ascii=False).encode())
        with self.connect() as db:
            db.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?)",
                (document_id, self.owner_hash(owner), json.dumps(public, ensure_ascii=False), secret),
            )
        return public

    def get(self, owner: str, document_id: str):
        with self.connect() as db:
            row = db.execute(
                "SELECT public, secret FROM documents WHERE id=? AND owner=?",
                (document_id, self.owner_hash(owner)),
            ).fetchone()
        if not row:
            raise KeyError("document_not_found")
        return {**json.loads(row[0]), "mapping": json.loads(self.cipher.decrypt(row[1]))}

    def delete(self, owner: str, document_id: str):
        with self.connect() as db:
            db.execute("PRAGMA secure_delete=ON")
            return (
                db.execute(
                    "DELETE FROM documents WHERE id=? AND owner=?", (document_id, self.owner_hash(owner))
                ).rowcount
                > 0
            )
