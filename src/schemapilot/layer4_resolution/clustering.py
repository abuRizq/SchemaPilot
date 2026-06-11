"""Stage 4 — Graph clustering & the chimera guards (FILE_2 §6.4).

Naive transitive closure is forbidden — it is the formal mechanism of chimera
manufacture (A↔B 0.9, B↔C 0.9, A↔C 0.05 ⇒ closure welds A and C). Instead:
average-linkage agglomerative clustering with super-threshold merges (A5),
hard cannot-link constraints on conflicting high-trust identifiers, the
conflict-entropy veto (the A6 feedback loop), and per-cluster stability scores.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from schemapilot.contracts.policy import Policy
from schemapilot.layer4_resolution.fellegi_sunter import Decision
from schemapilot.layer4_resolution.records import Record


@dataclass
class Cluster:
    cluster_id: str
    members: list[int]
    stability: float
    min_internal_edge: float
    edge_density: float
    veto_split: bool = False  # set when the chimera veto re-split this cluster


def cannot_link_pairs(records: list[Record]) -> set[tuple[int, int]]:
    """Hard constraints (§6.4.2): same source system asserting two distinct
    primary keys can never share a cluster (sources are presumed internally
    deduplicated) — the structural answer to CHAOS-3.3.3 ID collisions."""
    out: set[tuple[int, int]] = set()
    by_source: dict[str, list[int]] = {}
    for idx, r in enumerate(records):
        by_source.setdefault(r.source_system_id, []).append(idx)
    for indices in by_source.values():
        for ai in range(len(indices)):
            for bi in range(ai + 1, len(indices)):
                i, j = indices[ai], indices[bi]
                ki, kj = records[i].match_key("person.id"), records[j].match_key("person.id")
                if ki and kj and ki != kj:
                    out.add((min(i, j), max(i, j)))
    return out


def cluster(
    records: list[Record],
    decisions: list[Decision],
    policy: Policy,
) -> list[Cluster]:
    cannot = cannot_link_pairs(records)
    graph = nx.Graph()
    graph.add_nodes_from(range(len(records)))
    for d in decisions:
        if d.region == "auto-link" and (d.i, d.j) not in cannot:
            graph.add_edge(d.i, d.j, weight=d.probability)

    clusters = _agglomerate(graph, cannot, policy)
    return [_finalize(c, graph, idx) for idx, c in enumerate(clusters)]


def _agglomerate(
    graph: nx.Graph, cannot: set[tuple[int, int]], policy: Policy
) -> list[set[int]]:
    """Average-linkage agglomerative clustering: merge the best pair of
    clusters whose average inter-cluster link is super-threshold (A5) and
    which violates no cannot-link; clusters must be internally dense, never
    merely chained."""
    clusters: list[set[int]] = [{n} for n in sorted(graph.nodes)]
    while True:
        best: tuple[float, int, int] | None = None
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                link = _average_link(graph, clusters[a], clusters[b])
                if link is None or link < policy.merge_threshold:
                    continue
                if _violates(clusters[a], clusters[b], cannot):
                    continue
                if best is None or link > best[0]:
                    best = (link, a, b)
        if best is None:
            return clusters
        _, a, b = best
        clusters[a] |= clusters[b]
        del clusters[b]


def _average_link(graph: nx.Graph, ca: set[int], cb: set[int]) -> float | None:
    weights = [
        graph[u][v]["weight"] for u in ca for v in cb if graph.has_edge(u, v)
    ]
    if not weights:
        return None
    # Average over *observed* links, discounted by missing-link coverage —
    # a single strong chain edge cannot weld two large groups.
    coverage = len(weights) / (len(ca) * len(cb))
    return (sum(weights) / len(weights)) * (0.5 + 0.5 * coverage)


def _violates(ca: set[int], cb: set[int], cannot: set[tuple[int, int]]) -> bool:
    return any((min(u, v), max(u, v)) in cannot for u in ca for v in cb)


def _finalize(members: set[int], graph: nx.Graph, idx: int, *, veto_split: bool = False) -> Cluster:
    nodes = sorted(members)
    internal = [
        graph[u][v]["weight"] for ui, u in enumerate(nodes) for v in nodes[ui + 1:]
        if graph.has_edge(u, v)
    ]
    possible = len(nodes) * (len(nodes) - 1) / 2
    density = len(internal) / possible if possible else 1.0
    min_edge = min(internal) if internal else 1.0
    stability = min_edge * (0.5 + 0.5 * density) if len(nodes) > 1 else 1.0
    return Cluster(
        cluster_id=f"E{idx:06d}",
        members=nodes,
        stability=round(stability, 4),
        min_internal_edge=round(min_edge, 4),
        edge_density=round(density, 4),
        veto_split=veto_split,
    )


def chimera_veto(
    clusters: list[Cluster],
    decisions: list[Decision],
    entropy_by_cluster: dict[str, float],
    policy: Policy,
) -> list[Cluster]:
    """The A6 feedback loop (§6.4.3): a cluster whose members disagree on
    nearly everything is statistically a false merge (CHAOS-3.2.7) — re-split
    along its weakest internal edges and flag for review. The conflict
    resolver polices the entity resolver."""
    weight_of = {(d.i, d.j): d.probability for d in decisions}
    out: list[Cluster] = []
    next_idx = len(clusters)
    for c in clusters:
        entropy = entropy_by_cluster.get(c.cluster_id, 0.0)
        if entropy < policy.chimera_entropy_threshold or len(c.members) < 2:
            out.append(c)
            continue
        # Re-split: remove weakest internal edges until the cluster actually
        # disconnects — a chained chimera (strong A-B, strong B-C, weak A-C)
        # must break at its weakest cut, not merely shed its weakest edge.
        sub = nx.Graph()
        sub.add_nodes_from(c.members)
        edges = sorted(
            (weight_of.get((min(u, v), max(u, v)), 0.0), u, v)
            for ui, u in enumerate(c.members) for v in c.members[ui + 1:]
            if (min(u, v), max(u, v)) in weight_of
        )
        for w, u, v in edges:
            sub.add_edge(u, v, weight=w)
        for w, u, v in edges:  # ascending: weakest first
            if nx.number_connected_components(sub) > 1:
                break
            sub.remove_edge(u, v)
        for component in nx.connected_components(sub):
            out.append(_finalize(component, sub, next_idx, veto_split=True))
            next_idx += 1
    return out
