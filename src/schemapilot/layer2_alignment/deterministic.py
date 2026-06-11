"""Stage A — The deterministic matcher (FILE_2 §4.2).

Cheap, exact, high-precision label matching that drains the easy mass. Per
axiom A2 it is allowed to nominate, never to decide alone: every hit is
flagged HOMONYM-UNVERIFIED until instance evidence concurs (the structural
defense against CHAOS-1.1.7).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from schemapilot.layer2_alignment.cco import CCO
from schemapilot.layer3_standardize.encoding import repair, strip_bom
from schemapilot.layer3_standardize.unicode_norm import match_key

# Curated abbreviation dictionary (CHAOS-1.1.3 legacy truncations).
ABBREVIATIONS = {
    "mth": "mother", "nm": "name", "cust": "customer", "addr": "address",
    "tel": "telephone", "no": "number", "num": "number", "dob": "dob",
    "amt": "amount", "acct": "account", "wt": "weight", "m": "m",
}


def normalize_label(label: str) -> str:
    """§4.2 step 1: NFC → strip BOM/zero-width → casefold → tokenize on
    case/delimiter boundaries → abbreviation expansion. Headers get mojibake
    repair too (CHAOS-1.1.5 applies to headers)."""
    label = strip_bom(label)
    repaired = repair(label)
    if repaired.repaired:
        label = repaired.text
    # camelCase -> camel case, before delimiter folding
    label = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", label)
    label = re.sub(r"[_\-./:()\[\]]+", " ", label)
    key = match_key(label)
    tokens = [ABBREVIATIONS.get(t, t) for t in key.split()]
    return " ".join(tokens)


@dataclass
class Nomination:
    column: str
    concept_id: str
    score: float
    flag: str  # "HOMONYM-UNVERIFIED" for every deterministic hit (A2)


def match(columns: list[str], cco: CCO) -> list[Nomination]:
    out: list[Nomination] = []
    for col in columns:
        normalized = normalize_label(col)
        for concept_id in cco.lookup_label(normalized):
            out.append(Nomination(col, concept_id, 1.0, "HOMONYM-UNVERIFIED"))
    return out
