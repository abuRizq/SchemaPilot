"""Layer 4 — Entity resolution: partition the universal record set into
clusters, one per real-world entity, under A5's asymmetry (FILE_2 §6)."""
from __future__ import annotations

from schemapilot.contracts.policy import DEFAULT_POLICY, Policy
from schemapilot.layer3_standardize.driver import StandardizedSource
from schemapilot.layer4_resolution import blocking as _blocking
from schemapilot.layer4_resolution import comparison as _comparison
from schemapilot.layer4_resolution import fellegi_sunter as _fs
from schemapilot.layer4_resolution.clustering import Cluster, chimera_veto, cluster
from schemapilot.layer4_resolution.comparison import ComparisonVector, compare
from schemapilot.layer4_resolution.fellegi_sunter import Decision, FSModel, classify, fit_em
from schemapilot.layer4_resolution.records import Record, build_records


def resolve(
    sources: list[StandardizedSource],
    *,
    policy: Policy = DEFAULT_POLICY,
) -> tuple[list[Record], list[Cluster], list[Decision]]:
    """Block -> compare -> classify -> cluster. Returns (records, clusters,
    decisions); the chimera veto runs later, fed by Layer 5 entropy."""
    records = build_records(sources)
    pairs = _blocking.candidate_pairs(records, block_size_ceiling=policy.block_size_ceiling)
    vectors = [compare(records, i, j) for i, j in sorted(pairs)]
    model = fit_em(vectors)
    decisions = classify(vectors, model, policy)
    clusters = cluster(records, decisions, policy)
    return records, clusters, decisions


__all__ = [
    "resolve",
    "Cluster",
    "chimera_veto",
    "cluster",
    "ComparisonVector",
    "compare",
    "Decision",
    "FSModel",
    "classify",
    "fit_em",
    "Record",
    "build_records",
]
