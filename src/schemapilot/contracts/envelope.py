"""Layer 0 provenance envelope (FILE_2 §2).

Every inbound record is wrapped in one of these before anything else touches
it. Declared metadata (encoding, locale, timezone) are priors, not truths —
Layer 3 validates them against the data.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class ProvenanceEnvelope:
    source_system_id: str  # stable registry key for the silo
    source_file_id: str  # SHA-256 content hash of the carrier file
    extraction_timestamp: str  # ISO-8601 UTC, our trusted clock
    source_asserted_time: str | None  # untrusted (CHAOS-2.1.9)
    declared_encoding: str | None
    declared_locale: str | None  # seeds L3 date/number priors
    declared_timezone: str | None  # restores what CSV export destroyed (CHAOS-2.1.8)
    schema_version_hash: str  # detects structural drift (CHAOS-1.2.3)
    row_ordinal: int  # position in carrier
    batch_id: str  # detects re-ingestion (CHAOS-1.3.9/1.3.10)

    def to_dict(self) -> dict:
        return asdict(self)
