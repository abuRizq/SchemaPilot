"""The SSOT artifact — the five-part certified output (FILE_2 §9.2):

Golden Entity Store + Identity Crosswalk (bitemporal) + Conflict Ledger +
Lineage Graph + Trust Certificate. Every value can answer: where did you come
from, what was done to you, who disagreed, and how sure are we.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from schemapilot.contracts.confidence import CertificationTier
from schemapilot.contracts.nulls import TypedNull
from schemapilot.contracts.policy import Policy
from schemapilot.layer3_standardize.temporal import TemporalInterval, TemporalValue
from schemapilot.layer4_resolution.records import Record
from schemapilot.layer5_fusion.golden import GoldenRecord, LedgerEntry
from schemapilot.layer5_fusion.truth_discovery import ReliabilityMatrix
from schemapilot.layer6_certification.trust import CertifiedCell


def _render(value: object) -> str:
    if isinstance(value, TemporalValue):
        return value.instant.isoformat()
    if isinstance(value, TemporalInterval):
        return "interval:" + "|".join(
            f"{c.date().isoformat()}@{p:.2f}" for c, p in value.candidates
        )
    if isinstance(value, TypedNull):
        return str(value)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


@dataclass
class SSOTArtifact:
    root: Path

    @property
    def golden_path(self) -> Path:
        return self.root / "golden_entities.parquet"

    @property
    def crosswalk_path(self) -> Path:
        return self.root / "identity_crosswalk.parquet"

    @property
    def ledger_path(self) -> Path:
        return self.root / "conflict_ledger.parquet"

    @property
    def lineage_path(self) -> Path:
        return self.root / "lineage_graph.json"

    @property
    def certificate_path(self) -> Path:
        return self.root / "trust_certificate.json"

    @property
    def reliability_path(self) -> Path:
        return self.root / "reliability_priors.json"


def write(
    out_dir: Path | str,
    *,
    golden: list[GoldenRecord],
    certified: dict[str, dict[str, CertifiedCell]],  # cluster_id -> concept -> cell
    ledger: list[LedgerEntry],
    records: list[Record],
    cluster_of_record: dict[str, str],
    reliability: ReliabilityMatrix,
    policy: Policy,
    run_timestamp: str,
    population_violations: list[str],
    open_escalations: int,
) -> SSOTArtifact:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    artifact = SSOTArtifact(root)

    # ① Golden Entity Store — one row per (entity, attribute).
    golden_rows = []
    for record in sorted(golden, key=lambda g: g.cluster_id):
        for concept_id, cert in sorted(certified.get(record.cluster_id, {}).items()):
            cell = cert.cell
            golden_rows.append({
                "entity_id": record.cluster_id,
                "concept_id": concept_id,
                "value": _render(cell.value),
                "confidence": cert.trust,
                "tier": cert.tier.value,
                "strategy": cell.winning_strategy,
                "sources_for": ",".join(cell.source_set_for),
                "sources_against": ",".join(cell.source_set_against),
                "conflict_entropy": cell.conflict_entropy,
                "escalated": cell.escalated,
                "policy_version": cell.policy_version,
                "resolved_at": cell.resolution_timestamp,
            })
    pl.DataFrame(golden_rows).write_parquet(artifact.golden_path)

    # ② Identity Crosswalk — bitemporal: valid-time (source asserted) +
    # knowledge-time (this run).
    crosswalk_rows = [
        {
            "source_system_id": r.source_system_id,
            "source_record_id": r.record_id,
            "source_natural_key": r.match_key("person.id") or "",
            "entity_id": cluster_of_record.get(r.record_id, ""),
            "valid_from": r.source_asserted_time or "",
            "known_at": run_timestamp,
        }
        for r in sorted(records, key=lambda r: r.record_id)
    ]
    pl.DataFrame(crosswalk_rows).write_parquet(artifact.crosswalk_path)

    # ③ Conflict Ledger — every losing value, queryable forever.
    ledger_rows = [
        {
            "entity_id": e.cluster_id,
            "concept_id": e.concept_id,
            "losing_value": e.losing_value,
            "winning_value": e.winning_value or "",
            "sources": ",".join(e.sources),
            "record_ids": ",".join(e.record_ids),
            "reason": e.reason,
        }
        for e in sorted(ledger, key=lambda e: (e.cluster_id, e.concept_id, e.losing_value))
    ]
    pl.DataFrame(
        ledger_rows,
        schema={
            "entity_id": pl.Utf8, "concept_id": pl.Utf8, "losing_value": pl.Utf8,
            "winning_value": pl.Utf8, "sources": pl.Utf8, "record_ids": pl.Utf8,
            "reason": pl.Utf8,
        },
    ).write_parquet(artifact.ledger_path)

    # ④ Lineage Graph — cell-level: golden value -> transform chain -> vault bytes.
    lineage = {
        record.cluster_id: {
            concept_id: cert.cell.lineage_refs
            for concept_id, cert in sorted(certified.get(record.cluster_id, {}).items())
        }
        for record in sorted(golden, key=lambda g: g.cluster_id)
    }
    artifact.lineage_path.write_text(json.dumps(lineage, indent=2, sort_keys=True, ensure_ascii=False))

    # ⑤ Trust Certificate — the contract with the consumer.
    tier_census: dict[str, int] = {}
    for cells in certified.values():
        for cert in cells.values():
            tier_census[cert.tier.value] = tier_census.get(cert.tier.value, 0) + 1
    total_cells = sum(tier_census.values()) or 1
    certificate = {
        "run_timestamp": run_timestamp,
        "policy_version": policy.version,
        "entities": len(golden),
        "source_records": len(records),
        "cells": total_cells,
        "tier_census": dict(sorted(tier_census.items())),
        "certified_fraction": round(tier_census.get(CertificationTier.CERTIFIED.value, 0) / total_cells, 4),
        "open_escalations": open_escalations,
        "population_violations": population_violations,
        "reconciliation": {
            "source_rows": len(records),
            "crosswalk_rows": len(crosswalk_rows),
            "delta": len(records) - len(crosswalk_rows),
        },
    }
    artifact.certificate_path.write_text(json.dumps(certificate, indent=2, sort_keys=True))

    # Reliability priors feed back into the next run (§7.4 / §1 feedback loop 2).
    artifact.reliability_path.write_text(json.dumps(reliability.to_dict(), indent=2, sort_keys=True))
    return artifact
