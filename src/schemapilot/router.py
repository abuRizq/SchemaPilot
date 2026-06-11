"""The Complexity Router (FILE_2 §8) — cost-aware routing on the Chaos
Manifest. Escalation is one-way and evidence-triggered; nothing is demoted
without passing the stricter path's checks. Elegance under simplicity is a
property of routing, not a separate mode.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from schemapilot.contracts.manifest import ChaosManifest, Path


@dataclass
class RoutingReport:
    column_paths: dict[str, Path] = field(default_factory=dict)
    escalations: list[str] = field(default_factory=list)  # mid-flight promotions

    def census(self) -> dict[str, int]:
        out = {p.value: 0 for p in Path}
        for p in self.column_paths.values():
            out[p.value] += 1
        return out


def route(manifests: list[ChaosManifest]) -> RoutingReport:
    report = RoutingReport()
    for manifest in manifests:
        for column, path in manifest.column_paths.items():
            key = f"{manifest.source_file_id[:8]}:{column}"
            report.column_paths[key] = path
    return report


def escalate_midflight(
    report: RoutingReport, manifest: ChaosManifest, column: str, reason: str
) -> None:
    """Tripwire promotion (§8): pattern-census residual, unexpected script
    mass, or post-fusion entropy spike promotes a column mid-flight."""
    manifest.escalate(column, Path.DEEP)
    key = f"{manifest.source_file_id[:8]}:{column}"
    report.column_paths[key] = Path.DEEP
    report.escalations.append(f"{key}: {reason}")
