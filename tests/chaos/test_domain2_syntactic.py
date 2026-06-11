"""Adversarial regression suite — Domain 2: syntactic & encoding chaos
(FILE_1 §2.2)."""
from schemapilot.contracts.nulls import NullKind, TypedNull
from schemapilot.layer3_standardize.categorical import canonical_phone, conform_boolean
from schemapilot.layer3_standardize.encoding import repair, strip_bom
from schemapilot.layer3_standardize.numeric import infer_decimal_convention, parse_numeric
from schemapilot.layer3_standardize.temporal import (
    TemporalInterval,
    TemporalValue,
    decode_value,
    infer_column_format,
    segment_and_infer,
)
from schemapilot.layer3_standardize.unicode_norm import match_key


class TestTemporal:
    def test_chaos_2_1_1_column_verdict_from_unambiguous_anchors(self):
        """CHAOS-2.1.1: 13/04/2024 is an unambiguous DMY anchor; the column
        verdict decodes every sibling value, never a per-value coin flip."""
        verdict = infer_column_format(["13/04/2024", "03/04/2024", "25/12/2023"])
        assert verdict.verdict == "DMY"
        decoded = decode_value("03/04/2024", verdict)
        assert isinstance(decoded, TemporalValue)
        assert decoded.date_key == "2024-04-03"

    def test_chaos_2_1_1_residual_ambiguity_becomes_interval(self):
        """An undecidable column yields TemporalInterval — ambiguity is stored,
        not resolved by fiat."""
        verdict = infer_column_format(["03/04/1985"])
        decoded = decode_value("03/04/1985", verdict)
        assert isinstance(decoded, TemporalInterval)
        dates = {c.date().isoformat() for c, _ in decoded.candidates}
        assert dates == {"1985-04-03", "1985-03-04"}

    def test_chaos_2_1_1_mixture_segmentation(self):
        """A DMY shipment concatenated with an MDY shipment is segmented at
        the change point and each segment gets its own verdict."""
        values = ["13/04/2024", "25/12/2023", "31/01/2024", "04/13/2024", "12/25/2023", "01/31/2024"]
        segments = segment_and_infer(values)
        assert len(segments) == 2
        assert segments[0][1].verdict == "DMY"
        assert segments[1][1].verdict == "MDY"

    def test_chaos_2_1_7_sentinel_dates_become_typed_nulls(self):
        """CHAOS-2.1.7: 1900-01-01 / 9999-12-31 are excised to typed nulls
        before any recency logic can be poisoned by them."""
        verdict = infer_column_format(["2024-01-15", "1900-01-01", "9999-12-31"])
        for sentinel in ("1900-01-01", "9999-12-31"):
            decoded = decode_value(sentinel, verdict)
            assert isinstance(decoded, TypedNull)
            assert decoded.kind is NullKind.PENDING

    def test_chaos_2_1_8_timezone_restoration_and_dst_flags(self):
        """CHAOS-2.1.8: naive timestamps are re-anchored from the declared
        timezone; spring-forward gap times are flagged nonexistent."""
        verdict = infer_column_format(["2021-03-14 02:30:00", "2021-06-01 12:00:00"])
        decoded = decode_value("2021-06-01 12:00:00", verdict, declared_timezone="Asia/Riyadh")
        assert isinstance(decoded, TemporalValue)
        assert decoded.instant.isoformat() == "2021-06-01T09:00:00+00:00"
        gap = decode_value("2021-03-14 02:30:00", verdict, declared_timezone="America/New_York")
        assert isinstance(gap, TemporalValue)
        assert gap.dst_flag == "nonexistent"

    def test_date_only_values_never_shift_across_midnight(self):
        """A calendar date (DOB) is not an instant: timezone restoration must
        not move 1985-03-04 to 1985-03-03T21:00Z."""
        verdict = infer_column_format(["1985-03-04"])
        decoded = decode_value("1985-03-04", verdict, declared_timezone="Asia/Riyadh")
        assert decoded.date_key == "1985-03-04"

    def test_chaos_2_1_3_epoch_and_excel_serials(self):
        """CHAOS-2.1.3/2.1.4: epoch seconds vs milliseconds vs Excel-1900
        serials are distinct hypotheses."""
        v_s = infer_column_format(["1718409600", "1700000000"])
        assert decode_value("1718409600", v_s).date_key == "2024-06-15"
        v_ms = infer_column_format(["1718409600000"])
        assert decode_value("1718409600000", v_ms).date_key == "2024-06-15"
        v_xl = infer_column_format(["45458", "45000"])
        assert decode_value("45458", v_xl).date_key == "2024-06-15"

    def test_chaos_2_1_2_two_digit_year_pivot(self):
        """CHAOS-2.1.2: documented pivot — 03/04/85 lands in 1985, 03/04/24 in 2024."""
        verdict = infer_column_format(["13/04/85", "25/12/24"], declared_locale="en_GB")
        assert decode_value("13/04/85", verdict).date_key == "1985-04-13"
        assert decode_value("25/12/24", verdict).date_key == "2024-12-25"


