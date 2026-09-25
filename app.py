"""Streamlit interface for TALOS dataset intake and inspection."""

import logging
from pathlib import Path

import pandas as pd
import streamlit as st

from src.profiler import load_csv, profile_dataset
from src.quality_checks import (
    inspect_category_consistency,
    inspect_duplicates,
    inspect_missing_values,
    inspect_numeric_outliers,
    inspect_structure,
)
from src.scoring import calculate_integrity_score


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
    st.markdown(
        """
        <header class="talos-hero">
            <p class="talos-eyebrow">Data integrity observation system</p>
            <h1 class="talos-title"><span class="talos-title-mark">⚙</span> TALOS</h1>
            <p class="talos-subtitle">
                A watchful guardian between source data and trusted analysis.
            </p>
            <div class="talos-system-status">
                <span class="talos-status-dot"></span>
                Inspection system online
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
            "Many distinct text values can indicate an identifier, free text, or a granular category; "
            "it is not automatically a problem."
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
            "Identifier candidates are inferred from column names only. Uniqueness is shown for review, "
            "not treated as a requirement."
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
            "Negative values and zero-heavy fields may be valid. TALOS cannot infer the expected range from the data alone."
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


def main() -> None:
    """Render CSV upload, structural profile, quality checks, and score."""
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
        profile = profile_dataset(
            df,
            file_name=uploaded_file.name,
            file_size_bytes=len(file_contents),
        )
        findings = inspect_dataset(df)
    except Exception:
        logger.exception("Unexpected error while profiling an uploaded CSV.")
        st.error("TALOS received the file but could not complete its profile. Try another CSV.")
        return

    st.success("Dataset received. Beginning inspection.")
    render_dataset_profile(profile, df)
    render_missing_data(findings["missing"])
    render_duplicate_checks(findings["duplicates"])
    render_category_consistency(findings["categories"])
    render_numeric_outliers(findings["outliers"])
    render_structural_signals(findings["structure"])
    render_integrity_score(findings["score"])
    st.markdown(
        '<p class="talos-footer">Inspection complete · Uploaded data remains unchanged.</p>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
