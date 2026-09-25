"""Streamlit integration checks for approval, ledger, reset, and release controls."""

import pandas as pd
from streamlit.testing.v1 import AppTest


def test_forge_requires_approval_tracks_changes_and_can_reset():
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
    app = AppTest.from_file("../app.py", default_timeout=30).run()
    app.file_uploader[0].set_value(("orders.csv", csv, "text/csv"))
    app.run()

    assert not app.exception
    assert any(
        'alt="TALOS bronze guardian emblem"' in element.value
        for element in app.markdown
    )
    assert app.session_state["talos_original_df"].equals(
        app.session_state["talos_working_df"]
    )
    assert len(app.session_state["talos_transformation_ledger"]) == 0
    assert {item.label for item in app.get("download_button")} == {
        "Download cleaned CSV",
        "Download transformation log",
        "Download HTML report",
    }

    app.selectbox(key="talos_missing_choice:amount").select("Fill with median").run()
    assert not app.exception
    app.button(key="leave:missing:amount").click().run()
    assert app.session_state["talos_missing_choice:amount"] == "Leave unchanged"
    assert app.session_state["talos_transformation_ledger"] == []
    assert app.session_state["talos_original_df"].equals(
        app.session_state["talos_working_df"]
    )

    app.selectbox(key="talos_missing_choice:amount").select("Fill with median").run()
    app.button(key="apply:missing:amount").click().run()

    original = app.session_state["talos_original_df"]
    working = app.session_state["talos_working_df"]
    assert pd.isna(original.loc[10, "amount"])
    assert working.loc[10, "amount"] == 45.0
    assert len(app.session_state["talos_transformation_ledger"]) == 1

    app.button(key="apply:remove_exact_duplicates").click().run()
    assert len(app.session_state["talos_original_df"]) == 11
    assert len(app.session_state["talos_working_df"]) == 10
    assert len(app.session_state["talos_transformation_ledger"]) == 2
    assert not app.exception

    app.button(key="reset-working-copy").click().run()
    app.button(key="confirm-reset").click().run()

    assert app.session_state["talos_working_df"].equals(
        app.session_state["talos_original_df"]
    )
    assert app.session_state["talos_transformation_ledger"] == []
    assert not app.exception

    replacement_csv = b"city,count\nSydney,3\n"
    app.file_uploader[0].set_value(("replacement.csv", replacement_csv, "text/csv"))
    app.run()
    assert not app.exception
    assert len(app.session_state["talos_original_df"]) == 1
    assert app.session_state["talos_original_df"].equals(
        app.session_state["talos_working_df"]
    )
    assert app.session_state["talos_transformation_ledger"] == []
