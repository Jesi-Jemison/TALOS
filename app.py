"""Streamlit interface for TALOS dataset intake and inspection."""

import base64
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from pandas.api.types import is_bool_dtype, is_numeric_dtype, is_object_dtype, is_string_dtype

from src.profiler import identify_column_types, load_csv, profile_dataset
from src.evidence import (
    build_category_variants_table,
    build_comparison_table,
    build_duplicate_rows_table,
    build_evidence_pack,
    build_evidence_readme,
    build_identifier_findings_table,
    build_integrity_score_table,
    build_missing_values_table,
    build_outlier_rows_table,
    build_result_tables,
    build_score_comparison_table,
    build_structure_table,
    build_structural_findings_table,
)
from src.quality_checks import (
    inspect_category_consistency,
    inspect_duplicates,
    inspect_missing_values,
    inspect_numeric_outliers,
    inspect_structure,
)
from src.scoring import calculate_integrity_score
from src.theme import DEFAULT_THEME, theme_token_css, theme_tokens
from src.reporting import (
    build_cleaned_csv,
    build_export_filename,
    build_inspection_report_html,
    build_transformation_log,
)
from src.transformations import (
    append_ledger_record,
    apply_transformations,
    build_repair_plan,
    build_suggested_transformations,
    create_working_copy,
    reset_working_copy,
)


logger = logging.getLogger(__name__)
SESSION_PREFERENCE_KEYS = {"talos_theme_preference", "talos_demo_loaded"}


def load_stylesheet(theme: str = DEFAULT_THEME) -> None:
    """Apply shared TALOS styles and the selected session's colour tokens."""
    stylesheet_path = Path(__file__).parent / "assets" / "talos.css"
    try:
        stylesheet = stylesheet_path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("TALOS stylesheet was not available at %s", stylesheet_path)
        stylesheet = ""

    st.markdown(
        f"<style>{stylesheet}\n{theme_token_css(theme)}</style>",
        unsafe_allow_html=True,
    )


def render_dataframe(table: pd.DataFrame, **kwargs: object) -> None:
    """Render a readable table whose cell colours follow the active theme."""
    tokens = theme_tokens(st.session_state.get("talos_theme_preference", DEFAULT_THEME))
    styled_table = table.style.set_properties(
        **{
            "background-color": tokens["talos-panel"],
            "color": tokens["talos-text"],
            "border-color": tokens["talos-line"],
        }
    ).set_table_styles(
        [
            {
                "selector": "th",
                "props": [
                    ("background-color", tokens["talos-panel-raised"]),
                    ("color", tokens["talos-bronze-strong"]),
                    ("border-color", tokens["talos-line"]),
                ],
            },
            {"selector": "td", "props": [("border-color", tokens["talos-line"])]},
        ]
    )
    st.dataframe(styled_table, **kwargs)


def render_csv_download(
    table: pd.DataFrame,
    source_filename: str,
    export_type: str,
    widget_key: str,
    empty_message: str = "No applicable evidence to export.",
    button_label: str = "Download CSV",
) -> None:
    """Place a small CSV download beside an applicable result table."""
    if table.empty:
        st.caption(empty_message)
        return
    csv_bytes = table.to_csv(index=False).encode("utf-8")
    st.download_button(
        button_label,
        data=csv_bytes,
        file_name=build_export_filename(source_filename, export_type),
        mime="text/csv",
        key=f"download-evidence-{widget_key}",
    )


def build_header_visual_html(assets_directory: Path) -> str:
    """Load the wide guardian art, falling back to the compact local emblem."""
    guardian_path = assets_directory / "talos-sentinel-panel.webp"
    emblem_path = assets_directory / "talos-emblem.svg"
    try:
        guardian_bytes = guardian_path.read_bytes()
        encoded_guardian = base64.b64encode(guardian_bytes).decode("ascii")
        return (
            '<div class="talos-sentinel-panel">'
            f'<img class="talos-sentinel-image" src="data:image/webp;base64,{encoded_guardian}" '
            'alt="TALOS bronze automaton guardian with illuminated amethyst eyes">'
            "</div>"
        )
    except OSError:
        logger.warning("TALOS guardian artwork was not available at %s", guardian_path)
        try:
            emblem_svg = emblem_path.read_text(encoding="utf-8")
            encoded_emblem = base64.b64encode(emblem_svg.encode("utf-8")).decode("ascii")
            return (
                '<div class="talos-sentinel-panel talos-sentinel-panel--fallback">'
                '<div class="talos-emblem-wrap">'
                f'<img class="talos-emblem" src="data:image/svg+xml;base64,{encoded_emblem}" '
                'alt="TALOS bronze guardian emblem">'
                "</div></div>"
            )
        except OSError:
            logger.warning("TALOS emblem was not available at %s", emblem_path)
            return (
                '<div class="talos-sentinel-panel talos-sentinel-panel--fallback">'
                '<span role="img" aria-label="TALOS guardian emblem">◈</span></div>'
            )


