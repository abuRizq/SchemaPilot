"""Phonetic & cross-script keys (FILE_2 §6.1/§6.2).

The cross-script bridge: Arabic and Latin renderings of one name must
converge in phonetic space (CHAOS-3.1.1/3.1.2) — no string distance metric
bridges scripts. `consonant_skeleton` is a documented Beider–Morse-class
approximation: language-aware romanization to a consonant skeleton, which is
where `Mohammed`, `Muhammad`, and `محمد` all collapse to `mhmd`. Latin-script
phonetics additionally use Double Metaphone via jellyfish.
"""
from __future__ import annotations

import re

import jellyfish

from schemapilot.layer3_standardize.unicode_norm import arabic_match_fold, is_arabic

# Arabic letter -> Latin consonant romanization (post match-fold, so hamza/
# ta-marbuta/maqsura variants are already unified). و and ي are treated as
# matres lectionis (long-vowel carriers) and dropped, matching the y/w strip
# on the Latin side — خليل and Khalil must reach the same skeleton.
_ARABIC_ROMAN = {
    "ا": "", "ب": "b", "ت": "t", "ث": "t", "ج": "j", "ح": "h", "خ": "k",
    "د": "d", "ذ": "d", "ر": "r", "ز": "z", "س": "s", "ش": "s", "ص": "s",
    "ض": "d", "ط": "t", "ظ": "z", "ع": "", "غ": "g", "ف": "f", "ق": "q",
    "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "", "ي": "",
    "ء": "", "ئ": "", "ؤ": "",
}

# Latin digraph folding before vowel stripping.
_DIGRAPHS = [("ph", "f"), ("kh", "k"), ("gh", "g"), ("sh", "s"), ("th", "t"), ("ch", "k"), ("dh", "d")]
_VOWELS = re.compile(r"[aeiouyw]")


def romanize_arabic(text: str) -> str:
    folded = arabic_match_fold(text)
    return "".join(_ARABIC_ROMAN.get(ch, "") for ch in folded if not ch.isspace()) or folded


def consonant_skeleton(name_token: str) -> str:
    """Cross-script phonetic key for one name token."""
    token = name_token.strip().lower()
    if not token:
        return ""
    if is_arabic(token):
        skeleton = romanize_arabic(token)
    else:
        for a, b in _DIGRAPHS:
            token = token.replace(a, b)
        skeleton = _VOWELS.sub("", token)
        skeleton = re.sub(r"[^a-z]", "", skeleton)
    # Collapse doubled consonants: mohammed -> mhmmd -> mhmd.
    skeleton = re.sub(r"(.)\1+", r"\1", skeleton)
    # Trailing h is a vowel carrier in romanized Arabic (Fatimah/Fatima).
    if len(skeleton) > 2 and skeleton.endswith("h"):
        skeleton = skeleton[:-1]
    return skeleton


def name_phonetic_keys(full_name: str) -> set[str]:
    """Per-token phonetic keys for blocking: consonant skeletons plus, for
    Latin tokens, Metaphone codes."""
    keys: set[str] = set()
    for token in re.split(r"[\s\-,]+", full_name):
        if len(token) < 2:
            continue
        skeleton = consonant_skeleton(token)
        if len(skeleton) >= 2:
            keys.add(f"sk:{skeleton}")
        if not is_arabic(token):
            try:
                code = jellyfish.metaphone(token)
            except Exception:
                code = ""
            if len(code) >= 2:
                keys.add(f"mp:{code}")
    return keys


def phonetic_token_similarity(a: str, b: str) -> float:
    """Skeleton-space similarity for one token pair (cross-script safe)."""
    sa, sb = consonant_skeleton(a), consonant_skeleton(b)
    if not sa or not sb:
        return 0.0
    if sa == sb:
        return 1.0
    dist = jellyfish.levenshtein_distance(sa, sb)
    return max(0.0, 1.0 - dist / max(len(sa), len(sb)))
