"""Tests for TALOS CSV exports and printable HTML inspection reports."""
# TALOS FILE VERSION: v1.2.0

from io import BytesIO
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

from src.profiler import profile_dataset
from src.quality_checks import (
    inspect_category_consistency,
    inspect_duplicates,
    inspect_missing_values,
    inspect_numeric_outliers,
    inspect_structure,
)
from src.reporting import (
    TRANSFORMATION_LOG_COLUMNS,
    build_cleaned_csv,
    build_cleaned_excel,
    build_export_filename,
    build_inspection_report_html,
    build_inspection_report_pdf,
    build_transformation_log,
)
from src.scoring import calculate_integrity_score
from src.transformations import apply_transformation, build_text_normalisation_plan


def build_findings(df):
    """Run the project's existing checks and score for report fixtures."""
    missing = inspect_missing_values(df)
    duplicates = inspect_duplicates(df)
    categories = inspect_category_consistency(df)
    outliers = inspect_numeric_outliers(df)
    structure = inspect_structure(df)
    score = calculate_integrity_score(
        df, missing, duplicates, categories, outliers, structure
    )
    return {
        "missing": missing,
        "duplicates": duplicates,
        "categories": categories,
        "outliers": outliers,
        "structure": structure,
        "score": score,
    }


def build_report_inputs(filename="customer_data.csv"):
    """Create a small, intentionally imperfect source dataset and report inputs."""
    df = pd.DataFrame(
        {
            "region": ["Sydney", "SYDNEY", "north", "south", "west", "east", "west", "east", "north", None],
            "sales": [10, 11, 12, 13, 14, 15, 16, 17, 18, 1000],
            "record_id": list(range(1, 11)),
            "empty_field": [None] * 10,
            "status": ["active"] * 10,
        }
    )
    findings = build_findings(df)
    profile = profile_dataset(df, filename, 820)
    summary = {
        "row_count": len(df),
        "column_count": len(df.columns),
        "missing_cells": findings["missing"]["total_missing_cells"],
        "duplicate_rows": findings["duplicates"]["exact_duplicate_row_count"],
        "score": findings["score"]["score"],
    }
    return df, findings, profile, summary


def test_export_filenames_are_predictable_and_strip_path_components():
    assert build_export_filename("/private/folder/orders.csv", "cleaned") == "orders_talos_cleaned.csv"
    assert build_export_filename("C:\\upload\\orders.csv", "transformations") == "orders_talos_transformations.csv"
    assert build_export_filename(".csv", "report") == "dataset_talos_report.html"
    assert build_export_filename("orders.csv", "working-missing") == "orders_talos_working_missing_values.csv"
    assert build_export_filename("orders.csv", "pdf_report") == "orders_talos_report.pdf"


def test_cleaned_csv_contains_dataframe_without_index_and_is_utf8():
    working = pd.DataFrame({"name": ["Málaga"], "value": [3]})
    working.index = [47]

    exported = build_cleaned_csv(working)
    round_trip = pd.read_csv(BytesIO(exported))

    assert exported.decode("utf-8").startswith("name,value\n")
    assert "Unnamed" not in round_trip.columns[0]
    pd.testing.assert_frame_equal(round_trip, pd.DataFrame({"name": ["Málaga"], "value": [3]}))


def test_cleaned_csv_exports_approved_working_copy_without_touching_original():
    original = pd.DataFrame({"region": ["Sydney", "SYDNEY"], "value": [1, 2]})
    original_copy = original.copy(deep=True)
    working, _ = apply_transformation(
        original,
        {
            "type": "consolidate_category",
            "column": "region",
            "variants": ["Sydney", "SYDNEY"],
            "canonical_value": "Sydney",
        },
    )

    exported = pd.read_csv(BytesIO(build_cleaned_csv(working)))

    assert exported["region"].tolist() == ["Sydney", "Sydney"]
    pd.testing.assert_frame_equal(original, original_copy)