def render_header() -> None:
    """Show TALOS identity and system status."""
    visual_html = build_header_visual_html(Path(__file__).parent / "assets")

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
                {visual_html}
            </div>
        </header>
        """,
        unsafe_allow_html=True,
    )
    _, theme_column = st.columns([8, 2])
    with theme_column:
        with st.container(key="talos-theme-control"):
            st.radio(
                "Appearance",
                ["Dark", "Light"],
                horizontal=True,
                key="talos_theme_preference",
                label_visibility="collapsed",
            )


def build_guardian_summary(
    findings: dict[str, dict[str, object]],
) -> list[dict[str, str]]:
    """Translate existing inspection results into concise, qualified status lines."""
    missing = findings["missing"]
    affected_columns = int(missing["affected_column_count"])
    missing_percentage = float(missing["missing_percentage"])
    if affected_columns:
        missing_line = (
            f"{affected_columns} column{'s' if affected_columns != 1 else ''} "
            f"contain{'s' if affected_columns == 1 else ''} missing values "
            f"({missing_percentage:.1f}% of all cells)."
        )
        severity_counts = missing["severity_counts"]
        significant_columns = int(
            severity_counts.get("Significant", 0) + severity_counts.get("Critical", 0)
        )
        if significant_columns:
            missing_line += (
                f" {significant_columns} column{'s' if significant_columns != 1 else ''} "
                f"meet{'s' if significant_columns == 1 else ''} TALOS's significant missingness thresholds."
            )
            missing_status = "Significant finding"
        else:
            missing_status = "Review recommended"
    else:
        missing_line = "No missing values were detected."
        missing_status = "Clear"

    duplicates = findings["duplicates"]
    duplicate_count = int(duplicates["exact_duplicate_row_count"])
    repeated_identifiers = int(duplicates["identifier_candidates_with_repeats"])
    identifier_candidates = int(duplicates["identifier_candidate_count"])
    if duplicate_count:
        duplicate_line = (
            f"{duplicate_count} exact duplicate row{'s' if duplicate_count != 1 else ''} "
            f"appear{'s' if duplicate_count == 1 else ''}; this may be intentional."
        )
        duplicate_status = "Review recommended"
    elif repeated_identifiers:
        duplicate_line = (
            f"No exact duplicate rows; {repeated_identifiers} name-based identifier "
            "field(s) contain repeated values."
        )
        duplicate_status = "Observation"
    elif identifier_candidates:
        duplicate_line = (
            f"No exact duplicate rows. {identifier_candidates} field name(s) suggest "
            "possible identifiers; TALOS does not assume they must be unique."
        )
        duplicate_status = "Observation"
    else:
        duplicate_line = "No exact duplicate rows or identifier-name candidates were detected."
        duplicate_status = "Clear"

    categories = findings["categories"]
    category_groups = int(categories["inconsistent_group_count"])
    checked_category_columns = len(categories["checked_columns"])
    if category_groups:
        category_line = (
            f"{category_groups} category variant group{'s' if category_groups != 1 else ''} "
            f"differ{'s' if category_groups == 1 else ''} only by case or spacing; "
            "review their meaning before consolidating."
        )
        category_status = "Review recommended"
    elif checked_category_columns:
        category_line = "No case or spacing variants were detected in checked text fields."
        category_status = "Clear"
    else:
        category_line = "No suitable text fields were available for category comparison."
        category_status = "Observation"

    outliers = findings["outliers"]
    outlier_count = int(outliers["total_outlier_values"])
    eligible_numeric_columns = int(outliers["eligible_column_count"])
    if outlier_count:
        outlier_line = (
            f"{outlier_count} value{'s' if outlier_count != 1 else ''} "
            f"fall{'s' if outlier_count == 1 else ''} outside the IQR review range; "
            "a flag is not proof of an error."
        )
        outlier_status = "Observation"
    elif eligible_numeric_columns:
        outlier_line = "No IQR-range values were flagged in eligible numeric fields."
        outlier_status = "Clear"
    else:
        outlier_line = "No numeric fields met the requirements for IQR inspection."
        outlier_status = "Observation"

    structural_count = len(build_structural_findings_table(findings["structure"]))
    if structural_count:
        structural_line = (
            f"{structural_count} contextual structure signal{'s' if structural_count != 1 else ''} "
            f"{'was' if structural_count == 1 else 'were'} recorded; "
            "they are not automatically defects."
        )
        if findings["structure"]["empty_columns"] or findings["structure"]["constant_columns"]:
            structural_status = "Review recommended"
        else:
            structural_status = "Observation"
    else:
        structural_line = (
            "No empty, constant, high-cardinality, identifier, or numeric-pattern signals were found."
        )
        structural_status = "Clear"

    return [
        {"area": "Missing values", "status": missing_status, "message": missing_line},
        {"area": "Duplicates & identifiers", "status": duplicate_status, "message": duplicate_line},
        {"area": "Category consistency", "status": category_status, "message": category_line},
        {"area": "Numeric distribution", "status": outlier_status, "message": outlier_line},
        {"area": "Structure", "status": structural_status, "message": structural_line},
    ]


def render_guardian_summary(findings: dict[str, dict[str, object]]) -> None:
    """Keep a readable, non-verdict summary in view above the detailed checks."""
    st.subheader("👁️ Guardian Summary")
    st.caption("A concise reading of TALOS signals. Context still belongs to the dataset owner.")
    summary = build_guardian_summary(findings)
    status_icons = {
        "Clear": "✓",
        "Observation": "◌",
        "Review recommended": "⚠",
        "Significant finding": "◆",
    }
    columns = st.columns(2)
    for index, item in enumerate(summary):
        with columns[index % len(columns)].container(border=True):
            st.markdown(
                f"**{status_icons[item['status']]} {item['status']} · {item['area']}**"
            )
            st.write(item["message"])


def render_check_context(checked: str, why: str, limits: str) -> None:
    """Explain a check's scope and limits in plain language."""
    columns = st.columns(3)
    columns[0].markdown("**What TALOS checked**")
    columns[0].write(checked)
    columns[1].markdown("**Why it matters**")
    columns[1].write(why)
    columns[2].markdown("**What TALOS cannot conclude**")
    columns[2].write(limits)


def render_source_status(profile: dict[str, object], df: pd.DataFrame, demo: bool) -> None:
    """Show the active source and preservation state near the top of the inspection."""
    label = "Synthetic demo dataset · talos_demo.csv" if demo else str(profile["file_name"])
    st.markdown(
        f"**Source received** · {label} · {len(df.index):,} rows × {len(df.columns):,} columns  \n"
        "Original dataset preserved; no inspection step changes it."
    )


def render_dataset_profile(profile: dict[str, object], df: pd.DataFrame) -> None:
    """Render the dataset profile and preview inside compact, optional sections."""
    with st.expander(
        f"👁️ Dataset Overview & Structure · {profile['row_count']:,} rows · {profile['column_count']:,} columns",
        expanded=False,
    ):
        st.markdown('<p class="talos-section-kicker">Structural inspection</p>', unsafe_allow_html=True)
        st.subheader("Dataset Overview")
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
        structure = build_structure_table(profile)
        render_dataframe(structure, width="stretch", hide_index=True)

    with st.expander(f"📊 Data Preview · first {min(10, len(df.index)):,} rows", expanded=False):
        st.caption("A sample of the source only. TALOS does not alter these values during inspection.")
        render_dataframe(df.head(10), width="stretch", hide_index=True)


def render_missing_data(
    analysis: dict[str, object], source_filename: str = "dataset.csv"
) -> None:
    """Render dataset-wide and column-level missing-value findings."""
    with st.expander(
        f"🕳️ Missing Data · {analysis['affected_column_count']} affected columns · {analysis['missing_percentage']:.1f}% of cells",
        expanded=False,
    ):
        st.markdown('<p class="talos-section-kicker">Completeness</p>', unsafe_allow_html=True)
        st.subheader("Missing Data")
        render_check_context(
            "Counts blank or null cells by column and across the dataset.",
            "Missingness can affect totals, comparisons, joins, and the rows available to an analysis.",
            "TALOS cannot tell whether a value is unknown, inapplicable, or intentionally blank.",
        )
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

        rows = build_missing_values_table(analysis)
        if not rows.empty:
            render_dataframe(rows, width="stretch", hide_index=True)


def render_duplicate_checks(
    analysis: dict[str, object],
    df: pd.DataFrame | None = None,
    source_filename: str = "dataset.csv",
) -> None:
    """Render exact duplicate rows and possible identifier findings."""
    with st.expander(
        f"🪞 Duplicate Inspection · {analysis['exact_duplicate_row_count']} exact duplicate rows · {analysis['identifier_candidate_count']} identifier-name candidates",
        expanded=False,
    ):
        st.markdown('<p class="talos-section-kicker">Record repetition</p>', unsafe_allow_html=True)
        st.subheader("Duplicate Inspection")
        render_check_context(
            "Finds rows that match earlier rows and fields whose names suggest identifiers.",
            "Repeated records or identifier values can affect counts, record matching, and joins.",
            "TALOS cannot decide whether repeated records or identifier values are valid in context.",
        )
        metrics = st.columns(3)
        metrics[0].metric("Exact duplicate rows", analysis["exact_duplicate_row_count"])
        metrics[1].metric("Rows duplicated", f"{analysis['exact_duplicate_percentage']:.1f}%")
        metrics[2].metric("Possible identifier fields", analysis["identifier_candidate_count"])

        if analysis["exact_duplicate_row_count"]:
            st.warning(
                "Some rows exactly match an earlier row. This may be intentional; "
                "TALOS does not remove duplicates."
            )
            duplicate_rows = build_duplicate_rows_table(df if df is not None else pd.DataFrame(), analysis)
            st.caption("Rows involved in exact matches. Source row numbers refer to CSV data rows.")
            render_dataframe(duplicate_rows.head(20), width="stretch", hide_index=True)
            if len(duplicate_rows.index) > 20:
                st.caption(f"Showing 20 of {len(duplicate_rows.index):,} duplicate-group rows.")
        else:
            st.success("No exact duplicate rows found.")
            st.caption("No duplicate-row evidence to export.")

        rows = build_identifier_findings_table(analysis)
        if not rows.empty:
            st.caption(
                "Candidate fields are selected from their names only. Repeats are a review signal; "
                "not every candidate must be unique."
            )
            render_dataframe(rows, width="stretch", hide_index=True)
            if analysis["identifier_candidates_with_repeats"]:
                st.info(
                    "Repeated values appear in a possible identifier field. "
                    "Confirm whether uniqueness is required."
                )
        else:
            st.caption("No column names clearly suggest a possible identifier field.")


