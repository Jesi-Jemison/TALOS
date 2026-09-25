"""Streamlit interface for TALOS dataset intake and profiling."""

import logging

import pandas as pd
import streamlit as st

from src.profiler import load_csv, profile_dataset


logger = logging.getLogger(__name__)


def main() -> None:
    """Render the CSV upload flow and the resulting dataset profile."""
    st.set_page_config(
        page_title="TALOS",
        page_icon="⚙️",
        layout="wide",
    )

    st.title("⚙️ TALOS")
    st.write("A guardian at the gate between messy data and trustworthy analysis.")
    st.caption("Dataset intake and profiling · Stage 2")
    st.divider()

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
        st.error("TALOS could not read this file as a consistent CSV. Check its rows and separators.")
        return
    except UnicodeDecodeError:
        st.error("TALOS could not read the file's text encoding. Save it as UTF-8 CSV and try again.")
        return
    except Exception:
        logger.exception("Unexpected error while reading an uploaded CSV.")
        st.error("TALOS could not read this file. Check that it is a valid CSV and try again.")
        return

    if len(df.columns) == 0:
        st.warning("TALOS could not identify any usable columns in this CSV.")
        return

    has_named_column = any(
        str(column).strip() and not str(column).startswith("Unnamed:")
        for column in df.columns
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
    except Exception:
        logger.exception("Unexpected error while profiling an uploaded CSV.")
        st.error("TALOS received the file but could not complete its profile. Try another CSV.")
        return

    st.success("Inspection complete. TALOS has identified the structure of this dataset.")

    st.subheader("👁️ Dataset Overview")
    type_counts = profile["type_counts"]
    metrics = st.columns(6)
    metrics[0].metric("Rows", profile["row_count"])
    metrics[1].metric("Columns", profile["column_count"])
    metrics[2].metric("Numeric", type_counts["Numeric"])
    metrics[3].metric("Text", type_counts["Text"])
    metrics[4].metric("Boolean", type_counts["Boolean"])
    metrics[5].metric("Datetime", type_counts["Datetime"])

    st.subheader("📄 File Details")
    details = st.columns(2)
    details[0].metric("Filename", profile["file_name"])
    details[1].metric("File size", profile["file_size"])

    st.subheader("🧬 Dataset Structure")
    structure = pd.DataFrame(profile["columns"]).rename(
        columns={
            "column": "Column",
            "pandas_dtype": "Pandas dtype",
            "talos_type": "TALOS type",
        }
    )
    st.dataframe(structure, width="stretch", hide_index=True)

    st.subheader("🔎 Data Preview")
    st.caption("First 10 rows. TALOS is profiling structure only at this stage.")
    st.dataframe(df.head(10), width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
