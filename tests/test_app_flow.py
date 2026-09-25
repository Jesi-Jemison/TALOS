"""Streamlit integration checks for TALOS's session workflow."""

from pathlib import Path
import hashlib

import pandas as pd
from streamlit.testing.v1 import AppTest

from app import (
    build_guardian_summary,
    build_header_visual_html,
    inspect_dataset,
    outlier_widget_key,
    repair_selection_key,
)
from src.transformations import build_suggested_transformations


APP_PATH = "../app.py"


def test_landing_keeps_the_upload_demo_path_and_guardian_identity():
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()

    assert not app.exception
    assert app.button(key="talos-load-demo").label == "Load TALOS demo dataset"
    assert any(item.value == "The gate is open." for item in app.subheader)
    assert any(
        'alt="TALOS bronze automaton guardian with illuminated amethyst eyes"' in item.value
        for item in app.markdown
    )
    assert any("Raw data enters. Nothing passes unchecked." in item.value for item in app.markdown)
    assert any("GUARDIAN ACTIVE" in item.value for item in app.markdown)


def test_selected_repairs_require_approval_reinspect_and_reset():
    csv = b"""region,amount,record_id,empty_field
north ,10,1,
south,20,2,
east,30,3,
west,40,4,
north,50,5,
south,60,6,
east,70,7,
west,80,8,
north,90,9,
north ,10,1,
central,,11,
"""
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.radio(key="talos_theme_preference").set_value("Light").run()
    app.file_uploader[0].set_value(("orders.csv", csv, "text/csv"))
    app.run()

    assert not app.exception
    assert app.session_state["talos_theme_preference"] == "Light"
    assert any("--talos-bg: #F3EEE4" in item.value for item in app.markdown)
    assert any(
        'alt="TALOS bronze automaton guardian with illuminated amethyst eyes"' in element.value
        for element in app.markdown
    )
    assert "👁️ Guardian Summary" in {item.value for item in app.subheader}
    assert "🛡️ Dataset Integrity Score" in {item.value for item in app.subheader}
    assert any("Source received" in item.value for item in app.markdown)
    assert any('class="talos-inspection-status"' in item.value for item in app.markdown)
    expander_labels = {item.label for item in app.get("expander")}
    assert any("Missing Data ·" in label for label in expander_labels)
    assert any("Numeric Outliers ·" in label for label in expander_labels)
    assert any("Repair Control Center ·" in label for label in expander_labels)
    assert any("Detailed evidence exports ·" in label for label in expander_labels)
    collapsed_sections = (
        "Score components",
        "Dataset Overview & Structure",
        "Data Preview",
        "Missing Data ·",
        "Duplicate Inspection ·",
        "Category Consistency ·",
        "Numeric Outliers ·",
        "Structural & Identifier Checks ·",
        "Repair Control Center ·",
        "Detailed evidence exports ·",
    )
    for section in collapsed_sections:
        element = next(item for item in app.get("expander") if section in item.label)
        assert element.proto.expanded is False
    original = app.session_state["talos_original_df"].copy(deep=True)
    assert original.equals(app.session_state["talos_working_df"])
    assert app.session_state["talos_transformation_ledger"] == []
    assert {item.label for item in app.get("download_button")} >= {
        "Download cleaned CSV",
        "Download transformation log",
        "Download HTML report",
        "missing_values.csv",
        "structure.csv",
        "before_after_comparison.csv",
    }

    missing_key = "talos_missing_strategy_" + hashlib.sha256(b"amount").hexdigest()[:16]
    app.selectbox(key=missing_key).select("Fill with median").run()
    duplicate_key = repair_selection_key("remove_exact_duplicates")
    app.checkbox(key=duplicate_key).check().run()

    # Selections only prepare the plan. The active copy and ledger are unchanged.
    pd.testing.assert_frame_equal(original, app.session_state["talos_working_df"])
    assert app.session_state["talos_transformation_ledger"] == []
    assert any(item.value == "Repair Plan" for item in app.subheader)

    app.button(key="talos-apply-selected-repairs").click().run()
    assert not app.exception
    working = app.session_state["talos_working_df"]
    assert pd.isna(original.loc[10, "amount"])
    assert working.loc[10, "amount"] == 45.0
    assert len(original) == 11
    assert len(working) == 10
    assert [item["parameters"]["operation"] for item in app.session_state["talos_transformation_ledger"]] == [
        "fill_numeric_missing",
        "remove_exact_duplicates",
    ]
    assert app.session_state["talos_working_findings"]["missing"]["total_missing_cells"] < app.session_state[
        "talos_original_findings"
    ]["missing"]["total_missing_cells"]
    assert app.session_state["talos_working_findings"]["duplicates"][
        "exact_duplicate_row_count"
    ] == 0
    assert app.session_state["talos_working_findings"]["categories"][
        "inconsistent_group_count"
    ] > 0
    assert "north " in set(working["region"])
    assert app.session_state["talos_original_df"].equals(original)
    assert any("finding group(s) remain visible" in item.value for item in app.warning)

    app.button(key="reset-working-copy").click().run()
    app.button(key="confirm-reset").click().run()
    assert not app.exception
    pd.testing.assert_frame_equal(
        app.session_state["talos_working_df"], app.session_state["talos_original_df"]
    )
    assert app.session_state["talos_transformation_ledger"] == []
    assert app.session_state["talos_theme_preference"] == "Light"

    replacement_csv = b"city,count\nSydney,3\n"
    app.file_uploader[0].set_value(("replacement.csv", replacement_csv, "text/csv"))
    app.run()
    assert not app.exception
    assert len(app.session_state["talos_original_df"]) == 1
    pd.testing.assert_frame_equal(
        app.session_state["talos_original_df"], app.session_state["talos_working_df"]
    )
    assert app.session_state["talos_transformation_ledger"] == []
    assert app.session_state["talos_theme_preference"] == "Light"


