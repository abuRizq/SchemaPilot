"""Stage C — Global assignment (FILE_2 §4.4).

Mapping is a constrained maximum-weight bipartite assignment: within one
source, two columns must not both map to a single-valued concept, but may
both map to a multi-valued one (how CHAOS-1.3.4 concept-duplicate columns are
correctly absorbed). Multiplicity is handled by replicating concept slots.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

from schemapilot.layer2_alignment.cco import CCO
from schemapilot.layer2_alignment.evidence import EvidenceScore

# Assignments only add value above this baseline; below it, leaving a column
# unassigned beats assigning it. Without the baseline the solver prefers two
# mediocre mappings over one excellent mapping plus an honest UNMAPPED —
# exactly the guess-over-abstain behavior §4's mission statement forbids.
_VIABILITY_BASELINE = 0.5


def solve(
    columns: list[str],
    scores: list[EvidenceScore],
    cco: CCO,
    *,
    max_multi_slots: int = 4,
) -> dict[str, EvidenceScore]:
    """Return column -> winning EvidenceScore for the optimal global assignment."""
    by_pair = {(s.column, s.concept_id): s for s in scores}
    # Expand concepts into slots: single-valued -> 1 slot, multi-valued -> k.
    slots: list[str] = []
    for cid in sorted({s.concept_id for s in scores}):
        n = max_multi_slots if cco.contract(cid).multi_valued else 1
        slots.extend([cid] * n)
    if not slots or not columns:
        return {}

    n_rows, n_cols = len(columns), len(slots)
    size = max(n_rows, n_cols)
    cost = np.zeros((size, size))
    for i, col in enumerate(columns):
        for j, cid in enumerate(slots):
            s = by_pair.get((col, cid))
            value = (s.composite - _VIABILITY_BASELINE) if s else 0.0
            cost[i, j] = -value if value > 0 else 0.0

    row_idx, col_idx = linear_sum_assignment(cost)
    out: dict[str, EvidenceScore] = {}
    for i, j in zip(row_idx, col_idx):
        if i >= n_rows or j >= n_cols or cost[i, j] >= 0.0:
            continue
        out[columns[i]] = by_pair[(columns[i], slots[j])]
    return out
