"""Stage ③ — The Temporal Resolution Engine (FILE_2 §5.3, CHAOS-2.1.*).

Column-level inference followed by value-level decoding — never naive
per-value parsing. Unambiguous values vote for a format hypothesis; a Bayesian
update over the hypothesis space (seeded by the envelope's declared locale)
yields a column verdict; mixtures are segmented; residual ambiguity is stored
as a TemporalInterval rather than resolved by coin-flip; sentinels become
typed nulls before any recency logic can see them.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from schemapilot.contracts.nulls import NullKind, TypedNull
from schemapilot.layer1_profiling.chaos_scan import SENTINEL_DATES

HYPOTHESES = ("DMY", "MDY", "YMD", "ISO", "EPOCH_S", "EPOCH_MS", "EXCEL_1900", "HIJRI")

_TWO_DIGIT_PIVOT = 50  # 00-49 -> 20xx, 50-99 -> 19xx (documented; .NET convention)

_SEP_DATE = re.compile(r"^(\d{1,4})([/\-.])(\d{1,2})\2(\d{1,4})$")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})([T ](\d{2}):(\d{2})(:(\d{2}))?)?(Z|[+-]\d{2}:?\d{2})?$")
_EPOCH = re.compile(r"^\d{10}(\d{3})?$")
_EXCEL_SERIAL = re.compile(r"^\d{5}$")


@dataclass(frozen=True)
class TemporalValue:
    """A resolved instant: UTC + original offset + original wall-clock (A1)."""

    instant: datetime  # tz-aware UTC
    original: str
    original_offset: str | None
    fmt: str
    dst_flag: str | None = None  # "nonexistent" | "ambiguous" | None

    @property
    def date_key(self) -> str:
        return self.instant.strftime("%Y-%m-%d")


@dataclass(frozen=True)
class TemporalInterval:
    """Residual ambiguity preserved honestly: candidate instants + probabilities.

    Downstream fusion (L5) can collapse the interval using a sibling source's
    unambiguous value — cross-source disambiguation (§5.3 step 5).
    """

    candidates: tuple[tuple[datetime, float], ...]
    original: str

    def contains(self, instant: datetime) -> bool:
        return any(c.date() == instant.date() for c, _ in self.candidates)


@dataclass
class ColumnVerdict:
    posterior: dict[str, float]
    verdict: str | None  # winning hypothesis, or None if mixture/undecidable
    mixture: bool
    sentinels: set[str]


# ---------------------------------------------------------------------------
# Hypothesis voting
# ---------------------------------------------------------------------------

def _consistent_hypotheses(value: str) -> set[str]:
    value = value.strip()
    out: set[str] = set()
    if _ISO.match(value):
        out.add("ISO")
        return out
    m = _SEP_DATE.match(value)
    if m:
        a, _, b, c = int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4))
        if len(m.group(1)) == 4:  # YYYY first
            if 1 <= b <= 12 and 1 <= c <= 31:
                out.add("YMD")
            if 1300 <= a <= 1500 and 1 <= b <= 12 and 1 <= c <= 30:
                out.add("HIJRI")
            return out
        # day/month or month/day
        if 1 <= a <= 31 and 1 <= b <= 12:
            out.add("DMY")
        if 1 <= a <= 12 and 1 <= b <= 31:
            out.add("MDY")
        return out
    if _EPOCH.match(value):
        out.add("EPOCH_MS" if len(value) == 13 else "EPOCH_S")
        return out
    if _EXCEL_SERIAL.match(value) and 20000 <= int(value) <= 60000:
        out.add("EXCEL_1900")
    return out


_LOCALE_PRIORS = {
    "en_US": {"MDY": 4.0},
    "en_GB": {"DMY": 4.0},
    "ar_SA": {"DMY": 3.0, "HIJRI": 2.0},
    "fr_FR": {"DMY": 4.0},
    "de_DE": {"DMY": 4.0},
}


def infer_column_format(
    values: list[str],
    *,
    declared_locale: str | None = None,
    sentinel_values: set[str] | None = None,
) -> ColumnVerdict:
    """§5.3 steps 1-3: format census, unambiguous anchoring, mixture detection."""
    sentinels = set(SENTINEL_DATES) | (sentinel_values or set())
    prior = {h: 1.0 for h in HYPOTHESES}
    for h, boost in _LOCALE_PRIORS.get(declared_locale or "", {}).items():
        prior[h] *= boost

    log_post = {h: math.log(p) for h, p in prior.items()}
    anchor_counts = {h: 0 for h in HYPOTHESES}
    for value in values:
        if not value or value.strip() in sentinels:
            continue
        consistent = _consistent_hypotheses(value)
        if not consistent:
            continue
        if len(consistent) == 1:
            anchor_counts[next(iter(consistent))] += 1
        # Bayesian update: each value multiplies the likelihood of every
        # hypothesis it is consistent with.
        for h in HYPOTHESES:
            log_post[h] += math.log(0.95 if h in consistent else 0.01)

    max_log = max(log_post.values())
    weights = {h: math.exp(lp - max_log) for h, lp in log_post.items()}
    total = sum(weights.values())
    posterior = {h: w / total for h, w in weights.items()}

    # Mixture detection: bimodal *anchored* votes between DMY and MDY mean
    # two sub-populations share the column (FILE_1 §2.1) — undecidable as one.
    dmy, mdy = anchor_counts["DMY"], anchor_counts["MDY"]
    mixture = dmy > 0 and mdy > 0
    winner = max(posterior, key=lambda h: posterior[h])
    decided = posterior[winner] >= 0.7 and not mixture
    return ColumnVerdict(
        posterior=posterior,
        verdict=winner if decided else None,
        mixture=mixture,
        sentinels=sentinels,
    )


def segment_and_infer(
    values: list[str], *, declared_locale: str | None = None
) -> list[tuple[range, ColumnVerdict]]:
    """Mixture segmentation (§5.3 step 3): re-infer per contiguous row-ordinal
    segment, because mixtures almost always align with ingestion seams.
    """
    whole = infer_column_format(values, declared_locale=declared_locale)
    if not whole.mixture:
        return [(range(0, len(values)), whole)]
    # Single change-point search over anchored votes.
    best_split, best_score = None, -1.0
    anchors = []
    for v in values:
        c = _consistent_hypotheses(v or "")
        anchors.append(next(iter(c)) if len(c) == 1 else None)
    for split in range(1, len(values)):
        left = [a for a in anchors[:split] if a in ("DMY", "MDY")]
        right = [a for a in anchors[split:] if a in ("DMY", "MDY")]
        if not left or not right:
            continue
        purity = (max(left.count("DMY"), left.count("MDY")) / len(left)) * (
            max(right.count("DMY"), right.count("MDY")) / len(right)
        )
        if purity > best_score:
            best_score, best_split = purity, split
    if best_split is None:
        return [(range(0, len(values)), whole)]
    return [
        (range(0, best_split), infer_column_format(values[:best_split], declared_locale=declared_locale)),
        (range(best_split, len(values)), infer_column_format(values[best_split:], declared_locale=declared_locale)),
    ]


# ---------------------------------------------------------------------------
# Per-value decoding
# ---------------------------------------------------------------------------

def _pivot_year(y: int) -> int:
    if y >= 100:
        return y
    return 2000 + y if y < _TWO_DIGIT_PIVOT else 1900 + y


def _hijri_to_gregorian(hy: int, hm: int, hd: int) -> datetime:
    """Tabular (arithmetic) Islamic calendar conversion — deterministic
    approximation, ±1 day vs observational calendars; flagged in lineage.
    """
    jdn = (
        hd
        + math.ceil(29.5 * (hm - 1))
        + (hy - 1) * 354
        + math.floor((3 + 11 * hy) / 30)
        + 1948439
    )
    # JDN -> Gregorian (Fliegel-Van Flandern)
    l = jdn + 68569
    n = 4 * l // 146097
    l = l - (146097 * n + 3) // 4
    i = 4000 * (l + 1) // 1461001
    l = l - 1461 * i // 4 + 31
    j = 80 * l // 2447
    d = l - 2447 * j // 80
    l = j // 11
    m = j + 2 - 12 * l
    y = 100 * (n - 49) + i + l
    return datetime(y, m, d, tzinfo=timezone.utc)


def _decode_with(value: str, fmt: str) -> datetime | None:
    value = value.strip()
    try:
        if fmt == "ISO":
            m = _ISO.match(value)
            if not m:
                return None
            iso = value.replace(" ", "T") if " " in value and "T" not in value else value
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt
        m = _SEP_DATE.match(value)
        if fmt in ("DMY", "MDY", "YMD", "HIJRI") and m:
            a, b, c = int(m.group(1)), int(m.group(3)), int(m.group(4))
            if fmt == "DMY":
                return datetime(_pivot_year(c), b, a)
            if fmt == "MDY":
                return datetime(_pivot_year(c), a, b)
            if fmt == "YMD":
                return datetime(a, b, c)
            if fmt == "HIJRI":
                return _hijri_to_gregorian(a, b, c).replace(tzinfo=None)
        if fmt == "EPOCH_S" and _EPOCH.match(value) and len(value) == 10:
            return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
        if fmt == "EPOCH_MS" and _EPOCH.match(value) and len(value) == 13:
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).replace(tzinfo=None)
        if fmt == "EXCEL_1900" and _EXCEL_SERIAL.match(value):
            # Excel-1900 epoch, including the fictitious 1900-02-29 offset.
            return datetime(1899, 12, 30) + timedelta(days=int(value))
    except (ValueError, OverflowError, OSError):
        return None
    return None


def _restore_timezone(
    naive: datetime, declared_timezone: str | None
) -> tuple[datetime, str | None, str | None]:
    """§5.3 step 6: re-anchor naive datetimes from the envelope's declaration.

    Returns (utc_instant, original_offset, dst_flag). DST-nonexistent instants
    prove the declaration wrong and are flagged. Date-only values (midnight,
    no time component in the source) are calendar dates, not instants —
    shifting a DOB by a UTC offset would change the date itself, so they pass
    through unshifted.
    """
    if naive.tzinfo is not None:
        return naive.astimezone(timezone.utc), naive.strftime("%z"), None
    if naive.hour == 0 and naive.minute == 0 and naive.second == 0:
        return naive.replace(tzinfo=timezone.utc), None, None
    if not declared_timezone:
        return naive.replace(tzinfo=timezone.utc), None, "naive-assumed-utc"
    try:
        tz = ZoneInfo(declared_timezone)
    except KeyError:
        return naive.replace(tzinfo=timezone.utc), None, "unknown-tz"
    local0 = naive.replace(tzinfo=tz, fold=0)
    local1 = naive.replace(tzinfo=tz, fold=1)
    dst_flag = None
    if local0.utcoffset() != local1.utcoffset():
        # Fall-back repeat: wall clock occurs twice.
        dst_flag = "ambiguous"
    roundtrip = local0.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
    if roundtrip != naive:
        # Spring-forward gap: a wall clock that never existed.
        dst_flag = "nonexistent"
    return local0.astimezone(timezone.utc), local0.strftime("%z"), dst_flag


def decode_value(
    value: str,
    verdict: ColumnVerdict,
    *,
    declared_timezone: str | None = None,
) -> TemporalValue | TemporalInterval | TypedNull | None:
    """§5.3 steps 4-7 for one value. Returns None when the value doesn't parse
    under any hypothesis (caller flags, never coerces).
    """
    stripped = value.strip()
    # Step 7 first: sentinel excision before anything recency-shaped sees it.
    if stripped in verdict.sentinels:
        return TypedNull(NullKind.PENDING, stripped)

    consistent = _consistent_hypotheses(stripped)
    if not consistent:
        return None

    fmt = verdict.verdict
    if fmt is not None and fmt in consistent:
        naive = _decode_with(stripped, fmt)
        if naive is not None:
            utc, offset, dst = _restore_timezone(naive, declared_timezone)
            return TemporalValue(utc, value, offset, fmt, dst)

    if fmt is not None and fmt not in consistent and len(consistent) == 1:
        # Value inconsistent with the column verdict but unambiguous itself:
        # decode under its own format, flagged via fmt mismatch in lineage.
        only = next(iter(consistent))
        naive = _decode_with(stripped, only)
        if naive is not None:
            utc, offset, dst = _restore_timezone(naive, declared_timezone)
            return TemporalValue(utc, value, offset, only, dst)

    # Residual ambiguity (step 5): preserve the candidate set with posteriors.
    candidates: list[tuple[datetime, float]] = []
    mass = sum(verdict.posterior[h] for h in consistent) or 1.0
    for h in sorted(consistent):
        naive = _decode_with(stripped, h)
        if naive is not None:
            utc, _, _ = _restore_timezone(naive, declared_timezone)
            candidates.append((utc, verdict.posterior[h] / mass))
    if not candidates:
        return None
    if len(candidates) == 1:
        utc = candidates[0][0]
        return TemporalValue(utc, value, None, next(iter(consistent)))
    return TemporalInterval(tuple(candidates), value)
