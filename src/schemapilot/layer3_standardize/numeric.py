"""Stage ④a — Numeric, unit & identifier canonicalization (FILE_2 §5.4).

Decimal-separator convention is inferred per column from unambiguous values,
never per value (CHAOS-1.4.4). Id-like columns are contractually string-typed
forever (CHAOS-1.4.9). Units convert per CCO contract with lineage receipts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from schemapilot.layer3_standardize.unicode_norm import fold_digits

_DOT_DECIMAL = re.compile(r"^[+-]?\d{1,3}(,\d{3})+\.\d+$|^[+-]?\d+\.\d+$")
_COMMA_DECIMAL = re.compile(r"^[+-]?\d{1,3}(\.\d{3})+,\d+$|^[+-]?\d+,\d+$")
_INTEGER = re.compile(r"^[+-]?\d+$")
_SCIENTIFIC = re.compile(r"^[+-]?\d+(\.\d+)?[eE][+-]?\d+$")

UNIT_CONVERSIONS: dict[tuple[str, str], float] = {
    ("lbs", "kg"): 0.45359237,
    ("lb", "kg"): 0.45359237,
    ("mi", "km"): 1.609344,
    ("miles", "km"): 1.609344,
    ("ft", "m"): 0.3048,
    ("in", "cm"): 2.54,
}


@dataclass
class NumericVerdict:
    decimal_separator: str  # "." or ","
    confidence: float


def infer_decimal_convention(values: list[str]) -> NumericVerdict:
    """Column-level inference from unambiguous values: `1,234.56` is decidable,
    `1,234` is not."""
    dot_votes = comma_votes = 0
    for raw in values:
        if raw is None:
            continue
        v = fold_digits(str(raw).strip())
        if _DOT_DECIMAL.match(v) and "," in v:
            dot_votes += 1  # grouped thousands + dot decimal: unambiguous
        elif _COMMA_DECIMAL.match(v) and "." in v:
            comma_votes += 1
        elif _DOT_DECIMAL.match(v) and "," not in v and "." in v:
            dot_votes += 1
        elif _COMMA_DECIMAL.match(v) and "." not in v and "," in v:
            comma_votes += 1
    total = dot_votes + comma_votes
    if total == 0:
        return NumericVerdict(".", 0.5)
    if dot_votes >= comma_votes:
        return NumericVerdict(".", dot_votes / total)
    return NumericVerdict(",", comma_votes / total)


def parse_numeric(raw: str, verdict: NumericVerdict) -> float | None:
    """Decode one value under the column verdict; None when unparseable
    (caller flags, never coerces)."""
    v = fold_digits(str(raw).strip())
    if _SCIENTIFIC.match(v):
        return float(v)
    if _INTEGER.match(v):
        return float(v)
    if verdict.decimal_separator == ".":
        if _DOT_DECIMAL.match(v):
            return float(v.replace(",", ""))
    else:
        if _COMMA_DECIMAL.match(v):
            return float(v.replace(".", "").replace(",", "."))
    return None


def is_id_like_locked(fingerprint_dominant_type: str, leading_zero_seen: bool) -> bool:
    """CHAOS-1.4.9: id-like columns never pass through a numeric parser."""
    return fingerprint_dominant_type == "id_like" or leading_zero_seen


def convert_unit(value: float, from_unit: str, to_unit: str) -> float | None:
    if from_unit == to_unit:
        return value
    factor = UNIT_CONVERSIONS.get((from_unit.lower(), to_unit.lower()))
    return value * factor if factor is not None else None


def extract_label_unit(label: str) -> str | None:
    """Unit-embedded labels (CHAOS-1.1.9): weight_kg, Weight (lbs), WT."""
    m = re.search(r"[_\s(\[]+(kg|lbs?|km|mi|miles|m|cm|ft|in|sar|usd)[)\]\s]*$", label, re.I)
    return m.group(1).lower() if m else None
