"""Bayesian truth discovery — TruthFinder-class fixpoint iteration (FILE_2 §7.2/7.4).

Jointly estimate P(value is true) and per-source reliability by mutual
reinforcement: trustworthy sources assert true values; values asserted by
trustworthy sources are true. Votes are deduplicated per source (re-ingestion
cannot stuff the ballot box) and copy-discounted: sources sharing *errors*
are dependent — shared truth proves nothing, shared mistakes prove copying.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TruthResult:
    posteriors: dict[str, float]  # value key -> P(true)
    reliability: dict[str, float]  # source -> trustworthiness


def discover(
    claims: dict[str, set[str]],  # value key -> set of source ids asserting it
    *,
    prior_reliability: dict[str, float] | None = None,
    copy_discount: dict[str, float] | None = None,
    iterations: int = 25,
    damping: float = 0.3,
) -> TruthResult:
    """One attribute-domain fixpoint over (value posteriors ⇄ source trust)."""
    sources = sorted({s for ss in claims.values() for s in ss})
    if not sources:
        return TruthResult({}, {})
    trust = {s: (prior_reliability or {}).get(s, 0.8) for s in sources}
    discount = copy_discount or {}
    posteriors: dict[str, float] = {}

    confidence: dict[str, float] = {}
    for _ in range(iterations):
        # Value confidence from source trust (log-odds accumulation à la
        # TruthFinder, with independence discount per source).
        for value, ss in claims.items():
            score = 0.0
            for s in ss:
                t = min(0.999, max(1e-3, trust[s] * (1.0 - discount.get(s, 0.0))))
                score += -math.log(1 - t)
            confidence[value] = 1 - math.exp(-score)
        # Source trust from the (unnormalized) confidence of what it asserts.
        new_trust: dict[str, float] = {}
        for s in sources:
            asserted = [confidence[v] for v, ss in claims.items() if s in ss]
            est = sum(asserted) / len(asserted) if asserted else 0.5
            new_trust[s] = damping * trust[s] + (1 - damping) * min(0.99, max(0.05, est))
        converged = all(abs(new_trust[s] - trust[s]) < 1e-6 for s in sources)
        trust = new_trust
        if converged:
            break
    posteriors = confidence

    total = sum(posteriors.values()) or 1.0
    return TruthResult({v: p / total for v, p in posteriors.items()}, trust)


def estimate_copy_discount(
    error_agreements: dict[tuple[str, str], int],
    error_counts: dict[str, int],
) -> dict[str, float]:
    """Copy-discount from suspicious agreement on *errors* (§7.4): if source B
    shares most of its known errors with A, B's independence is discounted."""
    discount: dict[str, float] = defaultdict(float)
    for (a, b), shared in error_agreements.items():
        for s in (a, b):
            own = error_counts.get(s, 0)
            if own > 0:
                discount[s] = max(discount[s], min(0.9, shared / own * 0.5))
    return dict(discount)


@dataclass
class ReliabilityMatrix:
    """R[source, attribute-domain] — estimated, not asserted; versioned (§7.4)."""

    values: dict[tuple[str, str], float] = field(default_factory=dict)
    version: int = 1

    def get(self, source: str, domain: str, default: float = 0.8) -> float:
        return self.values.get((source, domain), default)

    def update(self, source: str, domain: str, observed: float, *, damping: float = 0.5) -> None:
        prev = self.get(source, domain)
        self.values[(source, domain)] = damping * prev + (1 - damping) * observed

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "values": {f"{s}|{d}": round(v, 6) for (s, d), v in sorted(self.values.items())},
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "ReliabilityMatrix":
        rm = cls(version=raw.get("version", 1))
        for key, v in raw.get("values", {}).items():
            s, d = key.split("|", 1)
            rm.values[(s, d)] = v
        return rm