def test_demo_mode_uses_standard_upload_inspection_pipeline_and_can_clear():
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.button(key="talos-load-demo").click().run()

    assert not app.exception
    expected = pd.read_csv(Path(__file__).parent.parent / "data/sample/talos_demo.csv")
    pd.testing.assert_frame_equal(
        app.session_state["talos_original_df"], expected, check_dtype=False
    )
    assert app.session_state["talos_demo_loaded"] is True
    findings = app.session_state["talos_original_findings"]
    assert findings["missing"]["total_missing_cells"] > 0
    assert findings["duplicates"]["exact_duplicate_row_count"] > 0
    assert findings["categories"]["inconsistent_group_count"] > 0
    assert findings["outliers"]["total_outlier_values"] > 0
    assert findings["structure"]["empty_columns"]
    assert findings["structure"]["constant_columns"]
    pd.testing.assert_frame_equal(
        app.session_state["talos_original_df"], app.session_state["talos_working_df"]
    )

    app.button(key="talos-clear-demo").click().run()
    assert not app.exception
    assert app.session_state["talos_demo_loaded"] is False
    assert "talos_original_df" not in app.session_state


def test_text_normalisation_requires_approval_and_updates_only_the_working_copy():
    csv = b"status\nopen\nOPEN\nclosed\n"
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.file_uploader[0].set_value(("status.csv", csv, "text/csv")).run()

    original = app.session_state["talos_original_df"].copy(deep=True)
    pd.testing.assert_frame_equal(app.session_state["talos_working_df"], original)
    app.selectbox(key="talos_text_global_rule").select("UPPERCASE").run()
    assert not app.exception
    assert "Repair Plan" in {item.value for item in app.subheader}
    pd.testing.assert_frame_equal(app.session_state["talos_working_df"], original)
    assert app.session_state["talos_transformation_ledger"] == []

    app.button(key="talos-apply-selected-repairs").click().run()
    assert not app.exception
    assert app.session_state["talos_original_df"]["status"].tolist() == [
        "open", "OPEN", "closed"
    ]
    assert app.session_state["talos_working_df"]["status"].tolist() == [
        "OPEN", "OPEN", "CLOSED"
    ]
    assert app.session_state["talos_transformation_ledger"][-1]["parameters"]["operation"] == "normalize_text"


def test_optional_pdf_is_prepared_on_demand_and_appears_in_downloads():
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.button(key="talos-load-demo").click().run()

    assert app.session_state.get("talos_cached_report_pdf") is None
    app.button(key="prepare-inspection-report-pdf").click().run()

    assert not app.exception
    pdf = app.session_state["talos_cached_report_pdf"]
    assert pdf.startswith(b"%PDF-")
    assert app.session_state["talos_cached_report_pdf_revision"] == app.session_state[
        "talos_data_revision"
    ]
    assert app.download_button(key="download-inspection-report-pdf").label == "Download PDF report"


