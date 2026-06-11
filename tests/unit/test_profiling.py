"""Unit tests for Layer-1 sketches, fingerprints, and the chaos pre-scan."""
from schemapilot.layer1_profiling import CountMinSketch, QuantileSketch, fingerprint_source, scan
from schemapilot.layer1_profiling.sketches import new_minhash


def test_cms_heavy_hitters_find_sentinel_mass():
    """CHAOS-1.4.2: a sentinel holding 10%+ mass is self-incriminating."""
    cms = CountMinSketch()
    for i in range(900):
        cms.add(str(i))
    for _ in range(100):
        cms.add("9999")
    hitters = dict(cms.heavy_hitters(0.05))
    assert "9999" in hitters
    assert 0.08 < hitters["9999"] < 0.15


def test_quantile_sketch_accuracy():
    qs = QuantileSketch()
    for i in range(10_000):
        qs.add(float(i))
    assert abs(qs.quantile(0.5) - 5000) < 200
    assert abs(qs.quantile(0.99) - 9900) < 200


def test_minhash_is_seed_pinned_deterministic():
    a, b = new_minhash(), new_minhash()
    for token in ("x", "y", "z"):
        a.update(token.encode())
        b.update(token.encode())
    assert a.jaccard(b) == 1.0


def test_fingerprint_type_vector_and_scan_findings():
    columns = ["id", "dob", "amount", "email"]
    rows = [
        {"id": "001", "dob": "03/04/2024", "amount": "9999", "email": "a@x.com"},
        {"id": "002", "dob": "13/04/2024", "amount": "42", "email": "b@x.com"},
        {"id": "003", "dob": "1900-01-01", "amount": "9999", "email": "c@x.com"},
    ]
    fps = fingerprint_source(columns, rows, "f")
    assert fps["id"].leading_zero_seen
    assert fps["email"].dominant_type() == "free_text"
    manifest = scan(fps, "f")
    found = {f.chaos_id for f in manifest.findings}
    assert {"CHAOS-1.4.9", "CHAOS-2.1.1", "CHAOS-2.1.7", "CHAOS-1.4.2"} <= found
    assert manifest.path_for("dob").value == "DEEP"
