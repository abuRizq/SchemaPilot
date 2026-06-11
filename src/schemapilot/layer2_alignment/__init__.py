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
from schemapilot.layer2_alignment.gate import GatedMapping, Route, find_duplicate_columns, gate


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
    best_concept: dict[str, tuple[str, float]] = {}
    for col in columns:
        fp = fingerprints[col]
        for concept_id in sorted(cco.concepts):
            s = _evidence.score(
                col, fp, concept_id, cco,
                mapped_fingerprints=mapped_fingerprints,
                deterministic_hit=(col, concept_id) in nominated,
                embedder=embedder,
            )
            scores.append(s)
            if col not in best_concept or s.composite > best_concept[col][1]:
                best_concept[col] = (concept_id, s.composite)

    # Duplicate columns are collapsed before assignment (CHAOS-1.3.1-1.3.4) so
    # they cannot fight over single-valued concept slots.
    duplicates = find_duplicate_columns(columns, fingerprints, best_concept)
    active = [c for c in columns if c not in duplicates]

    chosen = _assignment.solve(active, scores, cco)
    mappings = gate(chosen, scores, active, policy)
    by_column = {m.column: m for m in mappings}
    for dup, primary in sorted(duplicates.items()):
        p = by_column.get(primary)
        mappings.append(GatedMapping(
            column=dup,
            concept_id=p.concept_id if p else None,
            score=p.score if p else 0.0,
            route=p.route if p else Route.UNMAPPED,
            collapsed_into=primary,
        ))
    return mappings


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
