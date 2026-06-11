"""Sublinear sketches for one-pass profiling (FILE_2 §3).

HLL and KMV/MinHash come from datasketch with pinned seeds (A8); Count-Min
Sketch and a quantile sketch are implemented here so their behavior is
deterministic and auditable.
"""
from __future__ import annotations

import hashlib
import math

from datasketch import HyperLogLogPlusPlus, MinHash

PINNED_SEED = 1729  # A8: all stochastic components pinned
_MINHASH_PERMS = 128


def _hash64(value: str, salt: int) -> int:
    h = hashlib.blake2b(value.encode("utf-8"), digest_size=8, salt=salt.to_bytes(8, "little"))
    return int.from_bytes(h.digest(), "little")


class CountMinSketch:
    """Frequency estimation with heavy-hitter tracking (sentinel discovery,
    CHAOS-1.4.2: a numeric column where 9999 holds 11% mass is self-incriminating).
    """

    def __init__(self, width: int = 2048, depth: int = 4, top_k: int = 32):
        self.width = width
        self.depth = depth
        self.table = [[0] * width for _ in range(depth)]
        self.total = 0
        self.top_k = top_k
        self._heavy: dict[str, int] = {}

    def add(self, value: str) -> None:
        self.total += 1
        for d in range(self.depth):
            self.table[d][_hash64(value, d) % self.width] += 1
        est = self.estimate(value)
        self._heavy[value] = est
        if len(self._heavy) > self.top_k * 4:
            keep = sorted(self._heavy.items(), key=lambda kv: (-kv[1], kv[0]))[: self.top_k]
            self._heavy = dict(keep)

    def estimate(self, value: str) -> int:
        return min(self.table[d][_hash64(value, d) % self.width] for d in range(self.depth))

    def heavy_hitters(self, min_mass: float = 0.01) -> list[tuple[str, float]]:
        """(value, mass) pairs holding at least min_mass of total frequency."""
        if self.total == 0:
            return []
        out = [
            (v, self.estimate(v) / self.total)
            for v in self._heavy
            if self.estimate(v) / self.total >= min_mass
        ]
        return sorted(out, key=lambda kv: (-kv[1], kv[0]))[: self.top_k]


class QuantileSketch:
    """Simple deterministic quantile sketch (t-digest stand-in).

    Stores a bounded reservoir of sorted values with deterministic decimation —
    adequate for the distribution-similarity and range-plausibility uses in
    §3/§4.3; swap for a true t-digest at tier-1 scale.
    """

    def __init__(self, capacity: int = 4096):
        self.capacity = capacity
        self._values: list[float] = []
        self.count = 0

    def add(self, value: float) -> None:
        self.count += 1
        self._values.append(value)
        if len(self._values) > self.capacity * 2:
            self._values.sort()
            self._values = self._values[::2]  # deterministic decimation

    def quantile(self, q: float) -> float | None:
        if not self._values:
            return None
        values = sorted(self._values)
        idx = min(len(values) - 1, max(0, int(q * (len(values) - 1))))
        return values[idx]

    def ks_distance(self, other: "QuantileSketch", points: int = 21) -> float | None:
        """Kolmogorov–Smirnov-style sup distance over matched quantiles."""
        if not self._values or not other._values:
            return None
        a, b = sorted(self._values), sorted(other._values)
        lo = min(a[0], b[0])
        hi = max(a[-1], b[-1])
        if hi == lo:
            return 0.0

        def cdf(values: list[float], x: float) -> float:
            import bisect

            return bisect.bisect_right(values, x) / len(values)

        return max(
            abs(cdf(a, lo + (hi - lo) * i / (points - 1)) - cdf(b, lo + (hi - lo) * i / (points - 1)))
            for i in range(points)
        )


def new_hll() -> HyperLogLogPlusPlus:
    return HyperLogLogPlusPlus(p=12)


def new_minhash() -> MinHash:
    return MinHash(num_perm=_MINHASH_PERMS, seed=PINNED_SEED)


def jaccard_containment(a: MinHash, b: MinHash, a_count: int, b_count: int) -> float:
    """Estimated containment of a in b via MinHash resemblance.

    J = |A∩B| / |A∪B|; containment(A,B) = |A∩B| / |A| ≈ J·(|A|+|B|) / (|A|·(1+J)).
    """
    j = a.jaccard(b)
    if a_count == 0:
        return 0.0
    inter = j * (a_count + b_count) / (1 + j) if j < 1 else min(a_count, b_count)
    return min(1.0, inter / a_count)
