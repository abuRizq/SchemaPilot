"""The Chaos Manifest (FILE_2 §3) — per-source, machine-readable declaration of
detected chaos classes, produced by Layer 1's pre-scan and consumed by the
complexity router (§8).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum


class Path(Enum):
    FAST = "FAST"
    STANDARD = "STANDARD"
    DEEP = "DEEP"


_PATH_ORDER = {Path.FAST: 0, Path.STANDARD: 1, Path.DEEP: 2}


@dataclass
class ChaosFinding:
    chaos_id: str
    column: str
    mass: float  # fraction of values affected
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChaosManifest:
    source_file_id: str
    findings: list[ChaosFinding] = field(default_factory=list)
    column_paths: dict[str, Path] = field(default_factory=dict)

    def add(self, finding: ChaosFinding) -> None:
        self.findings.append(finding)

    def findings_for(self, column: str) -> list[ChaosFinding]:
        return [f for f in self.findings if f.column == column]

    def escalate(self, column: str, path: Path) -> None:
        """Routing law (§8): escalation is one-way; nothing is demoted."""
        current = self.column_paths.get(column, Path.FAST)
        if _PATH_ORDER[path] > _PATH_ORDER[current]:
            self.column_paths[column] = path
        else:
            self.column_paths.setdefault(column, current)

    def path_for(self, column: str) -> Path:
        return self.column_paths.get(column, Path.FAST)

    def to_dict(self) -> dict:
        return {
            "source_file_id": self.source_file_id,
            "findings": [f.to_dict() for f in self.findings],
            "column_paths": {c: p.value for c, p in sorted(self.column_paths.items())},
        }
