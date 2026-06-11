"""Stage 2 — The pairwise comparison vector (FILE_2 §6.2).

Each metric is chosen for the error physics it models. All string metrics
operate on the match-normalized keys from §5.2 (axiom A4: no comparison ever
sees raw mojibake), and LOSSY cells contribute nothing (match_key is None).
Features are None when either side is absent — agreement-pattern honesty for
sparse rows (CHAOS-1.2.1).
"""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz.distance import JaroWinkler

from schemapilot.layer3_standardize.temporal import TemporalInterval, TemporalValue
from schemapilot.layer4_resolution.phonetic import phonetic_token_similarity
from schemapilot.layer4_resolution.records import Record

FEATURES = ("name", "name_phonetic", "dob", "phone", "email", "address", "id_exact", "mother_name")

_CONCEPT_FOR = {
    "name": "person.name.full",
    "dob": "person.dob",
    "phone": "person.contact.phone",
    "email": "person.email",
    "address": "person.address",
    "id_exact": "person.id",
    "mother_name": "person.name.mother",
}


@dataclass
class ComparisonVector:
    i: int
    j: int
    features: dict[str, float | None]

    def agreement_pattern(self, thresholds: dict[str, float]) -> dict[str, bool | None]:
        return {
            f: (None if v is None else v >= thresholds.get(f, 0.85))
            for f, v in self.features.items()
        }


def _monge_elkan(tokens_a: list[str], tokens_b: list[str], inner) -> float:
    """Token-by-best-token alignment (§6.2): aligns ["mohammed","al-rashid"]
    against ["mohamed","abdullah","alrashid"]."""
    if not tokens_a or not tokens_b:
        return 0.0
    total = 0.0
    for ta in tokens_a:
        total += max(inner(ta, tb) for tb in tokens_b)
    return total / len(tokens_a)


def _jw(a: str, b: str) -> float:
    return JaroWinkler.similarity(a, b)


def _name_similarity(key_a: str, key_b: str) -> float:
    ta, tb = key_a.split(), key_b.split()
    me = max(_monge_elkan(ta, tb, _jw), _monge_elkan(tb, ta, _jw))
    jaccard = len(set(ta) & set(tb)) / len(set(ta) | set(tb)) if (ta or tb) else 0.0
    return max(me, 0.7 * me + 0.3 * jaccard)


def _name_phonetic_similarity(key_a: str, key_b: str) -> float:
    """Cross-script channel: Monge-Elkan with consonant-skeleton inner metric."""
    ta, tb = key_a.split(), key_b.split()
    return max(
        _monge_elkan(ta, tb, phonetic_token_similarity),
        _monge_elkan(tb, ta, phonetic_token_similarity),
    )


def _temporal_similarity(cell_a, cell_b) -> float | None:
    """DOB proximity honoring §5.3 temporal intervals: an ambiguous 03/04/85
    overlaps an unambiguous 1985-04-03 — that is agreement, not conflict."""
    va, vb = cell_a.value, cell_b.value
    if isinstance(va, TemporalValue) and isinstance(vb, TemporalValue):
        return 1.0 if va.instant.date() == vb.instant.date() else 0.0
    if isinstance(va, TemporalInterval) and isinstance(vb, TemporalValue):
        return 1.0 if va.contains(vb.instant) else 0.0
    if isinstance(vb, TemporalInterval) and isinstance(va, TemporalValue):
        return 1.0 if vb.contains(va.instant) else 0.0
    if isinstance(va, TemporalInterval) and isinstance(vb, TemporalInterval):
        dates_a = {c.date() for c, _ in va.candidates}
        dates_b = {c.date() for c, _ in vb.candidates}
        return 1.0 if dates_a & dates_b else 0.0
    return None


def compare(records: list[Record], i: int, j: int) -> ComparisonVector:
    ra, rb = records[i], records[j]
    features: dict[str, float | None] = {}

    for feature, concept in _CONCEPT_FOR.items():
        ca, cb = ra.cell(concept), rb.cell(concept)
        if feature == "dob":
            if ca is None or cb is None:
                features[feature] = None
            else:
                features[feature] = _temporal_similarity(ca, cb)
            continue
        ka = ca.match_key if ca else None
        kb = cb.match_key if cb else None
        if not ka or not kb:
            features[feature] = None  # absent or LOSSY: no evidence either way
            continue
        if feature in ("name", "mother_name"):
            features[feature] = _name_similarity(ka, kb)
        elif feature == "id_exact":
            if ka == kb:
                features[feature] = 1.0
            elif ra.source_system_id == rb.source_system_id:
                features[feature] = 0.0
            else:
                # Parallel ID universes (CHAOS-3.3.3): cross-system key
                # inequality is meaningless — no evidence either way.
                features[feature] = None
        elif feature in ("phone", "email"):
            features[feature] = 1.0 if ka == kb else 0.0
        elif feature == "address":
            ta, tb = set(ka.split()), set(kb.split())
            features[feature] = len(ta & tb) / len(ta | tb) if ta | tb else 0.0

    # Phonetic channel from stored names (handles cross-script where the
    # match keys themselves are in different scripts).
    na, nb = ra.cell("person.name.full"), rb.cell("person.name.full")
    if na and nb and isinstance(na.value, str) and isinstance(nb.value, str) and not (na.lossy or nb.lossy):
        features["name_phonetic"] = _name_phonetic_similarity(na.value, nb.value)
    else:
        features["name_phonetic"] = None

    return ComparisonVector(i, j, features)
