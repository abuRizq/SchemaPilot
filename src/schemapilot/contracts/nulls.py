"""Typed nulls — the unified null pantheon (FILE_2 §5.5, CHAOS-2.4.1).

A TypedNull is a first-class value, never collapsed to bare None: structural
absence, refusal, and GDPR erasure each demand different downstream handling.
ERASED is sticky and legally binding — Layer 5 fusion is hard-barred from
filling an ERASED cell from sibling sources.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NullKind(Enum):
    STRUCTURAL = "STRUCTURAL"  # source schema never had the field
    NOT_APPLICABLE = "NOT_APPLICABLE"  # field meaningless for this entity
    UNKNOWN = "UNKNOWN"  # exists in reality, never captured
    REFUSED = "REFUSED"  # subject declined; never impute
    PENDING = "PENDING"  # value will exist later (incl. excised sentinels)
    ERASED = "ERASED"  # GDPR; must never be re-fused


@dataclass(frozen=True)
class TypedNull:
    kind: NullKind
    surface_form: str | None = None  # original token, retained per A1

    def __str__(self) -> str:
        return f"<null:{self.kind.value}>"


# Surface forms of the null pantheon (CHAOS-1.4.3), all lower-cased/stripped.
NULL_PANTHEON: dict[str, NullKind] = {
    "": NullKind.UNKNOWN,
    "null": NullKind.UNKNOWN,
    "none": NullKind.UNKNOWN,
    "nil": NullKind.UNKNOWN,
    "n/a": NullKind.NOT_APPLICABLE,
    "na": NullKind.NOT_APPLICABLE,
    "n.a.": NullKind.NOT_APPLICABLE,
    "-": NullKind.UNKNOWN,
    "--": NullKind.UNKNOWN,
    "؟": NullKind.UNKNOWN,
    "?": NullKind.UNKNOWN,
    "unknown": NullKind.UNKNOWN,
    "tbd": NullKind.PENDING,
    "pending": NullKind.PENDING,
    "#n/a": NullKind.UNKNOWN,
    "#ref!": NullKind.UNKNOWN,
    "#value!": NullKind.UNKNOWN,
    "#div/0!": NullKind.UNKNOWN,
    "declined": NullKind.REFUSED,
    "refused": NullKind.REFUSED,
    "withheld": NullKind.REFUSED,
    "erased": NullKind.ERASED,
}


def classify_null(raw: object) -> TypedNull | None:
    """Return a TypedNull if `raw` is a null-pantheon surface form, else None."""
    if raw is None:
        return TypedNull(NullKind.UNKNOWN, None)
    if isinstance(raw, TypedNull):
        return raw
    if isinstance(raw, str):
        key = raw.strip().lower()
        if key in NULL_PANTHEON:
            return TypedNull(NULL_PANTHEON[key], raw)
    return None


def is_null(value: object) -> bool:
    return value is None or isinstance(value, TypedNull)
