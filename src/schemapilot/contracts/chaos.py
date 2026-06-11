"""CHAOS taxonomy registry (FILE_1).

Every threat class from THREAT_LANDSCAPE_AND_CHAOS_MAP.md carries a stable
identifier so detections, quarantine reason codes, and the adversarial
regression suite can all cite the same vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ChaosDomain(Enum):
    STRUCTURAL = 1
    SYNTACTIC = 2
    SEMANTIC = 3
    SYSTEMIC = 4


@dataclass(frozen=True)
class ChaosClass:
    chaos_id: str  # e.g. "CHAOS-1.1.7"
    domain: ChaosDomain
    name: str
    likelihood: int = 3  # 1-5
    detectability: int = 3  # 1-5 (5 = loud); risk uses (6 - D)
    blast_radius: int = 3  # 1-5

    @property
    def risk(self) -> int:
        return self.likelihood * (6 - self.detectability) * self.blast_radius


_D = ChaosDomain

REGISTRY: dict[str, ChaosClass] = {
    c.chaos_id: c
    for c in [
        # Domain 1 — Structural
        ChaosClass("CHAOS-1.0.1", _D.STRUCTURAL, "legacy mainframe export artifacts"),
        ChaosClass("CHAOS-1.0.2", _D.STRUCTURAL, "spreadsheet-culture exports"),
        ChaosClass("CHAOS-1.0.3", _D.STRUCTURAL, "acquired-company parallel systems"),
        ChaosClass("CHAOS-1.0.4", _D.STRUCTURAL, "SaaS schema-on-read drift"),
        ChaosClass("CHAOS-1.0.5", _D.STRUCTURAL, "IoT clock/unit drift"),
        ChaosClass("CHAOS-1.0.6", _D.STRUCTURAL, "manual-entry free-text abuse"),
        ChaosClass("CHAOS-1.0.7", _D.STRUCTURAL, "regional locale/calendar silos"),
        ChaosClass("CHAOS-1.1.1", _D.STRUCTURAL, "label synonymy"),
        ChaosClass("CHAOS-1.1.2", _D.STRUCTURAL, "cross-lingual labels"),
        ChaosClass("CHAOS-1.1.3", _D.STRUCTURAL, "abbreviation/truncation"),
        ChaosClass("CHAOS-1.1.4", _D.STRUCTURAL, "case & delimiter drift"),
        ChaosClass("CHAOS-1.1.5", _D.STRUCTURAL, "encoding-mangled headers"),
        ChaosClass("CHAOS-1.1.6", _D.STRUCTURAL, "positional anonymity"),
        ChaosClass("CHAOS-1.1.7", _D.STRUCTURAL, "homonym collision", 3, 1, 4),
        ChaosClass("CHAOS-1.1.8", _D.STRUCTURAL, "composite vs atomic columns"),
        ChaosClass("CHAOS-1.1.9", _D.STRUCTURAL, "unit-embedded labels"),
        ChaosClass("CHAOS-1.2.1", _D.STRUCTURAL, "structural vs value absence conflation"),
        ChaosClass("CHAOS-1.2.2", _D.STRUCTURAL, "exclusive-column orphaning"),
        ChaosClass("CHAOS-1.2.3", _D.STRUCTURAL, "temporal structural drift"),
        ChaosClass("CHAOS-1.2.4", _D.STRUCTURAL, "granularity asymmetry"),
        ChaosClass("CHAOS-1.3.1", _D.STRUCTURAL, "intra-file duplicate columns"),
        ChaosClass("CHAOS-1.3.2", _D.STRUCTURAL, "join-residue columns"),
        ChaosClass("CHAOS-1.3.3", _D.STRUCTURAL, "derived-column shadowing"),
        ChaosClass("CHAOS-1.3.4", _D.STRUCTURAL, "concept duplication under labels"),
        ChaosClass("CHAOS-1.3.5", _D.STRUCTURAL, "exact duplicate rows"),
        ChaosClass("CHAOS-1.3.6", _D.STRUCTURAL, "near duplicate rows"),
        ChaosClass("CHAOS-1.3.7", _D.STRUCTURAL, "fuzzy duplicate rows"),
        ChaosClass("CHAOS-1.3.8", _D.STRUCTURAL, "conflicting duplicate rows"),
        ChaosClass("CHAOS-1.3.9", _D.STRUCTURAL, "cross-batch re-ingestion"),
        ChaosClass("CHAOS-1.3.10", _D.STRUCTURAL, "overlapping extraction windows"),
        ChaosClass("CHAOS-1.4.1", _D.STRUCTURAL, "numeric-as-string contamination"),
        ChaosClass("CHAOS-1.4.2", _D.STRUCTURAL, "sentinel pollution"),
        ChaosClass("CHAOS-1.4.3", _D.STRUCTURAL, "null pantheon surface forms"),
        ChaosClass("CHAOS-1.4.4", _D.STRUCTURAL, "locale-split numerics"),
        ChaosClass("CHAOS-1.4.5", _D.STRUCTURAL, "spreadsheet artifact leakage"),
        ChaosClass("CHAOS-1.4.6", _D.STRUCTURAL, "boolean babel"),
        ChaosClass("CHAOS-1.4.7", _D.STRUCTURAL, "mixed-script digits"),
        ChaosClass("CHAOS-1.4.8", _D.STRUCTURAL, "precision schizophrenia"),
        ChaosClass("CHAOS-1.4.9", _D.STRUCTURAL, "leading-zero amputation"),
        # Domain 2 — Syntactic
        ChaosClass("CHAOS-2.1.1", _D.SYNTACTIC, "date format ambiguity", 5, 1, 3),
        ChaosClass("CHAOS-2.1.2", _D.SYNTACTIC, "two-digit year pivoting"),
        ChaosClass("CHAOS-2.1.3", _D.SYNTACTIC, "epoch unit confusion"),
        ChaosClass("CHAOS-2.1.4", _D.SYNTACTIC, "spreadsheet serial dates"),
        ChaosClass("CHAOS-2.1.5", _D.SYNTACTIC, "calendar system mixing"),
        ChaosClass("CHAOS-2.1.6", _D.SYNTACTIC, "month-name locale"),
        ChaosClass("CHAOS-2.1.7", _D.SYNTACTIC, "sentinel dates", 4, 2, 4),
        ChaosClass("CHAOS-2.1.8", _D.SYNTACTIC, "timezone loss", 4, 1, 3),
        ChaosClass("CHAOS-2.1.9", _D.SYNTACTIC, "clock skew / future dates"),
        ChaosClass("CHAOS-2.2.1", _D.SYNTACTIC, "single mis-decode mojibake", 5, 3, 4),
        ChaosClass("CHAOS-2.2.2", _D.SYNTACTIC, "double encoding"),
        ChaosClass("CHAOS-2.2.3", _D.SYNTACTIC, "replacement-character destruction"),
        ChaosClass("CHAOS-2.2.4", _D.SYNTACTIC, "BOM contamination"),
        ChaosClass("CHAOS-2.2.5", _D.SYNTACTIC, "normalization form divergence"),
        ChaosClass("CHAOS-2.2.6", _D.SYNTACTIC, "confusable/homoglyph substitution"),
        ChaosClass("CHAOS-2.2.7", _D.SYNTACTIC, "invisible character injection"),
        ChaosClass("CHAOS-2.2.8", _D.SYNTACTIC, "bidi scrambling"),
        ChaosClass("CHAOS-2.3.1", _D.SYNTACTIC, "address anti-structure"),
        ChaosClass("CHAOS-2.3.2", _D.SYNTACTIC, "name field abuse"),
        ChaosClass("CHAOS-2.3.3", _D.SYNTACTIC, "phone formatting explosion"),
        ChaosClass("CHAOS-2.3.4", _D.SYNTACTIC, "categorical value drift"),
        ChaosClass("CHAOS-2.3.5", _D.SYNTACTIC, "unit ambiguity"),
        ChaosClass("CHAOS-2.4.1", _D.SYNTACTIC, "null pantheon / typed missingness"),
        # Domain 3 — Semantic
        ChaosClass("CHAOS-3.1.1", _D.SEMANTIC, "phonetic/orthographic variation"),
        ChaosClass("CHAOS-3.1.2", _D.SEMANTIC, "cross-script identity"),
        ChaosClass("CHAOS-3.1.3", _D.SEMANTIC, "Arabic-internal orthographic variance"),
        ChaosClass("CHAOS-3.1.4", _D.SEMANTIC, "structural name variation"),
        ChaosClass("CHAOS-3.1.5", _D.SEMANTIC, "typographic noise"),
        ChaosClass("CHAOS-3.2.1", _D.SEMANTIC, "representational conflict"),
        ChaosClass("CHAOS-3.2.2", _D.SEMANTIC, "temporal staleness conflict"),
        ChaosClass("CHAOS-3.2.3", _D.SEMANTIC, "genuine multiplicity"),
        ChaosClass("CHAOS-3.2.4", _D.SEMANTIC, "error conflict"),
        ChaosClass("CHAOS-3.2.5", _D.SEMANTIC, "granularity conflict"),
        ChaosClass("CHAOS-3.2.6", _D.SEMANTIC, "semantic frame conflict"),
        ChaosClass("CHAOS-3.2.7", _D.SEMANTIC, "chimera merge", 3, 1, 5),
        ChaosClass("CHAOS-3.3.1", _D.SEMANTIC, "orphaned children"),
        ChaosClass("CHAOS-3.3.2", _D.SEMANTIC, "dangling references after partial loads"),
        ChaosClass("CHAOS-3.3.3", _D.SEMANTIC, "parallel ID universes", 3, 2, 5),
        ChaosClass("CHAOS-3.3.4", _D.SEMANTIC, "recycled keys"),
        ChaosClass("CHAOS-3.3.5", _D.SEMANTIC, "cardinality violations"),
        ChaosClass("CHAOS-3.3.6", _D.SEMANTIC, "cross-source FK type mismatch"),
        ChaosClass("CHAOS-3.4.1", _D.SEMANTIC, "physical impossibility"),
        ChaosClass("CHAOS-3.4.2", _D.SEMANTIC, "business-rule violation"),
        ChaosClass("CHAOS-3.4.3", _D.SEMANTIC, "cross-field incoherence"),
        ChaosClass("CHAOS-3.4.4", _D.SEMANTIC, "distributional impossibility"),
        # Domain 4 — Systemic
        ChaosClass("CHAOS-4.1.1", _D.SYSTEMIC, "fan-out multiplication", 4, 2, 5),
        ChaosClass("CHAOS-4.1.2", _D.SYSTEMIC, "COUNT DISTINCT inflation/deflation"),
        ChaosClass("CHAOS-4.1.3", _D.SYSTEMIC, "filter shear / dueling dashboards"),
        ChaosClass("CHAOS-4.1.4", _D.SYSTEMIC, "sentinel skew in aggregates"),
        ChaosClass("CHAOS-4.1.5", _D.SYSTEMIC, "slow drift below alert thresholds"),
        ChaosClass("CHAOS-4.2.1", _D.SYSTEMIC, "provenance amnesia"),
        ChaosClass("CHAOS-4.2.2", _D.SYSTEMIC, "transformation laundering"),
        ChaosClass("CHAOS-4.2.3", _D.SYSTEMIC, "cleaning without receipts"),
        ChaosClass("CHAOS-4.3.1", _D.SYSTEMIC, "label noise from conflicts"),
        ChaosClass("CHAOS-4.3.2", _D.SYSTEMIC, "duplicate leakage across splits"),
        ChaosClass("CHAOS-4.3.3", _D.SYSTEMIC, "sentinel features"),
        ChaosClass("CHAOS-4.3.4", _D.SYSTEMIC, "encoding-fractured categoricals"),
        ChaosClass("CHAOS-4.3.5", _D.SYSTEMIC, "imputation feedback loops"),
        ChaosClass("CHAOS-4.3.6", _D.SYSTEMIC, "train/serve skew"),
        ChaosClass("CHAOS-4.4.1", _D.SYSTEMIC, "spreadsheet shadow-correction economy"),
    ]
}


def get(chaos_id: str) -> ChaosClass:
    return REGISTRY[chaos_id]
