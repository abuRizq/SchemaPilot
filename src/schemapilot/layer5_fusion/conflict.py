"""Conflict detection & typing (FILE_2 §7.1).

For each (cluster, attribute): collapse representational conflicts first
(after L3, two formattings of one phone are already a single value), type
what remains against the CHAOS-3.2.* taxonomy, and measure it — conflict
entropy is the per-attribute temperature driving strategy selection, chimera
vetoes, and trust.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from schemapilot.contracts.nulls import NullKind, TypedNull
from schemapilot.layer3_standardize.driver import Cell
from schemapilot.layer3_standardize.temporal import TemporalInterval, TemporalValue
from schemapilot.layer4_resolution.records import Record


@dataclass
class Assertion:
    """One source's claim about one attribute of one entity."""

    record_id: str
    source_system_id: str
    source_asserted_time: str | None
    cell: Cell

    @property
    def surface(self) -> str:
        value = self.cell.value
        if isinstance(value, TemporalValue):
            return value.date_key
        if isinstance(value, TemporalInterval):
            return value.original
        return str(value)


@dataclass
class ConflictSet:
    concept_id: str
    cluster_id: str
    groups: dict[str, list[Assertion]] = field(default_factory=dict)  # canonical key -> assertions
    erased: bool = False  # any source carries an ERASED null for this attribute

    @property
    def distinct_values(self) -> int:
        return len(self.groups)

    @property
    def is_singleton(self) -> bool:
        return self.distinct_values <= 1

    def entropy(self, reliability: dict[str, float] | None = None) -> float:
        """H(a) = -Σ p(v) log2 p(v), votes deduplicated per source system and
        weighted by source reliability — re-ingested copies are one opinion,
        not three (CHAOS-1.3.9)."""
        weights: list[float] = []
        for assertions in self.groups.values():
            per_source: dict[str, float] = {}
            for a in assertions:
                r = (reliability or {}).get(a.source_system_id, 1.0)
                per_source[a.source_system_id] = max(per_source.get(a.source_system_id, 0.0), r)
            weights.append(sum(per_source.values()))
        total = sum(weights)
        if total == 0 or len(weights) <= 1:
            return 0.0
        return -sum((w / total) * math.log2(w / total) for w in weights if w > 0)


def _canonical_group_key(cell: Cell) -> str | None:
    """Representational collapse (CHAOS-3.2.1): group by post-L3 identity."""
    value = cell.value
    if isinstance(value, TypedNull):
        return None
    if isinstance(value, TemporalValue):
        return value.date_key
    if isinstance(value, TemporalInterval):
        # Each interval groups by its candidate set; collapse happens in the
        # cross-source disambiguation strategy.
        return "interval:" + "|".join(sorted(c.strftime("%Y-%m-%d") for c, _ in value.candidates))
    if cell.match_key:
        return cell.match_key
    return str(value)


def gather(
    cluster_id: str,
    member_records: list[Record],
    concept_id: str,
) -> ConflictSet:
    cs = ConflictSet(concept_id=concept_id, cluster_id=cluster_id)
    for record in member_records:
        cell = record.cell(concept_id)
        if cell is None:
            continue
        if isinstance(cell.value, TypedNull):
            if cell.value.kind is NullKind.ERASED:
                cs.erased = True
            continue
        key = _canonical_group_key(cell)
        if key is None:
            continue
        cs.groups.setdefault(key, []).append(
            Assertion(
                record_id=record.record_id,
                source_system_id=record.source_system_id,
                source_asserted_time=record.source_asserted_time,
                cell=cell,
            )
        )
    return cs
