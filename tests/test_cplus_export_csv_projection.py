import csv
import io
import pytest
from app.exports_v2.csv_projection import render_showcase_csv


def test_csv_preserves_sources_review_states_and_disarms_formulas():
    report = {
        "schema_version": "showcase-report-v2",
        "report_id": "r",
        "revision": 3,
        "snapshot": {
            "findings": [
                {
                    "finding_id": "f",
                    "kind": "model_interpretation",
                    "text": ' \t=HYPERLINK("evil")',
                    "data_origin": "live",
                    "source_status": "current",
                    "interpretation_review_status": "ai_unreviewed",
                    "evidence_refs": [
                        {
                            "document_id": "d",
                            "source_revision": "rev",
                            "content_sha256": "a" * 64,
                            "physical_page": 3,
                            "text": "-123",
                        }
                    ],
                }
            ]
        },
    }
    result = render_showcase_csv(report, current_source_status="stale")
    assert result.startswith(b"\xef\xbb\xbf")
    row = list(csv.DictReader(io.StringIO(result.decode("utf-8-sig"))))[0]
    assert row["text"].startswith("'") and row["evidence_text"] == "'-123"
    assert row["current_source_status"] == "stale" and row["historical_snapshot"] == "True"
    assert row["interpretation_review_status"] == "ai_unreviewed" and row["physical_page"] == "3"
    assert row["period_kind"] == row["unit"] == row["value_decimal"] == ""
    with pytest.raises(ValueError, match="unsupported_report_schema"):
        render_showcase_csv(
            {**report, "schema_version": "legacy-v1"}, current_source_status="current"
        )
