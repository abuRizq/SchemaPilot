"""The universal record set: standardized rows with stable record ids,
the unit of entity resolution."""
from __future__ import annotations

from dataclasses import dataclass

from schemapilot.layer3_standardize.driver import Cell, StandardizedSource


@dataclass
class Record:
    record_id: str  # "<source_system_id>:<file_id8>:<ordinal>"
    source_system_id: str
    source_file_id: str
    row_ordinal: int
    cells: dict[str, Cell]  # concept_id -> Cell
    source_asserted_time: str | None

    def cell(self, concept_id: str) -> Cell | None:
        return self.cells.get(concept_id)

    def match_key(self, concept_id: str) -> str | None:
        cell = self.cells.get(concept_id)
        return cell.match_key if cell else None


def build_records(sources: list[StandardizedSource]) -> list[Record]:
    records: list[Record] = []
    for src in sources:
        for ordinal, row in enumerate(src.rows):
            envelope = src.envelopes[ordinal] if ordinal < len(src.envelopes) else None
            records.append(
                Record(
                    record_id=f"{src.source_system_id}:{src.source_file_id[:8]}:{ordinal}",
                    source_system_id=src.source_system_id,
                    source_file_id=src.source_file_id,
                    row_ordinal=ordinal,
                    cells=row,
                    source_asserted_time=envelope.source_asserted_time if envelope else None,
                )
            )
    return records
