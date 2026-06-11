"""Full-pipeline test on the canonical three-source collision corpus
(FILE_1 §3.2): one person, three systems, every field in conflict."""
import hashlib
import json

import pytest

from schemapilot.contracts.confidence import CertificationTier
from schemapilot.contracts.nulls import NullKind, TypedNull
from schemapilot.demo import run_demo
from schemapilot.layer3_standardize.temporal import TemporalValue


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    return run_demo(tmp_path_factory.mktemp("ssot-run"))


@pytest.fixture(scope="module")
def mohammed(result):
    for g in result.golden:
        if len(g.member_record_ids) == 3:
            return g
    raise AssertionError("no 3-member golden entity found")


def test_three_entities_from_seven_records(result):
    assert len(result.records) == 7
    assert len(result.golden) == 3


def test_canonical_collision_resolves_to_one_entity(mohammed):
    systems = {rid.split(":")[0] for rid in mohammed.member_record_ids}
    assert systems == {"crm", "billing", "legacy"}


def test_dob_majority_wins_and_contest_is_escalated(mohammed):
    """CRM(ISO) + Legacy(DMY-decoded) agree on 1985-03-04; Billing's
    transposed 1985-04-03 loses but the contest goes to humans (A5/A7)."""
    dob = mohammed.cells["person.dob"]
    assert isinstance(dob.value, TemporalValue)
    assert dob.value.date_key == "1985-03-04"
    assert dob.winning_strategy == "bayesian_truth_discovery"
    assert dob.escalated
    assert dob.source_set_for == ["crm", "legacy"]
    assert dob.source_set_against == ["billing"]


def test_multiplicity_keeps_both_phones(mohammed):
    """CHAOS-3.2.3: work and personal phone are both true — neither is voted away."""
    phones = mohammed.cells["person.contact.phone"]
    assert phones.winning_strategy == "multiplicity"
    assert phones.value == ["+966501112222", "+966509998888"]


def test_recency_picks_current_address_and_status(mohammed):
    assert mohammed.cells["person.address"].value == "Jeddah, Corniche Rd."
    assert mohammed.cells["person.address"].winning_strategy == "recency"
    assert mohammed.cells["person.status"].value == "CHURNED"


def test_name_completeness_survivorship(mohammed):
    name = mohammed.cells["person.name.full"]
    assert name.value == "Mohammed Al-Rashid"
    assert name.winning_strategy == "most_complete_representation"


def test_erased_phone_is_never_refilled(result):
    """Sara's billing phone is GDPR-erased; CRM's copy must not resurrect it."""
    sara = next(g for g in result.golden
                if any("C-1002" in str(g.cells.get("person.id", "").value) for _ in [0]))
    phone = sara.cells["person.contact.phone"]
    assert isinstance(phone.value, TypedNull)
    assert phone.value.kind is NullKind.ERASED


def test_sentinel_dob_excised_not_fused(result):
    """Omar's CRM DOB is 1900-01-01 (sentinel): the golden DOB must come from
    legacy's real value, never the sentinel."""
    omar = next(g for g in result.golden
                if any("C-1003" in str(g.cells.get("person.id", "").value) for _ in [0]))
    dob = omar.cells["person.dob"]
    assert isinstance(dob.value, TemporalValue)
    assert dob.value.date_key == "1978-11-02"
    assert dob.source_set_for == ["legacy"]


def test_conflict_ledger_preserves_every_loser(result):
    entries = {(e.concept_id, e.losing_value) for e in result.ledger}
    assert ("person.dob", "1985-04-03") in entries
    assert ("person.status", "ACTIVE") in entries
    assert ("person.name.full", "محمد الراشد") in entries


def test_crosswalk_covers_every_source_record(result):
    import polars as pl

    crosswalk = pl.read_parquet(result.artifact_dir / "identity_crosswalk.parquet")
    assert crosswalk.height == 7
    assert crosswalk["entity_id"].null_count() == 0
    assert set(crosswalk["source_system_id"].unique()) == {"crm", "billing", "legacy"}


def test_four_lineage_questions_answerable(result, mohammed):
    """§9.2: every certified value answers where-from, what-was-done,
    who-disagreed, how-sure."""
    lineage = json.loads((result.artifact_dir / "lineage_graph.json").read_text())
    dob_refs = lineage[mohammed.cluster_id]["person.dob"]
    assert dob_refs, "where did you come from"
    assert all("source_file_id" in ref for ref in dob_refs)
    transforms = [r["transform"] for ref in dob_refs for r in ref["records"]]
    assert "temporal_decode" in transforms, "what was done to you"
    dob = mohammed.cells["person.dob"]
    assert dob.source_set_against, "who disagreed"
    assert 0.0 < dob.confidence_posterior < 1.0, "how sure are we"


def test_trust_certificate_contents(result):
    cert = json.loads((result.artifact_dir / "trust_certificate.json").read_text())
    assert cert["entities"] == 3
    assert cert["source_records"] == 7
    assert cert["policy_version"] == "policy-v1"
    assert cert["reconciliation"]["delta"] == 0
    assert sum(cert["tier_census"].values()) == cert["cells"]


def test_no_cell_silently_dropped(result):
    """A1: every tier is represented or at least every cell has a tier."""
    for cluster_id, cells in result.certified.items():
        for concept_id, cert in cells.items():
            assert isinstance(cert.tier, CertificationTier)


def test_determinism_byte_identical_reruns(tmp_path):
    """A8: identical inputs -> byte-identical SSOT artifacts."""
    r1 = run_demo(tmp_path / "a")
    r2 = run_demo(tmp_path / "b")

    def digest(root):
        out = {}
        for p in sorted(root.iterdir()):
            out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
        return out

    assert digest(r1.artifact_dir) == digest(r2.artifact_dir)


def test_adjudication_queue_ranked_and_persisted(result):
    ranked = result.queue.ranked()
    assert ranked, "the DOB contest must be queued"
    priorities = [i.priority for i in ranked]
    assert priorities == sorted(priorities, reverse=True)
    assert any(i.kind == "fusion" and "person.dob" in i.question for i in ranked)
