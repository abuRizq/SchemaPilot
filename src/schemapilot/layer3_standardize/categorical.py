"""Stage ④b — Categorical conformance & composite-field parsers (FILE_2 §5.4).

Surface forms map onto a concept's closed value domain via the same
normalize → dictionary → fuzzy → adjudicate ladder as schema labels
(CHAOS-2.3.4); phones canonicalize to E.164-style keys (CHAOS-2.3.3).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from schemapilot.layer3_standardize.unicode_norm import fold_digits, match_key


@dataclass
class CategoricalDomain:
    """Closed value domain with attested surface-form synonyms (accretes via
    adjudication, like the CCO's label edges)."""

    canonical_values: list[str]
    synonyms: dict[str, str] = field(default_factory=dict)  # match_key -> canonical

    def conform(self, raw: str) -> tuple[str | None, float]:
        """Returns (canonical_value | None, confidence)."""
        key = match_key(raw)
        for canon in self.canonical_values:
            if key == match_key(canon):
                return canon, 1.0
        if key in self.synonyms:
            return self.synonyms[key], 0.95
        # Fuzzy rung: prefix/abbreviation tolerance ("Act." -> "Active").
        best, best_score = None, 0.0
        for canon in self.canonical_values:
            ck = match_key(canon)
            score = fuzz.ratio(key, ck) / 100.0
            if ck.startswith(key.rstrip(".")) and len(key) >= 1:
                score = max(score, 0.9)
            if score > best_score:
                best, best_score = canon, score
        if best_score >= 0.85:
            return best, best_score
        return None, best_score

    def learn(self, surface: str, canonical: str) -> None:
        """Adjudication write-back: the system never asks the same question twice."""
        self.synonyms[match_key(surface)] = canonical


# --- phone canonicalization (CHAOS-2.3.3) -----------------------------------

_PHONE_JUNK = re.compile(r"[\s(). -]+")
_EXTENSION = re.compile(r"\s*(x|ext\.?)\s*\d+\s*$", re.I)


def canonical_phone(raw: str, *, default_country: str = "966") -> str | None:
    """E.164-style canonical key with envelope-country defaults."""
    value = fold_digits(raw.strip())
    value = _EXTENSION.sub("", value)
    value = _PHONE_JUNK.sub("", value)
    if value.startswith("00"):
        value = "+" + value[2:]
    if value.startswith("+"):
        digits = value[1:]
        return "+" + digits if digits.isdigit() and 8 <= len(digits) <= 15 else None
    if not value.isdigit():
        return None
    if value.startswith("0"):
        value = value.lstrip("0")
    if value.startswith(default_country):
        return "+" + value
    if 7 <= len(value) <= 10:
        return "+" + default_country + value
    return "+" + value if 8 <= len(value) <= 15 else None


# --- boolean babel (CHAOS-1.4.6) ---------------------------------------------

_BOOL_MAP = {
    "1": True, "0": False, "y": True, "n": False, "yes": True, "no": False,
    "true": True, "false": False, "t": True, "f": False, "نعم": True, "لا": False,
    "-1": True, "checked": True, "unchecked": False,
}


def conform_boolean(raw: str) -> bool | None:
    return _BOOL_MAP.get(match_key(raw))
