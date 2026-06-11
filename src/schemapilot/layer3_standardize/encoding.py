"""Stage ① — Encoding repair (FILE_2 §5.1, CHAOS-2.2.1–2.2.4).

Mojibake is deterministic damage, so repair is search over corruption chains:
enumerate plausible (true-encoding, assumed-encoding)ⁿ chains up to depth 3,
apply the inverse, score candidates by linguistic plausibility, and accept
only with round-trip consistency — re-applying the inferred corruption must
reproduce the observed bytes exactly. U+FFFD damage is irreparable: retained,
marked LOSSY, barred from serving as match evidence in L4.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

_ENCODING_PAIRS = [
    ("utf-8", "latin-1"),
    ("utf-8", "windows-1252"),
]
_MAX_DEPTH = 3

# Latin-1/CP1252 byte range that mojibake "punctuation salad" lives in.
_SALAD = set(range(0x80, 0x100)) | {0x0152, 0x0153, 0x0160, 0x0161, 0x0178, 0x017D,
                                    0x017E, 0x0192, 0x02C6, 0x02DC, 0x2013, 0x2014,
                                    0x2018, 0x2019, 0x201A, 0x201C, 0x201D, 0x201E,
                                    0x2020, 0x2021, 0x2022, 0x2026, 0x2030, 0x2039,
                                    0x203A, 0x20AC, 0x2122}


@dataclass(frozen=True)
class RepairResult:
    text: str
    repaired: bool
    lossy: bool
    chain: str  # e.g. "(utf-8 read as latin-1) x2"
    plausibility: float


def _plausibility(text: str) -> float:
    """Linguistic plausibility: coherent letters good, mojibake salad bad."""
    if not text:
        return 0.0
    good = bad = 0
    for ch in text:
        code = ord(ch)
        if code < 0x80:
            good += 1
        elif code in _SALAD:
            bad += 1
        else:
            category = unicodedata.category(ch)
            if category.startswith("L"):  # letter in some real script
                good += 2
            else:
                bad += 1
    return good / (good + 2 * bad) if (good + bad) else 0.0


def _suspicious(text: str) -> bool:
    return any(ord(ch) in _SALAD for ch in text)


def repair(text: str) -> RepairResult:
    """Attempt mojibake reversal; never destroys (returns original on failure)."""
    if "�" in text:
        # Replacement-character destruction (CHAOS-2.2.3): irreparable.
        return RepairResult(text, repaired=False, lossy=True, chain="U+FFFD", plausibility=0.0)
    if not _suspicious(text):
        return RepairResult(text, repaired=False, lossy=False, chain="", plausibility=1.0)

    base_score = _plausibility(text)
    best = RepairResult(text, False, False, "", base_score)
    for true_enc, assumed_enc in _ENCODING_PAIRS:
        candidate = text
        for depth in range(1, _MAX_DEPTH + 1):
            try:
                # Invert one corruption step: bytes were true_enc, read as assumed_enc.
                candidate = candidate.encode(assumed_enc).decode(true_enc)
            except (UnicodeEncodeError, UnicodeDecodeError):
                break
            # Round-trip consistency: re-applying the corruption chain must
            # reproduce the observed string exactly.
            forward = candidate
            try:
                for _ in range(depth):
                    forward = forward.encode(true_enc).decode(assumed_enc)
            except (UnicodeEncodeError, UnicodeDecodeError):
                break
            if forward != text:
                break
            score = _plausibility(candidate)
            if score > best.plausibility and score > base_score + 0.1:
                best = RepairResult(
                    candidate,
                    repaired=True,
                    lossy=False,
                    chain=f"({true_enc} read as {assumed_enc}) x{depth}",
                    plausibility=score,
                )
    return best


def strip_bom(text: str) -> str:
    """BOM contamination (CHAOS-2.2.4): U+FEFF prefixing headers/values."""
    return text.lstrip("﻿")
