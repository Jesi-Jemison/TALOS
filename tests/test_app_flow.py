"""Streamlit integration checks for TALOS's session workflow."""

from pathlib import Path
import hashlib

import pandas as pd
from streamlit.testing.v1 import AppTest

from app import repair_selection_key
from src.transformations import build_suggested_transformations


APP_PATH = "../app.py"


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
    assert any(
        'alt="TALOS bronze guardian emblem"' in element.value
        for element in app.markdown
    )
    original = app.session_state["talos_original_df"].copy(deep=True)
    assert original.equals(app.session_state["talos_working_df"])
    assert app.session_state["talos_transformation_ledger"] == []
    assert {item.label for item in app.get("download_button")} >= {
        "Download cleaned CSV",
        "Download transformation log",
        "Download HTML report",
        "Download CSV",
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