class TestEncoding:
    def test_chaos_2_2_1_single_mojibake_repaired_with_roundtrip_proof(self):
        corrupted = "محمد".encode("utf-8").decode("latin-1")
        result = repair(corrupted)
        assert result.repaired and result.text == "محمد"

    def test_chaos_2_2_2_double_encoding_repaired(self):
        corrupted = "José".encode("utf-8").decode("latin-1").encode("utf-8").decode("latin-1")
        result = repair(corrupted)
        assert result.repaired and result.text == "José"
        assert "x2" in result.chain

    def test_chaos_2_2_3_replacement_chars_are_lossy_never_guessed(self):
        result = repair("Mu�ammad")
        assert result.lossy and not result.repaired
        assert result.text == "Mu�ammad"  # retained, marked, not destroyed further

    def test_chaos_2_2_4_bom_stripped(self):
        assert strip_bom("﻿Customer_ID") == "Customer_ID"

    def test_clean_text_untouched(self):
        result = repair("Mohammed Al-Rashid")
        assert not result.repaired and not result.lossy


class TestScriptAndValues:
    def test_chaos_3_1_3_arabic_orthographic_profile(self):
        """Hamza variants, ta-marbuta, maqsura, tatweel and particle spacing
        all fold to one match key (FILE_2 §5.2)."""
        assert match_key("أحمد") == match_key("احمد")
        assert match_key("فاطمة") == match_key("فاطمه")
        assert match_key("مصطفى") == match_key("مصطفي")
        assert match_key("محمـــد") == match_key("محمد")
        assert match_key("عبد الله") == match_key("عبدالله")

    def test_chaos_2_2_6_confusables_fold_in_match_keys(self):
        assert match_key("Jоhn") == match_key("John")  # Cyrillic о

    def test_chaos_1_4_4_locale_split_numerics(self):
        """CHAOS-1.4.4: decimal convention inferred per column from
        unambiguous values, then applied uniformly."""
        eu = infer_decimal_convention(["1.234,56", "2.000,10"])
        assert eu.decimal_separator == ","
        assert parse_numeric("1.234,56", eu) == 1234.56
        us = infer_decimal_convention(["1,234.56", "2,000.10"])
        assert parse_numeric("1,234.56", us) == 1234.56

    def test_chaos_1_4_7_arabic_indic_digits_unify(self):
        us = infer_decimal_convention(["10.5"])
        assert parse_numeric("١٢٣٤", us) == 1234.0

    def test_chaos_2_3_3_phone_formatting_explosion_collapses(self):
        forms = ["+966 50 111 2222", "0501112222", "00966501112222",
                 "(050) 111-2222", "٠٥٠١١١٢٢٢٢"]
        keys = {canonical_phone(f) for f in forms}
        assert keys == {"+966501112222"}

    def test_chaos_1_4_6_boolean_babel(self):
        assert conform_boolean("Y") is True
        assert conform_boolean("نعم") is True
        assert conform_boolean("-1") is True
        assert conform_boolean("false") is False
