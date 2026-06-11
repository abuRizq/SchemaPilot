"""Layer 2 — Schema alignment: map every source column to a CCO node or
explicitly to UNMAPPED, never to a guess (FILE_2 §4)."""
from __future__ import annotations

from schemapilot.contracts.policy import DEFAULT_POLICY, Policy
from schemapilot.layer1_profiling.fingerprint import ColumnFingerprint
from schemapilot.layer2_alignment import assignment as _assignment
from schemapilot.layer2_alignment import deterministic as _deterministic
from schemapilot.layer2_alignment import evidence as _evidence
from schemapilot.layer2_alignment.cco import CCO, ConceptNode, LabelEdge, seed_person_cco
from schemapilot.layer2_alignment.evidence import EvidenceScore, LabelEmbedder
from schemapilot.layer2_alignment.gate import GatedMapping, Route, collapse_duplicate_columns, gate


def align(
    columns: list[str],
    fingerprints: dict[str, ColumnFingerprint],
    cco: CCO,
    *,
    mapped_fingerprints: dict[str, list[ColumnFingerprint]] | None = None,
    policy: Policy = DEFAULT_POLICY,
    embedder: LabelEmbedder | None = None,
) -> list[GatedMapping]:
    """Full Stage A -> Stage B -> Stage C -> gate pipeline for one source.

    `mapped_fingerprints`: concept_id -> fingerprints of columns previously
    mapped to that concept (the E3/E4 evidence corpus).
    """
    mapped_fingerprints = mapped_fingerprints or {}
    nominations = _deterministic.match(columns, cco)
    nominated = {(n.column, n.concept_id) for n in nominations}

    scores: list[EvidenceScore] = []
    for col in columns:
        fp = fingerprints[col]
        for concept_id in sorted(cco.concepts):
            scores.append(
                _evidence.score(
                    col, fp, concept_id, cco,
                    mapped_fingerprints=mapped_fingerprints,
                    deterministic_hit=(col, concept_id) in nominated,
                    embedder=embedder,
                )
            )

    chosen = _assignment.solve(columns, scores, cco)
    mappings = gate(chosen, scores, columns, policy)
    return collapse_duplicate_columns(mappings, fingerprints)


__all__ = [
    "align",
    "CCO",
    "ConceptNode",
    "LabelEdge",
    "seed_person_cco",
    "EvidenceScore",
    "LabelEmbedder",
    "GatedMapping",
    "Route",
    "collapse_duplicate_columns",
    "gate",
]