def test_cleaned_excel_keeps_a_named_sheet_and_export_filename():
    working = pd.DataFrame({"deity": ["Athena"], "count": [1]})
    exported = build_cleaned_excel(working, "Inspection Data")
    round_trip = pd.read_excel(BytesIO(exported), sheet_name="Inspection Data")

    pd.testing.assert_frame_equal(round_trip, working)
    assert build_export_filename("/private/myth.xlsx", "cleaned_excel") == "myth_talos_cleaned.xlsx"


def test_reports_name_selected_worksheet_and_summarise_only_different_text_overrides():
    original = pd.DataFrame({"status": ["OPEN", "special value", "CLOSED"]})
    findings = build_findings(original)
    profile = profile_dataset(original, "status.xlsx", 1024, "Inspection Data")
    summary = {
        "row_count": len(original),
        "column_count": len(original.columns),
        "missing_cells": findings["missing"]["total_missing_cells"],
        "duplicate_rows": findings["duplicates"]["exact_duplicate_row_count"],
        "score": findings["score"]["score"],
    }
    plan = build_text_normalisation_plan(
        original,
        "lowercase",
        ["status"],
        column_rules={"status": "Proper Case"},
        value_overrides={
            "status": {
                "special value": {
                    "mode": "custom",
                    "value": "PRIVATE_CANONICAL_VALUE",
                }
            }
        },
    )
    working, record = apply_transformation(
        original,
        {"type": "normalize_text", "plan": plan},
    )
    working_findings = build_findings(working)
    working_summary = {
        "row_count": len(working),
        "column_count": len(working.columns),
        "missing_cells": working_findings["missing"]["total_missing_cells"],
        "duplicate_rows": working_findings["duplicates"]["exact_duplicate_row_count"],
        "score": working_findings["score"]["score"],
    }
    report = build_inspection_report_html(
        profile, findings, working_findings, summary, working_summary, [record]
    )

    assert "Inspection Data" in report
    assert "Proper Case" in report
    assert "custom canonical values" in report
    assert "status" in report
    assert "PRIVATE_CANONICAL_VALUE" not in report
    assert "special value" not in report


def test_transformation_log_has_stable_columns_and_serializes_parameters():
    ledger = [
        {
            "transformation_type": "Numeric imputation",
            "column": "revenue",
            "affected_rows": 2,
            "description": "Filled missing values with 12.5.",
            "parameters": {"method": "custom", "fill_value": 12.5},
            "before_after": [{"before": "(missing)", "after": 12.5}],
            "rows_before": 8,
            "rows_after": 8,
            "columns_before": 3,
            "columns_after": 3,
        }
    ]

    log = build_transformation_log(ledger)

    assert list(log.columns) == TRANSFORMATION_LOG_COLUMNS
    assert log.loc[0, "Affected rows"] == 2
    assert '"method": "custom"' in log.loc[0, "Parameters"]
    assert '"after": 12.5' in log.loc[0, "Before and after"]
    assert list(build_transformation_log([]).columns) == TRANSFORMATION_LOG_COLUMNS
    exported_log = pd.read_csv(BytesIO(log.to_csv(index=False).encode("utf-8")))
    assert list(exported_log.columns) == TRANSFORMATION_LOG_COLUMNS
    assert not any(column.startswith("Unnamed") for column in exported_log.columns)


