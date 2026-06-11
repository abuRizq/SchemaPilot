"""Stage 3 — Match classification: the Fellegi–Sunter spine (FILE_2 §6.3).

m/u-probabilities estimated by EM over the candidate-pair corpus,
unsupervised; u-probabilities frequency-adjusted (agreeing on a rare surname
outweighs agreeing on محمد). W(γ) = Σ log₂(m/u) with three decision regions.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from schemapilot.contracts.policy import Policy
from schemapilot.layer4_resolution.comparison import FEATURES, ComparisonVector
from schemapilot.layer4_resolution.records import Record

_AGREE_THRESHOLDS = {
    "name": 0.85,
    "name_phonetic": 0.85,
    "dob": 0.99,
    "phone": 0.99,
    "email": 0.99,
    "address": 0.5,
    "id_exact": 0.99,
    "mother_name": 0.85,
}

# Priors keep EM stable on small candidate corpora.
_M_PRIOR = {f: 0.9 for f in FEATURES}
_U_PRIOR = {
    "name": 0.01, "name_phonetic": 0.05, "dob": 0.005, "phone": 0.001,
    "email": 0.001, "address": 0.05, "id_exact": 0.001, "mother_name": 0.01,
}


@dataclass
class FSModel:
    m: dict[str, float]
    u: dict[str, float]
    prior_match: float

    def weight(self, vector: ComparisonVector, *, token_rarity: dict[str, float] | None = None) -> float:
        """Agreement weight sum W(γ); frequency-adjusted u for name agreement."""
        pattern = vector.agreement_pattern(_AGREE_THRESHOLDS)
        w = 0.0
        for f, agrees in pattern.items():
            if agrees is None:
                continue  # absent evidence contributes nothing (CHAOS-1.2.1)
            m, u = self.m[f], self.u[f]
            if agrees and f in ("name", "mother_name") and token_rarity is not None:
                # Frequency adjustment: agreement on common tokens carries a
                # higher u (more accidental agreement among non-matches).
                rarity = token_rarity.get(f"{vector.i}:{vector.j}:{f}", 1.0)
                u = min(0.9, u / max(rarity, 1e-3))
            if agrees:
                w += math.log2(m / u)
            else:
                w += math.log2((1 - m) / (1 - u))
        return w

    def match_probability(self, vector: ComparisonVector, **kw) -> float:
        w = self.weight(vector, **kw)
        prior_odds = self.prior_match / (1 - self.prior_match)
        odds = prior_odds * (2.0 ** w)
        return odds / (1 + odds)


def fit_em(
    vectors: list[ComparisonVector],
    *,
    iterations: int = 20,
    prior_match: float = 0.1,
) -> FSModel:
    """Unsupervised EM over binary agreement patterns."""
    if not vectors:
        return FSModel(dict(_M_PRIOR), dict(_U_PRIOR), prior_match)
    patterns = [v.agreement_pattern(_AGREE_THRESHOLDS) for v in vectors]
    m = dict(_M_PRIOR)
    u = dict(_U_PRIOR)
    p_match = prior_match

    for _ in range(iterations):
        # E-step: responsibility of the match class per pair.
        resp: list[float] = []
        for pattern in patterns:
            lm = math.log(p_match)
            lu = math.log(1 - p_match)
            for f, agrees in pattern.items():
                if agrees is None:
                    continue
                lm += math.log(m[f] if agrees else 1 - m[f])
                lu += math.log(u[f] if agrees else 1 - u[f])
            mx = max(lm, lu)
            num = math.exp(lm - mx)
            den = num + math.exp(lu - mx)
            resp.append(num / den)
        # M-step with light smoothing to keep probabilities off the rails.
        total_match = sum(resp) + 1e-9
        total_non = sum(1 - r for r in resp) + 1e-9
        for f in FEATURES:
            agree_match = sum(r for r, p in zip(resp, patterns) if p[f] is True) + _M_PRIOR[f]
            seen_match = sum(r for r, p in zip(resp, patterns) if p[f] is not None) + 1.0
            agree_non = sum((1 - r) for r, p in zip(resp, patterns) if p[f] is True) + _U_PRIOR[f]
            seen_non = sum((1 - r) for r, p in zip(resp, patterns) if p[f] is not None) + 1.0
            m[f] = min(0.999, max(0.5, agree_match / seen_match))
            u[f] = min(0.5, max(1e-4, agree_non / seen_non))
        p_match = min(0.5, max(0.001, total_match / (total_match + total_non)))
    return FSModel(m, u, p_match)


def token_rarity_index(records: list[Record]) -> Counter:
    """Corpus token frequencies for the frequency-adjusted u (L1 skeleton role)."""
    counts: Counter = Counter()
    for r in records:
        for concept in ("person.name.full", "person.name.mother"):
            key = r.match_key(concept)
            if key:
                counts.update(key.split())
    return counts


@dataclass
class Decision:
    i: int
    j: int
    weight: float
    probability: float
    region: str  # "auto-link" | "clerical-review" | "non-link"


def classify(
    vectors: list[ComparisonVector],
    model: FSModel,
    policy: Policy,
) -> list[Decision]:
    out = []
    for v in vectors:
        w = model.weight(v)
        p = model.match_probability(v)
        if w >= policy.tau_upper:
            region = "auto-link"
        elif w <= policy.tau_lower:
            region = "non-link"
        else:
            region = "clerical-review"
        out.append(Decision(v.i, v.j, w, p, region))
    return out
