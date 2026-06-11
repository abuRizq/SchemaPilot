"""Shared fixtures: mini-ingestion helpers for chaos tests."""
from __future__ import annotations

import pytest

from schemapilot.layer0_ingestion import RawVault, SourceDeclaration, ingest_csv
from schemapilot.layer1_profiling import fingerprint_source, scan


@pytest.fixture
def vault(tmp_path):
    return RawVault(tmp_path / "vault")


@pytest.fixture
def staged(vault):
    """Ingest a CSV and return (StagedSource, fingerprints, manifest)."""

    def _ingest(csv_text: str, *, system="test", locale=None, timezone=None, batch="b1"):
        src = ingest_csv(
            vault,
            csv_text.encode("utf-8"),
            SourceDeclaration(system, locale=locale, timezone=timezone),
            batch,
        )
        fps = fingerprint_source(src.columns, src.rows, src.source_file_id)
        manifest = scan(fps, src.source_file_id)
        return src, fps, manifest

    return _ingest
