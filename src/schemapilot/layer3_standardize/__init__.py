"""Layer 3 — Syntactic Standardization. The only public entry point is
`standardize()`; the A4 stage ordering (encoding → script → temporal →
numeric/categorical → null/sentinel) is enforced by the driver and not
re-orderable by callers.
"""
from schemapilot.layer3_standardize.driver import Cell, StandardizedSource, standardize
from schemapilot.layer3_standardize.temporal import TemporalInterval, TemporalValue
from schemapilot.layer3_standardize.unicode_norm import fold_digits, is_arabic, match_key, normalize_stored

__all__ = [
    "Cell",
    "StandardizedSource",
    "standardize",
    "TemporalInterval",
    "TemporalValue",
    "fold_digits",
    "is_arabic",
    "match_key",
    "normalize_stored",
]