def render_category_consistency(
    analysis: dict[str, object], source_filename: str = "dataset.csv"
) -> None:
    """Render case and whitespace variation in suitable text categories."""
    with st.expander(
        f"🧬 Category Consistency · {analysis['inconsistent_group_count']} variant groups · {len(analysis['checked_columns'])} text columns checked",
        expanded=False,
    ):
        st.markdown('<p class="talos-section-kicker">Category variation</p>', unsafe_allow_html=True)
        st.subheader("Category Consistency")
        render_check_context(
            "Compares suitable text categories after trimming and collapsing spaces and ignoring case.",
            "Equivalent labels can split counts or create duplicate category values in summaries.",
            "TALOS cannot determine whether similar labels mean the same thing in the source context.",
        )
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
            rows = build_category_variants_table(analysis)
            render_dataframe(rows, width="stretch", hide_index=True)
        elif analysis["checked_columns"]:
            st.success("No case or whitespace variants found in the text columns TALOS checked.")
        else:
            st.info("No suitable text category columns were available for this check.")

        if analysis["skipped_columns"]:
            with st.expander(f"Columns not checked · {len(analysis['skipped_columns'])}"):
                skipped = pd.DataFrame(analysis["skipped_columns"]).rename(
                    columns={"column": "Column", "reason": "Reason"}
                )
                render_dataframe(skipped, width="stretch", hide_index=True)


def render_numeric_outliers(
    analysis: dict[str, object],
    df: pd.DataFrame | None = None,
    source_filename: str = "dataset.csv",
) -> None:
    """Render IQR summaries and explain which numeric fields were skipped."""
    with st.expander(
        f"📐 Numeric Outliers · {analysis['total_outlier_values']} IQR flags · {analysis['eligible_column_count']} eligible columns",
        expanded=False,
    ):
        st.markdown('<p class="talos-section-kicker">Distribution signals</p>', unsafe_allow_html=True)
        st.subheader("Numeric Outliers")
        render_check_context(
            "Flags values beyond Q1 − 1.5 × IQR or Q3 + 1.5 × IQR in eligible numeric fields.",
            "Unusual values can influence averages, ranges, and model inputs.",
            "An IQR flag does not establish that a value is incorrect or should be removed.",
        )
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
            render_dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            outlier_rows = build_outlier_rows_table(
                df if df is not None else pd.DataFrame(), analysis
            )
            st.caption(
                f"Flagged source values. Showing up to 20 of {len(outlier_rows):,}; "
                "the CSV contains every flagged value."
            )
            render_dataframe(outlier_rows.head(20), width="stretch", hide_index=True)
        elif analysis["eligible_column_count"]:
            st.success("No IQR outliers found in the numeric columns TALOS checked.")
            st.caption("No flagged-value evidence to export.")
        else:
            st.info("No numeric columns met the minimum requirements for IQR inspection.")

        if analysis["skipped_columns"]:
            with st.expander(f"Numeric fields not checked · {len(analysis['skipped_columns'])}"):
                skipped = pd.DataFrame(analysis["skipped_columns"]).rename(
                    columns={"column": "Column", "reason": "Reason"}
                )
                render_dataframe(skipped, width="stretch", hide_index=True)


def render_structural_signals(
    analysis: dict[str, object], source_filename: str = "dataset.csv"
) -> None:
    """Render a collapsed summary row for structural and identifier signals."""
    signal_count = len(build_structural_findings_table(analysis))
    with st.expander(
        f"🧱 Structural & Identifier Checks · {signal_count} contextual signals",
        expanded=False,
    ):
        render_check_context(
            "Looks for empty or constant fields, high-cardinality text, identifier-name hints, and numeric patterns.",
            "These patterns can affect grouping, joins, interpretation, or later analysis choices.",
            "TALOS cannot infer whether a field or value is appropriate without its intended use.",
        )
        _render_structural_signal_details(analysis, source_filename)


def _render_structural_signal_details(
    analysis: dict[str, object], source_filename: str
) -> None:
    """Render the detailed structural and identifier findings."""
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
        render_dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

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
        render_dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

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
        render_dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

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
        render_dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

def render_integrity_score(
    analysis: dict[str, object], source_filename: str = "dataset.csv"
) -> None:
    """Render the weighted score and the contribution of each component."""
    st.markdown('<p class="talos-section-kicker">Combined inspection</p>', unsafe_allow_html=True)
    st.subheader("🛡️ Dataset Integrity Score")
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
    with st.expander(
        f"Score components · {analysis['score']} / 100 · {analysis['band']}",
        expanded=False,
    ):
        rows = build_integrity_score_table(analysis)
        rows["Weight"] = rows["Weight"].map(lambda value: f"{value}%")
        rows["Component score"] = rows["Component score"].map(lambda value: f"{value:.1f}")
        rows["Weighted points"] = rows["Weighted points"].map(lambda value: f"{value:.1f}")
        render_dataframe(rows, width="stretch", hide_index=True)
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


def initialize_dataset_state(file_fingerprint: str, uploaded_df: pd.DataFrame) -> bool:
    """Keep an untouched original and cache read-only findings for one upload."""
    if st.session_state.get("talos_file_fingerprint") == file_fingerprint:
        return False

    for key in list(st.session_state.keys()):
        if key.startswith("talos_") and key not in SESSION_PREFERENCE_KEYS:
            del st.session_state[key]

    original_df = create_working_copy(uploaded_df)
    original_findings = inspect_dataset(original_df)
    st.session_state["talos_file_fingerprint"] = file_fingerprint
    st.session_state["talos_original_df"] = original_df
    st.session_state["talos_working_df"] = create_working_copy(original_df)
    st.session_state["talos_original_findings"] = original_findings
    st.session_state["talos_working_findings"] = original_findings
    st.session_state["talos_transformation_ledger"] = []
    st.session_state["talos_reset_confirmation"] = False
    st.session_state["talos_notice"] = ""
    st.session_state["talos_data_revision"] = 0
    return True


def clear_dataset_state() -> None:
    """Discard in-session data but preserve the user's theme preference."""
    for key in list(st.session_state.keys()):
        if key.startswith("talos_") and key not in SESSION_PREFERENCE_KEYS:
            del st.session_state[key]


def clear_repair_widget_state() -> None:
    """Clear selection controls in a callback-safe pre-rerun context."""
    for key in list(st.session_state.keys()):
        if key.startswith("talos_repair_select_"):
            st.session_state[key] = False
        elif key.startswith("talos_missing_strategy_"):
            st.session_state[key] = "Leave unchanged"
        elif key.startswith("talos_missing_number_"):
            st.session_state[key] = 0.0
        elif key.startswith("talos_missing_text_"):
            st.session_state[key] = ""
        elif key.startswith("talos_category_canonical_"):
            del st.session_state[key]
        elif key.startswith("talos_repair_group_"):
            st.session_state[key] = False


def invalidate_export_cache() -> None:
    """Discard session-generated exports after the working copy changes."""
    for key in ("talos_cached_report_html", "talos_cached_report_revision", "talos_cached_evidence_pack", "talos_cached_evidence_revision"):
        st.session_state.pop(key, None)


def update_working_inspection(working_df: pd.DataFrame) -> None:
    """Reinspect an approved working copy and invalidate its old exports."""
    st.session_state["talos_working_findings"] = inspect_dataset(working_df)
    st.session_state["talos_data_revision"] = st.session_state.get("talos_data_revision", 0) + 1
    invalidate_export_cache()


