"""Streamlit interface for TALOS dataset intake and inspection."""

import base64
import hashlib
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from pandas.api.types import is_bool_dtype, is_numeric_dtype, is_object_dtype, is_string_dtype

from src.profiler import load_csv, profile_dataset
from src.quality_checks import (
    inspect_category_consistency,
    inspect_duplicates,
    inspect_missing_values,
    inspect_numeric_outliers,
    inspect_structure,
)
from src.scoring import calculate_integrity_score
from src.reporting import (
    build_cleaned_csv,
    build_export_filename,
    build_inspection_report_html,
    build_transformation_log,
)
from src.transformations import (
    append_ledger_record,
    apply_transformation,
    build_suggested_transformations,
    create_working_copy,
    reset_working_copy,
)


logger = logging.getLogger(__name__)


def load_stylesheet() -> None:
    """Apply the TALOS stylesheet when the asset is available."""
    stylesheet_path = Path(__file__).parent / "assets" / "talos.css"
    try:
        stylesheet = stylesheet_path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("TALOS stylesheet was not available at %s", stylesheet_path)
        return

    st.markdown(f"<style>{stylesheet}</style>", unsafe_allow_html=True)


def render_header() -> None:
    """Show TALOS identity and system status."""
    emblem_path = Path(__file__).parent / "assets" / "talos-emblem.svg"
    try:
        emblem_svg = emblem_path.read_text(encoding="utf-8")
        encoded_emblem = base64.b64encode(emblem_svg.encode("utf-8")).decode("ascii")
        emblem_html = (
            '<div class="talos-emblem-wrap">'
            f'<img class="talos-emblem" src="data:image/svg+xml;base64,{encoded_emblem}" '
            'alt="TALOS bronze guardian emblem">'
            "</div>"
        )
    except OSError:
        logger.warning("TALOS emblem was not available at %s", emblem_path)
        emblem_html = '<span role="img" aria-label="TALOS guardian emblem">◈</span>'

    st.markdown(
        f"""
        <header class="talos-hero">
            <div class="talos-hero-layout">
                <div class="talos-hero-copy">
                    <p class="talos-eyebrow">Data integrity observation system</p>
                    <h1 class="talos-title"><span class="talos-title-mark">⚙</span> TALOS</h1>
                    <p class="talos-subtitle">
                        A watchful guardian between source data and trusted analysis.
                    </p>
                    <div class="talos-system-status">
                        <span class="talos-status-dot"></span>
                        Inspection system online
                    </div>
                </div>
                {emblem_html}
            </div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def render_dataset_profile(profile: dict[str, object], df: pd.DataFrame) -> None:
    """Render file details, the dataset structure, and a small preview."""
    st.markdown('<p class="talos-section-kicker">Structural inspection</p>', unsafe_allow_html=True)
    st.subheader("👁️ Dataset Overview")
    type_counts = profile["type_counts"]
    metrics = st.columns(6)
    metrics[0].metric("Rows", profile["row_count"])
    metrics[1].metric("Columns", profile["column_count"])
    metrics[2].metric("Numeric", type_counts["Numeric"])
    metrics[3].metric("Text", type_counts["Text"])
    metrics[4].metric("Boolean", type_counts["Boolean"])
    metrics[5].metric("Datetime", type_counts["Datetime"])

    details = st.columns(2)
    details[0].metric("Filename", profile["file_name"])
    details[1].metric("File size", profile["file_size"])

    st.subheader("Dataset Structure")
    structure = pd.DataFrame(profile["columns"]).rename(
        columns={
            "column": "Column",
            "pandas_dtype": "Pandas dtype",
            "talos_type": "TALOS type",
        }
    )
    st.dataframe(structure, width="stretch", hide_index=True)

    st.subheader("Data Preview")
    st.caption("First 10 rows. The inspection below reports signals and leaves the data unchanged.")
    st.dataframe(df.head(10), width="stretch", hide_index=True)


def render_missing_data(analysis: dict[str, object]) -> None:
    """Render dataset-wide and column-level missing-value findings."""
    st.markdown('<p class="talos-section-kicker">Completeness</p>', unsafe_allow_html=True)
    st.subheader("🕳️ Missing Data")
    metrics = st.columns(4)
    metrics[0].metric("Missing cells", analysis["total_missing_cells"])
    metrics[1].metric("Dataset missing", f"{analysis['missing_percentage']:.1f}%")
    metrics[2].metric("Affected columns", analysis["affected_column_count"])
    metrics[3].metric("Clear columns", analysis["clear_column_count"])

    if analysis["total_missing_cells"]:
        st.warning(
            "Some values are missing. Their effect depends on how each field is used; "
            "TALOS does not fill or remove them."
        )
    else:
        st.success("No missing cells found in this dataset.")

    rows = pd.DataFrame(analysis["columns"]).rename(
        columns={
            "column": "Column",
            "pandas_dtype": "Pandas dtype",
            "missing_count": "Missing cells",
            "missing_percentage": "Missing %",
            "severity": "Severity",
            "explanation": "Possible effect",
        }
    )
    if not rows.empty:
        rows["Missing %"] = rows["Missing %"].map(lambda value: f"{value:.1f}%")
        st.dataframe(rows, width="stretch", hide_index=True)


def render_duplicate_checks(analysis: dict[str, object]) -> None:
    """Render exact duplicate rows and possible identifier findings."""
    st.markdown('<p class="talos-section-kicker">Record repetition</p>', unsafe_allow_html=True)
    st.subheader("🪞 Duplicate Inspection")
    metrics = st.columns(3)
    metrics[0].metric("Exact duplicate rows", analysis["exact_duplicate_row_count"])
    metrics[1].metric("Rows duplicated", f"{analysis['exact_duplicate_percentage']:.1f}%")
    metrics[2].metric("Possible identifier fields", analysis["identifier_candidate_count"])

    if analysis["exact_duplicate_row_count"]:
        st.warning(
            "Some rows exactly match an earlier row. This may be intentional; "
            "TALOS does not remove duplicates."
        )
        st.caption("Sample rows involved in exact matches")
        st.dataframe(analysis["exact_duplicate_sample"], width="stretch", hide_index=True)
    else:
        st.success("No exact duplicate rows found.")

    rows = []
    for candidate in analysis["identifier_candidates"]:
        repeated_values = "; ".join(
            f"{item['value']} ({item['row_count']} rows)"
            for item in candidate["duplicate_values"]
        )
        rows.append(
            {
                "Column": candidate["column"],
                "Missing values": candidate["missing_count"],
                "Distinct non-missing values": candidate["unique_count"],
                "Repeated values after first": candidate["duplicate_value_count"],
                "Uniqueness": f"{candidate['uniqueness_percentage']:.1f}%",
                "Repeated value examples": repeated_values or "None found",
            }
        )

    if rows:
        st.caption(
            "Candidate fields are selected from their names only. Repeats are a review signal; "
            "not every candidate must be unique."
        )
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        if analysis["identifier_candidates_with_repeats"]:
            st.info(
                "Repeated values appear in a possible identifier field. "
                "Confirm whether uniqueness is required."
            )
    else:
        st.caption("No column names clearly suggest a possible identifier field.")


def render_category_consistency(analysis: dict[str, object]) -> None:
    """Render case and whitespace variation in suitable text categories."""
    st.markdown('<p class="talos-section-kicker">Category variation</p>', unsafe_allow_html=True)
    st.subheader("🧬 Category Consistency")
    metrics = st.columns(3)
    metrics[0].metric("Text columns checked", len(analysis["checked_columns"]))
    metrics[1].metric("Variant groups", analysis["inconsistent_group_count"])
    metrics[2].metric("Columns with variants", analysis["column_count_with_variants"])
    st.markdown(
        """
        <p class="talos-note">
            TALOS compares text after trimming outer whitespace, collapsing repeated spaces,
            and ignoring letter case. It does not merge or change values.
        </p>
        """,
        unsafe_allow_html=True,
    )

    if analysis["variant_groups"]:
        st.warning(
            "Some category values look equivalent after simple text normalisation. "
            "Review them in context."
        )
        rows = [
            {
                "Column": group["column"],
                "Normalised value": group["normalized_value"],
                "Original variants": "; ".join(
                    f"{item['value']} ({item['count']})" for item in group["variants"]
                ),
            }
            for group in analysis["variant_groups"]
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    elif analysis["checked_columns"]:
        st.success("No case or whitespace variants found in the text columns TALOS checked.")
    else:
        st.info("No suitable text category columns were available for this check.")

    if analysis["skipped_columns"]:
        with st.expander("Columns not checked"):
            skipped = pd.DataFrame(analysis["skipped_columns"]).rename(
                columns={"column": "Column", "reason": "Reason"}
            )
            st.dataframe(skipped, width="stretch", hide_index=True)


def render_numeric_outliers(analysis: dict[str, object]) -> None:
    """Render IQR summaries and explain which numeric fields were skipped."""
    st.markdown('<p class="talos-section-kicker">Distribution signals</p>', unsafe_allow_html=True)
    st.subheader("📐 Numeric Outliers")
    metrics = st.columns(3)
    metrics[0].metric("Potential outlier values", analysis["total_outlier_values"])
    metrics[1].metric("Numeric columns checked", analysis["eligible_column_count"])
    metrics[2].metric("Outlier values", f"{analysis['outlier_percentage']:.1f}%")
    st.markdown(
        """
        <p class="talos-note">
            TALOS uses the IQR rule: values below Q1 − 1.5 × IQR or above Q3 + 1.5 × IQR
            are flagged. An outlier is not automatically an error.
        </p>
        """,
        unsafe_allow_html=True,
    )

    if analysis["total_outlier_values"]:
        st.warning("Some numeric values are outside the IQR range and may deserve review.")
        rows = [
            {
                "Column": item["column"],
                "Q1": item["q1"],
                "Median": item["median"],
                "Q3": item["q3"],
                "Lower bound": item["lower_bound"],
                "Upper bound": item["upper_bound"],
                "Outliers": item["outlier_count"],
                "Outlier %": f"{item['outlier_percentage']:.1f}%",
                "Sample values": ", ".join(map(str, item["sample_values"])) or "None",
            }
            for item in analysis["columns"]
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    elif analysis["eligible_column_count"]:
        st.success("No IQR outliers found in the numeric columns TALOS checked.")
    else:
        st.info("No numeric columns met the minimum requirements for IQR inspection.")

    if analysis["skipped_columns"]:
        with st.expander("Numeric fields not checked"):
            skipped = pd.DataFrame(analysis["skipped_columns"]).rename(
                columns={"column": "Column", "reason": "Reason"}
            )
            st.dataframe(skipped, width="stretch", hide_index=True)


def render_structural_signals(analysis: dict[str, object]) -> None:
    """Render empty, constant, high-cardinality, identifier, and numeric signals."""
    st.markdown('<p class="talos-section-kicker">Dataset shape signals</p>', unsafe_allow_html=True)
    st.subheader("🧱 Structural & Identifier Checks")
    metrics = st.columns(4)
    metrics[0].metric("Empty columns", len(analysis["empty_columns"]))
    metrics[1].metric("Constant columns", len(analysis["constant_columns"]))
    metrics[2].metric("High-cardinality fields", len(analysis["high_cardinality_columns"]))
    metrics[3].metric("Possible identifier fields", len(analysis["identifier_columns"]))

    if analysis["empty_columns"] or analysis["constant_columns"]:
        st.warning(
            "Empty or constant columns may deserve review, depending on the dataset's purpose."
        )
        rows = [
            {"Column": column, "Signal": "No usable values"}
            for column in analysis["empty_columns"]
        ]
        rows.extend(
            {
                "Column": item["column"],
                "Signal": f"One distinct value across {item['non_missing_count']} non-missing rows",
            }
            for item in analysis["constant_columns"]
        )
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.success("No empty or constant columns found.")

    if analysis["high_cardinality_columns"]:
        st.caption(
            "Many distinct text values can indicate an identifier, free text, or a granular "
            "category; it is not automatically a problem."
        )
        rows = [
            {
                "Column": item["column"],
                "Distinct values": item["unique_count"],
                "Non-missing rows": item["non_missing_count"],
                "Uniqueness": f"{item['uniqueness_percentage']:.1f}%",
            }
            for item in analysis["high_cardinality_columns"]
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if analysis["identifier_columns"]:
        st.caption(
            "Identifier candidates are inferred from column names only. Uniqueness is shown "
            "for review, not treated as a requirement."
        )
        rows = [
            {
                "Column": item["column"],
                "Missing values": item["missing_count"],
                "Repeated values after first": item["duplicate_value_count"],
                "Uniqueness": f"{item['uniqueness_percentage']:.1f}%",
            }
            for item in analysis["identifier_columns"]
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if analysis["numeric_patterns"]:
        st.caption(
            "Negative values and zero-heavy fields may be valid. TALOS cannot infer the "
            "expected range from the data alone."
        )
        rows = []
        for item in analysis["numeric_patterns"]:
            signals = []
            if item["negative_count"]:
                signals.append(
                    f"{item['negative_count']} negative "
                    f"({item['negative_percentage']:.1f}%)"
                )
            if item["zero_percentage"] >= 80:
                signals.append(f"zero-heavy ({item['zero_percentage']:.1f}% zeros)")
            rows.append(
                {
                    "Column": item["column"],
                    "Usable values": item["usable_value_count"],
                    "Observed pattern": "; ".join(signals),
                }
            )
        st.info(
            "Some numeric patterns may deserve investigation; "
            "none are classified as incorrect by themselves."
        )
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def render_integrity_score(analysis: dict[str, object]) -> None:
    """Render the weighted score and the contribution of each component."""
    st.markdown('<p class="talos-section-kicker">Combined inspection</p>', unsafe_allow_html=True)
    st.subheader("🛡️ Dataset Integrity")
    if analysis["score"] is None:
        st.info(analysis["explanation"])
        return

    st.markdown(
        f"""
        <section class="talos-score-panel" aria-label="Dataset Integrity Score">
            <span class="talos-score-label">Custom inspection score</span>
            <strong class="talos-score-value">{analysis['score']}<small>/ 100</small></strong>
            <span class="talos-score-band">{analysis['band']}</span>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        "An illustrative TALOS heuristic, not an industry-standard data-quality measure. "
        "It summarises the findings above; it is not a verdict that data is correct or incorrect."
    )
    rows = [
        {
            "Component": item["component"],
            "Weight": f"{item['weight']}%",
            "Component score": f"{item['score']:.1f}",
            "Weighted points": f"{item['weighted_points']:.1f}",
        }
        for item in analysis["components"]
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.markdown(
        """
        <p class="talos-note">
            Potential identifier repeats, high-cardinality text, negative values, and
            zero-heavy fields remain visible as contextual signals. They do not lower the
            score because their meaning depends on the dataset.
        </p>
        """,
        unsafe_allow_html=True,
    )


def inspect_dataset(df: pd.DataFrame) -> dict[str, dict[str, object]]:
    """Run every read-only inspection and calculate the summary score."""
    findings = {
        "missing": inspect_missing_values(df),
        "duplicates": inspect_duplicates(df),
        "categories": inspect_category_consistency(df),
        "outliers": inspect_numeric_outliers(df),
        "structure": inspect_structure(df),
    }
    findings["score"] = calculate_integrity_score(
        df,
        findings["missing"],
        findings["duplicates"],
        findings["categories"],
        findings["outliers"],
        findings["structure"],
    )
    return findings


def initialize_dataset_state(file_fingerprint: str, uploaded_df: pd.DataFrame) -> None:
    """Keep an untouched original and a separate working copy for one upload."""
    if st.session_state.get("talos_file_fingerprint") == file_fingerprint:
        return

    for key in list(st.session_state.keys()):
        if key.startswith("talos_"):
            del st.session_state[key]

    original_df = create_working_copy(uploaded_df)
    st.session_state["talos_file_fingerprint"] = file_fingerprint
    st.session_state["talos_original_df"] = original_df
    st.session_state["talos_working_df"] = create_working_copy(original_df)
    st.session_state["talos_transformation_ledger"] = []
    st.session_state["talos_dismissed_suggestions"] = set()
    st.session_state["talos_reset_confirmation"] = False
    st.session_state["talos_notice"] = ""


def leave_missing_values_unchanged(column: str) -> None:
    """Return a missing-value selector to its safe default before rerunning."""
    st.session_state[f"talos_missing_choice:{column}"] = "Leave unchanged"


def clear_dataset_state() -> None:
    """Discard in-session TALOS data when the uploaded file is cleared."""
    for key in list(st.session_state.keys()):
        if key.startswith("talos_"):
            del st.session_state[key]


def _is_text_column(series: pd.Series) -> bool:
    """Check whether missing-value text options are suitable for a column."""
    is_text_type = (
        is_object_dtype(series.dtype)
        or is_string_dtype(series.dtype)
        or isinstance(series.dtype, pd.CategoricalDtype)
    )
    observed_values = series.dropna()
    contains_only_booleans = bool(len(observed_values)) and bool(
        observed_values.map(lambda value: isinstance(value, (bool, np.bool_))).all()
    )
    return is_text_type and not is_bool_dtype(series.dtype) and not contains_only_booleans


def render_transformation_preview(
    df: pd.DataFrame,
    action: dict[str, object],
    widget_key: str,
    display_name: str,
    leave_button_label: str = "Leave unchanged",
    dismiss_on_leave: bool = True,
) -> None:
    """Show a concrete before/after preview and apply only on explicit approval."""
    try:
        preview_df, record = apply_transformation(df, action)
    except (KeyError, TypeError, ValueError) as error:
        st.error(f"TALOS could not prepare this preview: {error}")
        return

    with st.container(border=True):
        st.write(record["description"])
        counts = st.columns(4)
        counts[0].metric("Affected rows", record["affected_rows"])
        counts[1].metric("Rows after", len(preview_df.index))
        counts[2].metric("Columns after", len(preview_df.columns))
        counts[3].metric("Examples", len(record["before_after"]))
        if record["before_after"]:
            st.caption("Preview examples")
            st.dataframe(
                pd.DataFrame(record["before_after"]).rename(
                    columns={"before": "Before", "after": "After"}
                ),
                width="stretch",
                hide_index=True,
            )

    apply_column, leave_column = st.columns(2)
    with apply_column:
        apply_clicked = st.button(
            "Apply to working copy",
            key=f"apply:{widget_key}",
            type="primary",
        )
    with leave_column:
        if dismiss_on_leave:
            leave_clicked = st.button(leave_button_label, key=f"leave:{widget_key}")
        else:
            st.button(
                leave_button_label,
                key=f"leave:{widget_key}",
                on_click=leave_missing_values_unchanged,
                args=(str(action["column"]),),
            )
            leave_clicked = False

    if apply_clicked:
        record["transformation_type"] = display_name
        st.session_state["talos_working_df"] = preview_df
        st.session_state["talos_transformation_ledger"] = append_ledger_record(
            st.session_state["talos_transformation_ledger"], record
        )
        st.session_state["talos_dismissed_suggestions"].discard(widget_key)
        st.session_state["talos_notice"] = "Transformation recorded in the ledger."
        st.rerun()

    if leave_clicked:
        if dismiss_on_leave:
            st.session_state["talos_dismissed_suggestions"].add(widget_key)
        else:
            st.session_state[f"talos_missing_choice:{action['column']}"] = "Leave unchanged"
        st.rerun()


def render_suggested_fixes(
    working_df: pd.DataFrame,
    findings: dict[str, dict[str, object]],
) -> None:
    """Render safe proposals derived from current findings."""
    dismissed = st.session_state["talos_dismissed_suggestions"]
    suggestions = [
        suggestion
        for suggestion in build_suggested_transformations(working_df, findings)
        if suggestion["suggestion_id"] not in dismissed
    ]

    if not suggestions:
        st.success("No proposed repairs are awaiting review.")
        return

    st.markdown(f"**{len(suggestions)} proposed repairs are awaiting review.**")
    for suggestion in suggestions:
        suggestion_id = suggestion["suggestion_id"]
        with st.expander(suggestion["title"], expanded=False):
            st.write(suggestion["description"])
            action = dict(suggestion["action"])
            if "variants" in suggestion:
                variants = suggestion["variants"]
                st.caption("Observed values and their counts")
                st.dataframe(
                    pd.DataFrame(variants).rename(
                        columns={"value": "Observed value", "count": "Rows"}
                    ),
                    width="stretch",
                    hide_index=True,
                )
                values = [item["value"] for item in variants]
                proposed = suggestion["proposed_canonical"]
                selected = st.selectbox(
                    "Proposed canonical value",
                    values,
                    index=values.index(proposed),
                    key=f"talos_canonical:{suggestion_id}",
                )
                st.caption(
                    "TALOS proposes the most common observed spelling. "
                    "You choose the final representation."
                )
                action["canonical_value"] = selected
            render_transformation_preview(
                working_df,
                action,
                widget_key=suggestion_id,
                display_name=suggestion["title"],
            )


def render_missing_value_actions(working_df: pd.DataFrame) -> None:
    """Offer explicit row removal or user-selected imputation for missing values."""
    missing_columns = [
        column for column in working_df.columns if working_df[column].isna().any()
    ]
    if not missing_columns:
        st.caption("No missing values remain in the current working copy.")
        return

    for column in missing_columns:
        series = working_df[column]
        missing_count = int(series.isna().sum())
        choice_key = f"talos_missing_choice:{column}"
        with st.expander(f"{column} · {missing_count} missing values", expanded=False):
            choices = ["Leave unchanged", "Remove rows with missing values"]
            is_numeric = is_numeric_dtype(series.dtype) and not is_bool_dtype(series.dtype)
            is_text = _is_text_column(series)
            if is_numeric:
                choices.append("Fill with custom number")
                if not series.dropna().empty:
                    choices.extend(["Fill with median", "Fill with mean"])
            elif is_text:
                choices.append("Fill with custom text")
                if not series.dropna().empty:
                    choices.append("Fill with most common value")

            selected = st.selectbox(
                "Choose an action. TALOS will leave this column unchanged by default.",
                choices,
                key=choice_key,
            )
            if selected == "Leave unchanged":
                st.caption("No change is proposed until you select an action.")
                continue

            if selected == "Remove rows with missing values":
                action = {"type": "remove_rows_with_missing", "column": column}
            elif selected in {"Fill with median", "Fill with mean"}:
                action = {
                    "type": "fill_numeric_missing",
                    "column": column,
                    "method": "median" if selected.endswith("median") else "mean",
                }
            elif selected == "Fill with custom number":
                custom_value = st.number_input(
                    "Custom numeric value",
                    value=0.0,
                    key=f"talos_missing_number:{column}",
                )
                action = {
                    "type": "fill_numeric_missing",
                    "column": column,
                    "method": "custom",
                    "value": custom_value,
                }
            elif selected == "Fill with custom text":
                custom_value = st.text_input(
                    "Custom replacement text",
                    value="",
                    placeholder="Enter a value",
                    key=f"talos_missing_text:{column}",
                )
                action = {
                    "type": "fill_text_missing",
                    "column": column,
                    "method": "custom",
                    "value": custom_value,
                }
            else:
                action = {
                    "type": "fill_text_missing",
                    "column": column,
                    "method": "mode",
                }

            render_transformation_preview(
                working_df,
                action,
                widget_key=f"missing:{column}",
                display_name=selected,
                leave_button_label="Leave unchanged",
                dismiss_on_leave=False,
            )


def render_transformation_ledger(ledger: list[dict[str, object]]) -> None:
    """Show the session-only record of approved working-copy changes."""
    st.subheader("📜 Transformation Ledger")
    if not ledger:
        st.caption("No transformations have been approved in this session.")
        return

    st.markdown(
        f'<p class="talos-ledger-count">{len(ledger)} approved transformation(s) recorded</p>',
        unsafe_allow_html=True,
    )
    rows = [
        {
            "Transformation": item["transformation_type"],
            "Column": item["column"] or "—",
            "Affected rows": item["affected_rows"],
            "Description": item["description"],
            "Rows": f"{item['rows_before']} → {item['rows_after']}",
            "Columns": f"{item['columns_before']} → {item['columns_after']}",
        }
        for item in ledger
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    for index, item in enumerate(ledger, start=1):
        label = f"Entry {index} · {item['transformation_type']}"
        with st.expander(label):
            st.write(item["description"])
            st.write(f"Column: {item['column'] or 'Entire dataset'}")
            st.write(f"Chosen action: {item['action']}")
            st.write(f"Parameters: {item['parameters']}")
            if item["before_after"]:
                st.dataframe(
                    pd.DataFrame(item["before_after"]).rename(
                        columns={"before": "Before", "after": "After"}
                    ),
                    width="stretch",
                    hide_index=True,
                )


def summarize_dataset(
    df: pd.DataFrame, findings: dict[str, dict[str, object]]
) -> dict[str, object]:
    """Collect a compact before/after summary without implying improvement."""
    return {
        "row_count": len(df.index),
        "column_count": len(df.columns),
        "missing_cells": findings["missing"]["total_missing_cells"],
        "duplicate_rows": findings["duplicates"]["exact_duplicate_row_count"],
        "score": findings["score"]["score"],
    }


def render_dataset_comparison(
    original_summary: dict[str, object],
    working_summary: dict[str, object],
    ledger: list[dict[str, object]],
) -> None:
    """Compare current counts and findings with the source upload."""
    st.subheader("👁️ Original / Working Copy")
    st.caption(
        "Current working-copy inspection. Fewer signals do not automatically mean better data."
    )
    labels = [
        ("Rows", "row_count"),
        ("Columns", "column_count"),
        ("Missing cells", "missing_cells"),
        ("Exact duplicates", "duplicate_rows"),
        ("Integrity score", "score"),
    ]
    columns = st.columns(len(labels))
    for container, (label, key) in zip(columns, labels):
        before = original_summary[key]
        after = working_summary[key]
        before_text = "—" if before is None else str(before)
        after_text = "—" if after is None else str(after)
        container.metric(
            label,
            after_text,
            delta=f"Original: {before_text}",
            delta_color="off",
        )

    if not ledger:
        st.caption("The working copy currently matches the original dataset.")


def render_reset_control(original_df: pd.DataFrame) -> None:
    """Require confirmation before restoring the original working copy."""
    if not st.session_state["talos_transformation_ledger"]:
        return
    with st.container(border=True):
        if st.button("Reset working copy", key="reset-working-copy"):
            st.session_state["talos_reset_confirmation"] = True

        if st.session_state["talos_reset_confirmation"]:
            st.warning(
                "Reset the Forge? This discards approved transformations and restores "
                "the original uploaded dataset."
            )
            confirm, cancel = st.columns(2)
            if confirm.button("Confirm reset", key="confirm-reset"):
                st.session_state["talos_working_df"] = reset_working_copy(original_df)
                st.session_state["talos_transformation_ledger"] = []
                st.session_state["talos_dismissed_suggestions"] = set()
                st.session_state["talos_reset_confirmation"] = False
                st.session_state["talos_notice"] = (
                    "The original dataset has been restored to the working copy."
                )
                st.rerun()
            if cancel.button("Keep current working copy", key="cancel-reset"):
                st.session_state["talos_reset_confirmation"] = False
                st.rerun()


def render_forge(
    original_df: pd.DataFrame,
    working_df: pd.DataFrame,
    original_findings: dict[str, dict[str, object]],
    working_findings: dict[str, dict[str, object]],
) -> None:
    """Render suggestions, approvals, the ledger, comparison, and reset controls."""
    st.markdown(
        '<p class="talos-section-kicker">User-controlled transformations</p>',
        unsafe_allow_html=True,
    )
    st.header("🔨 The Forge")
    st.markdown(
        "TALOS can prepare a cleaned working copy of your dataset. "
        "No transformation is applied without your approval."
    )
    st.info("The original dataset remains untouched. TALOS alters only the working copy.")

    st.subheader("Suggested fixes")
    render_suggested_fixes(working_df, working_findings)
    st.subheader("Missing-value handling")
    st.caption(
        "Leave unchanged is the default. Select a method, inspect its preview, then approve it."
    )
    render_missing_value_actions(working_df)

    ledger = st.session_state["talos_transformation_ledger"]
    render_transformation_ledger(ledger)
    original_summary = summarize_dataset(original_df, original_findings)
    working_summary = summarize_dataset(working_df, working_findings)
    render_dataset_comparison(original_summary, working_summary, ledger)
    render_reset_control(original_df)


def load_emblem_svg() -> str:
    """Read the local emblem for a self-contained report, if available."""
    emblem_path = Path(__file__).parent / "assets" / "talos-emblem.svg"
    try:
        return emblem_path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("TALOS emblem was not available for the report at %s", emblem_path)
        return ""


def render_exports_and_report(
    original_profile: dict[str, object],
    original_findings: dict[str, dict[str, object]],
    working_findings: dict[str, dict[str, object]],
) -> None:
    """Offer the approved working copy, ledger, and HTML dossier for download."""
    original_df = st.session_state["talos_original_df"]
    working_df = st.session_state["talos_working_df"]
    ledger = st.session_state["talos_transformation_ledger"]
    original_summary = summarize_dataset(original_df, original_findings)
    working_summary = summarize_dataset(working_df, working_findings)

    st.markdown('<p class="talos-section-kicker">Release</p>', unsafe_allow_html=True)
    st.header("📦 Export Working Copy")
    st.info(
        "TALOS creates a new transformed copy. "
        "Your original uploaded dataset remains unchanged."
    )
    csv_bytes = build_cleaned_csv(working_df)
    st.download_button(
        "Download cleaned CSV",
        data=csv_bytes,
        file_name=build_export_filename(original_profile["file_name"], "cleaned"),
        mime="text/csv",
        key="download-working-copy",
    )

    log_df = build_transformation_log(ledger)
    log_bytes = log_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download transformation log",
        data=log_bytes,
        file_name=build_export_filename(original_profile["file_name"], "transformations"),
        mime="text/csv",
        key="download-transformation-log",
    )

    st.markdown('<p class="talos-section-kicker">Recorded findings</p>', unsafe_allow_html=True)
    st.header("📜 TALOS Inspection Report")
    st.caption("The guardian's findings, recorded.")
    report_html = build_inspection_report_html(
        original_profile,
        original_findings,
        working_findings,
        original_summary,
        working_summary,
        ledger,
        emblem_svg=load_emblem_svg(),
    )
    st.download_button(
        "Download HTML report",
        data=report_html.encode("utf-8"),
        file_name=build_export_filename(original_profile["file_name"], "report"),
        mime="text/html",
        key="download-inspection-report",
    )


def main() -> None:
    """Render CSV upload, inspection, approved transformations, and exports."""
    st.set_page_config(page_title="TALOS", page_icon="⚙️", layout="wide")
    load_stylesheet()
    render_header()
    st.markdown('<p class="talos-section-kicker">Source file</p>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Upload a CSV file for inspection",
        type=["csv"],
        help="TALOS reads the file in memory for this session; it is not saved by the app.",
    )
    st.caption(
        "Please do not upload confidential, sensitive, or personally identifiable information. "
        "Files are processed for this session and are not intentionally stored."
    )
    if uploaded_file is None:
        clear_dataset_state()
        st.info("Upload a CSV to view its structure and first ten rows.")
        return

    file_contents = uploaded_file.getvalue()
    if not file_contents:
        st.warning("This file appears to contain no content. Choose a CSV with a header and data.")
        return

    try:
        df = load_csv(file_contents)
    except pd.errors.EmptyDataError:
        st.warning("This CSV contains no readable header or data.")
        return
    except pd.errors.ParserError:
        st.error(
            "TALOS could not read this file as a consistent CSV. "
            "Check its rows and separators."
        )
        return
    except UnicodeDecodeError:
        st.error(
            "TALOS could not read the file's text encoding. "
            "Save it as UTF-8 CSV and try again."
        )
        return
    except Exception:
        logger.exception("Unexpected error while reading an uploaded CSV.")
        st.error("TALOS could not read this file. Check that it is a valid CSV and try again.")
        return

    if len(df.columns) == 0:
        st.warning("TALOS could not identify any usable columns in this CSV.")
        return
    has_named_column = any(
        str(column).strip() and not str(column).startswith("Unnamed:") for column in df.columns
    )
    if not has_named_column:
        st.warning("TALOS could not identify usable column names in this CSV.")
        return
    if len(df.index) == 0:
        st.warning("This CSV has column headings but no data rows to profile.")
        return

    try:
        fingerprint_input = uploaded_file.name.encode("utf-8") + b"\0" + file_contents
        file_fingerprint = hashlib.sha256(fingerprint_input).hexdigest()
        initialize_dataset_state(file_fingerprint, df)
        original_df = st.session_state["talos_original_df"]
        working_df = st.session_state["talos_working_df"]
        profile = profile_dataset(
            original_df,
            file_name=uploaded_file.name,
            file_size_bytes=len(file_contents),
        )
        original_findings = inspect_dataset(original_df)
        working_findings = inspect_dataset(working_df)
    except Exception:
        logger.exception("Unexpected error while profiling an uploaded CSV.")
        st.error("TALOS received the file but could not complete its profile. Try another CSV.")
        return

    notice = st.session_state.get("talos_notice", "")
    if notice:
        st.success(notice)
        st.session_state["talos_notice"] = ""
    else:
        st.success("Inspection complete. The guardian has recorded the findings.")

    render_dataset_profile(profile, original_df)
    st.markdown('<p class="talos-section-kicker">Original dataset inspection</p>', unsafe_allow_html=True)
    render_missing_data(original_findings["missing"])
    render_duplicate_checks(original_findings["duplicates"])
    render_category_consistency(original_findings["categories"])
    render_numeric_outliers(original_findings["outliers"])
    render_structural_signals(original_findings["structure"])
    render_integrity_score(original_findings["score"])
    render_forge(original_df, working_df, original_findings, working_findings)
    render_exports_and_report(profile, original_findings, working_findings)
    st.markdown(
        '<p class="talos-footer">Original data preserved · Approved transformations remain in this session.</p>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
