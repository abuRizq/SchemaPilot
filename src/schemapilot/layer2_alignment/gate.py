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


def find_duplicate_columns(
    columns: list[str],
    fingerprints: dict[str, ColumnFingerprint],
    best_concept: dict[str, tuple[str, float]],  # column -> (concept_id, score)
    *,
    overlap_threshold: float = 0.95,
) -> dict[str, str]:
    """Pre-assignment duplicate-column collapse (CHAOS-1.3.1–1.3.4): intra-file
    columns with near-1.0 mutual instance overlap whose evidence points at the
    same concept are one column wearing two labels. Returns duplicate -> primary;
    duplicates are withheld from the assignment so they cannot consume (or be
    starved of) a single-valued concept slot."""
    out: dict[str, str] = {}
    for ai, a in enumerate(columns):
        for b in columns[ai + 1:]:
            if b in out or a in out:
                continue
            ca, cb = best_concept.get(a), best_concept.get(b)
            if not ca or not cb or ca[0] != cb[0]:
                continue
            fa, fb = fingerprints.get(a), fingerprints.get(b)
            if fa is None or fb is None:
                continue
            mutual = min(fa.value_overlap(fb), fb.value_overlap(fa))
            if mutual >= overlap_threshold:
                primary, dup = (a, b) if ca[1] >= cb[1] else (b, a)
                out[dup] = primary
    return out
