"""Confidence as a first-class datum (axioms A3, FILE_2 §10).

Trust composition is monotone: no step can raise trust above its weakest
predecessor; only human adjudication can. Certification tiers partition all
output — nothing is dropped, everything is graded.
"""
from __future__ import annotations

from enum import Enum


class CertificationTier(Enum):
    CERTIFIED = "CERTIFIED"
    STANDARD = "STANDARD"
    PROVISIONAL = "PROVISIONAL"
    QUARANTINED = "QUARANTINED"


# Tier thresholds on the composed trust score.
TIER_THRESHOLDS: list[tuple[float, CertificationTier]] = [
    (0.95, CertificationTier.CERTIFIED),
    (0.80, CertificationTier.STANDARD),
    (0.50, CertificationTier.PROVISIONAL),
]


def compose_trust(*stage_scores: float, adjudicated: bool = False) -> float:
    """Monotone composition g(T_mapping, T_standardization, T_cluster, T_fusion, V_validation).

    The composed trust never exceeds the weakest stage (min-composition with a
    mild product penalty so several mediocre stages score below one mediocre
    stage). Human adjudication is the only override.
    """
    if adjudicated:
        return 1.0
    scores = [max(0.0, min(1.0, s)) for s in stage_scores if s is not None]
    if not scores:
        return 0.0
    floor = min(scores)
    product = 1.0
    for s in scores:
        product *= s
    # Weakest-link dominated, gently pulled down by accumulated uncertainty.
    return floor * (0.5 + 0.5 * product / floor) if floor > 0 else 0.0


def tier_for(trust: float, validation_passed: bool = True) -> CertificationTier:
    if not validation_passed:
        return CertificationTier.QUARANTINED
    for threshold, tier in TIER_THRESHOLDS:
        if trust >= threshold:
            return tier
    return CertificationTier.QUARANTINED
