"""Immutable, content-addressed Raw Vault (FILE_2 §2, axiom A1).

Files are stored under their SHA-256; a re-uploaded file hashes identically
and is rejected at the gate (CHAOS-1.3.9) before it can stuff the ballot box
of Layer-5 voting. Vault contents are never mutated.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class DuplicateIngestionError(Exception):
    """Raised when a byte-identical file is re-ingested (CHAOS-1.3.9)."""


class RawVault:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.objects.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "index.json"
        self._index: dict[str, dict] = (
            json.loads(self._index_path.read_text()) if self._index_path.exists() else {}
        )

    @staticmethod
    def content_hash(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def ingest(self, data: bytes, *, source_system_id: str, batch_id: str,
               allow_duplicate: bool = False) -> str:
        """Store raw bytes; return the content hash (source_file_id)."""
        digest = self.content_hash(data)
        if digest in self._index and not allow_duplicate:
            raise DuplicateIngestionError(
                f"CHAOS-1.3.9: file {digest[:12]}… already ingested "
                f"(batch {self._index[digest]['batch_id']})"
            )
        path = self.objects / digest
        if not path.exists():
            path.write_bytes(data)
        self._index[digest] = {"source_system_id": source_system_id, "batch_id": batch_id}
        self._index_path.write_text(json.dumps(self._index, indent=2, sort_keys=True))
        return digest

    def read(self, source_file_id: str) -> bytes:
        return (self.objects / source_file_id).read_bytes()

    def __contains__(self, source_file_id: str) -> bool:
        return source_file_id in self._index
