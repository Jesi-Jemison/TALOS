"""Streamlit integration checks for TALOS's session workflow."""
# TALOS FILE VERSION: v1.2.0

from pathlib import Path
from io import BytesIO
import hashlib

import pandas as pd
from streamlit.testing.v1 import AppTest

from app import (
    build_guardian_summary,
    build_header_visual_html,
    inspect_dataset,
    outlier_widget_key,
    repair_selection_key,
    text_widget_key,
)
from src.transformations import build_suggested_transformations


APP_PATH = "../app.py"


def go_to_forge(app):
    """Navigate from First Watch to the pre-clean approval stage."""
    if app.session_state.get("talos_flow_step") == 1:
        app.button(key="talos-firstwatch-to-forge").click().run()


def go_to_range_watch(app):
    """Skip optional pre-clean actions and open the fresh inspection stage."""
    step = app.session_state.get("talos_flow_step", 1)
    if step == 1:
        app.button(key="talos-firstwatch-skip-forge").click().run()
    elif step == 2:
        app.button(key="talos-skip-preclean").click().run()


def go_to_evidence(app):
    """Move from the current review stage to the Evidence Vault."""
    go_to_range_watch(app)
    if app.session_state.get("talos_flow_step") == 3:
        app.button(key="talos-range-to-evidence").click().run()


def test_landing_keeps_the_upload_demo_path_and_guardian_identity():
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()

    assert not app.exception
    assert app.button(key="talos-load-demo").label == "Load Greek mythology demo"
    assert any("TALOS inspects your source" in item.value for item in app.markdown)
    assert any("THE ROUTE" in item.value and "Evidence Vault" in item.value for item in app.markdown)
    assert any("200 MB per file" in item.label for item in app.file_uploader)
    assert any(
        'alt="TALOS bronze automaton guardian with illuminated amethyst eyes"' in item.value
        for item in app.markdown
    )
    assert any("Raw data enters. Nothing passes unchecked." in item.value for item in app.markdown)
    assert any("GUARDIAN ACTIVE" in item.value for item in app.markdown)


def test_guided_skip_route_and_global_detail_controls():
    csv = b"amount,region\n1,north\n2,south\n3,north\n4,south\n5,east\n6,west\n"
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.file_uploader[0].set_value(("small.csv", csv, "text/csv")).run()

    assert app.session_state["talos_flow_step"] == 1
    assert app.button(key="talos-flow-step-4").disabled
    app.button(key="talos-firstwatch-skip-forge").click().run()
    assert app.session_state["talos_flow_step"] == 3
    assert any(item.value == "Reinspection & Range Watch" for item in app.header)
    assert app.button(key="talos-range-to-evidence").label == "Continue to Evidence Vault"

    app.button(key="talos-collapse-all-details").click().run()
    assert app.session_state["talos_expand_all_details"] is False
    app.button(key="talos-expand-all-details").click().run()
    assert app.session_state["talos_expand_all_details"] is True
    app.button(key="talos-range-to-evidence").click().run()
    assert app.session_state["talos_flow_step"] == 4
    assert "Evidence Vault" in {item.value for item in app.header}


