"""Adversarial regression suite — Domain 4: systemic & emergent chaos
(FILE_1 §2.4): failures that only exist at interaction scale."""
import pytest

from schemapilot.contracts.concept import ConceptContract, Datatype, TemporalClass
from schemapilot.contracts.lineage import LineageChain
from schemapilot.contracts.nulls import NullKind, TypedNull
from schemapilot.contracts.policy import Policy
from schemapilot.layer3_standardize.driver import Cell
from schemapilot.layer5_fusion.conflict import Assertion, ConflictSet
from schemapilot.layer5_fusion.golden import ErasedFillError, _materialize
from schemapilot.layer5_fusion.strategies import Resolution, resolve_attribute
from schemapilot.layer6_certification.constraints import reconcile_fanout


def _assertion(record_id, system, value, asserted=None):
    cell = Cell(value, value, str(value).lower(), False, LineageChain("f", 0, "c"))
    return Assertion(record_id, system, asserted, cell)


def _cs(concept, groups, erased=False):
    cs = ConflictSet(concept, "E000000", erased=erased)
    cs.groups = groups
    return cs


CONTRACT = ConceptContract("person.status", Datatype.CATEGORICAL,
                           temporal_class=TemporalClass.MUTABLE)


class TestBallotStuffing:
    def test_chaos_1_3_9_votes_deduplicate_per_source(self):
        """A source whose extract was loaded three times still casts one vote:
        the wrong value with 3 duplicate assertions loses to two independent
        sources."""
        cs = _cs("person.status", {
            "churned": [
                _assertion("dup:0", "billing", "CHURNED"),
                _assertion("dup:1", "billing", "CHURNED"),
                _assertion("dup:2", "billing", "CHURNED"),
            ],
            "active": [
                _assertion("crm:0", "crm", "ACTIVE"),
                _assertion("legacy:0", "legacy", "ACTIVE"),
            ],
        })
        contract = ConceptContract("person.status", Datatype.CATEGORICAL)
        res = resolve_attribute(cs, contract, Policy())
        assert res.strategy == "weighted_vote"
        assert res.winners == ["active"]

    def test_entropy_is_per_source_not_per_row(self):
        cs = _cs("person.status", {
            "a": [_assertion(f"x:{i}", "billing", "A") for i in range(10)],
            "b": [_assertion("y:0", "crm", "B")],
        })
        # 10 copies vs 1 source = a 1v1 contest, max entropy 1 bit.
        assert cs.entropy() == pytest.approx(1.0)


class TestSentinelPoisonedRecency:
    def test_chaos_2_1_7_recency_rides_envelope_time_not_sentinel_values(self):
        """Sentinel-poisoned recency (FILE_1 §2.4 cascade): last-write-wins
        must key on envelope asserted time; a 9999-12-31 value can't win
        because L3 already excised it to a typed null (absent from groups)."""
        cs = _cs("person.address", {
            "old": [_assertion("a:0", "legacy", "Riyadh", "2019-01-01T00:00:00Z")],
            "new": [_assertion("b:0", "billing", "Jeddah", "2024-06-10T00:00:00Z")],
        })
        contract = ConceptContract("person.address", Datatype.ADDRESS,
                                   temporal_class=TemporalClass.MUTABLE)
        res = resolve_attribute(cs, contract, Policy())
        assert res.strategy == "recency"
        assert res.winners == ["new"]


class TestErasedAndFabrication:
    def test_erased_attribute_is_never_refilled(self):
        """§5.5 legal bar: ERASED blocks fusion even when siblings have values."""
        cs = _cs("person.contact.phone",
                 {"+966555": [_assertion("crm:0", "crm", "+966555")]},
                 erased=True)
        contract = ConceptContract("person.contact.phone", Datatype.PHONE, multiplicity=-1)
        res = resolve_attribute(cs, contract, Policy())
        assert res.strategy == "erased_bar"
        assert res.winners == []

    def test_erased_fill_attempt_raises(self):
        """Defense in depth: a (buggy) strategy returning winners for an
        erased attribute trips ErasedFillError at materialization."""
        cs = _cs("person.contact.phone",
                 {"+966555": [_assertion("crm:0", "crm", "+966555")]},
                 erased=True)
        bad = Resolution("erased_bar", ["+966555"], 1.0)
        with pytest.raises(ErasedFillError):
            _materialize("E000000", "person.contact.phone", cs, bad, 0.0, Policy(),
                         stability=1.0, resolution_timestamp="2024-06-15T00:00:00Z")

    def test_unattested_winner_raises_fabrication_error(self):
        from schemapilot.layer5_fusion.golden import FabricationError

        cs = _cs("person.status", {"active": [_assertion("crm:0", "crm", "ACTIVE")]})
        forged = Resolution("weighted_vote", ["imputed_value"], 0.9)
        with pytest.raises(FabricationError):
            _materialize("E000000", "person.status", cs, forged, 0.0, Policy(),
                         stability=1.0, resolution_timestamp="2024-06-15T00:00:00Z")


class TestAggregateIntegrity:
    def test_chaos_4_1_1_fanout_reconciliation_is_arithmetic(self):
        assert reconcile_fanout(7, 7) is None
        broken = reconcile_fanout(7, 9)
        assert broken is not None and "CHAOS-4.1.1" in broken
