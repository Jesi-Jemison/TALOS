"""Tests for the Streamlit-independent TALOS Python workflow."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import zipfile

import pandas as pd
import pytest

from src.workflow import TalosSession, TransformationPlan, inspect_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_CSV = PROJECT_ROOT / "data" / "sample" / "talos_demo.csv"


def test_from_csv_inspection_findings_score_and_summary():
    session = TalosSession.from_csv(DEMO_CSV)

    assert session.profile["file_name"] == "talos_demo.csv"
    assert session.profile["row_count"] == 161
    assert session.original_findings is None
    findings = session.inspect()

    assert set(findings) == {
        "missing",
        "duplicates",
        "categories",
        "outliers",
        "structure",
        "score",
    }
    assert session.original_findings["missing"]["total_missing_cells"] > 0
    assert session.working_findings["score"] == session.original_findings["score"]
    assert session.integrity_score == findings["score"]["score"]
    assert session.working_integrity_score == session.integrity_score
    assert "TALOS DATASET INSPECTION" in session.summary()
    assert "Rows:                 161" in session.summary()


def test_from_dataframe_protects_source_and_returns_defensive_snapshots():
    caller_frame = pd.DataFrame(
        {"region": ["north", "North"], "amount": [1.0, None]}
    )
    caller_before = caller_frame.copy(deep=True)
    session = TalosSession.from_dataframe(caller_frame, filename="orders.csv")

    caller_frame.loc[0, "region"] = "caller edit"
    assert session.original_df.loc[0, "region"] == "north"
    snapshot = session.working_df
    snapshot.loc[0, "region"] = "snapshot edit"
    assert session.working_df.loc[0, "region"] == "north"
    pd.testing.assert_frame_equal(caller_before, pd.DataFrame(
        {"region": ["north", "North"], "amount": [1.0, None]}
    ))
    assert session.profile["file_name"] == "orders.csv"


def test_original_and_working_dataframes_are_separate_and_inspection_is_shared():
    frame = pd.DataFrame({"state": ["nsw", "NSW", None]})
    original_snapshot = frame.copy(deep=True)
    session = TalosSession.from_dataframe(frame)
    source_findings = inspect_dataset(frame)

    result = session.inspect()

    assert result["score"] == source_findings["score"]
    assert result["missing"]["total_missing_cells"] == source_findings["missing"]["total_missing_cells"]
    assert result["categories"]["variant_groups"] == source_findings["categories"]["variant_groups"]
    assert session._original_df is not session._working_df
    pd.testing.assert_frame_equal(frame, original_snapshot)
    pd.testing.assert_frame_equal(session.original_df, session.working_df)


def test_text_preview_override_apply_ledger_reinspection_and_reset():
    frame = pd.DataFrame(
        {
            "region": ["north", "NORTH", "South", "south"],
            "membership_tier": ["gold", "GOLD", "Silver", "silver"],
        }
    )
    session = TalosSession.from_dataframe(frame)
    session.inspect()
    before = session.working_df
    plan = session.preview_text_normalisation(
        columns=["region", "membership_tier"],
        default_rule="proper",
        column_rules={"region": "UPPERCASE"},
        value_overrides={
            "region": {
                "north": {"mode": "rule", "rule": "Proper"},
                "NORTH": "North",
            }
        },
        trim_whitespace=True,
        collapse_spaces=True,
    )

    assert isinstance(plan, TransformationPlan)
    assert plan.operation == "normalize_text"
    assert plan.target_columns == ("region", "membership_tier")
    assert plan.affected_rows > 0
    assert plan.affected_values > 0
    assert plan.affected_cells > 0
    assert plan.parameters["actions"][0]["plan"]["global_rule"] == "Proper Case"
    assert not plan.examples.empty
    assert session.transformation_ledger == []
    pd.testing.assert_frame_equal(session.working_df, before)
    assert session.original_df.loc[0, "region"] == "north"

    session.apply(plan)
    assert session.needs_reinspection
    assert session.working_findings is None
    assert session.working_integrity_score is None
    assert len(session.transformation_ledger) == 1
    assert session.transformation_ledger[0]["parameters"]["operation"] == "normalize_text"
    assert session.working_df["region"].tolist() == ["North", "North", "SOUTH", "SOUTH"]

    working_findings = session.reinspect()
    assert not session.needs_reinspection
    assert session.working_findings["score"] == working_findings["score"]
    assert session.working_integrity_score == working_findings["score"]["score"]
    assert session.integrity_score == session.original_findings["score"]["score"]

    session.reset()
    assert not session.needs_reinspection
    assert session.transformation_ledger == []
    pd.testing.assert_frame_equal(session.original_df, session.working_df)
    assert session.working_integrity_score == session.integrity_score


def test_explicit_normalisation_of_identifier_like_text_warns_but_remains_opt_in():
    session = TalosSession.from_dataframe(
        pd.DataFrame({"customer_email": ["One@Example.com", "two@example.com"]})
    )
    plan = session.preview_text_normalisation(
        columns=["customer_email"], default_rule="lowercase"
    )

    assert any("identifier/free-text safeguards" in warning for warning in plan.warnings)
    assert session.transformation_ledger == []


def test_preview_is_revision_and_session_bound_and_does_not_mutate():
    session = TalosSession.from_dataframe(pd.DataFrame({"region": ["north", " north "]}))
    session.inspect()
    plan = session.preview({"type": "normalize_whitespace", "column": "region"})
    session.apply(plan)
    with pytest.raises(ValueError, match="stale"):
        session.apply(plan)

    other_session = TalosSession.from_dataframe(pd.DataFrame({"region": ["north"]}))
    with pytest.raises(ValueError, match="another TALOS session"):
        other_session.apply(plan)


@pytest.mark.parametrize(
    ("frame", "action", "expected_rows", "expected_columns"),
    [
        (
            pd.DataFrame({"region": [" north ", "south"]}),
            {"type": "normalize_whitespace", "column": "region"},
            2,
            1,
        ),
        (
            pd.DataFrame({"region": ["north", "NORTH", "south"]}),
            {
                "type": "consolidate_category",
                "column": "region",
                "variants": ["north", "NORTH"],
                "canonical_value": "North",
            },
            3,
            1,
        ),
        (
            pd.DataFrame({"record_id": [1, 1, 2], "value": ["a", "a", "b"]}),
            {"type": "remove_exact_duplicates"},
            2,
            2,
        ),
        (
            pd.DataFrame({"amount": [1.0, None, 3.0]}),
            {"type": "fill_numeric_missing", "column": "amount", "method": "median"},
            3,
            1,
        ),
        (
            pd.DataFrame({"status": ["open", None, "closed"]}),
            {"type": "fill_text_missing", "column": "status", "method": "mode"},
            3,
            1,
        ),
        (
            pd.DataFrame({"status": ["open", None, "closed"]}),
            {"type": "remove_rows_with_missing", "column": "status"},
            2,
            1,
        ),
        (
            pd.DataFrame({"status": ["open", "closed"], "empty": [None, None]}),
            {"type": "remove_empty_column", "column": "empty"},
            2,
            1,
        ),
    ],
)
def test_existing_transformations_can_be_previewed_and_applied(
    frame, action, expected_rows, expected_columns
):
    session = TalosSession.from_dataframe(frame)
    plan = session.preview(action)
    assert session.transformation_ledger == []
    assert len(session.working_df.index) == len(frame.index)

    result = session.apply(plan)

    assert len(result.index) == expected_rows
    assert len(result.columns) == expected_columns
    assert len(session.transformation_ledger) == 1
    pd.testing.assert_frame_equal(session.original_df, frame)


def test_export_methods_write_reports_tables_and_evidence_pack(tmp_path):
    session = TalosSession.from_csv(DEMO_CSV)
    session.inspect()
    plan = session.preview({"type": "normalize_whitespace", "column": "region"})
    session.apply(plan)
    session.reinspect()

    cleaned = session.export_cleaned_csv(tmp_path / "nested" / "cleaned.csv")
    ledger = session.export_transformation_log(tmp_path / "nested" / "ledger.csv")
    html = session.export_html_report(tmp_path / "nested" / "report.html")
    pdf = session.export_pdf_report(tmp_path / "nested" / "report.pdf")
    tables = session.export_evidence_tables(tmp_path / "nested" / "tables")
    pack = session.export_evidence_pack(tmp_path / "nested" / "evidence.zip")

    assert cleaned.is_file() and pd.read_csv(cleaned).equals(session.working_df)
    assert ledger.is_file() and "Transformation type" in ledger.read_text(encoding="utf-8")
    assert "TALOS" in html.read_text(encoding="utf-8")
    assert pdf.read_bytes().startswith(b"%PDF")
    assert tables and any(path.name == "before_after_comparison.csv" for path in tables)
    assert any(path.name.startswith("working_") for path in tables)
    with zipfile.ZipFile(pack) as archive:
        members = set(archive.namelist())
    assert "talos_evidence_pack/inspection_report.html" in members
    assert "talos_evidence_pack/inspection_report.pdf" in members
    assert "talos_evidence_pack/cleaned_dataset.csv" in members
    assert "talos_evidence_pack/transformation_ledger.csv" in members
    assert "talos_evidence_pack/working_missing_values.csv" in members


def test_evidence_tables_include_comparisons_before_repairs(tmp_path):
    session = TalosSession.from_dataframe(pd.DataFrame({"city": ["Oslo", "Paris"]}))
    paths = session.export_evidence_tables(tmp_path / "tables")

    assert any(path.name == "before_after_comparison.csv" for path in paths)
    assert any(path.name == "score_comparison.csv" for path in paths)
    assert not any(path.name.startswith("working_") for path in paths)


def test_core_workflow_import_and_operations_do_not_import_streamlit(tmp_path):
    code = """
import sys
import pandas as pd
from src.workflow import TalosSession
session = TalosSession.from_dataframe(pd.DataFrame({'state': ['nsw', 'NSW']}))
session.inspect()
session.export_html_report(sys.argv[1])
assert 'streamlit' not in sys.modules
assert 'app' not in sys.modules
print(session.integrity_score)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "core-report.html")],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip()