def test_excel_sheet_choice_report_and_cleaned_workbook_export():
    workbook = BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        pd.DataFrame({"unused": [99]}).to_excel(writer, index=False, sheet_name="Overview")
        pd.DataFrame({"deity": ["Athena", "Zeus"], "rank": [1, 2]}).to_excel(
            writer, index=False, sheet_name="Inspection Data"
        )
    content = workbook.getvalue()
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.file_uploader[0].set_value(("myth.xlsx", content, mime)).run()

    sheet_picker = app.selectbox(key="talos_selected_sheet")
    assert sheet_picker.options == ["Overview", "Inspection Data"]
    sheet_picker.select("Inspection Data").run()
    assert app.session_state["talos_original_profile"]["sheet_name"] == "Inspection Data"
    assert app.session_state["talos_original_df"]["deity"].tolist() == ["Athena", "Zeus"]

    go_to_evidence(app)
    assert app.download_button(key="download-working-copy").label == "Download cleaned Excel"
    assert "Inspection Data" in app.session_state["talos_cached_report_html"]
    app.button(key="prepare-evidence-pack").click().run()
    from zipfile import ZipFile

    with ZipFile(BytesIO(app.session_state["talos_cached_evidence_pack"])) as archive:
        cleaned = archive.read("talos_evidence_pack/cleaned_dataset.xlsx")
    round_trip = pd.read_excel(BytesIO(cleaned), sheet_name="Inspection Data")
    assert round_trip.to_dict(orient="list") == {
        "deity": ["Athena", "Zeus"],
        "rank": [1, 2],
    }


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
    assert "Guardian Summary" in {item.value for item in app.subheader}
    assert "First Watch" in {item.value for item in app.header}
    assert any("Source received" in item.value for item in app.markdown)
    assert any('class="talos-inspection-status"' in item.value for item in app.markdown)
    assert app.session_state["talos_flow_step"] == 1
    assert app.button(key="talos-expand-all-details").label == "Expand all details"
    assert app.button(key="talos-collapse-all-details").label == "Collapse all details"
    original = app.session_state["talos_original_df"].copy(deep=True)
    assert original.equals(app.session_state["talos_working_df"])
    assert app.session_state["talos_transformation_ledger"] == []

    go_to_forge(app)
    assert not app.exception
    expander_labels = {item.label for item in app.get("expander")}
    assert any("Missing values ·" in label for label in expander_labels)
    assert any("Exact duplicates ·" in label for label in expander_labels)
    assert any("Text Normalisation" in label for label in expander_labels)
    assert app.button(key="talos-skip-preclean").label == "Skip pre-clean and continue to Range Watch"

    missing_key = "talos_missing_strategy_" + hashlib.sha256(b"amount").hexdigest()[:16]
    app.selectbox(key=missing_key).select("Fill with median").run()
    duplicate_key = repair_selection_key("remove_exact_duplicates")
    app.checkbox(key=duplicate_key).check().run()

    # Selections only prepare the plan. The active copy and ledger stay unchanged.
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
    assert app.session_state["talos_flow_step"] == 3
    go_to_evidence(app)
    assert any("signal group" in item.value and "remain" in item.value for item in app.warning)
    assert {item.label for item in app.get("download_button")} >= {
        "Download cleaned CSV",
        "Download transformation log",
        "Download HTML report",
        "missing_values.csv",
        "structure.csv",
        "before_after_comparison.csv",
    }

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
    go_to_forge(app)

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


def test_annual_spend_keeps_usable_iqr_actions_and_text_styles_allow_column_overrides():
    values = [0] * 20 + list(range(1, 11)) + [1000]
    csv = ("annual_spend,status\n" + "\n".join(f"{value},open" for value in values) + "\n").encode()
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.file_uploader[0].set_value(("spend.csv", csv, "text/csv")).run()
    go_to_range_watch(app)

    annual_spend = app.selectbox(key=outlier_widget_key("annual_spend"))
    assert annual_spend.value == "Leave unchanged"
    assert "Replace with median" in annual_spend.options
    assert "Remove affected rows" in annual_spend.options

    app.button(key="talos-flow-step-2").click().run()
    style_options = app.selectbox(key="talos_text_global_rule").options
    assert set(style_options) >= {
        "Proper Case", "Sentence case", "camelCase", "UPPERCASE", "lowercase"
    }
    region_rule = app.selectbox(key=text_widget_key("column_rule", "status"))
    assert "Use global default" in region_rule.options
    assert "Sentence case" in region_rule.options


def test_text_normalisation_global_style_column_override_and_address_suffix_option_apply_after_approval():
    csv = (
        b"region,status,address\nnorth,open,10 main rd\nsouth,CLOSED,8 oak st.\n"
    )
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.file_uploader[0].set_value(("addresses.csv", csv, "text/csv")).run()
    go_to_forge(app)
    original = app.session_state["talos_original_df"].copy(deep=True)

    app.checkbox(key="talos_text_address_suffixes").check().run()
    assert "address" in app.multiselect(key="talos_text_selected_columns").options
    app.multiselect(key="talos_text_selected_columns").set_value(
        ["region", "status", "address"]
    ).run()
    app.selectbox(key="talos_text_global_rule").select("UPPERCASE").run()
    app.selectbox(key=text_widget_key("column_rule", "status")).select("Sentence case").run()

    assert not app.exception
    pd.testing.assert_frame_equal(app.session_state["talos_working_df"], original)

    app.button(key="talos-apply-selected-repairs").click().run()
    assert not app.exception
    assert app.session_state["talos_working_df"]["region"].tolist() == ["NORTH", "SOUTH"]
    assert app.session_state["talos_working_df"]["status"].tolist() == ["Open", "Closed"]
    assert app.session_state["talos_working_df"]["address"].tolist() == [
        "10 MAIN ROAD", "8 OAK STREET"
    ]


