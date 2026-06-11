"""Unit tests for Layer-5 strategies and truth discovery."""
from datetime import datetime, timezone

import pytest

from schemapilot.contracts.concept import ConceptContract, Datatype, TemporalClass
from schemapilot.contracts.lineage import LineageChain
from schemapilot.contracts.policy import Policy
from schemapilot.layer3_standardize.driver import Cell
from schemapilot.layer3_standardize.temporal import TemporalInterval, TemporalValue
from schemapilot.layer5_fusion.conflict import Assertion, ConflictSet
from schemapilot.layer5_fusion.strategies import resolve_attribute
from schemapilot.layer5_fusion.truth_discovery import discover


def _assertion(record_id, system, cell_value, key=None, asserted=None):
    cell = Cell(str(cell_value), cell_value, key or str(cell_value).lower(), False,
                LineageChain("f", 0, "c"))
    return Assertion(record_id, system, asserted, cell)


def _cs(concept, groups):
    cs = ConflictSet(concept, "E0")
    cs.groups = groups
    return cs


def test_cross_source_disambiguation_collapses_interval():
    """§5.3 step 5 hand-off: source A's ambiguous 03/04/85 + source B's
    unambiguous ISO date -> the interval collapses to agreement, free win."""
    dt_a = datetime(1985, 4, 3, tzinfo=timezone.utc)
    dt_b = datetime(1985, 3, 4, tzinfo=timezone.utc)
    interval = TemporalInterval(((dt_a, 0.5), (dt_b, 0.5)), "03/04/1985")
    exact = TemporalValue(dt_b, "1985-03-04", None, "ISO")
    cs = _cs("person.dob", {
        "interval:1985-03-04|1985-04-03": [_assertion("a:0", "src_a", interval, key=None)],
        "1985-03-04": [_assertion("b:0", "src_b", exact, key="1985-03-04")],
    })
    contract = ConceptContract("person.dob", Datatype.DATE)
    res = resolve_attribute(cs, contract, Policy())
    assert res.strategy == "cross_source_disambiguation"
    assert res.winners == ["1985-03-04"]
    assert res.posterior > 0.9  # two corroborating sources


def test_specificity_lattice_consistent_subsumption():
    cs = _cs("geo", {
        "riyadh olaya st": [_assertion("a:0", "a", "Riyadh Olaya St")],
        "riyadh": [_assertion("b:0", "b", "Riyadh")],
    })
    contract = ConceptContract("geo", Datatype.ADDRESS,
                               temporal_class=TemporalClass.HIERARCHICAL)
    res = resolve_attribute(cs, contract, Policy())
    assert res.strategy == "specificity_lattice"
    assert res.winners == ["riyadh olaya st"]


def test_specificity_lattice_rejects_inconsistent_values():
    cs = _cs("geo", {
        "riyadh olaya st": [_assertion("a:0", "a", "Riyadh Olaya St")],
        "jeddah": [_assertion("b:0", "b", "Jeddah")],
    })
    contract = ConceptContract("geo", Datatype.ADDRESS,
                               temporal_class=TemporalClass.HIERARCHICAL)
    res = resolve_attribute(cs, contract, Policy())
    assert res.strategy == "weighted_vote"  # genuine disagreement, not granularity


def test_recency_requires_asserted_times():
    cs = _cs("person.status", {
        "active": [_assertion("a:0", "a", "ACTIVE")],
        "churned": [_assertion("b:0", "b", "CHURNED")],
    })
    contract = ConceptContract("person.status", Datatype.CATEGORICAL,
                               temporal_class=TemporalClass.MUTABLE)
    res = resolve_attribute(cs, contract, Policy())
    assert res.strategy == "weighted_vote"  # no envelope times -> fallback


def test_truth_discovery_majority_with_reliability():
    result = discover({
        "1985-03-04": {"crm", "legacy"},
        "1985-04-03": {"billing"},
    })
    assert result.posteriors["1985-03-04"] > result.posteriors["1985-04-03"]
    assert result.reliability["crm"] > result.reliability["billing"]


def test_truth_discovery_copy_discount_weakens_copiers():
    independent = discover({"v1": {"a", "b"}, "v2": {"c"}})
    discounted = discover({"v1": {"a", "b"}, "v2": {"c"}},
                          copy_discount={"b": 0.9})
    assert discounted.posteriors["v1"] < independent.posteriors["v1"]