def test_category_variant_group_can_be_selected_and_applied_alone():
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.button(key="talos-load-demo").click().run()
    original = app.session_state["talos_original_df"].copy(deep=True)

    category_ids = [
        str(item["suggestion_id"])
        for item in build_suggested_transformations(
            original, app.session_state["talos_original_findings"]
        )
        if item["action"]["type"] == "consolidate_category"
    ]
    app.button(key="talos-select-category-repairs").click().run()
    assert all(
        app.session_state[repair_selection_key(repair_id)] for repair_id in category_ids
    )
    app.button(key="talos-clear-repairs").click().run()
    assert not any(
        app.session_state[repair_selection_key(repair_id)] for repair_id in category_ids
    )

    group_id = "category:region:north"
    app.checkbox(key=repair_selection_key(group_id)).check().run()
    assert not app.exception
    pd.testing.assert_frame_equal(original, app.session_state["talos_working_df"])
    assert app.session_state["talos_transformation_ledger"] == []

    manager_key = "talos_missing_strategy_" + hashlib.sha256(
        b"account_manager"
    ).hexdigest()[:16]
    manager_options = list(app.selectbox(key=manager_key).options)
    assert "Fill with custom text" in manager_options
    assert "Fill with mean" not in manager_options
    assert "Fill with median" not in manager_options

    app.button(key="talos-apply-selected-repairs").click().run()
    working = app.session_state["talos_working_df"]
    assert set(working.loc[original["region"].str.strip().str.casefold() == "north", "region"]) == {
        "North"
    }
    assert working.loc[original["region"].str.strip().str.casefold() == "south", "region"].tolist() == original.loc[
        original["region"].str.strip().str.casefold() == "south", "region"
    ].tolist()
    assert len(app.session_state["talos_transformation_ledger"]) == 1
    assert app.session_state["talos_transformation_ledger"][0]["parameters"][
        "canonical_value"
    ] == "North"


def test_evidence_pack_is_created_on_demand_with_applicable_outputs():
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.button(key="talos-load-demo").click().run()
    app.button(key="prepare-evidence-pack").click().run()

    assert not app.exception
    from io import BytesIO
    from zipfile import ZipFile

    with ZipFile(BytesIO(app.session_state["talos_cached_evidence_pack"])) as archive:
        members = set(archive.namelist())
        assert "talos_evidence_pack/README.txt" in members
        assert "talos_evidence_pack/inspection_report.html" in members
        assert "talos_evidence_pack/cleaned_dataset.csv" in members
        assert "talos_evidence_pack/structure.csv" in members
        assert "talos_evidence_pack/missing_values.csv" in members
        assert "talos_evidence_pack/duplicate_rows.csv" in members
        assert "talos_evidence_pack/category_variants.csv" in members
        assert "talos_evidence_pack/outliers.csv" in members
        assert "talos_evidence_pack/integrity_score.csv" in members
        assert "talos_evidence_pack/transformation_ledger.csv" not in members
        assert "talos_evidence_pack/working_missing_values.csv" not in members
        report = archive.read("talos_evidence_pack/inspection_report.html").decode("utf-8")
        assert "Report created" in report
        assert "The original uploaded DataFrame was not mutated" in report


def test_empty_and_malformed_uploads_show_readable_feedback():
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.file_uploader[0].set_value(("empty.csv", b"", "text/csv"))
    app.run()
    assert not app.exception

    app.file_uploader[0].set_value(
        ("malformed.csv", b'a,b\n1,"unterminated\n', "text/csv")
    )
    app.run()
    assert not app.exception
    assert any("could not read" in alert.value.lower() for alert in app.error)


def test_guardian_summary_uses_existing_findings_and_qualifies_signals():
    demo = pd.read_csv(Path(__file__).parent.parent / "data/sample/talos_demo.csv")
    findings = inspect_dataset(demo)
    summary = {item["area"]: item for item in build_guardian_summary(findings)}

    assert "3 fields contain missing values" in summary["Missing values"]["message"]
    assert "review the matches before removal" in summary["Duplicates & identifiers"]["message"]
    assert "7 category variant groups" in summary["Category consistency"]["message"]
    assert "31 values fall" in summary["Numeric distribution"]["message"]
    assert "cannot determine their intended role" in summary["Structure"]["message"]
    assert summary["Missing values"]["status"] == "Significant finding"
    assert summary["Duplicates & identifiers"]["status"] == "Review recommended"
    assert summary["Numeric distribution"]["status"] == "Observation"
    assert {item["status"] for item in summary.values()} >= {
        "Observation",
        "Review recommended",
        "Significant finding",
    }