def test_html_report_contains_profile_findings_score_ledger_and_embedded_emblem():
    original, findings, profile, summary = build_report_inputs()
    working = original.drop(columns=["empty_field"]).copy(deep=True)
    working_findings = build_findings(working)
    working_summary = {
        "row_count": len(working),
        "column_count": len(working.columns),
        "missing_cells": working_findings["missing"]["total_missing_cells"],
        "duplicate_rows": working_findings["duplicates"]["exact_duplicate_row_count"],
        "score": working_findings["score"]["score"],
    }
    ledger = [
        {
            "transformation_type": "Remove empty column",
            "column": "empty_field",
            "affected_rows": 0,
            "description": "Removed the empty column.",
            "parameters": {"column": "empty_field"},
            "before_after": [{"before": "empty_field", "after": "(column removed)"}],
            "rows_before": 10,
            "rows_after": 10,
            "columns_before": 5,
            "columns_after": 4,
        }
    ]

    report = build_inspection_report_html(
        profile,
        findings,
        working_findings,
        summary,
        working_summary,
        ledger,
        emblem_svg='<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>',
    )

    assert "TALOS" in report
    assert "INSPECTION DOSSIER" in report
    assert "customer_data.csv" in report
    assert "Dataset Integrity Score" in report
    assert "A TALOS heuristic summarising the signals detected" in report
    assert "Missing values" in report
    assert "Category variants" in report
    assert "Numeric outliers" in report
    assert "Remove empty column" in report
    assert "Before and after examples" in report
    assert "Working Copy Reinspection" in report
    assert 'alt="TALOS bronze guardian emblem"' in report
    assert "data:image/svg+xml;base64," in report
    assert "Before / After the Forge" in report
    HTMLParser().feed(report)
    assert "table-layout: auto" in report
    assert "overflow-wrap: break-word" in report
    assert "white-space: nowrap" in report
    assert ".talos-table-wrap--wide table" in report


def test_html_report_handles_no_transformations_and_escapes_uploaded_names():
    df, findings, profile, summary = build_report_inputs("customer <report>.csv")
    report = build_inspection_report_html(
        profile,
        findings,
        findings,
        summary,
        summary,
        [],
    )

    assert "No repairs were approved" in report
    assert "customer &lt;report&gt;.csv" in report
    assert "customer <report>.csv" not in report
    assert "The original uploaded dataset remains unchanged" in report


def test_html_report_includes_row_evidence_creation_note_and_escapes_cell_values():
    original, findings, profile, summary = build_report_inputs()
    evidence_tables = {
        "outliers.csv": pd.DataFrame(
            {
                "Column": ["<script>alert(1)</script>"],
                "Value": [1000],
                "Source row (1-based)": [10],
            }
        )
    }
    report = build_inspection_report_html(
        profile,
        findings,
        findings,
        summary,
        summary,
        [],
        original_evidence_tables=evidence_tables,
        created_at="2026-09-25T00:00:00+00:00",
    )

    assert "2026-09-25T00:00:00+00:00" in report
    assert "Flagged numeric values" in report
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in report
    assert "<script>alert(1)</script>" not in report
    assert "Fewer signals mean fewer findings under TALOS's rules" in report


def test_pdf_report_is_generated_as_a_printable_standalone_document():
    original, findings, profile, summary = build_report_inputs()
    working = original.drop(columns=["empty_field"]).copy(deep=True)
    working_findings = build_findings(working)
    working_summary = {
        **summary,
        "column_count": len(working.columns),
        "missing_cells": working_findings["missing"]["total_missing_cells"],
        "duplicate_rows": working_findings["duplicates"]["exact_duplicate_row_count"],
        "score": working_findings["score"]["score"],
    }
    pdf = build_inspection_report_pdf(
        profile,
        findings,
        working_findings,
        summary,
        working_summary,
        [],
        created_at="2026-09-25T00:00:00+00:00",
    )

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) < 1_000_000


