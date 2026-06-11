"""Source connectors: raw bytes -> envelope-wrapped staging records (FILE_2 §2).

Every record leaves this module wrapped in a ProvenanceEnvelope. All values
stay strings at this stage — typing is Layer 3's job (id-like columns must
never pass through a numeric parser, CHAOS-1.4.9).
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from schemapilot.contracts.envelope import ProvenanceEnvelope
from schemapilot.layer0_ingestion.drift import schema_version_hash
from schemapilot.layer0_ingestion.vault import RawVault


@dataclass
class StagedSource:
    """One ingested file: column names + envelope-wrapped string rows."""

    source_system_id: str
    source_file_id: str
    columns: list[str]
    rows: list[dict[str, str | None]]
    envelopes: list[ProvenanceEnvelope]


@dataclass(frozen=True)
class SourceDeclaration:
    """What the source claims about itself — priors, not truths."""

    source_system_id: str
    encoding: str | None = "utf-8"
    locale: str | None = None
    timezone: str | None = None
    asserted_time: str | None = None


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ingest_csv(
    vault: RawVault,
    data: bytes,
    declaration: SourceDeclaration,
    batch_id: str,
    *,
    extraction_timestamp: str | None = None,
) -> StagedSource:
    source_file_id = vault.ingest(
        data, source_system_id=declaration.source_system_id, batch_id=batch_id
    )
    # Decode with the declared encoding; decode errors are surfaced rather than
    # silently replaced — replacement chars destroy match evidence (CHAOS-2.2.3).
    text = data.decode(declaration.encoding or "utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    table = list(reader)
    columns = table[0] if table else []
    extraction = extraction_timestamp or _utcnow()
    sv_hash = schema_version_hash(columns)

    rows: list[dict[str, str | None]] = []
    envelopes: list[ProvenanceEnvelope] = []
    for ordinal, raw in enumerate(table[1:]):
        row = {col: (raw[i] if i < len(raw) else None) for i, col in enumerate(columns)}
        rows.append(row)
        envelopes.append(
            ProvenanceEnvelope(
                source_system_id=declaration.source_system_id,
                source_file_id=source_file_id,
                extraction_timestamp=extraction,
                source_asserted_time=declaration.asserted_time,
                declared_encoding=declaration.encoding,
                declared_locale=declaration.locale,
                declared_timezone=declaration.timezone,
                schema_version_hash=sv_hash,
                row_ordinal=ordinal,
                batch_id=batch_id,
            )
        )
    return StagedSource(
        source_system_id=declaration.source_system_id,
        source_file_id=source_file_id,
        columns=columns,
        rows=rows,
        envelopes=envelopes,
    )


def ingest_ndjson(
    vault: RawVault,
    data: bytes,
    declaration: SourceDeclaration,
    batch_id: str,
    *,
    extraction_timestamp: str | None = None,
) -> StagedSource:
    source_file_id = vault.ingest(
        data, source_system_id=declaration.source_system_id, batch_id=batch_id
    )
    text = data.decode(declaration.encoding or "utf-8", errors="replace")
    parsed = [json.loads(line) for line in text.splitlines() if line.strip()]
    columns: list[str] = []
    for obj in parsed:
        for key in obj:
            if key not in columns:
                columns.append(key)
    extraction = extraction_timestamp or _utcnow()
    sv_hash = schema_version_hash(columns)

    rows: list[dict[str, str | None]] = []
    envelopes: list[ProvenanceEnvelope] = []
    for ordinal, obj in enumerate(parsed):
        rows.append({c: (None if obj.get(c) is None else str(obj.get(c))) for c in columns})
        envelopes.append(
            ProvenanceEnvelope(
                source_system_id=declaration.source_system_id,
                source_file_id=source_file_id,
                extraction_timestamp=extraction,
                source_asserted_time=declaration.asserted_time,
                declared_encoding=declaration.encoding,
                declared_locale=declaration.locale,
                declared_timezone=declaration.timezone,
                schema_version_hash=sv_hash,
                row_ordinal=ordinal,
                batch_id=batch_id,
            )
        )
    return StagedSource(
        source_system_id=declaration.source_system_id,
        source_file_id=source_file_id,
        columns=columns,
        rows=rows,
        envelopes=envelopes,
    )
