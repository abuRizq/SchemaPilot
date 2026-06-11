"""Concept contracts — the per-attribute slice of the CCO that downstream
layers consume (datatype contract, unit contract, multiplicity, sensitivity,
validation predicates). Defined here so Layer 3 can standardize against
contracts without importing the full ontology.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class Datatype(Enum):
    STRING = "string"
    ID = "id"  # contractually string-typed forever (CHAOS-1.4.9)
    DECIMAL = "decimal"
    INTEGER = "integer"
    DATE = "date"
    BOOLEAN = "boolean"
    CATEGORICAL = "categorical"
    PHONE = "phone"
    NAME = "name"
    ADDRESS = "address"


class TemporalClass(Enum):
    """Drives Layer-5 strategy selection (§7.2): recency applies only to
    temporal-mutable attributes."""

    IMMUTABLE = "immutable"  # DOB: time-invariant, recency is meaningless
    MUTABLE = "mutable"  # address, status: latest true value wins
    HIERARCHICAL = "hierarchical"  # geo/taxonomy: specificity lattice applies


@dataclass
class ConceptContract:
    concept_id: str  # e.g. "person.dob"
    datatype: Datatype
    multiplicity: int = 1  # 1 = single-valued; >1 or -1 (unbounded) = multi
    temporal_class: TemporalClass = TemporalClass.IMMUTABLE
    canonical_unit: str | None = None
    domain: list[str] = field(default_factory=list)  # closed categorical domain
    sensitivity: str = "normal"  # "pii" enables ERASED handling
    high_stakes: bool = False  # routes contested values to Bayesian discovery
    validators: list[Callable[[object], bool]] = field(default_factory=list)

    @property
    def multi_valued(self) -> bool:
        return self.multiplicity != 1