def test_manual_column_removal_waits_for_approval_reinspects_and_can_reset():
    rows = [f"r{index},note {index},{index}" for index in range(10)]
    csv = ("record_id,notes,amount\n" + "\n".join(rows) + "\n").encode()
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.file_uploader[0].set_value(("manual-columns.csv", csv, "text/csv")).run()
    original = app.session_state["talos_original_df"].copy(deep=True)

    assert app.multiselect(key="talos_manual_column_remove").value == []
    app.multiselect(key="talos_manual_column_remove").set_value(["notes", "record_id"]).run()
    assert not app.exception
    assert app.session_state["talos_working_df"].columns.tolist() == ["record_id", "notes", "amount"]
    assert app.session_state["talos_transformation_ledger"] == []
    assert any(item.value == "Repair Plan" for item in app.subheader)
    assert any("Current columns: 3" in item.value and "After repair: 1 column" in item.value for item in app.markdown)

    app.button(key="talos-apply-selected-repairs").click().run()
    assert not app.exception
    assert app.session_state["talos_working_df"].columns.tolist() == ["amount"]
    assert app.session_state["talos_transformation_ledger"][-1]["parameters"]["columns_removed"] == ["notes", "record_id"]
    assert app.session_state["talos_working_findings"]["structure"] == inspect_dataset(app.session_state["talos_working_df"])["structure"]
    pd.testing.assert_frame_equal(app.session_state["talos_original_df"], original)

    app.button(key="reset-working-copy").click().run()
    app.button(key="confirm-reset").click().run()
    pd.testing.assert_frame_equal(app.session_state["talos_working_df"], original)
    assert app.session_state["talos_transformation_ledger"] == []


def test_column_removal_refuses_to_remove_every_field():
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.file_uploader[0].set_value(("two-columns.csv", b"left,right\na,b\nc,d\n", "text/csv")).run()
    app.multiselect(key="talos_manual_column_remove").set_value(["left", "right"]).run()
    assert not app.exception
    assert any("Keep at least one column" in alert.value for alert in app.error)
    assert app.session_state["talos_working_df"].columns.tolist() == ["left", "right"]
    assert app.session_state["talos_transformation_ledger"] == []


def test_outlier_remediation_per_column_requires_approval_and_reinspects():
    values = list(range(1, 11)) + [100, 200]
    csv = ("amount,volume\n" + "\n".join(f"{value},{value * 2}" for value in values) + "\n").encode()
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.file_uploader[0].set_value(("outliers.csv", csv, "text/csv")).run()
    original = app.session_state["talos_original_df"].copy(deep=True)
    assert app.session_state["talos_original_findings"]["outliers"]["total_outlier_values"] == 4

    assert app.selectbox(key=outlier_widget_key("amount")).value == "Leave unchanged"
    app.selectbox(key=outlier_widget_key("amount")).select("Replace with median").run()
    assert not app.exception
    pd.testing.assert_frame_equal(app.session_state["talos_working_df"], original)
    assert app.session_state["talos_transformation_ledger"] == []
    assert any("5.5" in item.value for item in app.markdown)
    assert any(item.value == "Repair Plan" for item in app.subheader)

    app.button(key="talos-apply-selected-repairs").click().run()
    assert not app.exception
    assert app.session_state["talos_working_df"]["amount"].tolist()[-2:] == [5.5, 5.5]
    assert app.session_state["talos_working_findings"]["outliers"]["total_outlier_values"] == 2
    assert all(
        item["column"] != "amount" or item["outlier_count"] == 0
        for item in app.session_state["talos_working_findings"]["outliers"]["columns"]
    )
    assert any(
        item["column"] == "volume" and item["outlier_count"] == 2
        for item in app.session_state["talos_working_findings"]["outliers"]["columns"]
    )
    record = app.session_state["talos_transformation_ledger"][-1]
    assert record["parameters"]["operation"] == "remediate_outliers"
    assert record["parameters"]["columns"][0]["strategy"] == "median"
    pd.testing.assert_frame_equal(app.session_state["talos_original_df"], original)

    app.button(key="reset-working-copy").click().run()
    app.button(key="confirm-reset").click().run()
    pd.testing.assert_frame_equal(app.session_state["talos_working_df"], original)
    assert app.session_state["talos_transformation_ledger"] == []


def test_guardian_summary_reports_a_clean_dataset_without_false_findings():
    clean = pd.DataFrame(
        {"region": ["north", "south"] * 15, "amount": list(range(1, 31))}
    )
    summary = build_guardian_summary(inspect_dataset(clean))

    assert len(summary) == 5
    assert all(item["status"] == "Clear" for item in summary)
    assert all("No " in item["message"] for item in summary)


def test_header_visual_uses_wide_art_and_falls_back_to_the_compact_emblem(tmp_path):
    assets = Path(__file__).parent.parent / "assets"
    visual = build_header_visual_html(assets)
    assert 'alt="TALOS bronze automaton guardian with illuminated amethyst eyes"' in visual
    assert "data:image/webp;base64," in visual

    fallback_assets = tmp_path / "assets"
    fallback_assets.mkdir()
    (fallback_assets / "talos-emblem.svg").write_text(
        (assets / "talos-emblem.svg").read_text(encoding="utf-8"), encoding="utf-8"
    )
    fallback = build_header_visual_html(fallback_assets)
    assert 'alt="TALOS bronze guardian emblem"' in fallback
    assert "talos-sentinel-panel--fallback" in fallback
