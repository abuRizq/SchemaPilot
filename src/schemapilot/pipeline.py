"""Pipeline orchestration: L0 → L6 with both feedback loops (FILE_2 §1).

Determinism (A8): seeds are pinned, iteration orders are sorted, and the run
timestamp is derived from the inputs — identical inputs yield byte-identical
SSOT output. Policy version is stamped into every output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from schemapilot.adjudication import AdjudicationItem, AdjudicationQueue
from schemapilot.contracts.concept import ConceptContract
from schemapilot.contracts.manifest import ChaosManifest
from schemapilot.contracts.policy import DEFAULT_POLICY, Policy
from schemapilot.layer0_ingestion.connectors import SourceDeclaration, StagedSource, ingest_csv
from schemapilot.layer0_ingestion.drift import DriftMonitor, SchemaDriftEvent
from schemapilot.layer0_ingestion.vault import RawVault
from schemapilot.layer1_profiling.chaos_scan import scan
from schemapilot.layer1_profiling.fingerprint import ColumnFingerprint, fingerprint_source
from schemapilot.layer2_alignment import Route, align
from schemapilot.layer2_alignment.cco import CCO
from schemapilot.layer3_standardize import standardize
from schemapilot.layer4_resolution import build_records, chimera_veto, classify, cluster as cluster_records, compare, fit_em
from schemapilot.layer4_resolution import blocking as _blocking
from schemapilot.layer5_fusion.conflict import gather
from schemapilot.layer5_fusion.golden import GoldenRecord, LedgerEntry, fuse_cluster
from schemapilot.layer5_fusion.truth_discovery import ReliabilityMatrix
from schemapilot.layer6_certification import (
    certify_record,
    validate_population,
    validate_rows,
    write,
)
from schemapilot.layer6_certification.constraints import reconcile_fanout
from schemapilot.router import RoutingReport, route


@dataclass
class SourceInput:
    data: bytes
    declaration: SourceDeclaration
    batch_id: str
    extraction_timestamp: str | None = None  # pin for byte-identical reruns (A8)


@dataclass
class PipelineResult:
    artifact_dir: Path
    golden: list[GoldenRecord]
    certified: dict[str, dict]
    ledger: list[LedgerEntry]
    drift_events: list[SchemaDriftEvent]
    routing: RoutingReport
    queue: AdjudicationQueue
    manifests: list[ChaosManifest]
    records: list


def run(
    inputs: list[SourceInput],
    cco: CCO,
    out_dir: Path | str,
    *,
    vault_dir: Path | str | None = None,
    policy: Policy = DEFAULT_POLICY,
    reliability: ReliabilityMatrix | None = None,
) -> PipelineResult:
    out_dir = Path(out_dir)
    vault = RawVault(vault_dir or out_dir / "vault")
    drift = DriftMonitor()
    queue = AdjudicationQueue()
    reliability = reliability or _load_priors(out_dir)

    # ---- L0: ingest into the raw vault -------------------------------------
    staged: list[StagedSource] = []
    drift_events: list[SchemaDriftEvent] = []
    for src in inputs:
        s = ingest_csv(
            vault, src.data, src.declaration, src.batch_id,
            extraction_timestamp=src.extraction_timestamp,
        )
        event = drift.check(s.source_system_id, s.columns)
        if event is not None:
            drift_events.append(event)  # routes through re-alignment below, never positional append
        staged.append(s)

    # Determinism: run timestamp derives from inputs, not the wall clock.
    run_timestamp = max(s.envelopes[0].extraction_timestamp for s in staged if s.envelopes)

    # ---- L1: fingerprints + chaos manifests ----------------------------------
    fingerprints: dict[str, dict[str, ColumnFingerprint]] = {}
    manifests: list[ChaosManifest] = []
    for s in staged:
        fps = fingerprint_source(s.columns, s.rows, s.source_file_id)
        fingerprints[s.source_file_id] = fps
        manifests.append(scan(fps, s.source_file_id, sentinel_mass_threshold=policy.sentinel_mass_threshold))
    routing = route(manifests)

    # ---- L2: schema alignment (per source, sharing the evidence corpus) ------
    mapped_fps: dict[str, list[ColumnFingerprint]] = {}
    mappings_per_source: list[dict[str, tuple[str, ConceptContract]]] = []
    mapping_scores: dict[str, float] = {}
    for s in staged:
        fps = fingerprints[s.source_file_id]
        gated = align(s.columns, fps, cco, mapped_fingerprints=mapped_fps, policy=policy)
        mapping: dict[str, tuple[str, ConceptContract]] = {}
        for m in gated:
            if m.route is Route.ADJUDICATE:
                queue.submit(AdjudicationItem(
                    item_id=f"map:{s.source_file_id[:8]}:{m.column}",
                    kind="mapping",
                    question=f"Does column {m.column!r} of {s.source_system_id} map to {m.concept_id}?",
                    uncertainty=1.0 - m.score,
                    impact=0.7,
                    context={"competitors": m.competitors},
                ))
            if m.concept_id is None or m.collapsed_into is not None:
                continue
            mapping[m.column] = (m.concept_id, cco.contract(m.concept_id))
            mapped_fps.setdefault(m.concept_id, []).append(fps[m.column])
            mapping_scores[m.concept_id] = min(mapping_scores.get(m.concept_id, 1.0), m.score)
        mappings_per_source.append(mapping)

    # ---- L3: standardization (A4 ordering inside the driver) ------------------
    standardized = [
        standardize(s, mapping, manifest)
        for s, mapping, manifest in zip(staged, mappings_per_source, manifests)
    ]

    # ---- L4: entity resolution --------------------------------------------------
    records = build_records(standardized)
    pairs = _blocking.candidate_pairs(records, block_size_ceiling=policy.block_size_ceiling)
    vectors = [compare(records, i, j) for i, j in sorted(pairs)]
    model = fit_em(vectors)
    decisions = classify(vectors, model, policy)
    clusters = cluster_records(records, decisions, policy)
    for d in decisions:
        if d.region == "clerical-review":
            queue.submit(AdjudicationItem(
                item_id=f"match:{records[d.i].record_id}|{records[d.j].record_id}",
                kind="match",
                question=f"Are {records[d.i].record_id} and {records[d.j].record_id} the same entity?",
                uncertainty=1.0 - abs(2 * d.probability - 1),
                impact=0.5,
                context={"weight": round(d.weight, 3)},
            ))

    # ---- L5: fusion, with the chimera-veto feedback into L4 (A6) ----------------
    contracts = {cid: cco.contract(cid) for cid in sorted(cco.concepts)}
    rel_flat = {
        s.source_system_id: _flat_reliability(reliability, s.source_system_id)
        for s in staged
    }

    def fuse_all(cluster_list):
        golden_list, ledger_list = [], []
        for c in cluster_list:
            g, l = fuse_cluster(
                c, records, contracts, policy,
                reliability=rel_flat, resolution_timestamp=run_timestamp,
            )
            golden_list.append(g)
            ledger_list.extend(l)
        return golden_list, ledger_list

    golden, ledger = fuse_all(clusters)
    entropy_by_cluster = {g.cluster_id: g.mean_conflict_entropy for g in golden}
    vetoed = chimera_veto(clusters, decisions, entropy_by_cluster, policy)
    if [c.cluster_id for c in vetoed] != [c.cluster_id for c in clusters]:
        clusters = vetoed
        golden, ledger = fuse_all(clusters)  # one bounded re-pass, not a loop
    for g in golden:
        for concept_id, cell in g.cells.items():
            if cell.escalated:
                queue.submit(AdjudicationItem(
                    item_id=f"fuse:{g.cluster_id}:{concept_id}",
                    kind="fusion",
                    question=f"Which value of {concept_id} is true for {g.cluster_id}?",
                    uncertainty=1.0 - cell.confidence_posterior,
                    impact=0.8 if contracts[concept_id].high_stakes else 0.4,
                    context={"entropy": cell.conflict_entropy},
                ))

    # ---- L6: validation, certification, SSOT assembly ----------------------------
    validation = validate_rows(golden)
    population_violations: list[str] = []
    for s in staged:
        population_violations.extend(
            validate_population(fingerprints[s.source_file_id], policy)
        )
    cluster_of_record: dict[str, str] = {}
    for c in clusters:
        for i in c.members:
            cluster_of_record[records[i].record_id] = c.cluster_id
    fanout = reconcile_fanout(len(records), len(cluster_of_record))
    if fanout:
        population_violations.append(fanout)

    certified = {
        g.cluster_id: certify_record(g, mapping_scores, validation) for g in golden
    }

    # Feedback loop 2: certified outcomes update reliability priors per domain.
    _update_reliability(reliability, golden, contracts)

    artifact = write(
        out_dir / "ssot",
        golden=golden,
        certified=certified,
        ledger=ledger,
        records=records,
        cluster_of_record=cluster_of_record,
        reliability=reliability,
        policy=policy,
        run_timestamp=run_timestamp,
        population_violations=population_violations,
        open_escalations=queue.open_count,
    )
    queue.save(out_dir / "adjudication_queue.json")
    return PipelineResult(
        artifact_dir=artifact.root,
        golden=golden,
        certified=certified,
        ledger=ledger,
        drift_events=drift_events,
        routing=routing,
        queue=queue,
        manifests=manifests,
        records=records,
    )


def _flat_reliability(matrix: ReliabilityMatrix, source: str) -> float:
    domains = [v for (s, _), v in matrix.values.items() if s == source]
    return sum(domains) / len(domains) if domains else 0.8


def _load_priors(out_dir: Path) -> ReliabilityMatrix:
    import json

    path = out_dir / "ssot" / "reliability_priors.json"
    if path.exists():
        return ReliabilityMatrix.from_dict(json.loads(path.read_text()))
    return ReliabilityMatrix()


def _update_reliability(
    reliability: ReliabilityMatrix,
    golden: list[GoldenRecord],
    contracts: dict[str, ConceptContract],
) -> None:
    """Agreement rate with discovered truth, per (source, domain) (§7.4)."""
    tally: dict[tuple[str, str], list[int]] = {}
    for g in golden:
        for concept_id, cell in g.cells.items():
            domain = concept_id.split(".")[0]
            for s in cell.source_set_for:
                tally.setdefault((s, domain), []).append(1)
            for s in cell.source_set_against:
                tally.setdefault((s, domain), []).append(0)
    for (source, domain), outcomes in sorted(tally.items()):
        reliability.update(source, domain, sum(outcomes) / len(outcomes))
