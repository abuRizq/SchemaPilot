"""Stage 1 — Blocking & indexing (FILE_2 §6.1): defeat O(n²) with multiple
redundant passes in union — a true pair need survive only one. Block-size
governance recursively sub-blocks heavy-hitter keys.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from datasketch import MinHash, MinHashLSH

from schemapilot.layer4_resolution.phonetic import name_phonetic_keys
from schemapilot.layer4_resolution.records import Record
from schemapilot.layer1_profiling.sketches import PINNED_SEED

NAME_CONCEPT = "person.name.full"
PHONE_CONCEPT = "person.contact.phone"
EMAIL_CONCEPT = "person.email"
DOB_CONCEPT = "person.dob"


def candidate_pairs(
    records: list[Record],
    *,
    block_size_ceiling: int = 500,
    lsh_threshold: float = 0.4,
    window: int = 5,
) -> set[tuple[int, int]]:
    """Union of all blocking passes; pairs are (i, j) indices with i < j."""
    pairs: set[tuple[int, int]] = set()
    pairs |= _exact_key_pass(records, block_size_ceiling)
    pairs |= _sorted_neighborhood_pass(records, window)
    pairs |= _lsh_pass(records, lsh_threshold)
    pairs |= _phonetic_pass(records, block_size_ceiling)
    return pairs


def _emit_block(indices: list[int], pairs: set, ceiling: int, records: list[Record], depth: int = 0) -> None:
    if len(indices) <= 1:
        return
    if len(indices) > ceiling and depth < 3:
        # Block-size governance: recursively sub-block on secondary keys
        # (DOB year, then phone) to tame heavy hitters like surname محمد.
        secondary: dict[str, list[int]] = defaultdict(list)
        key_concepts = [DOB_CONCEPT, PHONE_CONCEPT, NAME_CONCEPT][depth:]
        concept = key_concepts[0] if key_concepts else None
        for i in indices:
            k = records[i].match_key(concept) if concept else None
            secondary[k or f"_none_{i}"].append(i)
        for sub in secondary.values():
            _emit_block(sub, pairs, ceiling, records, depth + 1)
        return
    for i, j in combinations(sorted(indices), 2):
        pairs.add((i, j))


def _exact_key_pass(records: list[Record], ceiling: int) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for concept in (PHONE_CONCEPT, EMAIL_CONCEPT):
        blocks: dict[str, list[int]] = defaultdict(list)
        for i, r in enumerate(records):
            key = r.match_key(concept)
            if key:
                blocks[key].append(i)
        for indices in blocks.values():
            _emit_block(indices, pairs, ceiling, records)
    return pairs


def _sorted_neighborhood_pass(records: list[Record], window: int) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    # Two rotated composite keys catch near-boundary variants.
    for key_fn in (
        lambda r: (r.match_key(NAME_CONCEPT) or "~", r.match_key(DOB_CONCEPT) or "~"),
        lambda r: (r.match_key(DOB_CONCEPT) or "~", r.match_key(NAME_CONCEPT) or "~"),
    ):
        order = sorted(range(len(records)), key=lambda i: key_fn(records[i]))
        for pos in range(len(order)):
            for ahead in range(1, window):
                if pos + ahead < len(order):
                    i, j = order[pos], order[pos + ahead]
                    pairs.add((min(i, j), max(i, j)))
    return pairs


def _lsh_pass(records: list[Record], threshold: float) -> set[tuple[int, int]]:
    """MinHash banding over name token sets: token reorderings and missing
    tokens (CHAOS-3.1.4) collide with probability ≈ 1 - (1 - t^r)^b."""
    lsh = MinHashLSH(threshold=threshold, num_perm=64)
    hashes: dict[int, MinHash] = {}
    for i, r in enumerate(records):
        name = r.match_key(NAME_CONCEPT)
        if not name:
            continue
        mh = MinHash(num_perm=64, seed=PINNED_SEED)
        for token in name.split():
            mh.update(token.encode("utf-8"))
        hashes[i] = mh
        lsh.insert(str(i), mh)
    pairs: set[tuple[int, int]] = set()
    for i, mh in hashes.items():
        for hit in lsh.query(mh):
            j = int(hit)
            if i != j:
                pairs.add((min(i, j), max(i, j)))
    return pairs


def _phonetic_pass(records: list[Record], ceiling: int) -> set[tuple[int, int]]:
    """Phonetic-space blocking — the only channel that bridges cross-script
    identity (CHAOS-3.1.2): Mohammed and محمد share a consonant skeleton."""
    blocks: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(records):
        cell = r.cell(NAME_CONCEPT)
        name = cell.value if cell and isinstance(cell.value, str) else None
        if not name:
            continue
        for key in name_phonetic_keys(name):
            blocks[key].append(i)
    pairs: set[tuple[int, int]] = set()
    for indices in blocks.values():
        _emit_block(indices, pairs, ceiling, records)
    return pairs
