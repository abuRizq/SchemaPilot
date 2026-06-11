"""The confidence gate (FILE_2 §4.4) and duplicate-column machinery.

| S >= tau_auto and no competitor within delta  -> auto-map
| tau_review <= S < tau_auto, or close race     -> human adjudication queue
| S < tau_review                                -> UNMAPPED (extension zone,
|                                                  zero trust inheritance)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from schemapilot.contracts.policy import Policy
from schemapilot.layer1_profiling.fingerprint import ColumnFingerprint
from schemapilot.layer2_alignment.evidence import EvidenceScore


class Route(Enum):
    AUTO_MAP = "AUTO_MAP"
    ADJUDICATE = "ADJUDICATE"
    UNMAPPED = "UNMAPPED"


def _logit(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    import math

    return math.log(p / (1 - p))


@dataclass
class GatedMapping:
    column: str
    concept_id: str | None
    score: float
    route: Route
    competitors: list[tuple[str, float]] = field(default_factory=list)
    collapsed_into: str | None = None  # duplicate-column collapse target
    derived: bool = False


def gate(
    assignment: dict[str, EvidenceScore],
    all_scores: list[EvidenceScore],
    columns: list[str],
    policy: Policy,
) -> list[GatedMapping]:
    by_column: dict[str, list[EvidenceScore]] = {}
    for s in all_scores:
        by_column.setdefault(s.column, []).append(s)

    out: list[GatedMapping] = []
    for col in columns:
        winner = assignment.get(col)
        if winner is None:
            out.append(GatedMapping(col, None, 0.0, Route.UNMAPPED))
            continue
        rivals = sorted(
            ((s.concept_id, s.composite) for s in by_column.get(col, []) if s.concept_id != winner.concept_id),
            key=lambda kv: -kv[1],
        )
        # Competing-assignment margin is measured in log-odds space — the
        # sigmoid saturates near 1.0, where raw-probability deltas lose meaning.
        close_race = bool(rivals) and (
            _logit(winner.composite) - _logit(rivals[0][1])
        ) < policy.delta_competing_logit
        if winner.composite >= policy.tau_auto and not close_race:
            route = Route.AUTO_MAP
        elif winner.composite >= policy.tau_review or close_race:
            route = Route.ADJUDICATE
        else:
            out.append(GatedMapping(col, None, winner.composite, Route.UNMAPPED, rivals[:3]))
            continue
        out.append(GatedMapping(col, winner.concept_id, winner.composite, route, rivals[:3]))
    return out


def collapse_duplicate_columns(
    mappings: list[GatedMapping],
    fingerprints: dict[str, ColumnFingerprint],
    *,
    overlap_threshold: float = 0.95,
) -> list[GatedMapping]:
    """Intra-file columns with near-1.0 mutual instance overlap mapped to the
    same concept collapse pre-assignment (CHAOS-1.3.1–1.3.4); the survivors'
    disagreements become L5's input via the normal fusion path."""
    by_concept: dict[str, list[GatedMapping]] = {}
    for m in mappings:
        if m.concept_id and m.route is not Route.UNMAPPED:
            by_concept.setdefault(m.concept_id, []).append(m)
    for concept_id, group in by_concept.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda m: (-m.score, m.column))
        primary = group[0]
        for other in group[1:]:
            fa, fb = fingerprints.get(primary.column), fingerprints.get(other.column)
            if fa and fb:
                mutual = min(fa.value_overlap(fb), fb.value_overlap(fa))
                if mutual >= overlap_threshold:
                    other.collapsed_into = primary.column
    return mappings
