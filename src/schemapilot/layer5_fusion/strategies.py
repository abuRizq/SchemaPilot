"""The resolution strategy arsenal & per-attribute pipeline (FILE_2 §7.2/§7.3).

Strategy selection is a function of conflict type and the CCO contract:
multiplicity pre-check first, cross-source disambiguation always first among
resolvers (free wins), recency only for temporal-mutable attributes and only
post sentinel-excision, specificity lattice for hierarchical, weighted vote
for categorical, Bayesian truth discovery for contested/high-stakes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from schemapilot.contracts.concept import ConceptContract, Datatype, TemporalClass
from schemapilot.contracts.policy import Policy
from schemapilot.layer3_standardize.temporal import TemporalInterval, TemporalValue
from schemapilot.layer5_fusion.conflict import Assertion, ConflictSet
from schemapilot.layer5_fusion.truth_discovery import discover


@dataclass
class Resolution:
    strategy: str
    winners: list[str]  # canonical group keys that survive (1 unless multi-valued)
    posterior: float
    escalate: bool = False
    quarantine: bool = False
    detail: str = ""


def resolve_attribute(
    cs: ConflictSet,
    contract: ConceptContract,
    policy: Policy,
    *,
    reliability: dict[str, float] | None = None,
) -> Resolution:
    """The §7.3 pipeline for one (cluster, attribute)."""
    reliability = reliability or {}

    if cs.erased:
        # Hard legal bar (§5.5): an ERASED cell is never filled from siblings.
        return Resolution("erased_bar", [], 1.0, detail="GDPR: fusion barred")

    if not cs.groups:
        return Resolution("no_assertions", [], 0.0)

    # ① representational collapse already happened in gather(); singleton?
    if cs.is_singleton:
        key = next(iter(cs.groups))
        return Resolution("unanimous", [key], _corroborated_trust(cs.groups[key], reliability))

    # ② multiplicity pre-check (CHAOS-3.2.3): conflict may be plural truth.
    if contract.multi_valued:
        winners = sorted(cs.groups)
        return Resolution(
            "multiplicity", winners,
            min(_corroborated_trust(a, reliability) for a in cs.groups.values()),
            detail=f"{len(winners)} simultaneous values promoted",
        )

    # ③ cross-source disambiguation: a sibling's unambiguous value collapses
    # ambiguity intervals (the §5.3 hand-off) — evidence, not choice.
    collapsed = _collapse_intervals(cs)
    if collapsed.is_singleton:
        key = next(iter(collapsed.groups))
        return Resolution(
            "cross_source_disambiguation", [key],
            _corroborated_trust(collapsed.groups[key], reliability),
            detail="ambiguity interval collapsed by sibling source",
        )
    cs = collapsed

    # ⑤ strategy by attribute type.
    if contract.high_stakes:
        return _bayesian(cs, policy, reliability)
    if contract.temporal_class is TemporalClass.MUTABLE:
        return _recency(cs, policy, reliability)
    if contract.temporal_class is TemporalClass.HIERARCHICAL:
        return _specificity(cs, policy, reliability)
    if contract.datatype is Datatype.NAME:
        return _most_complete_name(cs, policy, reliability)
    return _weighted_vote(cs, policy, reliability)


def _max_source_trust(assertions: list[Assertion], reliability: dict[str, float]) -> float:
    return max(reliability.get(a.source_system_id, 0.8) for a in assertions)


def _corroborated_trust(assertions: list[Assertion], reliability: dict[str, float]) -> float:
    """Noisy-or over distinct attesting sources: independent corroboration
    compounds (two 0.8-reliable sources agreeing -> 0.96), but one source
    counted twice does not (CHAOS-1.3.9)."""
    per_source: dict[str, float] = {}
    for a in assertions:
        r = reliability.get(a.source_system_id, 0.8)
        per_source[a.source_system_id] = max(per_source.get(a.source_system_id, 0.0), r)
    miss = 1.0
    for r in per_source.values():
        miss *= 1.0 - r
    return 1.0 - miss


def _collapse_intervals(cs: ConflictSet) -> ConflictSet:
    interval_keys = [k for k in cs.groups if k.startswith("interval:")]
    if not interval_keys:
        return cs
    exact_keys = [k for k in cs.groups if not k.startswith("interval:")]
    out = ConflictSet(cs.concept_id, cs.cluster_id, dict(cs.groups), cs.erased)
    for ikey in interval_keys:
        candidates = set(ikey.removeprefix("interval:").split("|"))
        matches = [k for k in exact_keys if k in candidates]
        if len(matches) == 1:
            out.groups.setdefault(matches[0], []).extend(out.groups.pop(ikey))
    return out


def _recency(cs: ConflictSet, policy: Policy, reliability: dict[str, float]) -> Resolution:
    """Last-write-wins — safe here because sentinel dates were excised in L3
    (CHAOS-2.1.7) and asserted times ride the envelope, not the values."""
    def newest(assertions: list[Assertion]) -> str:
        return max((a.source_asserted_time or "") for a in assertions)

    ranked = sorted(cs.groups.items(), key=lambda kv: newest(kv[1]), reverse=True)
    winner, runner_up = ranked[0], (ranked[1] if len(ranked) > 1 else None)
    if not newest(winner[1]):
        # No asserted times at all: recency is inapplicable, fall back.
        return _weighted_vote(cs, policy, reliability)
    margin_known = runner_up is None or newest(runner_up[1]) < newest(winner[1])
    posterior = (0.9 if margin_known else 0.5) * _max_source_trust(winner[1], reliability)
    return Resolution(
        "recency", [winner[0]], posterior,
        escalate=posterior < policy.tau_survive,
        detail=f"asserted {newest(winner[1])}",
    )


def _specificity(cs: ConflictSet, policy: Policy, reliability: dict[str, float]) -> Resolution:
    """Specificity lattice (CHAOS-3.2.5): more-specific wins iff consistent
    with the less-specific value; inconsistency doubles as error detection."""
    keys = sorted(cs.groups, key=len, reverse=True)
    most = keys[0]
    most_tokens = set(most.split())
    for other in keys[1:]:
        if not set(other.split()) <= most_tokens:
            # Not a granularity conflict — genuine disagreement.
            return _weighted_vote(cs, policy, reliability)
    return Resolution(
        "specificity_lattice", [most],
        _max_source_trust(cs.groups[most], reliability),
        detail="most-specific consistent value subsumes the rest",
    )


def _weighted_vote(cs: ConflictSet, policy: Policy, reliability: dict[str, float]) -> Resolution:
    """Votes deduplicated per source system (CHAOS-1.3.9 ballot-stuffing
    defense) and weighted by reliability — the practical default."""
    weights: dict[str, float] = {}
    for key, assertions in cs.groups.items():
        per_source: dict[str, float] = {}
        for a in assertions:
            r = reliability.get(a.source_system_id, 0.8)
            per_source[a.source_system_id] = max(per_source.get(a.source_system_id, 0.0), r)
        weights[key] = sum(per_source.values())
    total = sum(weights.values()) or 1.0
    winner = max(sorted(weights), key=lambda k: weights[k])
    posterior = weights[winner] / total
    return Resolution(
        "weighted_vote", [winner], posterior,
        escalate=posterior < policy.tau_survive,
    )


def _most_complete_name(
    cs: ConflictSet, policy: Policy, reliability: dict[str, float]
) -> Resolution:
    """Survivorship for name spellings: when the variants are phonetically the
    same person-name (consonant skeletons agree), keep the most complete
    representation rather than escalating a non-conflict. Genuinely different
    names fall through to the weighted vote."""
    from schemapilot.layer4_resolution.phonetic import consonant_skeleton

    def skeleton_set(key: str) -> frozenset[str]:
        return frozenset(filter(None, (consonant_skeleton(t) for t in key.split())))

    skeletons = {key: skeleton_set(key) for key in cs.groups}
    base = max(skeletons.values(), key=len, default=frozenset())
    if not all(s <= base or base <= s for s in skeletons.values()):
        return _weighted_vote(cs, policy, reliability)
    # All variants phonetically compatible: most tokens, then longest surface.
    winner = max(sorted(cs.groups), key=lambda k: (len(k.split()), len(k)))
    all_assertions = [a for v in cs.groups.values() for a in v]
    return Resolution(
        "most_complete_representation", [winner],
        _corroborated_trust(all_assertions, reliability),
        detail="phonetically-equivalent spellings; completeness survivorship",
    )


def _bayesian(cs: ConflictSet, policy: Policy, reliability: dict[str, float]) -> Resolution:
    """Bayesian truth discovery — the engine of record for high-stakes
    contested attributes."""
    claims = {key: {a.source_system_id for a in assertions} for key, assertions in cs.groups.items()}
    result = discover(claims, prior_reliability=reliability)
    winner = max(sorted(result.posteriors), key=lambda k: result.posteriors[k])
    posterior = result.posteriors[winner]
    return Resolution(
        "bayesian_truth_discovery", [winner], posterior,
        escalate=posterior < policy.tau_survive,
        detail=f"source trust: { {s: round(t, 3) for s, t in sorted(result.reliability.items())} }",
    )
