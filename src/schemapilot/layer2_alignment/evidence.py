"""Stage B — Probabilistic evidence channels E₁–E₄ (FILE_2 §4.3).

Four independent channels per (column, concept) pair; channel availability is
explicit — absent channels are renormalized away, not zeroed. E₂ is a veto
channel: hard type incompatibility drives the score negative, which is what
defeats homonyms (CHAOS-1.1.7).
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from schemapilot.layer1_profiling.fingerprint import ColumnFingerprint
from schemapilot.layer2_alignment.cco import CCO, ConceptNode
from schemapilot.layer2_alignment.deterministic import normalize_label
from schemapilot.contracts.concept import Datatype

# E2 carries a small positive weight — type compatibility is necessary but
# never sufficient (any free-text column is type-compatible with any text
# concept). Identity evidence must come from labels (E1) or instances (E4);
# E2's real power is the veto below.
_W = {"e1": 4.0, "e2": 1.0, "e3": 1.0, "e4": 5.0, "det": 1.5}
_BIAS = -3.5


class LabelEmbedder:
    """Pluggable label-similarity backend (§4.3 E₁).

    Default implementation: character-trigram cosine over normalized labels.
    Cross-lingual equivalence rides on the CCO's multilingual label edges —
    a label only needs to be near *one* attested edge in any language. A
    sentence-transformer drop-in implements the same two methods.
    """

    def embed(self, text: str) -> Counter:
        text = f"  {text}  "
        return Counter(text[i : i + 3] for i in range(len(text) - 2))

    def similarity(self, a: str, b: str) -> float:
        va, vb = self.embed(a), self.embed(b)
        dot = sum(va[g] * vb[g] for g in va)
        norm = math.sqrt(sum(v * v for v in va.values())) * math.sqrt(
            sum(v * v for v in vb.values())
        )
        return dot / norm if norm else 0.0


@dataclass
class EvidenceScore:
    column: str
    concept_id: str
    e1: float | None  # label semantic similarity
    e2: float | None  # type & pattern compatibility (veto channel: may be negative)
    e3: float | None  # distributional similarity
    e4: float | None  # instance overlap (the heavyweight)
    deterministic_hit: bool
    composite: float


# Datatype contract -> compatible dominant fingerprint types (E₂).
_TYPE_COMPAT: dict[Datatype, set[str]] = {
    Datatype.ID: {"id_like", "int"},
    Datatype.INTEGER: {"int"},
    Datatype.DECIMAL: {"decimal", "int"},
    Datatype.DATE: {"date"},
    Datatype.BOOLEAN: {"bool", "int"},
    Datatype.PHONE: {"free_text", "int", "id_like"},
    Datatype.NAME: {"free_text"},
    Datatype.ADDRESS: {"free_text"},
    Datatype.CATEGORICAL: {"free_text", "bool", "int"},
    Datatype.STRING: {"free_text", "int", "id_like"},
}


def _e1_label(column: str, node: ConceptNode, embedder: LabelEmbedder) -> float:
    norm = normalize_label(column)
    raw = max(
        (embedder.similarity(norm, normalize_label(edge.surface)) for edge in node.labels),
        default=0.0,
    )
    # Rectify: trigram similarity below ~0.55 is accidental n-gram overlap
    # ("internal notes" grazing "nom de la mere"), not synonymy. Genuine
    # label matches in this space score >= 0.7; noise must contribute zero.
    return max(0.0, (raw - 0.55) / 0.45)


def _e2_type(fp: ColumnFingerprint, node: ConceptNode) -> float:
    """Type/pattern compatibility in [-1, 1]; hard incompatibility is a veto."""
    compatible = _TYPE_COMPAT[node.contract.datatype]
    tv = fp.type_vector()
    mass = sum(tv[t] for t in compatible if t in tv)
    pattern_bonus = 0.0
    if node.pattern_library and fp.n_present:
        attested = sum(fp.pattern_census[p] for p in node.pattern_library)
        pattern_bonus = 0.3 * (attested / fp.n_present)
    score = 2.0 * mass - 1.0 + pattern_bonus  # mass 0 -> -1 (veto), mass 1 -> +1
    return max(-1.0, min(1.0, score))


def _e3_distribution(fp: ColumnFingerprint, mapped: list[ColumnFingerprint]) -> float | None:
    if not mapped:
        return None  # channel absent, not zero (§4.3)
    scores = []
    for other in mapped:
        ks = fp.quantiles.ks_distance(other.quantiles)
        if ks is not None:
            scores.append(1.0 - ks)
            continue
        # Categorical/text: Jensen-Shannon divergence over heavy hitters.
        ha = dict(fp.cms.heavy_hitters(0.001))
        hb = dict(other.cms.heavy_hitters(0.001))
        if ha and hb:
            scores.append(1.0 - _js_divergence(ha, hb))
    return max(scores) if scores else None


def _js_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    keys = set(p) | set(q)
    sp, sq = sum(p.values()) or 1.0, sum(q.values()) or 1.0

    def _kl(a: dict, sa: float, m: dict) -> float:
        out = 0.0
        for k in keys:
            pa = a.get(k, 0.0) / sa
            if pa > 0 and m[k] > 0:
                out += pa * math.log2(pa / m[k])
        return out

    m = {k: 0.5 * (p.get(k, 0.0) / sp + q.get(k, 0.0) / sq) for k in keys}
    return min(1.0, 0.5 * _kl(p, sp, m) + 0.5 * _kl(q, sq, m))


def _e4_overlap(fp: ColumnFingerprint, mapped: list[ColumnFingerprint]) -> float | None:
    if not mapped:
        return None
    return max(fp.value_overlap(other) for other in mapped)


def score(
    column: str,
    fp: ColumnFingerprint,
    concept_id: str,
    cco: CCO,
    *,
    mapped_fingerprints: dict[str, list[ColumnFingerprint]],
    deterministic_hit: bool,
    embedder: LabelEmbedder | None = None,
) -> EvidenceScore:
    node = cco.concepts[concept_id]
    embedder = embedder or LabelEmbedder()
    history = mapped_fingerprints.get(concept_id, [])

    e1 = _e1_label(column, node, embedder)
    e2 = _e2_type(fp, node)
    e3 = _e3_distribution(fp, history)
    e4 = _e4_overlap(fp, history)

    # Calibrated log-linear combination with channel-absence renormalization:
    # absent channels' weights are removed from the denominator scale.
    channels = {"e1": e1, "e2": e2, "e3": e3, "e4": e4}
    present_weight = sum(_W[c] for c, v in channels.items() if v is not None)
    full_weight = sum(_W[c] for c in channels)
    scale = full_weight / present_weight if present_weight else 1.0
    linear = _BIAS
    for c, v in channels.items():
        if v is not None:
            linear += _W[c] * v * scale
    if deterministic_hit:
        linear += _W["det"]
    composite = 1.0 / (1.0 + math.exp(-linear))
    # Veto channel: hard type incompatibility caps the composite regardless of
    # how good the label looks — labels lie (CHAOS-1.1.7), values don't.
    if e2 is not None and e2 <= -0.5:
        composite = min(composite, 0.15)
    return EvidenceScore(column, concept_id, e1, e2, e3, e4, deterministic_hit, composite)
