"""Unit tests for the shared data contracts."""
import re

import pytest

from schemapilot.contracts import (
    CHAOS_REGISTRY,
    CertificationTier,
    ChaosManifest,
    Path,
    compose_trust,
    tier_for,
)
from schemapilot.contracts.nulls import NullKind, classify_null


def test_chaos_registry_ids_well_formed():
    assert len(CHAOS_REGISTRY) > 90
    for chaos_id, cls in CHAOS_REGISTRY.items():
        assert re.match(r"^CHAOS-\d\.\d\.\d+$", chaos_id)
        assert cls.risk > 0


def test_trust_composition_is_monotone_weakest_link():
    """A3: no step raises trust above its weakest predecessor."""
    assert compose_trust(0.99, 0.98, 0.97) <= 0.97
    assert compose_trust(0.99, 0.10, 0.99) <= 0.10
    assert compose_trust(0.9) <= 0.9
    # Only adjudication overrides.
    assert compose_trust(0.2, adjudicated=True) == 1.0


def test_tiers_partition_all_output():
    assert tier_for(0.99) is CertificationTier.CERTIFIED
    assert tier_for(0.85) is CertificationTier.STANDARD
    assert tier_for(0.60) is CertificationTier.PROVISIONAL
    assert tier_for(0.10) is CertificationTier.QUARANTINED
    assert tier_for(0.99, validation_passed=False) is CertificationTier.QUARANTINED


def test_null_pantheon_classification():
    """CHAOS-1.4.3/2.4.1: surface forms map to typed semantics."""
    assert classify_null("N/A").kind is NullKind.NOT_APPLICABLE
    assert classify_null("NULL").kind is NullKind.UNKNOWN
    assert classify_null("#REF!").kind is NullKind.UNKNOWN
    assert classify_null("declined").kind is NullKind.REFUSED
    assert classify_null("TBD").kind is NullKind.PENDING
    assert classify_null("").kind is NullKind.UNKNOWN
    assert classify_null("Mohammed") is None  # real values pass through


def test_router_escalation_is_one_way():
    manifest = ChaosManifest("f")
    manifest.escalate("col", Path.DEEP)
    manifest.escalate("col", Path.FAST)  # demotion attempt is ignored
    assert manifest.path_for("col") is Path.DEEP