def prepare_evidence_tables(profile: dict[str, object]) -> None:
    """Build original and current-copy evidence tables once per session revision."""
    revision = int(st.session_state.get("talos_data_revision", 0))
    if st.session_state.get("talos_evidence_revision") == revision:
        return

    original_df = st.session_state["talos_original_df"]
    working_df = st.session_state["talos_working_df"]
    original_findings = st.session_state["talos_original_findings"]
    working_findings = st.session_state["talos_working_findings"]
    original_tables = build_result_tables(original_df, profile, original_findings)
    working_profile = {"columns": identify_column_types(working_df)}
    working_tables = build_result_tables(working_df, working_profile, working_findings)
    st.session_state["talos_original_result_tables"] = original_tables
    st.session_state["talos_working_result_tables"] = working_tables
    st.session_state["talos_comparison_table"] = build_comparison_table(
        original_df, working_df, original_findings, working_findings
    )
    st.session_state["talos_original_summary"] = summarize_dataset(
        original_df, original_findings
    )
    st.session_state["talos_working_summary"] = summarize_dataset(
        working_df, working_findings
    )
    st.session_state["talos_evidence_revision"] = revision


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


def repair_selection_key(repair_id: str) -> str:
    """Build a stable, compact Streamlit key for a repair suggestion."""
    digest = hashlib.sha256(repair_id.encode("utf-8")).hexdigest()[:16]
    return f"talos_repair_select_{digest}"


def _selection_callback(repair_ids: tuple[str, ...], selected: bool) -> None:
    """Select or clear a known set of repair checkboxes before rerun."""
    for repair_id in repair_ids:
        st.session_state[repair_selection_key(repair_id)] = selected


def _group_selection_key(group_id: str) -> str:
    """Build a stable widget key for a repair group selector."""
    digest = hashlib.sha256(group_id.encode("utf-8")).hexdigest()[:16]
    return f"talos_repair_group_{digest}"


def _group_selection_callback(
    repair_ids: tuple[str, ...], group_widget_key: str
) -> None:
    """Apply a group checkbox state to its individual repair proposals."""
    _selection_callback(repair_ids, bool(st.session_state.get(group_widget_key, False)))


def _clear_repair_callback(repair_ids: tuple[str, ...], missing_columns: tuple[str, ...]) -> None:
    """Clear action and missing-strategy controls in Streamlit's callback phase."""
    _selection_callback(repair_ids, False)
    for column in missing_columns:
        digest = hashlib.sha256(column.encode("utf-8")).hexdigest()[:16]
        st.session_state[f"talos_missing_strategy_{digest}"] = "Leave unchanged"
        st.session_state[f"talos_missing_number_{digest}"] = 0.0
        st.session_state[f"talos_missing_text_{digest}"] = ""
    for key in list(st.session_state.keys()):
        if key.startswith("talos_repair_group_"):
            st.session_state[key] = False


def _canonical_state_key(repair_id: str) -> str:
    digest = hashlib.sha256(repair_id.encode("utf-8")).hexdigest()[:16]
    return f"talos_category_canonical_{digest}"


def _selected_missing_action(
    series: pd.Series, column: str, selected: str, digest: str
) -> dict[str, object] | None:
    """Translate one explicit per-column choice into a transformation action."""
    if selected == "Leave unchanged":
        return None
    if selected == "Remove rows with missing values":
        action_type = "remove_rows_with_missing"
        action: dict[str, object] = {"type": action_type, "column": column}
    elif selected in {"Fill with median", "Fill with mean"}:
        action_type = "fill_numeric_missing"
        method = "median" if selected.endswith("median") else "mean"
        action = {"type": action_type, "column": column, "method": method}
    elif selected == "Fill with custom number":
        action_type = "fill_numeric_missing"
        action = {
            "type": action_type,
            "column": column,
            "method": "custom",
            "value": st.session_state.get(f"talos_missing_number_{digest}", 0.0),
        }
    elif selected == "Fill with custom text":
        action_type = "fill_text_missing"
        action = {
            "type": action_type,
            "column": column,
            "method": "custom",
            "value": st.session_state.get(f"talos_missing_text_{digest}", ""),
        }
    elif selected == "Fill with most common value":
        action_type = "fill_text_missing"
        action = {"type": action_type, "column": column, "method": "mode"}
    else:
        return None
    action["label"] = f"{selected} · {column}"
    return action


def apply_selected_repairs(actions: tuple[dict[str, object], ...]) -> None:
    """Callback that atomically applies selected repairs and reinspects the copy."""
    if not actions:
        return
    working_df = st.session_state["talos_working_df"]
    updated_df, records = apply_transformations(working_df, list(actions))
    updated_ledger = st.session_state["talos_transformation_ledger"]
    for record in records:
        updated_ledger = append_ledger_record(updated_ledger, record)
    st.session_state["talos_working_df"] = updated_df
    st.session_state["talos_transformation_ledger"] = updated_ledger
    update_working_inspection(updated_df)
    clear_repair_widget_state()
    st.session_state["talos_notice"] = (
        f"{len(records)} approved repair(s) recorded in the ledger. The working copy has returned to inspection."
    )


def queue_selected_repairs(actions: tuple[dict[str, object], ...]) -> None:
    """Queue an approved repair batch so it can run with visible status text."""
    if actions:
        st.session_state["talos_pending_repair_actions"] = actions


def reset_working_copy_callback() -> None:
    """Restore the source copy, clear review controls, and reinspect it."""
    original_df = st.session_state["talos_original_df"]
    reset_df = reset_working_copy(original_df)
    st.session_state["talos_working_df"] = reset_df
    st.session_state["talos_transformation_ledger"] = []
    st.session_state["talos_reset_confirmation"] = False
    st.session_state["talos_working_findings"] = st.session_state["talos_original_findings"]
    st.session_state["talos_data_revision"] = st.session_state.get("talos_data_revision", 0) + 1
    invalidate_export_cache()
    clear_repair_widget_state()
    st.session_state["talos_notice"] = "The Forge has been cleared. Original source restored."


