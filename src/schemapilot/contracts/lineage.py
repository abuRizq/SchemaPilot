"""Cell-level lineage (FILE_2 §9.2, axiom A1; CHAOS-4.2.1–4.2.3).

Every transform appends a TransformRecord; the chain links a golden value back
to raw vault bytes. Transforms are reversible or explicitly marked lossy —
"cleaning without receipts" is impossible by construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class TransformRecord:
    transform: str  # e.g. "encoding_repair", "temporal_decode"
    layer: int  # 0-6
    input_repr: str
    output_repr: str
    reversible: bool
    lossy: bool = False
    detail: str = ""  # e.g. inferred corruption chain, format verdict

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LineageChain:
    """Ordered transform chain for one cell, rooted at the raw vault."""

    source_file_id: str
    row_ordinal: int
    column: str
    records: list[TransformRecord] = field(default_factory=list)

    def append(self, record: TransformRecord) -> None:
        self.records.append(record)

    @property
    def lossy(self) -> bool:
        return any(r.lossy for r in self.records)

    @property
    def fully_reversible(self) -> bool:
        return all(r.reversible for r in self.records)

    def to_dict(self) -> dict:
        return {
            "source_file_id": self.source_file_id,
            "row_ordinal": self.row_ordinal,
            "column": self.column,
            "records": [r.to_dict() for r in self.records],
        }
