"""The dual-grain constraint engine (FILE_2 §9.1).

Row grain: CCO-attached predicates and cross-field coherence. Population
grain: distributional assertions — Benford conformance, default-value mass
ceilings, fan-out reconciliation — because CHAOS-3.4.4 is invisible to
row-level validation. Failures never delete; they grade (A1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from schemapilot.contracts.manifest import ChaosFinding
from schemapilot.contracts.policy import Policy
from schemapilot.layer1_profiling.fingerprint import ColumnFingerprint
from schemapilot.layer3_standardize.temporal import TemporalValue
from schemapilot.layer5_fusion.golden import GoldenRecord

# scipy's chi2 critical value at p=0.01 with 8 dof (Benford digits 1-9).
_BENFORD_CHI2_CRITICAL = 20.09


@dataclass
class ValidationReport:
    row_violations: dict[str, list[str]] = field(default_factory=dict)  # cluster_id -> reasons
    population_violations: list[str] = field(default_factory=list)

    def passed(self, cluster_id: str) -> bool:
        return cluster_id not in self.row_violations

    def violation_bitmap(self, cluster_id: str) -> list[str]:
        return self.row_violations.get(cluster_id, [])


def validate_rows(golden: list[GoldenRecord], *, now: datetime | None = None) -> ValidationReport:
    report = ValidationReport()
    now = now or datetime.now(timezone.utc)
    for record in golden:
        reasons: list[str] = []
        dob = record.cells.get("person.dob")
        if dob and isinstance(dob.value, TemporalValue):
            instant = dob.value.instant
            if instant > now:
                reasons.append("CHAOS-3.4.1: DOB in the future")
            if (now - instant).days > 130 * 365:
                reasons.append("CHAOS-3.4.1: age exceeds 130 years")
        status = record.cells.get("person.status")
        if status and isinstance(status.value, str) and status.value not in (
            "ACTIVE", "CHURNED", "SUSPENDED", "CLOSED"
        ):
            reasons.append("CHAOS-2.3.4: status outside closed domain")
        if reasons:
            report.row_violations[record.cluster_id] = reasons
    return report


def validate_population(
    fingerprints: dict[str, ColumnFingerprint],
    policy: Policy,
    *,
    financial_columns: set[str] = frozenset(),
) -> list[str]:
    """Population-grain assertions over source fingerprints."""
    violations: list[str] = []
    for col, fp in sorted(fingerprints.items()):
        hitters = fp.cms.heavy_hitters(policy.default_mass_ceiling)
        if hitters and fp.cardinality > 10:
            value, mass = hitters[0]
            violations.append(
                f"CHAOS-3.4.4: column {col!r} has {mass:.0%} mass at {value!r} (default-value spike)"
            )
        if col in financial_columns:
            chi2 = fp.benford_chi2()
            if chi2 is not None and chi2 > _BENFORD_CHI2_CRITICAL:
                violations.append(
                    f"CHAOS-3.4.4: column {col!r} violates Benford conformance (chi2={chi2:.1f})"
                )
    return violations


def reconcile_fanout(
    source_row_count: int,
    fused_member_count: int,
) -> str | None:
    """Fan-out reconciliation (CHAOS-4.1.1) as arithmetic: every source row
    must be attributed to exactly one entity — Σ members == Σ source rows."""
    if fused_member_count != source_row_count:
        return (
            f"CHAOS-4.1.1: {source_row_count} source rows -> "
            f"{fused_member_count} cluster memberships (fan-out broken)"
        )
    return None
