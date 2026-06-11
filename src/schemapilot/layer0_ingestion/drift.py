"""Schema-version hashing & structural drift detection (FILE_2 §2, CHAOS-1.2.3).

A source's column census (names, count, order) is hashed; when a feed changes
shape, ingestion raises an explicit SchemaDriftEvent instead of appending
positionally — the inserted-middle-column shear becomes impossible.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


def schema_version_hash(columns: list[str]) -> str:
    payload = "\x1f".join(columns).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class SchemaDriftEvent:
    source_system_id: str
    previous_hash: str
    new_hash: str
    previous_columns: tuple[str, ...]
    new_columns: tuple[str, ...]

    @property
    def added(self) -> set[str]:
        return set(self.new_columns) - set(self.previous_columns)

    @property
    def removed(self) -> set[str]:
        return set(self.previous_columns) - set(self.new_columns)

    @property
    def positional_shift(self) -> bool:
        """True when shared columns changed position — the CHAOS-1.2.3 shear."""
        shared = [c for c in self.previous_columns if c in self.new_columns]
        return shared != [c for c in self.new_columns if c in self.previous_columns]


class DriftMonitor:
    def __init__(self) -> None:
        self._known: dict[str, tuple[str, tuple[str, ...]]] = {}

    def check(self, source_system_id: str, columns: list[str]) -> SchemaDriftEvent | None:
        new_hash = schema_version_hash(columns)
        previous = self._known.get(source_system_id)
        self._known[source_system_id] = (new_hash, tuple(columns))
        if previous is None or previous[0] == new_hash:
            return None
        return SchemaDriftEvent(
            source_system_id=source_system_id,
            previous_hash=previous[0],
            new_hash=new_hash,
            previous_columns=previous[1],
            new_columns=tuple(columns),
        )
