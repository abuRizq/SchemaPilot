"""The chaos pre-scan (FILE_2 §3): fingerprints pattern-matched against the
FILE_1 taxonomy to produce a per-source Chaos Manifest — what the complexity
router (§8) routes on.
"""
from __future__ import annotations

import re

from schemapilot.contracts.manifest import ChaosFinding, ChaosManifest, Path
from schemapilot.layer1_profiling.fingerprint import ColumnFingerprint

# Boundary dates that are nulls in disguise (CHAOS-2.1.7).
SENTINEL_DATES = {
    "1900-01-01",
    "1970-01-01",
    "9999-12-31",
    "0000-00-00",
    "01/01/1900",
    "31/12/9999",
    "12/31/9999",
}
# Magic numbers used as null surrogates (CHAOS-1.4.2).
SENTINEL_NUMBERS = {"-1", "0", "999", "9999", "99999", "-999"}


def scan(
    fingerprints: dict[str, ColumnFingerprint],
    source_file_id: str,
    *,
    sentinel_mass_threshold: float = 0.02,
) -> ChaosManifest:
    manifest = ChaosManifest(source_file_id=source_file_id)
    for col, fp in fingerprints.items():
        _scan_column(manifest, col, fp, sentinel_mass_threshold)
        manifest.escalate(col, manifest.path_for(col))  # materialize default
    return manifest


def _scan_column(
    manifest: ChaosManifest, col: str, fp: ColumnFingerprint, sentinel_mass: float
) -> None:
    if fp.n_present == 0:
        return

    # --- temporal hazards -------------------------------------------------
    date_mass = fp.pattern_fraction("iso_date") + fp.pattern_fraction("slash_date") + fp.pattern_fraction("dash_date")
    slash_mass = fp.pattern_fraction("slash_date") + fp.pattern_fraction("dash_date")
    if date_mass > 0.5:
        if slash_mass > 0.01:
            manifest.add(ChaosFinding("CHAOS-2.1.1", col, slash_mass, "ambiguous slash/dash dates"))
            manifest.escalate(col, Path.DEEP)
        elif fp.pattern_fraction("iso_date") < 0.999:
            manifest.escalate(col, Path.STANDARD)
        for value, mass in fp.cms.heavy_hitters(sentinel_mass):
            if value in SENTINEL_DATES:
                manifest.add(ChaosFinding("CHAOS-2.1.7", col, mass, f"sentinel date {value!r}"))
                manifest.escalate(col, Path.STANDARD)

    # --- sentinel numbers ---------------------------------------------------
    if fp.dominant_type() in ("int", "decimal"):
        for value, mass in fp.cms.heavy_hitters(sentinel_mass):
            if value in SENTINEL_NUMBERS and mass >= sentinel_mass:
                manifest.add(ChaosFinding("CHAOS-1.4.2", col, mass, f"sentinel number {value!r}"))
                manifest.escalate(col, Path.STANDARD)

    # --- locale-split numerics (CHAOS-1.4.4) --------------------------------
    dot = fp.pattern_fraction("decimal_dot")
    comma = fp.pattern_fraction("decimal_comma")
    if dot > 0.01 and comma > 0.01:
        manifest.add(ChaosFinding("CHAOS-1.4.4", col, min(dot, comma), "mixed decimal conventions"))
        manifest.escalate(col, Path.DEEP)

    # --- spreadsheet artifacts / scientific IDs ------------------------------
    if fp.pattern_fraction("excel_error") > 0:
        manifest.add(ChaosFinding("CHAOS-1.4.5", col, fp.pattern_fraction("excel_error"), "excel error literals"))
        manifest.escalate(col, Path.STANDARD)
    if fp.pattern_fraction("scientific") > 0 and fp.dominant_type() == "id_like":
        manifest.add(ChaosFinding("CHAOS-1.4.5", col, fp.pattern_fraction("scientific"), "scientific-notation-mangled ids"))
        manifest.escalate(col, Path.DEEP)

    # --- id protection (CHAOS-1.4.9) -----------------------------------------
    if fp.leading_zero_seen or fp.dominant_type() == "id_like":
        manifest.add(ChaosFinding("CHAOS-1.4.9", col, 1.0, "id-like: contractually string-typed"))

    # --- encoding hazards -----------------------------------------------------
    moji = fp.script_fraction("latin1_supplement") + fp.script_fraction("arabic_presentation")
    if moji > 0.02:
        manifest.add(ChaosFinding("CHAOS-2.2.1", col, moji, "mojibake block signature"))
        manifest.escalate(col, Path.DEEP)
    if fp.script_fraction("replacement") > 0:
        manifest.add(ChaosFinding("CHAOS-2.2.3", col, fp.script_fraction("replacement"), "U+FFFD irreparable loss"))
        manifest.escalate(col, Path.DEEP)
    if fp.script_fraction("invisible") > 0:
        manifest.add(ChaosFinding("CHAOS-2.2.7", col, fp.script_fraction("invisible"), "invisible characters"))
        manifest.escalate(col, Path.STANDARD)
    if fp.script_fraction("arabic_digit") > 0 and fp.script_fraction("ascii_digit") > 0:
        manifest.add(ChaosFinding("CHAOS-1.4.7", col, fp.script_fraction("arabic_digit"), "mixed-script digits"))
        manifest.escalate(col, Path.STANDARD)

    # --- header hazards ---------------------------------------------------------
    if re.match(r"^(column\d+|f\d+|unnamed:?\s*\d+)$", col.strip().lower()):
        manifest.add(ChaosFinding("CHAOS-1.1.6", col, 1.0, "anonymous header — label carries zero signal"))
        manifest.escalate(col, Path.DEEP)
    if any(_unicode_suspicious(ch) for ch in col):
        manifest.add(ChaosFinding("CHAOS-1.1.5", col, 1.0, "encoding-mangled or contaminated header"))
        manifest.escalate(col, Path.DEEP)

    # --- distributional alarms ----------------------------------------------------
    hitters = fp.cms.heavy_hitters(0.30)
    if hitters and fp.cardinality > 10:
        value, mass = hitters[0]
        manifest.add(ChaosFinding("CHAOS-3.4.4", col, mass, f"default-mass spike at {value!r}"))
        manifest.escalate(col, Path.STANDARD)


def _unicode_suspicious(ch: str) -> bool:
    code = ord(ch)
    return code in (0xFEFF, 0x200B, 0x200E, 0x200F) or 0x0080 <= code <= 0x00BF
