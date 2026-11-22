"""Tests for TALOS CSV and Excel intake and dataset profiling."""
# TALOS FILE VERSION: v1.2.0

from io import BytesIO
import pandas as pd
import pytest

from src.profiler import (
    format_file_size,
    identify_column_types,
    list_excel_sheets,
    load_excel,
    load_csv,
    profile_dataset,
)


def test_load_csv_and_profile_normal_dataset():
    """A normal CSV is loaded and its basic structure is profiled."""
    file_contents = (
        b"customer_id,name,suburb,revenue\n"
        b"1,Alice,Sydney,120\n"
        b"2,Bob,Parramatta,250\n"
        b"3,Charlie,Newtown,180\n"
    )

    df = load_csv(file_contents)
    profile = profile_dataset(df, "customers.csv", len(file_contents))

    assert df.shape == (3, 4)
    assert profile["file_name"] == "customers.csv"
    assert profile["row_count"] == 3
    assert profile["column_count"] == 4
    assert profile["type_counts"]["Numeric"] == 2
    assert profile["type_counts"]["Text"] == 2


def test_empty_dataframe_has_an_empty_profile():
    """An empty DataFrame can be profiled without special-case failures."""
    profile = profile_dataset(pd.DataFrame(), "empty.csv", 0)

    assert profile["row_count"] == 0
    assert profile["column_count"] == 0
    assert profile["columns"] == []
    assert profile["type_counts"] == {
        "Numeric": 0,
        "Text": 0,
        "Boolean": 0,
        "Datetime": 0,
    }


def test_column_classification_covers_mixed_types():
    """Booleans and true datetime dtypes are distinct from numeric and text."""
    df = pd.DataFrame(
        {
            "amount": [10.5, 22.0],
            "name": ["Alice", "Bob"],
            "active": [True, False],
            "created_at": pd.to_datetime(["2025-01-01", "2025-01-02"]),
            "date_as_text": ["2025-01-01", "not a date"],
        }
    )

    columns = identify_column_types(df)
    labels = {column["column"]: column["talos_type"] for column in columns}

    assert labels == {
        "amount": "Numeric",
        "name": "Text",
        "active": "Boolean",
        "created_at": "Datetime",
        "date_as_text": "Text",
    }


def test_profile_counts_mixed_columns_and_keeps_file_metadata():
    """The profile reports all type counts without analyzing cell values."""
    df = pd.DataFrame(
        {
            "quantity": [1, None],
            "label": ["present", None],
            "enabled": [True, False],
        }
    )
    profile = profile_dataset(df, "mixed.csv", 2048)

    assert profile["file_size"] == "2.0 KB"
    assert profile["type_counts"] == {
        "Numeric": 1,
        "Text": 1,
        "Boolean": 1,
        "Datetime": 0,
    }


@pytest.mark.parametrize(
    ("size_bytes", "expected"),
    [(0, "0 B"), (512, "512 B"), (1024, "1.0 KB"), (1048576, "1.0 MB")],
)
def test_format_file_size(size_bytes, expected):
    """File sizes use readable units."""
    assert format_file_size(size_bytes) == expected


def test_format_file_size_rejects_negative_values():
    with pytest.raises(ValueError):
        format_file_size(-1)


def test_empty_csv_raises_pandas_empty_data_error():
    with pytest.raises(pd.errors.EmptyDataError):
        load_csv(b"")


def test_malformed_csv_raises_pandas_parser_error():
    file_contents = b"name,amount\nAlice,10\nBob,20,unexpected\n"

    with pytest.raises(pd.errors.ParserError):
        load_csv(file_contents)


def test_latin_1_csv_uses_encoding_fallback():
    df = load_csv("name\nCafé\n".encode("latin-1"))

    assert df.loc[0, "name"] == "Café"


def test_excel_intake_lists_and_reads_the_selected_sheet_in_memory():
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame({"ignore": [99]}).to_excel(writer, index=False, sheet_name="Overview")
        pd.DataFrame({"city": ["Athens", "Delphi"], "count": [2, 3]}).to_excel(
            writer, index=False, sheet_name="Inspection Data"
        )
    contents = buffer.getvalue()

    assert list_excel_sheets(contents) == ["Overview", "Inspection Data"]
    selected = load_excel(contents, "Inspection Data")
    assert selected.to_dict(orient="list") == {
        "city": ["Athens", "Delphi"],
        "count": [2, 3],
    }
    assert profile_dataset(selected, "myth.xlsx", len(contents), "Inspection Data")[
        "sheet_name"
    ] == "Inspection Data"


def test_empty_malformed_and_unknown_excel_inputs_have_readable_errors():
    with pytest.raises(ValueError, match="empty"):
        list_excel_sheets(b"")
    with pytest.raises(ValueError, match="could not open"):
        list_excel_sheets(b"not an excel workbook")

    buffer = BytesIO()
    pd.DataFrame({"name": ["Zeus"]}).to_excel(buffer, index=False, sheet_name="Gods")
    with pytest.raises(ValueError, match="not in this workbook"):
        load_excel(buffer.getvalue(), "Titans")