def test_pdf_is_an_aggregate_report_with_dynamic_summary_repairs_and_guardian_header():
    from pypdf import PdfReader

    original, findings, profile, summary = build_report_inputs()
    working = original.drop(columns=["empty_field", "status"]).copy(deep=True)
    working_findings = build_findings(working)
    working_summary = {
        **summary,
        "column_count": len(working.columns),
        "missing_cells": working_findings["missing"]["total_missing_cells"],
        "duplicate_rows": working_findings["duplicates"]["exact_duplicate_row_count"],
        "score": working_findings["score"]["score"],
    }
    ledger = [
        {
            "transformation_type": "Remove selected columns",
            "column": "empty_field, status",
            "action": "Remove selected columns",
            "affected_rows": 0,
            "parameters": {
                "operation": "remove_columns",
                "columns_removed": ["empty_field", "status"],
                "columns_removed_count": 2,
            },
            "before_after": [],
        },
        {
            "transformation_type": "IQR outlier remediation",
            "column": "sales, score",
            "action": "IQR outlier remediation",
            "affected_rows": 1,
            "parameters": {
                "operation": "remediate_outliers",
                "columns": [
                    {"column": "sales", "strategy": "median", "outlier_count": 1},
                    {"column": "score", "strategy": "blank", "outlier_count": 2},
                ],
            },
            "before_after": [],
        },
    ]
    evidence = {
        "outliers.csv": pd.DataFrame(
            {"Column": ["sales"], "Source row (1-based)": [987654321], "Value": ["ROW-LEVEL-PRIVATE-MARKER"]}
        ),
        "duplicate_rows.csv": pd.DataFrame(
            {"Source row (1-based)": [123456789], "Value": ["ANOTHER-ROW-MARKER"]}
        ),
    }
    pdf = build_inspection_report_pdf(
        profile,
        findings,
        working_findings,
        summary,
        working_summary,
        ledger,
        guardian_image=(Path(__file__).parent.parent / "assets/talos-sentinel-panel.webp").read_bytes(),
        original_evidence_tables=evidence,
        working_evidence_tables=evidence,
        created_at="2026-09-25T00:00:00+00:00",
    )
    reader = PdfReader(BytesIO(pdf))
    text = " ".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)

    assert pdf.startswith(b"%PDF-")
    assert len(reader.pages) >= 2
    assert reader.pages[0].images
    assert "Inspection Summary" in text
    assert "10 rows entered inspection across 5 fields" in text
    assert "approved changes were committed to the working copy" in text
    assert "Integrity moved from" in text
    assert "Repairs Applied" in text
    assert "Remaining Signals" in text
    assert "2 columns removed" in text
    assert "1 outlier in sales was replaced using the non-outlier median" in text
    assert "Detailed Aggregate Findings" in text
    assert "Minor Observations" not in text
    assert "ROW-LEVEL-PRIVATE-MARKER" not in text
    assert "ANOTHER-ROW-MARKER" not in text
    assert "987654321" not in text


def test_pdf_without_repairs_says_the_working_copy_matches_the_source():
    from pypdf import PdfReader

    original, findings, profile, summary = build_report_inputs()
    pdf = build_inspection_report_pdf(
        profile,
        findings,
        findings,
        summary,
        summary,
        [],
        created_at="2026-09-25T00:00:00+00:00",
    )
    text = " ".join(" ".join((page.extract_text() or "").split()) for page in PdfReader(BytesIO(pdf)).pages)
    assert "No repairs were approved" in text
    assert "working copy still matches the source" in text


def test_pdf_ignores_large_row_level_evidence_tables():
    from pypdf import PdfReader

    original, findings, profile, summary = build_report_inputs()
    many_rows = pd.DataFrame(
        {"Source row (1-based)": range(1, 1001), "Value": ["ROW-DETAIL"] * 1000}
    )
    pdf = build_inspection_report_pdf(
        profile,
        findings,
        findings,
        summary,
        summary,
        [],
        original_evidence_tables={"outliers.csv": many_rows},
        working_evidence_tables={"duplicate_rows.csv": many_rows},
        created_at="2026-09-25T00:00:00+00:00",
    )
    text = " ".join(" ".join((page.extract_text() or "").split()) for page in PdfReader(BytesIO(pdf)).pages)
    assert len(pdf) < 1_000_000
    assert "ROW-DETAIL" not in text
    assert "1000" not in text
