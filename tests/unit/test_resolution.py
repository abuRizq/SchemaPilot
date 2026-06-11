"""Unit tests for Layer-4: EM convergence, decision regions, clustering math."""
from schemapilot.contracts.policy import Policy
from schemapilot.layer4_resolution.comparison import ComparisonVector
from schemapilot.layer4_resolution.fellegi_sunter import classify, fit_em


def _vec(i, j, **features):
    base = {f: None for f in
            ("name", "name_phonetic", "dob", "phone", "email", "address",
             "id_exact", "mother_name")}
    base.update(features)
    return ComparisonVector(i, j, base)


def test_em_separates_matches_from_nonmatches():
    """Synthetic corpus: 10 true pairs (agree nearly everywhere) and 90 noise
    pairs (agree nearly nowhere). EM must learn m >> u for evidential fields."""
    vectors = []
    for k in range(10):
        vectors.append(_vec(k, 100 + k, name=0.95, dob=1.0, phone=1.0, address=0.8))
    for k in range(90):
        vectors.append(_vec(200 + k, 300 + k, name=0.2, dob=0.0, phone=0.0, address=0.1))
    model = fit_em(vectors)
    for field in ("name", "dob", "phone"):
        assert model.m[field] > 0.7
        assert model.u[field] < 0.2
        assert model.m[field] / model.u[field] > 4

    decisions = {(d.i, d.j): d for d in classify(vectors, model, Policy())}
    assert decisions[(0, 100)].region == "auto-link"
    assert decisions[(200, 300)].region == "non-link"


def test_absent_features_contribute_no_weight():
    model = fit_em([])
    sparse = _vec(0, 1)  # everything None
    assert model.weight(sparse) == 0.0
