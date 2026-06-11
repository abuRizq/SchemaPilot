"""Trust scoring & certification (FILE_2 §10).

T(cell) = g(T_mapping, T_standardization, T_cluster, T_fusion, V_validation),
a monotone composition — no step raises trust above its weakest predecessor.
"""
from __future__ import annotations

from dataclasses import dataclass

from schemapilot.contracts.confidence import CertificationTier, compose_trust, tier_for
from schemapilot.layer5_fusion.golden import GoldenCell, GoldenRecord
from schemapilot.layer6_certification.constraints import ValidationReport


@dataclass
class CertifiedCell:
    cell: GoldenCell
    trust: float
    tier: CertificationTier


def certify_record(
    record: GoldenRecord,
    mapping_scores: dict[str, float],  # concept_id -> min mapping score across sources
    validation: ValidationReport,
) -> dict[str, CertifiedCell]:
    out: dict[str, CertifiedCell] = {}
    passed = validation.passed(record.cluster_id)
    for concept_id, cell in record.cells.items():
        t_mapping = mapping_scores.get(concept_id, 0.5)
        t_standardization = 0.3 if _lossy(cell) else 1.0
        t_cluster = record.cluster_stability
        t_fusion = cell.confidence_posterior
        trust = compose_trust(t_mapping, t_standardization, t_cluster, t_fusion)
        if cell.escalated:
            trust = min(trust, 0.50)  # escalated cells cap at PROVISIONAL (§10): a
            # best-guess under open contest is usable but never certified
        out[concept_id] = CertifiedCell(cell, round(trust, 4), tier_for(trust, passed))
    return out


def _lossy(cell: GoldenCell) -> bool:
    return any(
        any(r.get("lossy") for r in ref.get("records", []))
        for ref in cell.lineage_refs
    )
