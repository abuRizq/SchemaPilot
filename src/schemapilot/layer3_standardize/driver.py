"""The Layer-3 driver. Axiom A4 makes the stage ordering mandatory:

    encoding → script → temporal → numeric/categorical → null/sentinel

This module is the only public entry point to standardization; stage modules
are implementation detail. Every cell change appends a TransformRecord (A1) —
no cleaning without receipts.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from schemapilot.contracts.concept import ConceptContract, Datatype
from schemapilot.contracts.lineage import LineageChain, TransformRecord
from schemapilot.contracts.manifest import ChaosManifest
from schemapilot.contracts.nulls import NullKind, TypedNull
from schemapilot.layer0_ingestion.connectors import StagedSource
from schemapilot.layer3_standardize import categorical as _cat
from schemapilot.layer3_standardize import encoding as _enc
from schemapilot.layer3_standardize import numeric as _num
from schemapilot.layer3_standardize import temporal as _tmp
from schemapilot.layer3_standardize import unicode_norm as _uni
from schemapilot.layer3_standardize.nulls import unify as _unify_null


@dataclass
class Cell:
    raw: str | None
    value: object  # str | float | bool | TypedNull | TemporalValue | TemporalInterval
    match_key: str | None  # normalized comparison key; None bars match evidence
    lossy: bool
    lineage: LineageChain
    flags: list[str] = field(default_factory=list)

    @property
    def is_null(self) -> bool:
        return self.value is None or isinstance(self.value, TypedNull)


@dataclass
class StandardizedSource:
    source_system_id: str
    source_file_id: str
    rows: list[dict[str, Cell]]  # keyed by concept_id
    envelopes: list


def standardize(
    staged: StagedSource,
    mapping: dict[str, tuple[str, ConceptContract]],
    manifest: ChaosManifest,
    *,
    default_country: str = "966",
) -> StandardizedSource:
    """Standardize every mapped column of a staged source.

    `mapping`: source column -> (concept_id, contract). Unmapped columns are
    carried into the extension zone (concept "UNMAPPED.<col>") with zero trust
    inheritance (§4.4) rather than dropped.
    """
    declared_locale = staged.envelopes[0].declared_locale if staged.envelopes else None
    declared_tz = staged.envelopes[0].declared_timezone if staged.envelopes else None

    # Column-level verdicts are computed once, before any per-value decode.
    temporal_verdicts: dict[str, list[tuple[range, _tmp.ColumnVerdict]]] = {}
    numeric_verdicts: dict[str, _num.NumericVerdict] = {}
    sentinel_numbers: dict[str, set[str]] = {}
    for col, (concept_id, contract) in mapping.items():
        values = [r.get(col) or "" for r in staged.rows]
        if contract.datatype == Datatype.DATE:
            temporal_verdicts[col] = _tmp.segment_and_infer(values, declared_locale=declared_locale)
        elif contract.datatype in (Datatype.DECIMAL, Datatype.INTEGER):
            numeric_verdicts[col] = _num.infer_decimal_convention(values)
            sentinel_numbers[col] = {
                f.detail.split("'")[1]
                for f in manifest.findings_for(col)
                if f.chaos_id == "CHAOS-1.4.2" and "'" in f.detail
            }

    out_rows: list[dict[str, Cell]] = []
    for ordinal, row in enumerate(staged.rows):
        out_row: dict[str, Cell] = {}
        for col, (concept_id, contract) in mapping.items():
            cell = _standardize_cell(
                raw=row.get(col),
                column=col,
                ordinal=ordinal,
                contract=contract,
                source_file_id=staged.source_file_id,
                temporal_verdicts=temporal_verdicts.get(col),
                numeric_verdict=numeric_verdicts.get(col),
                sentinel_numbers=sentinel_numbers.get(col, set()),
                declared_tz=declared_tz,
                default_country=default_country,
            )
            out_row[concept_id] = cell
        out_rows.append(out_row)
    return StandardizedSource(
        source_system_id=staged.source_system_id,
        source_file_id=staged.source_file_id,
        rows=out_rows,
        envelopes=staged.envelopes,
    )


def _standardize_cell(
    *,
    raw: str | None,
    column: str,
    ordinal: int,
    contract: ConceptContract,
    source_file_id: str,
    temporal_verdicts,
    numeric_verdict,
    sentinel_numbers: set[str],
    declared_tz: str | None,
    default_country: str,
) -> Cell:
    lineage = LineageChain(source_file_id, ordinal, column)
    flags: list[str] = []

    # Null pantheon (logically stage ⑤, checked up front so no parser ever
    # sees a missingness token; sentinel excision stays inside its stage).
    typed = _unify_null(raw)
    if typed is not None:
        return Cell(raw, typed, None, False, lineage, [f"null:{typed.kind.value}"])

    text = str(raw)

    # ① Encoding repair.
    text = _enc.strip_bom(text)
    repair = _enc.repair(text)
    lossy = repair.lossy
    if repair.repaired:
        lineage.append(TransformRecord(
            "encoding_repair", 3, text, repair.text, reversible=True, detail=repair.chain,
        ))
        text = repair.text
    elif repair.lossy:
        flags.append("LOSSY")
        lineage.append(TransformRecord(
            "encoding_irreparable", 3, text, text, reversible=True, lossy=True,
            detail="replacement characters: barred from match evidence",
        ))

    # ② Unicode & script normalization (conservative profile for storage).
    stored = _uni.normalize_stored(text)
    if stored != text:
        lineage.append(TransformRecord("unicode_normalize", 3, text, stored, reversible=False))

    # ③/④ typed decode under the column verdict.
    value: object = stored
    key: str | None = None
    dt = contract.datatype

    if dt == Datatype.DATE and temporal_verdicts is not None:
        verdict = next(v for rng, v in temporal_verdicts if ordinal in rng)
        decoded = _tmp.decode_value(stored, verdict, declared_timezone=declared_tz)
        if decoded is None:
            flags.append("UNPARSEABLE_DATE")
            value, key = stored, None
        elif isinstance(decoded, TypedNull):
            lineage.append(TransformRecord(
                "sentinel_excision", 3, stored, str(decoded), reversible=True,
                detail="CHAOS-2.1.7: boundary date -> typed null",
            ))
            value, key = decoded, None
        elif isinstance(decoded, _tmp.TemporalInterval):
            flags.append("TEMPORAL_INTERVAL")
            lineage.append(TransformRecord(
                "temporal_interval", 3, stored, repr(decoded.candidates), reversible=True,
                detail="CHAOS-2.1.1: ambiguity preserved, not coin-flipped",
            ))
            value, key = decoded, None
        else:
            lineage.append(TransformRecord(
                "temporal_decode", 3, stored, decoded.instant.isoformat(),
                reversible=True, detail=f"format={decoded.fmt} tz={declared_tz}",
            ))
            if decoded.dst_flag:
                flags.append(f"DST_{decoded.dst_flag.upper()}")
            value, key = decoded, decoded.date_key

    elif dt in (Datatype.DECIMAL, Datatype.INTEGER) and numeric_verdict is not None:
        if stored in sentinel_numbers:
            null = TypedNull(NullKind.PENDING, stored)
            lineage.append(TransformRecord(
                "sentinel_excision", 3, stored, str(null), reversible=True,
                detail="CHAOS-1.4.2: magic number -> typed null",
            ))
            value, key = null, None
        else:
            number = _num.parse_numeric(stored, numeric_verdict)
            if number is None:
                flags.append("UNPARSEABLE_NUMERIC")
                value, key = stored, None
            else:
                lineage.append(TransformRecord(
                    "numeric_decode", 3, stored, repr(number), reversible=True,
                    detail=f"decimal_sep={numeric_verdict.decimal_separator!r}",
                ))
                value, key = number, repr(number)

    elif dt == Datatype.ID:
        # CHAOS-1.4.9: contractually string-typed forever.
        value = stored
        key = _uni.fold_digits(stored)

    elif dt == Datatype.PHONE:
        canon = _cat.canonical_phone(stored, default_country=default_country)
        if canon is None:
            flags.append("UNPARSEABLE_PHONE")
            value, key = stored, None
        else:
            lineage.append(TransformRecord(
                "phone_canonicalize", 3, stored, canon, reversible=False,
                detail="CHAOS-2.3.3: E.164-style key",
            ))
            value, key = canon, canon

    elif dt == Datatype.BOOLEAN:
        b = _cat.conform_boolean(stored)
        if b is None:
            flags.append("UNPARSEABLE_BOOLEAN")
            value, key = stored, None
        else:
            value, key = b, str(b)

    elif dt == Datatype.CATEGORICAL and contract.domain:
        domain = _cat.CategoricalDomain(contract.domain)
        canon, conf = domain.conform(stored)
        if canon is None:
            flags.append("UNCONFORMED_CATEGORY")
            value, key = stored, _uni.match_key(stored)
        else:
            if canon != stored:
                lineage.append(TransformRecord(
                    "categorical_conform", 3, stored, canon, reversible=True,
                    detail=f"CHAOS-2.3.4 confidence={conf:.2f}",
                ))
            value, key = canon, _uni.match_key(canon)

    else:  # STRING / NAME / ADDRESS
        value = stored
        key = None if lossy else _uni.match_key(stored)

    if lossy:
        key = None  # LOSSY values are barred from serving as match evidence (§5.1)
    return Cell(raw, value, key, lossy, lineage, flags)
