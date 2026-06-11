"""Column fingerprinting — compact statistical identity per column (FILE_2 §3).

One streaming pass produces every component in the §3 table: cardinality,
frequency skeleton, value-set signature, distribution sketch, pattern census,
script census, type-inference vector, null census, Benford profile.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from datasketch import HyperLogLogPlusPlus, MinHash

from schemapilot.contracts.nulls import classify_null
from schemapilot.layer1_profiling.sketches import (
    CountMinSketch,
    QuantileSketch,
    new_hll,
    new_minhash,
)

# Pattern census classes (CHAOS-2.1.1 format-mixture detection, CHAOS-1.4.x).
_PATTERN_CLASSES: list[tuple[str, re.Pattern]] = [
    ("iso_date", re.compile(r"^\d{4}-\d{2}-\d{2}([T ].*)?$")),
    ("slash_date", re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")),
    ("dash_date", re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$")),
    ("integer", re.compile(r"^[+-]?\d+$")),
    ("decimal_dot", re.compile(r"^[+-]?\d{1,3}(,\d{3})*\.\d+$|^[+-]?\d+\.\d+$")),
    ("decimal_comma", re.compile(r"^[+-]?\d{1,3}(\.\d{3})*,\d+$|^[+-]?\d+,\d+$")),
    ("scientific", re.compile(r"^[+-]?\d+(\.\d+)?[eE][+-]?\d+$")),
    ("leading_zero_id", re.compile(r"^0\d+$")),
    ("phone_like", re.compile(r"^[+()\d\s/.x-]{7,}$")),
    ("email", re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")),
    ("bool_like", re.compile(r"^(1|0|y|n|yes|no|true|false|t|f|نعم|لا|checked|-1)$", re.I)),
    ("excel_error", re.compile(r"^#(VALUE|DIV/0|REF|N/A|NAME\?)!?$")),
]

_TYPES = ("int", "decimal", "date", "bool", "id_like", "free_text")


def _unicode_block(ch: str) -> str:
    code = ord(ch)
    if code < 0x80:
        if ch.isdigit():
            return "ascii_digit"
        if ch.isalpha():
            return "latin"
        return "ascii_other"
    if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
        if "٠" <= ch <= "٩" or "۰" <= ch <= "۹":
            return "arabic_digit"
        return "arabic"
    if 0xFB50 <= code <= 0xFDFF or 0xFE70 <= code <= 0xFEFF:
        return "arabic_presentation"
    if 0x0400 <= code <= 0x04FF:
        return "cyrillic"
    if code in (0x00A0, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF):
        return "invisible"
    if code == 0xFFFD:
        return "replacement"
    if 0x0080 <= code <= 0x00FF:
        return "latin1_supplement"  # mojibake salad lives here (CHAOS-2.2.1)
    return "other"


@dataclass
class ColumnFingerprint:
    column: str
    source_file_id: str
    n_values: int = 0
    n_nulls: int = 0
    hll: HyperLogLogPlusPlus = field(default_factory=new_hll)
    minhash: MinHash = field(default_factory=new_minhash)
    cms: CountMinSketch = field(default_factory=CountMinSketch)
    quantiles: QuantileSketch = field(default_factory=QuantileSketch)
    pattern_census: Counter = field(default_factory=Counter)
    script_census: Counter = field(default_factory=Counter)
    null_census: Counter = field(default_factory=Counter)  # per NullKind name
    first_digit_census: Counter = field(default_factory=Counter)  # Benford
    length_min: int | None = None
    length_max: int | None = None
    leading_zero_seen: bool = False
    _distinct_sample: set = field(default_factory=set)

    # ---- streaming update -------------------------------------------------
    def add(self, raw: str | None) -> None:
        self.n_values += 1
        typed = classify_null(raw)
        if typed is not None:
            self.n_nulls += 1
            self.null_census[typed.kind.value] += 1
            return
        value = str(raw)
        key = value.strip()
        self.hll.update(key.encode("utf-8"))
        self.minhash.update(key.lower().encode("utf-8"))
        self.cms.add(key)
        if len(self._distinct_sample) < 4096:
            self._distinct_sample.add(key.lower())
        self.length_min = len(key) if self.length_min is None else min(self.length_min, len(key))
        self.length_max = len(key) if self.length_max is None else max(self.length_max, len(key))
        if re.match(r"^0\d+$", key):
            self.leading_zero_seen = True

        matched = False
        for name, pattern in _PATTERN_CLASSES:
            if pattern.match(key):
                self.pattern_census[name] += 1
                matched = True
                break
        if not matched:
            self.pattern_census["other"] += 1

        for ch in value:
            self.script_census[_unicode_block(ch)] += 1

        cleaned = key.replace(",", "").lstrip("+-")
        if re.match(r"^\d+(\.\d+)?$", cleaned):
            try:
                self.quantiles.add(float(cleaned))
            except ValueError:
                pass
            stripped = cleaned.lstrip("0.")
            if stripped:
                self.first_digit_census[stripped[0]] += 1

    # ---- derived measures ---------------------------------------------------
    @property
    def n_present(self) -> int:
        return self.n_values - self.n_nulls

    @property
    def cardinality(self) -> float:
        return self.hll.count()

    @property
    def null_fraction(self) -> float:
        return self.n_nulls / self.n_values if self.n_values else 0.0

    def pattern_fraction(self, name: str) -> float:
        return self.pattern_census[name] / self.n_present if self.n_present else 0.0

    def type_vector(self) -> dict[str, float]:
        """P(type) from value-level voting — a vector, not a verdict (§3)."""
        if self.n_present == 0:
            return {t: 0.0 for t in _TYPES}
        votes = {t: 0.0 for t in _TYPES}
        votes["int"] = self.pattern_census["integer"] + self.pattern_census["bool_like"] * 0.2
        votes["decimal"] = (
            self.pattern_census["decimal_dot"]
            + self.pattern_census["decimal_comma"]
            + self.pattern_census["scientific"]
        )
        votes["date"] = (
            self.pattern_census["iso_date"]
            + self.pattern_census["slash_date"]
            + self.pattern_census["dash_date"]
        )
        votes["bool"] = self.pattern_census["bool_like"] * 0.8
        # id-like: high cardinality, fixed width or leading zeros (CHAOS-1.4.9) —
        # suppressed when a semantic pattern (email/phone/date) explains the
        # column, since those are also high-cardinality and often fixed-width.
        distinct_ratio = min(1.0, self.cardinality / self.n_present)
        fixed_width = self.length_min == self.length_max and (self.length_min or 0) >= 4
        semantic_mass = (
            self.pattern_census["email"] + self.pattern_census["phone_like"] + votes["date"]
        ) / self.n_present
        if distinct_ratio > 0.9 and (fixed_width or self.leading_zero_seen) and semantic_mass < 0.5:
            votes["id_like"] = self.n_present * distinct_ratio
        votes["free_text"] = (
            self.pattern_census["other"]
            + self.pattern_census["email"]
            + self.pattern_census["phone_like"] * 0.3
        )
        total = sum(votes.values()) or 1.0
        return {t: v / total for t, v in votes.items()}

    def dominant_type(self) -> str:
        tv = self.type_vector()
        return max(tv, key=lambda t: tv[t])

    def script_fraction(self, block: str) -> float:
        total = sum(self.script_census.values())
        return self.script_census[block] / total if total else 0.0

    def benford_chi2(self) -> float | None:
        """Chi-square statistic of first digits vs Benford's law (CHAOS-3.4.4)."""
        total = sum(self.first_digit_census[str(d)] for d in range(1, 10))
        if total < 50:
            return None
        chi2 = 0.0
        for d in range(1, 10):
            expected = total * math.log10(1 + 1 / d)
            observed = self.first_digit_census[str(d)]
            chi2 += (observed - expected) ** 2 / expected
        return chi2

    def value_overlap(self, other: "ColumnFingerprint") -> float:
        """Estimated Jaccard containment of self's values in other's (E4 channel)."""
        if self._distinct_sample and other._distinct_sample:
            inter = len(self._distinct_sample & other._distinct_sample)
            return inter / len(self._distinct_sample)
        return self.minhash.jaccard(other.minhash)


def fingerprint_source(
    columns: list[str], rows: list[dict[str, str | None]], source_file_id: str
) -> dict[str, ColumnFingerprint]:
    prints = {c: ColumnFingerprint(column=c, source_file_id=source_file_id) for c in columns}
    for row in rows:
        for col in columns:
            prints[col].add(row.get(col))
    return prints
