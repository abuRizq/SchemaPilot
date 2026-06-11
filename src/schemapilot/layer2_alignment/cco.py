"""The Canonical Concept Ontology (FILE_2 §4.1) — a typed graph, not a flat list.

Concept nodes carry datatype/unit/multiplicity contracts; label edges accrete
every attested surface label across languages with provenance, so matching
accuracy is monotonically increasing over the engine's lifetime. Composition
edges make 1:N correspondences (CHAOS-1.1.8) first-class.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from schemapilot.contracts.concept import ConceptContract, Datatype, TemporalClass


@dataclass
class LabelEdge:
    surface: str  # normalized label form
    provenance: str  # "seed" | "adjudication:<id>" | source system
    weight: float = 1.0


@dataclass
class ConceptNode:
    contract: ConceptContract
    labels: list[LabelEdge] = field(default_factory=list)
    composition: list[list[str]] = field(default_factory=list)  # e.g. [["person.name.first","person.name.last"]]
    pattern_library: list[str] = field(default_factory=list)  # attested pattern-census classes


class CCO:
    def __init__(self) -> None:
        self.concepts: dict[str, ConceptNode] = {}

    def add(self, node: ConceptNode) -> None:
        self.concepts[node.contract.concept_id] = node

    def add_label(self, concept_id: str, surface: str, provenance: str, weight: float = 1.0) -> None:
        """Adjudication write-back: the system never asks the same question twice."""
        node = self.concepts[concept_id]
        if not any(e.surface == surface for e in node.labels):
            node.labels.append(LabelEdge(surface, provenance, weight))

    def lookup_label(self, normalized: str) -> list[str]:
        """Exact label-edge match -> candidate concept ids. Edge surfaces are
        compared in the same normalized label space as incoming columns."""
        from schemapilot.layer2_alignment.deterministic import normalize_label

        return sorted(
            cid for cid, node in self.concepts.items()
            if any(normalize_label(e.surface) == normalized for e in node.labels)
        )

    def contract(self, concept_id: str) -> ConceptContract:
        return self.concepts[concept_id].contract

    # ---- persistence (the ontology's memory) -------------------------------
    def save(self, path: Path | str) -> None:
        payload = {
            cid: {
                "datatype": node.contract.datatype.value,
                "multiplicity": node.contract.multiplicity,
                "temporal_class": node.contract.temporal_class.value,
                "domain": node.contract.domain,
                "sensitivity": node.contract.sensitivity,
                "high_stakes": node.contract.high_stakes,
                "labels": [[e.surface, e.provenance, e.weight] for e in node.labels],
                "composition": node.composition,
                "pattern_library": node.pattern_library,
            }
            for cid, node in sorted(self.concepts.items())
        }
        Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path | str) -> "CCO":
        cco = cls()
        for cid, raw in json.loads(Path(path).read_text()).items():
            contract = ConceptContract(
                concept_id=cid,
                datatype=Datatype(raw["datatype"]),
                multiplicity=raw["multiplicity"],
                temporal_class=TemporalClass(raw["temporal_class"]),
                domain=raw["domain"],
                sensitivity=raw["sensitivity"],
                high_stakes=raw["high_stakes"],
            )
            node = ConceptNode(
                contract=contract,
                labels=[LabelEdge(*e) for e in raw["labels"]],
                composition=raw["composition"],
                pattern_library=raw["pattern_library"],
            )
            cco.add(node)
        return cco


def seed_person_cco() -> CCO:
    """A seeded ontology for the person/customer domain used by the demo
    corpus and tests. Label edges include cross-lingual forms (CHAOS-1.1.2)."""
    cco = CCO()

    def concept(cid, dt, labels, *, mult=1, tclass=TemporalClass.IMMUTABLE,
                domain=None, stakes=False, sensitivity="normal", patterns=None):
        node = ConceptNode(
            ConceptContract(cid, dt, multiplicity=mult, temporal_class=tclass,
                            domain=domain or [], high_stakes=stakes, sensitivity=sensitivity),
            labels=[LabelEdge(s, "seed") for s in labels],
            pattern_library=patterns or [],
        )
        cco.add(node)

    concept("person.id", Datatype.ID,
            ["id", "customer id", "cust id", "client id", "record id", "رقم العميل"],
            patterns=["integer", "leading_zero_id"])
    concept("person.name.full", Datatype.NAME,
            ["name", "full name", "customer name", "client name", "الاسم", "اسم العميل",
             "nom", "nombre"],
            patterns=["other"])
    concept("person.name.mother", Datatype.NAME,
            ["mother name", "maternal name", "mothers fullname", "mother full name",
             "اسم الوالدة", "اسم الام", "nom de la mere", "nombre madre", "mth nm", "m name",
             "mothname", "parent2 name"],
            patterns=["other"])
    concept("person.dob", Datatype.DATE,
            ["dob", "date of birth", "birth date", "birthdate", "تاريخ الميلاد"],
            stakes=True,
            patterns=["iso_date", "slash_date", "dash_date"])
    concept("person.contact.phone", Datatype.PHONE,
            ["phone", "mobile", "contact no", "phone number", "tel", "telephone",
             "الهاتف", "الجوال", "رقم الهاتف"],
            mult=-1,  # multi-valued: work + personal both true (CHAOS-3.2.3)
            sensitivity="pii",
            patterns=["phone_like", "integer"])
    concept("person.address", Datatype.ADDRESS,
            ["address", "home address", "addr", "العنوان", "location"],
            tclass=TemporalClass.MUTABLE,
            sensitivity="pii",
            patterns=["other"])
    concept("person.status", Datatype.CATEGORICAL,
            ["status", "customer status", "account status", "الحالة"],
            tclass=TemporalClass.MUTABLE,
            domain=["ACTIVE", "CHURNED", "SUSPENDED", "CLOSED"],
            patterns=["other", "bool_like"])
    concept("person.email", Datatype.STRING,
            ["email", "e mail", "email address", "البريد الالكتروني"],
            sensitivity="pii",
            patterns=["email"])
    concept("txn.amount", Datatype.DECIMAL,
            ["amount", "total", "txn amount", "balance", "المبلغ"],
            patterns=["integer", "decimal_dot", "decimal_comma"])
    return cco
