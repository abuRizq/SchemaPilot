"""Versioned declarative thresholds (FILE_2 §8, axiom A8).

All gates are policy, not code constants: finance runs paranoid settings,
marketing runs permissive ones, and every output is stamped with the policy
version that produced it.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Policy:
    version: str = "policy-v1"
    seed: int = 1729  # pinned for A8 determinism

    # Layer 2 — confidence gate (§4.4)
    tau_auto: float = 0.95
    tau_review: float = 0.60
    delta_competing_logit: float = 2.0  # competing-assignment margin (log-odds)

    # Layer 3 — temporal engine
    sentinel_mass_threshold: float = 0.02  # frequency mass that flags a sentinel
    format_vote_min: int = 1  # unambiguous anchors needed for a verdict

    # Layer 4 — Fellegi–Sunter decision regions (§6.3) and clustering (§6.4)
    tau_upper: float = 6.0  # W >= tau_upper -> auto-link
    tau_lower: float = 0.0  # W <= tau_lower -> non-link
    merge_threshold: float = 0.85  # super-threshold merge probability (A5)
    block_size_ceiling: int = 500
    chimera_entropy_threshold: float = 1.5  # mean conflict entropy that vetoes a cluster

    # Layer 5 — fusion
    tau_survive: float = 0.60  # posterior below this escalates to humans
    entropy_escalation: float = 1.5

    # Layer 6 — certification
    benford_p_threshold: float = 0.01
    default_mass_ceiling: float = 0.30  # max share of one value before population alarm

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_POLICY = Policy()
