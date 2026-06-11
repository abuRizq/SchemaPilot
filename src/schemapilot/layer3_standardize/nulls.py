"""Stage ⑤ — Null pantheon unification & sentinel neutralization (FILE_2 §5.5).

Every missingness surface form becomes a typed null. Structural nulls are
assigned at union time from the schema-presence matrix — the engine always
knows whether a source *could* have had the field (CHAOS-1.2.1).
"""
from __future__ import annotations

from schemapilot.contracts.nulls import NullKind, TypedNull, classify_null


def unify(raw: object, *, column_present_in_source: bool = True) -> TypedNull | None:
    """Return the TypedNull for `raw` if it is a missingness form, else None."""
    if not column_present_in_source:
        return TypedNull(NullKind.STRUCTURAL, None)
    return classify_null(raw)


def structural_null() -> TypedNull:
    return TypedNull(NullKind.STRUCTURAL, None)