def test_optional_pdf_is_prepared_on_demand_and_appears_in_downloads():
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.button(key="talos-load-demo").click().run()
    go_to_evidence(app)

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
    go_to_forge(app)
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

    chosen_group = next(
        item
        for item in build_suggested_transformations(
            original, app.session_state["talos_original_findings"]
        )
        if item["action"]["type"] == "consolidate_category"
    )
    group_id = str(chosen_group["suggestion_id"])
    app.checkbox(key=repair_selection_key(group_id)).check().run()
    assert not app.exception
    pd.testing.assert_frame_equal(original, app.session_state["talos_working_df"])
    assert app.session_state["talos_transformation_ledger"] == []

    manager_key = "talos_missing_strategy_" + hashlib.sha256(
        b"parent_1"
    ).hexdigest()[:16]
    manager_options = list(app.selectbox(key=manager_key).options)
    assert "Fill with custom text" in manager_options
    assert "Fill with mean" not in manager_options
    assert "Fill with median" not in manager_options

    app.button(key="talos-apply-selected-repairs").click().run()
    working = app.session_state["talos_working_df"]
    chosen_column = str(chosen_group["action"]["column"])
    chosen_values = {str(item["value"]) for item in chosen_group["variants"]}
    chosen_mask = original[chosen_column].astype(str).isin(chosen_values)
    assert set(working.loc[chosen_mask, chosen_column]) == {
        str(chosen_group["proposed_canonical"])
    }
    assert len(app.session_state["talos_transformation_ledger"]) == 1
    assert app.session_state["talos_transformation_ledger"][0]["parameters"][
        "canonical_value"
    ] == chosen_group["proposed_canonical"]


def test_evidence_pack_is_created_on_demand_with_applicable_outputs():
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.button(key="talos-load-demo").click().run()
    go_to_evidence(app)
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
        assert "The original uploaded dataset remains unchanged by TALOS" in report
        assert "Source preserved · Repairs recorded · Nothing changed without approval" in report


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
    assert any("could not be read consistently" in alert.value.lower() for alert in app.error)


def test_guardian_summary_uses_existing_findings_and_qualifies_signals():
    demo = pd.read_csv(Path(__file__).parent.parent / "data/sample/talos_demo.csv")
    findings = inspect_dataset(demo)
    summary = {item["area"]: item for item in build_guardian_summary(findings)}

    assert "Gaps detected" in summary["Missing values"]["message"]
    assert "exact duplicate row was found" in summary["Duplicates & identifiers"]["message"]
    assert "category groups are wearing more than one label" in summary["Category consistency"]["message"]
    assert "numeric values sit beyond the IQR watchline" in summary["Numeric distribution"]["message"]
    assert "caught the watch" in summary["Structure"]["message"]
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
    go_to_forge(app)
    original = app.session_state["talos_original_df"].copy(deep=True)

    assert app.multiselect(key="talos_manual_column_remove").value == []
    app.multiselect(key="talos_manual_column_remove").set_value(["notes", "record_id"]).run()
    assert not app.exception
    assert app.session_state["talos_working_df"].columns.tolist() == ["record_id", "notes", "amount"]
    assert app.session_state["talos_transformation_ledger"] == []
    assert any(item.value == "Repair Plan" for item in app.subheader)
    assert any("Current columns: 3" in item.value and "After repair: 1 column" in item.value for item in app.markdown)
    assert any(
        "Preview only" in item.value and "after approval" in item.value
        for item in app.markdown
    )

    app.button(key="talos-apply-selected-repairs").click().run()
    assert not app.exception
    assert app.session_state["talos_working_df"].columns.tolist() == ["amount"]
    assert app.session_state["talos_transformation_ledger"][-1]["parameters"]["columns_removed"] == ["notes", "record_id"]
    assert app.session_state["talos_working_findings"]["structure"] == inspect_dataset(app.session_state["talos_working_df"])["structure"]
    pd.testing.assert_frame_equal(app.session_state["talos_original_df"], original)

    go_to_evidence(app)
    app.button(key="reset-working-copy").click().run()
    app.button(key="confirm-reset").click().run()
    pd.testing.assert_frame_equal(app.session_state["talos_working_df"], original)
    assert app.session_state["talos_transformation_ledger"] == []


