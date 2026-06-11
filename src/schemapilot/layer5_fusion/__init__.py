"""Layer 5 — Multi-source conflict resolution & data fusion (FILE_2 §7)."""
from schemapilot.layer5_fusion.conflict import Assertion, ConflictSet, gather
from schemapilot.layer5_fusion.golden import (
    ErasedFillError,
    FabricationError,
    GoldenCell,
    GoldenRecord,
    LedgerEntry,
    fuse_cluster,
)
from schemapilot.layer5_fusion.strategies import Resolution, resolve_attribute
from schemapilot.layer5_fusion.truth_discovery import ReliabilityMatrix, discover

__all__ = [
    "Assertion",
    "ConflictSet",
    "gather",
    "ErasedFillError",
    "FabricationError",
    "GoldenCell",
    "GoldenRecord",
    "LedgerEntry",
    "fuse_cluster",
    "Resolution",
    "resolve_attribute",
    "ReliabilityMatrix",
    "discover",
]
