"""Stage ② — Unicode & script normalization (FILE_2 §5.2; CHAOS-2.2.5–2.2.8, 3.1.3).

Two profiles: conservative for stored values (NFC + invisible stripping only),
aggressive for match keys (confusable folding + the full Arabic profile).
Stored values keep their orthography; comparison keys collapse the variance.
"""
from __future__ import annotations

import re
import unicodedata

_INVISIBLES = "​‌‍‎‏‪‫‬‭‮﻿"
_NBSP = " "

# Confusable folding for match keys (CHAOS-2.2.6): common homoglyphs.
_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p",  # Cyrillic lookalikes
    "с": "c", "х": "x", "у": "y",
    "ӏ": "l", "і": "i",
})

# Arabic match-normalization profile (§5.2) — comparison keys only.
_ARABIC_FOLD = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",  # hamza/alef unification
    "ة": "ه",  # ta-marbuta -> ha
    "ى": "ي",  # alef-maqsura -> ya
    "ی": "ي", "ک": "ك", "گ": "ك", "پ": "ب", "چ": "ج", "ژ": "ز", "ڤ": "ف",  # Farsi unification
    "ـ": None,  # tatweel removal
})
_ARABIC_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ]")
_ARABIC_RANGE = re.compile(r"[؀-ۿ]")
# Particles whose spacing is canonicalized: عبد الله -> عبدالله
_PARTICLE_JOIN = re.compile(r"\b(عبد|آل|ال)\s+")

_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_stored(text: str) -> str:
    """Conservative profile: NFC + invisible stripping + NBSP→space."""
    text = unicodedata.normalize("NFC", text)
    for ch in _INVISIBLES:
        text = text.replace(ch, "")
    return text.replace(_NBSP, " ").strip()


def fold_digits(text: str) -> str:
    """Arabic-Indic / Extended Arabic-Indic digits -> ASCII (CHAOS-1.4.7)."""
    return text.translate(_DIGIT_MAP)


def arabic_match_fold(text: str) -> str:
    text = _ARABIC_DIACRITICS.sub("", text)
    text = text.translate(_ARABIC_FOLD)
    text = _PARTICLE_JOIN.sub(lambda m: m.group(1), text)
    return text


def match_key(text: str) -> str:
    """Aggressive profile for comparison keys (never for stored values)."""
    text = normalize_stored(text)
    text = text.translate(_CONFUSABLES)
    text = fold_digits(text)
    if _ARABIC_RANGE.search(text):
        text = arabic_match_fold(text)
    text = text.casefold()
    return re.sub(r"\s+", " ", text).strip()


def is_arabic(text: str) -> bool:
    return bool(_ARABIC_RANGE.search(text))
