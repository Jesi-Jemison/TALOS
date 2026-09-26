"""TALOS FILE VERSION: v1.2.0. CSV/Excel intake and dataset profiling."""
# TALOS FILE VERSION: v1.2.0

from io import BytesIO

import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
)


def load_csv(file_contents: bytes) -> pd.DataFrame:
    """Load CSV bytes into a DataFrame without writing the file to disk.

    UTF-8 (including files with a byte-order mark) is tried first. Latin-1 is
    used as a small fallback for older CSV exports that are not valid UTF-8.
    Empty and malformed files raise pandas' standard parsing exceptions.
    """
    if not file_contents:
        raise pd.errors.EmptyDataError("The uploaded file is empty.")

    try:
        return pd.read_csv(BytesIO(file_contents), encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(BytesIO(file_contents), encoding="latin-1")


def list_excel_sheets(file_contents: bytes) -> list[str]:
    """Return worksheet names from an uploaded Excel workbook in memory."""
    if not file_contents:
        raise ValueError("The uploaded workbook is empty.")
    try:
        with pd.ExcelFile(BytesIO(file_contents)) as workbook:
            sheets = list(workbook.sheet_names)
    except Exception as error:
        raise ValueError(
            "TALOS could not open this Excel workbook. Check that it is a supported, unencrypted .xlsx, .xlsm, or .xls file."
        ) from error
    if not sheets:
        raise ValueError("This workbook does not contain any worksheets.")
    return sheets


def load_excel(file_contents: bytes, sheet_name: str) -> pd.DataFrame:
    """Load one explicitly selected workbook sheet without writing to disk."""
    if not file_contents:
        raise ValueError("The uploaded workbook is empty.")
    try:
        with pd.ExcelFile(BytesIO(file_contents)) as workbook:
            if sheet_name not in workbook.sheet_names:
                raise ValueError(f"Worksheet {sheet_name!r} is not in this workbook.")
            return pd.read_excel(workbook, sheet_name=sheet_name)
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(
            "TALOS could not read the selected worksheet. Check that the workbook is supported and not encrypted or damaged."
        ) from error


def _classify_series(series: pd.Series) -> str:
    """Return a plain-language type label for one pandas Series."""
    if is_bool_dtype(series.dtype):
        return "Boolean"
    if is_datetime64_any_dtype(series.dtype):
        return "Datetime"
    if is_numeric_dtype(series.dtype):
        return "Numeric"
    return "Text"


def identify_column_types(df: pd.DataFrame) -> list[dict[str, str]]:
    """Describe each column by its name, pandas dtype, and broad TALOS type.

    Object and string columns remain Text. TALOS does not infer dates from
    strings during intake, so a date-looking text column is not mislabeled.
    """
    column_details = []

    for column_name, series in df.items():
        column_details.append(
            {
                "column": str(column_name),
                "pandas_dtype": str(series.dtype),
                "talos_type": _classify_series(series),
            }
        )

    return column_details


def format_file_size(size_bytes: int) -> str:
    """Convert a non-negative byte count to a readable size string."""
    if size_bytes < 0:
        raise ValueError("File size cannot be negative.")

    size = float(size_bytes)
    units = ("B", "KB", "MB", "GB", "TB")

    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} TB"


def profile_dataset(
    df: pd.DataFrame,
    file_name: str,
    file_size_bytes: int,
    sheet_name: str | None = None,
) -> dict[str, object]:
    """Summarise file metadata, dataset dimensions, and broad column types.

    The result is plain data for the Streamlit layer to display. It does not
    inspect missing values, duplicates, outliers, or other quality issues.
    """
    columns = identify_column_types(df)
    type_counts = {
        "Numeric": 0,
        "Text": 0,
        "Boolean": 0,
        "Datetime": 0,
    }

    for column in columns:
        type_counts[column["talos_type"]] += 1

    return {
        "file_name": file_name,
        "sheet_name": sheet_name,
        "file_size": format_file_size(file_size_bytes),
        "row_count": len(df.index),
        "column_count": len(df.columns),
        "type_counts": type_counts,
        "columns": columns,
    }