def render_repair_control_center(
    working_df: pd.DataFrame, findings: dict[str, dict[str, object]]
) -> None:
    """Render grouped repair selections, an explicit plan, and one apply action."""
    suggestions = build_suggested_transformations(working_df, findings)
    whitespace = [item for item in suggestions if item["action"]["type"] == "normalize_whitespace"]
    categories = [item for item in suggestions if item["action"]["type"] == "consolidate_category"]
    duplicates = [item for item in suggestions if item["action"]["type"] == "remove_exact_duplicates"]
    empty_columns = [item for item in suggestions if item["action"]["type"] == "remove_empty_column"]
    missing_columns = [
        str(column)
        for column in working_df.columns
        if working_df[column].isna().any()
    ]
    repair_classes = sum(
        bool(group)
        for group in (whitespace, categories, missing_columns, duplicates, empty_columns)
    )
    st.markdown(
        f"**{repair_classes} repair classes available · "
        f"{len(suggestions) + len(missing_columns)} proposed transformations**"
    )

    all_ids = tuple(str(item["suggestion_id"]) for item in suggestions)
    whitespace_ids = tuple(str(item["suggestion_id"]) for item in whitespace)
    category_ids = tuple(str(item["suggestion_id"]) for item in categories)
    duplicate_ids = tuple(str(item["suggestion_id"]) for item in duplicates)
    recommended_ids = tuple(
        str(item["suggestion_id"])
        for item in suggestions
        if item["action"]["type"] in {
            "normalize_whitespace",
            "consolidate_category",
            "remove_exact_duplicates",
            "remove_empty_column",
        }
    )
    action_buttons = st.columns(2)
    action_buttons[0].button(
        "Select recommended repairs",
        key="talos-select-recommended",
        disabled=not recommended_ids,
        on_click=_selection_callback,
        args=(recommended_ids, True),
        help="Select only the listed proposals. TALOS still shows a repair plan before applying them.",
    )
    action_buttons[1].button(
        "Clear all selections",
        key="talos-clear-repairs",
        on_click=_clear_repair_callback,
        args=(all_ids, tuple(missing_columns)),
    )
    bulk_buttons = st.columns(3)
    bulk_buttons[0].button(
        "Select text cleanups",
        key="talos-select-text-repairs",
        disabled=not whitespace_ids,
        on_click=_selection_callback,
        args=(whitespace_ids, True),
    )
    bulk_buttons[1].button(
        "Select category repairs",
        key="talos-select-category-repairs",
        disabled=not category_ids,
        on_click=_selection_callback,
        args=(category_ids, True),
    )
    bulk_buttons[2].button(
        "Select exact duplicate removal",
        key="talos-select-duplicate-repair",
        disabled=not duplicate_ids,
        on_click=_selection_callback,
        args=(duplicate_ids, True),
    )

    selected_actions: list[dict[str, object]] = []
    with st.expander(f"Text & whitespace · {len(whitespace)} proposed", expanded=False):
        if not whitespace:
            st.caption("No safe whitespace normalisations are currently suggested.")
        elif len(whitespace) > 1:
            group_key = _group_selection_key("whitespace")
            st.session_state[group_key] = all(
                bool(st.session_state.get(repair_selection_key(repair_id), False))
                for repair_id in whitespace_ids
            )
            st.checkbox(
                "Select all text cleanups",
                key=group_key,
                on_change=_group_selection_callback,
                args=(whitespace_ids, group_key),
            )
        for suggestion in whitespace:
            column = str(suggestion["action"]["column"])
            repair_id = str(suggestion["suggestion_id"])
            selected = st.checkbox(
                f"{column} · {suggestion['affected_count']} values",
                key=repair_selection_key(repair_id),
                help=str(suggestion["description"]),
            )
            if selected:
                action = dict(suggestion["action"])
                action["label"] = f"Normalize whitespace · {column}"
                selected_actions.append(action)

    with st.expander(f"Category normalisation · {len(categories)} proposed", expanded=False):
        if not categories:
            st.caption("No category-variant groups are currently suggested.")
        elif len(categories) > 1:
            group_key = _group_selection_key("categories")
            st.session_state[group_key] = all(
                bool(st.session_state.get(repair_selection_key(repair_id), False))
                for repair_id in category_ids
            )
            st.checkbox(
                "Select all category groups",
                key=group_key,
                on_change=_group_selection_callback,
                args=(category_ids, group_key),
            )
        for suggestion in categories:
            repair_id = str(suggestion["suggestion_id"])
            action = dict(suggestion["action"])
            column = str(action["column"])
            normalized = str(suggestion.get("normalized_value", ""))
            variant_names = [str(item["value"]) for item in suggestion["variants"]]
            variant_label = " / ".join(variant_names[:4])
            if len(variant_names) > 4:
                variant_label += f" / +{len(variant_names) - 4} more"
            selected = st.checkbox(
                f"{column} · {normalized}: {variant_label}",
                key=repair_selection_key(repair_id),
                help=str(suggestion["description"]),
            )
            variants = suggestion["variants"]
            variant_table = pd.DataFrame(variants).rename(
                columns={"value": "Observed value", "count": "Rows"}
            )
            render_dataframe(variant_table, width="stretch", hide_index=True)
            values = [item["value"] for item in variants]
            proposed = suggestion["proposed_canonical"]
            canonical = st.selectbox(
                "Proposed canonical value",
                values,
                index=values.index(proposed),
                key=_canonical_state_key(repair_id),
            )
            st.caption("TALOS proposes the most common spelling. You choose the final representation.")
            if selected:
                action["canonical_value"] = canonical
                action["label"] = f"Consolidate {column} variants to {canonical}"
                selected_actions.append(action)

    with st.expander(f"Missing values · {len(missing_columns)} columns", expanded=False):
        if not missing_columns:
            st.caption("No missing values remain in the current working copy.")
        for column in missing_columns:
            series = working_df[column]
            digest = hashlib.sha256(column.encode("utf-8")).hexdigest()[:16]
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
            with st.container(border=True):
                st.markdown(f"**{column}** · {int(series.isna().sum())} missing values")
                selected = st.selectbox(
                    "Choose a strategy; TALOS leaves this field unchanged by default.",
                    choices,
                    key=f"talos_missing_strategy_{digest}",
                )
                if selected == "Fill with custom number":
                    st.number_input(
                        "Custom numeric value",
                        value=0.0,
                        key=f"talos_missing_number_{digest}",
                    )
                elif selected == "Fill with custom text":
                    st.text_input(
                        "Custom replacement text",
                        value="",
                        key=f"talos_missing_text_{digest}",
                    )
                action = _selected_missing_action(series, column, selected, digest)
                if action:
                    selected_actions.append(action)

    with st.expander(f"Exact duplicates · {len(duplicates)} proposed", expanded=False):
        if not duplicates:
            st.caption("No exact duplicate-row removal is suggested.")
        elif len(duplicates) > 1:
            group_key = _group_selection_key("duplicates")
            st.session_state[group_key] = all(
                bool(st.session_state.get(repair_selection_key(repair_id), False))
                for repair_id in duplicate_ids
            )
            st.checkbox(
                "Select all duplicate groups",
                key=group_key,
                on_change=_group_selection_callback,
                args=(duplicate_ids, group_key),
            )
        for suggestion in duplicates:
            repair_id = str(suggestion["suggestion_id"])
            selected = st.checkbox(
                f"Remove {suggestion['affected_count']} exact duplicate row(s)",
                key=repair_selection_key(repair_id),
                help=str(suggestion["description"]),
            )
            if selected:
                action = dict(suggestion["action"])
                action["label"] = "Remove exact duplicate rows"
                selected_actions.append(action)

    with st.expander(f"Empty columns · {len(empty_columns)} proposed", expanded=False):
        if not empty_columns:
            st.caption("No completely empty columns are currently suggested for removal.")
        for suggestion in empty_columns:
            repair_id = str(suggestion["suggestion_id"])
            column = str(suggestion["action"]["column"])
            selected = st.checkbox(
                f"Remove empty column · {column}",
                key=repair_selection_key(repair_id),
                help=str(suggestion["description"]),
            )
            if selected:
                action = dict(suggestion["action"])
                action["label"] = f"Remove empty column · {column}"
                selected_actions.append(action)

    if not selected_actions:
        st.info("Select one or more repairs to prepare a Repair Plan. Nothing changes yet.")
        return

    try:
        plan = build_repair_plan(working_df, selected_actions)
    except (KeyError, TypeError, ValueError) as error:
        st.error(f"TALOS could not prepare this repair plan: {error}")
        return

    st.subheader("Repair Plan")
    st.markdown(
        "The Forge is loaded. Review the selected actions before applying them. "
        "The estimates describe the proposed edits; they do not establish that a replacement is correct."
    )
    plan_metrics = st.columns(5)
    plan_metrics[0].metric("Selected repairs", plan["selected_count"])
    plan_metrics[1].metric("Affected columns", len(plan["affected_columns"]))
    plan_metrics[2].metric("Values changed", plan["estimated_values_changed"])
    plan_metrics[3].metric("Rows removed", plan["estimated_rows_removed"])
    plan_metrics[4].metric("Columns removed", plan["estimated_columns_removed"])
    st.caption("Affected fields: " + ", ".join(plan["affected_columns"]))

    for action, record in zip(selected_actions, plan["records"]):
        with st.expander(f"Preview · {action.get('label', action['type'])}", expanded=False):
            st.write(record["description"])
            summary = st.columns(3)
            summary[0].metric("Affected rows", record["affected_rows"])
            summary[1].metric("Rows after", record["rows_after"])
            summary[2].metric("Columns after", record["columns_after"])
            if record["before_after"]:
                render_dataframe(
                    pd.DataFrame(record["before_after"]).rename(
                        columns={"before": "Before", "after": "After"}
                    ),
                    width="stretch",
                    hide_index=True,
                )

    st.button(
        "Apply selected repairs",
        key="talos-apply-selected-repairs",
        type="primary",
        on_click=queue_selected_repairs,
        args=(tuple(selected_actions),),
        help="Only the repairs shown above will be applied to the working copy.",
    )


