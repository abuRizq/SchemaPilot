"""Golden record assembly & the survivorship output contract (FILE_2 §7.5).

Every golden cell records its full decision context; every losing value lives
in the Conflict Ledger, queryable forever. Hard rules enforced here in code:
ERASED cells are never filled (legal), and no strategy ever fabricates — the
golden value is always an attested source value or a typed null
(CHAOS-4.3.5 imputation laundering is barred at the contract level).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from schemapilot.contracts.concept import ConceptContract
from schemapilot.contracts.nulls import NullKind, TypedNull
from schemapilot.contracts.policy import Policy
from schemapilot.layer4_resolution.clustering import Cluster
from schemapilot.layer4_resolution.records import Record
from schemapilot.layer5_fusion.conflict import ConflictSet, gather
from schemapilot.layer5_fusion.strategies import Resolution, resolve_attribute


class ErasedFillError(Exception):
    """A strategy attempted to fill a GDPR-erased cell — legal violation."""


class FabricationError(Exception):
    """A strategy produced a value no source ever attested."""


@dataclass
class GoldenCell:
    concept_id: str
    value: object  # attested value or TypedNull — never an interpolation
    confidence_posterior: float
    winning_strategy: str
    source_set_for: list[str]
    source_set_against: list[str]
    conflict_entropy: float
    resolution_timestamp: str
    policy_version: str
    escalated: bool = False
    lineage_refs: list[dict] = field(default_factory=list)


@dataclass
class LedgerEntry:
    cluster_id: str
    concept_id: str
    losing_value: str
    sources: list[str]
    record_ids: list[str]
    reason: str
    winning_value: str | None


@dataclass
class GoldenRecord:
    cluster_id: str
    member_record_ids: list[str]
    cluster_stability: float
    cells: dict[str, GoldenCell]
    mean_conflict_entropy: float


def fuse_cluster(
    cluster: Cluster,
    records: list[Record],
    contracts: dict[str, ConceptContract],
    policy: Policy,
    *,
    reliability: dict[str, float] | None = None,
    resolution_timestamp: str,
) -> tuple[GoldenRecord, list[LedgerEntry]]:
    members = [records[i] for i in cluster.members]
    cells: dict[str, GoldenCell] = {}
    ledger: list[LedgerEntry] = []
    entropies: list[float] = []

    for concept_id in sorted(contracts):
        contract = contracts[concept_id]
        cs = gather(cluster.cluster_id, members, concept_id)
        entropy = cs.entropy(reliability)
        if cs.distinct_values > 1:
            entropies.append(entropy)
        resolution = resolve_attribute(cs, contract, policy, reliability=reliability)
        cell, entries = _materialize(
            cluster.cluster_id, concept_id, cs, resolution, entropy, policy,
            stability=cluster.stability, resolution_timestamp=resolution_timestamp,
        )
        if cell is not None:
            cells[concept_id] = cell
        ledger.extend(entries)

    return (
        GoldenRecord(
            cluster_id=cluster.cluster_id,
            member_record_ids=[r.record_id for r in members],
            cluster_stability=cluster.stability,
            cells=cells,
            mean_conflict_entropy=(sum(entropies) / len(entropies)) if entropies else 0.0,
        ),
        ledger,
    )


def _materialize(
    cluster_id: str,
    concept_id: str,
    cs: ConflictSet,
    resolution: Resolution,
    entropy: float,
    policy: Policy,
    *,
    stability: float,
    resolution_timestamp: str,
) -> tuple[GoldenCell | None, list[LedgerEntry]]:
    ledger: list[LedgerEntry] = []

    if resolution.strategy == "erased_bar":
        # Enforce, don't trust: any winner here is a legal violation.
        if resolution.winners:
            raise ErasedFillError(f"{cluster_id}/{concept_id}: ERASED cell would be filled")
        cell = GoldenCell(
            concept_id=concept_id,
            value=TypedNull(NullKind.ERASED),
            confidence_posterior=1.0,
            winning_strategy="erased_bar",
            source_set_for=[],
            source_set_against=[],
            conflict_entropy=entropy,
            resolution_timestamp=resolution_timestamp,
            policy_version=policy.version,
        )
        return cell, ledger

    if not resolution.winners:
        return None, ledger

    # No-fabrication contract: every winner must be an attested group key.
    for w in resolution.winners:
        if w not in cs.groups:
            raise FabricationError(f"{cluster_id}/{concept_id}: unattested value {w!r}")

    winner_key = resolution.winners[0]
    winner_assertions = [a for w in resolution.winners for a in cs.groups[w]]
    losers = {k: v for k, v in cs.groups.items() if k not in resolution.winners}
    for key, assertions in sorted(losers.items()):
        ledger.append(LedgerEntry(
            cluster_id=cluster_id,
            concept_id=concept_id,
            losing_value=assertions[0].surface,
            sources=sorted({a.source_system_id for a in assertions}),
            record_ids=[a.record_id for a in assertions],
            reason=f"lost to {resolution.strategy}",
            winning_value=cs.groups[winner_key][0].surface,
        ))

    if len(resolution.winners) > 1:
        value: object = sorted(
            {str(cs.groups[w][0].cell.value) for w in resolution.winners}
        )
    else:
        value = cs.groups[winner_key][0].cell.value

    cell = GoldenCell(
        concept_id=concept_id,
        value=value,
        confidence_posterior=round(min(resolution.posterior, stability + 0.5), 4),
        winning_strategy=resolution.strategy,
        source_set_for=sorted({a.source_system_id for a in winner_assertions}),
        source_set_against=sorted({a.source_system_id for v in losers.values() for a in v}),
        conflict_entropy=round(entropy, 4),
        resolution_timestamp=resolution_timestamp,
        policy_version=policy.version,
        escalated=resolution.escalate,
        lineage_refs=[a.cell.lineage.to_dict() for a in cs.groups[winner_key]],
    )
    return cell, ledger