def test_column_removal_refuses_to_remove_every_field():
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.file_uploader[0].set_value(("two-columns.csv", b"left,right\na,b\nc,d\n", "text/csv")).run()
    go_to_forge(app)
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
    go_to_range_watch(app)
    original = app.session_state["talos_original_df"].copy(deep=True)
    assert app.session_state["talos_original_findings"]["outliers"]["total_outlier_values"] == 4

    assert app.selectbox(key=outlier_widget_key("amount")).value == "Leave unchanged"
    app.selectbox(key=outlier_widget_key("amount")).select("Replace with median").run()
    assert not app.exception
    pd.testing.assert_frame_equal(app.session_state["talos_working_df"], original)
    assert app.session_state["talos_transformation_ledger"] == []
    assert any("5.5" in item.value for item in app.markdown)
    assert any(item.value == "Repair Plan" for item in app.subheader)
    assert any("Outlier preview" in item.value for item in app.markdown)
    assert app.button(key="talos-apply-range-watch-repairs").label == "Approve and apply Range Watch repairs"
    assert not any(
        "Applied the approved per-column" in item.value for item in app.markdown
    )

    app.button(key="talos-apply-range-watch-repairs").click().run()
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

    go_to_evidence(app)
    app.button(key="reset-working-copy").click().run()
    app.button(key="confirm-reset").click().run()
    pd.testing.assert_frame_equal(app.session_state["talos_working_df"], original)
    assert app.session_state["talos_transformation_ledger"] == []


def test_forge_can_remove_only_negative_integer_values_and_leave_fractional_values():
    values = [7, 4, -3, -2, -1.5]
    csv = ("amount\n" + "\n".join(map(str, values)) + "\n").encode()
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.file_uploader[0].set_value(("negative-values.csv", csv, "text/csv")).run()
    go_to_range_watch(app)

    selector = app.selectbox(key=outlier_widget_key("amount"))
    assert "Remove rows with negative integer values" in selector.options
    assert "Remove rows with negative integer outliers only" not in selector.options
    original = app.session_state["talos_original_df"].copy(deep=True)

    selector.select("Remove rows with negative integer values").run()
    assert not app.exception
    pd.testing.assert_frame_equal(app.session_state["talos_working_df"], original)
    assert any("2 unique rows to remove" in item.value for item in app.markdown)

    app.button(key="talos-apply-range-watch-repairs").click().run()
    assert not app.exception
    assert app.session_state["talos_working_df"]["amount"].tolist()[-1] == -1.5
    assert not app.session_state["talos_working_df"]["amount"].isin([-3, -2]).any()
    assert app.session_state["talos_transformation_ledger"][-1]["parameters"]["columns"][0][
        "criteria"
    ] == "negative_integer_values"


def test_range_watch_exposes_negative_integer_iqr_outlier_only_choice():
    values = list(range(10, 20)) + [-100, -1.5]
    csv = ("amount\n" + "\n".join(map(str, values)) + "\n").encode()
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.file_uploader[0].set_value(("negative-outliers.csv", csv, "text/csv")).run()
    go_to_range_watch(app)

    selector = app.selectbox(key=outlier_widget_key("amount"))
    assert "Remove rows with negative integer values" in selector.options
    assert "Remove rows with negative integer outliers only" in selector.options
    selector.select("Remove rows with negative integer outliers only").run()
    assert any("1 unique row to remove" in item.value for item in app.markdown)
    app.button(key="talos-apply-range-watch-repairs").click().run()

    assert not app.exception
    assert -100 not in app.session_state["talos_working_df"]["amount"].tolist()
    assert -1.5 in app.session_state["talos_working_df"]["amount"].tolist()
    assert app.session_state["talos_transformation_ledger"][-1]["parameters"]["columns"][0][
        "criteria"
    ] == "negative_integer_iqr_outliers"


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