def render_transformation_ledger(
    ledger: list[dict[str, object]], source_filename: str = "dataset.csv"
) -> None:
    """Show the session-only record of approved working-copy changes."""
    st.subheader(f"📜 Transformation Ledger · {len(ledger)} approved")
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
    render_dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    for index, item in enumerate(ledger, start=1):
        label = f"Entry {index} · {item['transformation_type']}"
        with st.expander(label):
            st.write(item["description"])
            st.write(f"Column: {item['column'] or 'Entire dataset'}")
            st.write(f"Chosen action: {item['action']}")
            st.write(f"Parameters: {item['parameters']}")
            if item["before_after"]:
                render_dataframe(
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
        "category_variant_groups": findings["categories"]["inconsistent_group_count"],
        "outlier_values": findings["outliers"]["total_outlier_values"],
        "empty_columns": len(findings["structure"]["empty_columns"]),
        "score": findings["score"]["score"],
    }


def render_dataset_comparison(
    original_df: pd.DataFrame,
    working_df: pd.DataFrame,
    original_summary: dict[str, object],
    working_summary: dict[str, object],
    ledger: list[dict[str, object]],
    original_findings: dict[str, dict[str, object]],
    working_findings: dict[str, dict[str, object]],
    source_filename: str,
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

    original_score = original_summary["score"]
    working_score = working_summary["score"]
    score_delta = (
        working_score - original_score
        if original_score is not None and working_score is not None
        else None
    )
    st.metric(
        "Dataset Integrity",
        "Not assessable" if working_score is None else f"{working_score} / 100",
        delta=None if score_delta is None else f"{score_delta:+d}",
        delta_color="off",
        help="A higher score means fewer signals under TALOS's current rules; it does not prove the data is correct.",
    )
    st.caption(
        "A higher TALOS score means fewer detected signals under the current rules. "
        "It does not prove the working copy is suitable for its intended use."
    )

    comparison = build_comparison_table(
        original_df, working_df, original_findings, working_findings
    )
    score_comparison = build_score_comparison_table(
        original_findings["score"], working_findings["score"]
    )
    with st.expander("Detailed original / working copy comparison", expanded=False):
        render_dataframe(comparison, width="stretch", hide_index=True)
        if not score_comparison.empty:
            render_dataframe(score_comparison, width="stretch", hide_index=True)

    unresolved = {
        "Missing values": working_findings["missing"]["total_missing_cells"] > 0,
        "Exact duplicates": working_findings["duplicates"]["exact_duplicate_row_count"] > 0,
        "Category variants": working_findings["categories"]["inconsistent_group_count"] > 0,
        "IQR outliers": working_findings["outliers"]["total_outlier_values"] > 0,
        "Structural signals": bool(
            working_findings["structure"]["empty_columns"]
            or working_findings["structure"]["constant_columns"]
            or working_findings["structure"]["high_cardinality_columns"]
            or working_findings["structure"]["identifier_columns"]
            or working_findings["structure"]["numeric_patterns"]
        ),
    }
    remaining_groups = sum(unresolved.values())
    if remaining_groups:
        st.warning(f"{remaining_groups} finding group(s) remain visible in the working copy.")
        remaining_details = []
        missing = working_findings["missing"]
        if missing["total_missing_cells"]:
            affected = [item for item in missing["columns"] if item["missing_count"]]
            remaining_details.append(
                {
                    "Finding group": "Missing values",
                    "Remaining signals": f"{missing['total_missing_cells']} cells across {len(affected)} columns",
                    "Fields": ", ".join(
                        f"{item['column']} ({item['missing_count']})" for item in affected[:6]
                    ),
                }
            )
        duplicates = working_findings["duplicates"]["exact_duplicate_row_count"]
        if duplicates:
            remaining_details.append(
                {
                    "Finding group": "Exact duplicates",
                    "Remaining signals": f"{duplicates} repeated rows after the first copy",
                    "Fields": "Review the duplicate-row evidence before removal.",
                }
            )
        categories = working_findings["categories"]["variant_groups"]
        if categories:
            remaining_details.append(
                {
                    "Finding group": "Category variants",
                    "Remaining signals": f"{len(categories)} variant groups",
                    "Fields": ", ".join(dict.fromkeys(item["column"] for item in categories)),
                }
            )
        outliers = working_findings["outliers"]
        if outliers["total_outlier_values"]:
            affected = [item for item in outliers["columns"] if item["outlier_count"]]
            remaining_details.append(
                {
                    "Finding group": "IQR outliers",
                    "Remaining signals": f"{outliers['total_outlier_values']} flagged values",
                    "Fields": ", ".join(item["column"] for item in affected),
                }
            )
        structure = working_findings["structure"]
        structural_findings = build_structural_findings_table(structure)
        if not structural_findings.empty:
            remaining_details.append(
                {
                    "Finding group": "Structural signals",
                    "Remaining signals": f"{len(structural_findings)} contextual observations",
                    "Fields": ", ".join(
                        dict.fromkeys(structural_findings["Column"].astype(str))
                    ),
                }
            )
        with st.expander("What remains in the working copy", expanded=False):
            render_dataframe(pd.DataFrame(remaining_details), width="stretch", hide_index=True)
            st.caption(
                "These are the results of reinspection. Some signals are contextual and may be intentionally left unchanged."
            )
    else:
        st.success("Nothing obvious escaped reinspection.")

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
            confirm.button(
                "Confirm reset",
                key="confirm-reset",
                on_click=reset_working_copy_callback,
            )
            if cancel.button("Keep current working copy", key="cancel-reset"):
                st.session_state["talos_reset_confirmation"] = False
                st.rerun()


def render_forge(
    original_df: pd.DataFrame,
    working_df: pd.DataFrame,
    original_findings: dict[str, dict[str, object]],
    working_findings: dict[str, dict[str, object]],
    source_filename: str,
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

    suggested_actions = build_suggested_transformations(working_df, working_findings)
    missing_columns = sum(int(working_df[column].isna().any()) for column in working_df.columns)
    proposal_count = len(suggested_actions) + missing_columns
    if proposal_count:
        st.markdown(f"**TALOS has prepared {proposal_count} proposed repairs for review.**")
    else:
        st.markdown("**No repairs are proposed for the current working copy.**")
    with st.expander(
        f"Repair Control Center · {proposal_count} proposed repairs",
        expanded=False,
    ):
        st.caption(
            "Choose by category, column, or category group. TALOS applies nothing until "
            "you approve a complete Repair Plan."
        )
        render_repair_control_center(working_df, working_findings)

    ledger = st.session_state["talos_transformation_ledger"]
    render_transformation_ledger(ledger, source_filename)
    original_summary = summarize_dataset(original_df, original_findings)
    working_summary = summarize_dataset(working_df, working_findings)
    render_dataset_comparison(
        original_df,
        working_df,
        original_summary,
        working_summary,
        ledger,
        original_findings,
        working_findings,
        source_filename,
    )
    render_reset_control(original_df)


def load_emblem_svg() -> str:
    """Read the local emblem for a self-contained report, if available."""
    emblem_path = Path(__file__).parent / "assets" / "talos-emblem.svg"
    try:
        return emblem_path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("TALOS emblem was not available for the report at %s", emblem_path)
        return ""


def render_detailed_evidence_exports(
    source_filename: str,
    original_tables: dict[str, pd.DataFrame],
    working_tables: dict[str, pd.DataFrame],
    original_findings: dict[str, dict[str, object]],
    working_findings: dict[str, dict[str, object]],
    ledger: list[dict[str, object]],
) -> None:
    """Collect optional individual evidence CSVs in one predictable place."""
    working_count = len(working_tables) if ledger else 0
    with st.expander(
        f"Detailed evidence exports · {len(original_tables)} original tables · {working_count} working-copy tables",
        expanded=False,
    ):
        st.caption(
            "Individual CSVs for the findings above. These files document signals; they do not change either dataset."
        )
        export_types = {
            "structure": "structure",
            "missing_values": "missing",
            "duplicate_rows": "duplicates",
            "identifier_findings": "identifiers",
            "category_variants": "categories",
            "outliers": "outliers",
            "structural_findings": "structural",
            "integrity_score": "score",
        }

        def render_group(
            tables: dict[str, pd.DataFrame],
            label: str,
            export_prefix: str,
            widget_prefix: str,
        ) -> None:
            if not tables:
                return
            st.markdown(f"**{label}**")
            columns = st.columns(2)
            for index, (filename, table) in enumerate(tables.items()):
                stem = Path(filename).stem
                export_type = export_types.get(stem, stem)
                if export_prefix:
                    export_type = f"{export_prefix}-{export_type}"
                with columns[index % len(columns)]:
                    render_csv_download(
                        table,
                        source_filename,
                        export_type,
                        f"{widget_prefix}-{stem}",
                        button_label=f"{filename}",
                    )

        render_group(original_tables, "Original inspection evidence", "", "original")
        if ledger:
            render_group(
                working_tables,
                "Current working-copy evidence",
                "working",
                "working",
            )

        comparison = build_comparison_table(
            st.session_state["talos_original_df"],
            st.session_state["talos_working_df"],
            original_findings,
            working_findings,
        )
        score_comparison = build_score_comparison_table(
            original_findings["score"], working_findings["score"]
        )
        st.markdown("**Comparison and ledger evidence**")
        columns = st.columns(2)
        with columns[0]:
            render_csv_download(
                comparison,
                source_filename,
                "comparison",
                "comparison",
                button_label="before_after_comparison.csv",
            )
        with columns[1]:
            if not score_comparison.empty:
                render_csv_download(
                    score_comparison,
                    source_filename,
                    "score_comparison",
                    "score-comparison",
                    button_label="score_comparison.csv",
                )
        if ledger:
            render_csv_download(
                build_transformation_log(ledger),
                source_filename,
                "transformations",
                "transformation-ledger",
                button_label="transformation_ledger.csv",
            )


def render_exports_and_report(
    original_profile: dict[str, object],
    original_findings: dict[str, dict[str, object]],
    working_findings: dict[str, dict[str, object]],
) -> None:
    """Offer the Evidence Vault's portable tables, report, data, and ZIP pack."""
    original_df = st.session_state["talos_original_df"]
    working_df = st.session_state["talos_working_df"]
    ledger = st.session_state["talos_transformation_ledger"]
    prepare_evidence_tables(original_profile)
    original_summary = st.session_state["talos_original_summary"]
    working_summary = st.session_state["talos_working_summary"]
    original_tables = st.session_state["talos_original_result_tables"]
    working_tables = st.session_state["talos_working_result_tables"]
    revision = int(st.session_state.get("talos_data_revision", 0))

    st.markdown('<p class="talos-section-kicker">Release</p>', unsafe_allow_html=True)
    st.header("📜 Evidence Vault")
    st.markdown("The inspection is complete. Findings, repairs and working data — packaged for release.")
    st.caption("Export tables, the approved working copy, a printable inspection dossier, or a complete ZIP pack.")
    st.info(
        "TALOS creates a new transformed copy. "
        "Your original uploaded dataset remains unchanged."
    )

    if st.session_state.get("talos_cached_report_revision") != revision:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        report_html = build_inspection_report_html(
            original_profile,
            original_findings,
            working_findings,
            original_summary,
            working_summary,
            ledger,
            emblem_svg=load_emblem_svg(),
            original_evidence_tables=original_tables,
            working_evidence_tables=working_tables,
            created_at=created_at,
        )
        st.session_state["talos_cached_report_html"] = report_html
        st.session_state["talos_cached_report_created_at"] = created_at
        st.session_state["talos_cached_report_revision"] = revision
    report_html = st.session_state["talos_cached_report_html"]

    downloads = st.columns(3)
    with downloads[0]:
        st.download_button(
            "Download cleaned CSV",
            data=build_cleaned_csv(working_df),
            file_name=build_export_filename(str(original_profile["file_name"]), "cleaned"),
            mime="text/csv",
            key="download-working-copy",
        )
    with downloads[1]:
        log_bytes = build_transformation_log(ledger).to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download transformation log",
            data=log_bytes,
            file_name=build_export_filename(str(original_profile["file_name"]), "transformations"),
            mime="text/csv",
            key="download-transformation-log",
        )
    with downloads[2]:
        st.download_button(
            "Download HTML report",
            data=report_html.encode("utf-8"),
            file_name=build_export_filename(str(original_profile["file_name"]), "report"),
            mime="text/html",
            key="download-inspection-report",
        )

    table_descriptions = {
        "structure.csv": "Column names, pandas dtypes, and TALOS types.",
        "missing_values.csv": "Per-column missing counts, percentages, severity, and explanation.",
        "duplicate_rows.csv": "All source rows involved in exact duplicate groups.",
        "identifier_findings.csv": "Name-based identifier candidates, repeats, uniqueness, and examples.",
        "category_variants.csv": "Observed variants, counts, normalized forms, and proposed canonical values.",
        "outliers.csv": "Every flagged numeric value with row position and IQR bounds.",
        "structural_findings.csv": "Empty, constant, high-cardinality, identifier, and numeric review signals.",
        "integrity_score.csv": "Original integrity-score components, weights, and weighted points.",
    }
    st.subheader("Evidence pack")
    st.caption("The archive includes applicable result tables only; absent findings do not become empty placeholder files.")
    if st.button("Prepare evidence pack", type="primary", key="prepare-evidence-pack"):
        with st.spinner("Sealing inspection evidence."):
            pack_files: dict[str, bytes] = {
                "inspection_report.html": report_html.encode("utf-8"),
                "cleaned_dataset.csv": build_cleaned_csv(working_df),
            }
            descriptions = {
                "inspection_report.html": "Complete, self-contained TALOS inspection dossier.",
                "cleaned_dataset.csv": "The user-approved working copy, exported without a DataFrame index.",
            }
            for filename, table in original_tables.items():
                pack_files[filename] = table.to_csv(index=False).encode("utf-8")
                descriptions[filename] = table_descriptions.get(filename, "Original inspection evidence table.")
            if ledger:
                log_filename = "transformation_ledger.csv"
                pack_files[log_filename] = build_transformation_log(ledger).to_csv(index=False).encode("utf-8")
                descriptions[log_filename] = "The ordered record of approved transformations and examples."
                for filename, table in working_tables.items():
                    working_filename = f"working_{filename}"
                    pack_files[working_filename] = table.to_csv(index=False).encode("utf-8")
                    descriptions[working_filename] = f"Current working-copy {table_descriptions.get(filename, 'inspection evidence table').lower()}"
            comparison = build_comparison_table(
                original_df, working_df, original_findings, working_findings
            )
            pack_files["before_after_comparison.csv"] = comparison.to_csv(index=False).encode("utf-8")
            descriptions["before_after_comparison.csv"] = "Original and current working-copy metrics."
            score_comparison = build_score_comparison_table(
                original_findings["score"], working_findings["score"]
            )
            if not score_comparison.empty:
                pack_files["score_comparison.csv"] = score_comparison.to_csv(index=False).encode("utf-8")
                descriptions["score_comparison.csv"] = "Original and current working-copy score components and changes."
            created_at = str(st.session_state.get("talos_cached_report_created_at", ""))
            pack_files["README.txt"] = build_evidence_readme(
                str(original_profile["file_name"]), created_at, descriptions
            )
            st.session_state["talos_cached_evidence_pack"] = build_evidence_pack(pack_files)
            st.session_state["talos_cached_evidence_revision"] = revision

    evidence_pack = st.session_state.get("talos_cached_evidence_pack")
    if (
        evidence_pack is not None
        and st.session_state.get("talos_cached_evidence_revision") == revision
    ):
        st.download_button(
            "Download evidence pack ZIP",
            data=evidence_pack,
            file_name=build_export_filename(str(original_profile["file_name"]), "evidence_pack"),
            mime="application/zip",
            key="download-evidence-pack",
        )

    render_detailed_evidence_exports(
        str(original_profile["file_name"]),
        original_tables,
        working_tables,
        original_findings,
        working_findings,
        ledger,
    )


def render_first_time_experience() -> None:
    """Explain the normal TALOS workflow before a source file is provided."""
    st.subheader("The gate is open.")
    st.markdown(
        "TALOS inspects a CSV, explains what it finds, and lets you choose whether to repair the working copy."
    )
    st.markdown(
        """
        <div class="talos-workflow-cards">
          <div class="talos-workflow-card"><strong>1 · Upload</strong><span>Give TALOS a CSV. The original stays in this session.</span></div>
          <div class="talos-workflow-card"><strong>2 · Inspect</strong><span>Review structure, missingness, duplicates, categories, and numeric signals.</span></div>
          <div class="talos-workflow-card"><strong>3 · Forge</strong><span>Select repairs, inspect the plan, then approve only what you choose.</span></div>
          <div class="talos-workflow-card"><strong>4 · Export</strong><span>Take the working copy, evidence tables, ZIP pack, and inspection dossier.</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def clear_demo_dataset_callback() -> None:
    """Leave showcase mode and discard its in-session dataset state."""
    st.session_state["talos_demo_loaded"] = False
    clear_dataset_state()


def main() -> None:
    """Render the session-aware TALOS inspection and evidence workflow."""
    st.set_page_config(page_title="TALOS", page_icon="⚙️", layout="wide")
    if "talos_theme_preference" not in st.session_state:
        st.session_state["talos_theme_preference"] = DEFAULT_THEME
    theme = st.session_state["talos_theme_preference"]
    if theme not in {"Dark", "Light"}:
        theme = DEFAULT_THEME
        st.session_state["talos_theme_preference"] = theme
    load_stylesheet(theme)
    render_header()
    st.markdown('<p class="talos-section-kicker">Source file</p>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Upload a CSV file for inspection",
        type=["csv"],
        help="TALOS reads the file in memory for this session; it is not saved by the app.",
    )
    st.caption("Please do not upload confidential, sensitive, or personally identifiable information. Files are processed for this session and are not intentionally stored.")

    demo_loaded = bool(st.session_state.get("talos_demo_loaded", False))
    if uploaded_file is None and not demo_loaded:
        clear_dataset_state()
        if st.button("Load TALOS demo dataset", key="talos-load-demo", type="primary"):
            st.session_state["talos_demo_loaded"] = True
            st.rerun()
        st.caption("No dataset? Release something questionable.")
        render_first_time_experience()
        return

    if uploaded_file is None and demo_loaded:
        if st.button("Clear demo dataset", key="talos-clear-demo", on_click=clear_demo_dataset_callback):
            return
        demo_path = Path(__file__).parent / "data" / "sample" / "talos_demo.csv"
        try:
            file_contents = demo_path.read_bytes()
        except OSError:
            logger.exception("The TALOS demo dataset was not available at %s", demo_path)
            st.error("The built-in TALOS demo dataset could not be loaded.")
            return
        source_filename = "talos_demo.csv"
    elif uploaded_file is not None:
        st.session_state["talos_demo_loaded"] = False
        file_contents = uploaded_file.getvalue()
        source_filename = uploaded_file.name
    else:
        clear_dataset_state()
        render_first_time_experience()
        return

    if not file_contents:
        clear_dataset_state()
        st.warning("This file appears to contain no content. Choose a CSV with a header and data.")
        return

    fingerprint_input = source_filename.encode("utf-8") + b"\0" + file_contents
    file_fingerprint = hashlib.sha256(fingerprint_input).hexdigest()
    if st.session_state.get("talos_file_fingerprint") != file_fingerprint:
        clear_dataset_state()
        try:
            with st.spinner("Source received. Checking the CSV structure."):
                df = load_csv(file_contents)
        except pd.errors.EmptyDataError:
            st.warning("This CSV contains no readable header or data.")
            return
        except pd.errors.ParserError:
            st.error("TALOS could not read this file as a consistent CSV. Check its rows and separators.")
            return
        except UnicodeDecodeError:
            st.error("TALOS could not read the file's text encoding. Save it as UTF-8 CSV and try again.")
            return
        except Exception:
            logger.exception("Unexpected error while reading a source CSV.")
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
            with st.spinner(f"Guardian inspection in progress. Reviewing {len(df):,} records."):
                initialize_dataset_state(file_fingerprint, df)
                profile = profile_dataset(
                    st.session_state["talos_original_df"],
                    file_name=source_filename,
                    file_size_bytes=len(file_contents),
                )
                st.session_state["talos_original_profile"] = profile
        except Exception:
            logger.exception("Unexpected error while profiling a source CSV.")
            st.error("TALOS received the file but could not complete its profile. Try another CSV.")
            return
    else:
        profile = st.session_state["talos_original_profile"]

    pending_actions = st.session_state.pop("talos_pending_repair_actions", None)
    if pending_actions:
        with st.spinner("Reinspection underway. Reviewing the approved working copy."):
            apply_selected_repairs(tuple(pending_actions))

    original_df = st.session_state["talos_original_df"]
    working_df = st.session_state["talos_working_df"]
    original_findings = st.session_state["talos_original_findings"]
    working_findings = st.session_state["talos_working_findings"]
    if st.session_state.get("talos_evidence_revision") != st.session_state.get("talos_data_revision"):
        with st.spinner(f"Preparing portable evidence for {len(working_df):,} working-copy records."):
            prepare_evidence_tables(profile)

    notice = st.session_state.get("talos_notice", "")
    if notice:
        st.success(notice)
        st.session_state["talos_notice"] = ""
    else:
        st.success("Inspection complete. The guardian has recorded the findings.")

    render_source_status(profile, original_df, demo_loaded)
    render_integrity_score(original_findings["score"], source_filename)
    render_guardian_summary(original_findings)
    render_dataset_profile(profile, original_df)
    st.markdown('<p class="talos-section-kicker">Original dataset inspection</p>', unsafe_allow_html=True)
    render_missing_data(original_findings["missing"], source_filename)
    render_duplicate_checks(original_findings["duplicates"], original_df, source_filename)
    render_category_consistency(original_findings["categories"], source_filename)
    render_numeric_outliers(original_findings["outliers"], original_df, source_filename)
    render_structural_signals(original_findings["structure"], source_filename)
    render_forge(original_df, working_df, original_findings, working_findings, source_filename)
    render_exports_and_report(profile, original_findings, working_findings)
    st.markdown(
        '<p class="talos-footer">Original data preserved · Approved transformations remain in this session.</p>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
