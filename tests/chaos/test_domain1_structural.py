"""Adversarial regression suite — Domain 1: structural & architectural chaos
(FILE_1 §2.1, operationalized per §10.5)."""
import pytest

from schemapilot.contracts.concept import ConceptContract, Datatype
from schemapilot.layer0_ingestion import DriftMonitor, DuplicateIngestionError
from schemapilot.layer2_alignment import Route, align, seed_person_cco
from schemapilot.layer3_standardize import standardize


def test_chaos_1_3_9_reingestion_blocked_at_the_gate(vault):
    """CHAOS-1.3.9: a byte-identical file re-ingested under a new batch id is
    rejected by the content-addressed vault before it can stuff any ballot."""
    data = b"id,name\n1,Mohammed\n"
    vault.ingest(data, source_system_id="crm", batch_id="b1")
    with pytest.raises(DuplicateIngestionError):
        vault.ingest(data, source_system_id="crm", batch_id="b2")


def test_chaos_1_2_3_middle_column_shear_raises_drift_event():
    """CHAOS-1.2.3: an inserted middle column produces an explicit
    SchemaDriftEvent with positional shift detected — never positional append."""
    monitor = DriftMonitor()
    assert monitor.check("crm", ["id", "name", "phone"]) is None
    event = monitor.check("crm", ["id", "name", "middle_name", "phone"])
    assert event is not None
    assert event.added == {"middle_name"}
    # And a true reorder is flagged as positional shear:
    monitor.check("erp", ["a", "b", "c"])
    shear = monitor.check("erp", ["a", "c", "b"])
    assert shear is not None and shear.positional_shift


def test_chaos_1_4_9_leading_zeros_survive_standardization(staged):
    """CHAOS-1.4.9: id-like columns are contractually string-typed; 00420
    never becomes 420."""
    src, fps, manifest = staged("account\n00420\n00421\n07001\n")
    assert any(f.chaos_id == "CHAOS-1.4.9" for f in manifest.findings_for("account"))
    mapping = {"account": ("person.id", ConceptContract("person.id", Datatype.ID))}
    out = standardize(src, mapping, manifest)
    assert out.rows[0]["person.id"].value == "00420"


def test_chaos_1_1_7_homonym_column_defeated_by_instance_veto(staged):
    """CHAOS-1.1.7: a column labeled 'Name' holding numerics must not map to
    person.name.full — the E2 type veto overrides the perfect label match."""
    src, fps, _ = staged("Name\n42\n77\n91\n13\n")
    mappings = align(src.columns, fps, seed_person_cco())
    name_mapping = next(m for m in mappings if m.column == "Name")
    assert name_mapping.route is Route.UNMAPPED


def test_chaos_1_3_1_duplicate_columns_collapse(staged):
    """CHAOS-1.3.1/1.3.4: two intra-file columns with near-total instance
    overlap mapped to one concept collapse into a single mapping."""
    src, fps, _ = staged(
        "email,email_address\n"
        "a@x.com,a@x.com\nb@x.com,b@x.com\nc@x.com,c@x.com\nd@x.com,d@x.com\n"
    )
    mappings = align(src.columns, fps, seed_person_cco())
    by_col = {m.column: m for m in mappings}
    mapped = [m for m in by_col.values() if m.concept_id == "person.email"]
    assert len(mapped) == 2
    assert sum(1 for m in mapped if m.collapsed_into is not None) == 1


def test_chaos_1_1_6_anonymous_headers_route_deep(staged):
    """CHAOS-1.1.6: positional anonymity (Column1, F2) zeroes label signal and
    routes the column to the DEEP path."""
    _, _, manifest = staged("Column1,F2\nfoo,1\nbar,2\n")
    assert manifest.path_for("Column1").value == "DEEP"
    assert any(f.chaos_id == "CHAOS-1.1.6" for f in manifest.findings_for("Column1"))
