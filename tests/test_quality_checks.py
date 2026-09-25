"""Tests for TALOS read-only dataset quality inspections."""

import pandas as pd
import pytest

from src.quality_checks import (
    classify_missing_severity,
    inspect_category_consistency,
    inspect_duplicates,
    inspect_missing_values,
    inspect_numeric_outliers,
    inspect_structure,
    is_likely_identifier,
)


def test_missing_values_reports_counts_percentages_and_context():
    df = pd.DataFrame(
        {
            "record_id": [1, 2, None, 4],
            "event_date": ["2025-01-01", None, "2025-01-03", "2025-01-04"],
            "revenue": [10.0, 20.0, 30.0, None],
            "region": ["Sydney", "Sydney", "Melbourne", "Perth"],
        }
    )
    original = df.copy(deep=True)

    result = inspect_missing_values(df)
    by_name = {item["column"]: item for item in result["columns"]}

    assert result["total_missing_cells"] == 3
    assert result["total_cells"] == 16
    assert result["affected_column_count"] == 3
    assert result["clear_column_count"] == 1
    assert by_name["record_id"]["missing_percentage"] == 25.0
    assert by_name["record_id"]["severity"] == "Significant"
    assert "joins" in by_name["record_id"]["explanation"]
    assert "time-based" in by_name["event_date"]["explanation"]
    assert "aggregates" in by_name["revenue"]["explanation"]
    pd.testing.assert_frame_equal(df, original)


def test_missing_values_zero_missing_case_and_empty_dataframe():
    clean_result = inspect_missing_values(pd.DataFrame({"name": ["A", "B"]}))
    empty_result = inspect_missing_values(pd.DataFrame())

    assert clean_result["total_missing_cells"] == 0
    assert clean_result["missing_percentage"] == 0.0
    assert clean_result["clear_column_count"] == 1
    assert empty_result["columns"] == []
    assert empty_result["missing_percentage"] == 0.0


@pytest.mark.parametrize(
    ("percentage", "expected"),
    [
        (0, "Clear"),
        (0.1, "Minor"),
        (5, "Minor"),
        (5.01, "Review"),
        (20, "Review"),
        (20.01, "Significant"),
        (40, "Significant"),
        (40.01, "Critical"),
    ],
)
def test_missing_severity_thresholds(percentage, expected):
    assert classify_missing_severity(percentage) == expected


def test_duplicate_inspection_separates_repeated_rows_from_identifier_values():
    df = pd.DataFrame(
        {
            "customer_id": [101, 101, 102, None],
            "customer_name": ["Ada", "Ada", "Bo", "Cy"],
            "paid": [True, True, False, False],
            "region": ["East", "East", "West", "North"],
        }
    )
    original = df.copy(deep=True)

    result = inspect_duplicates(df)
    identifier = result["identifier_candidates"][0]

    assert result["exact_duplicate_row_count"] == 1
    assert result["exact_duplicate_percentage"] == 25.0
    assert len(result["exact_duplicate_sample"]) == 2
    assert identifier["column"] == "customer_id"
    assert identifier["duplicate_value_count"] == 1
    assert identifier["missing_count"] == 1
    assert identifier["uniqueness_percentage"] == pytest.approx(200 / 3)
    assert identifier["duplicate_values"] == [{"value": "101.0", "row_count": 2}]
    pd.testing.assert_frame_equal(df, original)


def test_duplicate_inspection_no_duplicates_and_empty_dataframe():
    clean = inspect_duplicates(pd.DataFrame({"record_id": [1, 2, 3], "value": ["a", "b", "c"]}))
    empty = inspect_duplicates(pd.DataFrame())

    assert clean["exact_duplicate_row_count"] == 0
    assert clean["exact_duplicate_percentage"] == 0.0
    assert clean["identifier_candidates"][0]["uniqueness_percentage"] == 100.0
    assert empty["exact_duplicate_row_count"] == 0
    assert empty["identifier_candidates"] == []


@pytest.mark.parametrize(
    ("column_name", "expected"),
    [
        ("customer_id", True),
        ("customerID", True),
        ("order_number", True),
        ("paid", False),
        ("customer_name", False),
    ],
)
def test_identifier_name_heuristic_is_deliberate(column_name, expected):
    assert is_likely_identifier(column_name) is expected


def test_category_consistency_finds_case_and_whitespace_variants():
    df = pd.DataFrame(
        {
            "region": [
                "Sydney",
                "SYDNEY",
                "sydney ",
                "Sydney",
                "Melbourne",
                "Melbourne",
            ],
            "notes": ["Call tomorrow", "call tomorrow", "other", "other", "free text", "free text"],
            "customer_name": ["A", "a", "B", "b", "C", "c"],
        }
    )
    original = df.copy(deep=True)

    result = inspect_category_consistency(df)

    assert result["checked_columns"] == ["region"]
    assert result["inconsistent_group_count"] == 1
    assert result["column_count_with_variants"] == 1
    group = result["variant_groups"][0]
    assert group["normalized_value"] == "sydney"
    assert {item["value"]: item["count"] for item in group["variants"]} == {
        "SYDNEY": 1,
        "Sydney": 2,
        "sydney ": 1,
    }
    assert {item["column"] for item in result["skipped_columns"]} == {
        "notes",
        "customer_name",
    }
    pd.testing.assert_frame_equal(df, original)


def test_category_consistency_skips_high_cardinality_and_clean_categories():
    df = pd.DataFrame(
        {
            "region": ["north", "south"] * 10,
            "reference": [f"ref-{number}" for number in range(20)],
        }
    )

    result = inspect_category_consistency(df)

    assert result["checked_columns"] == ["region"]
    assert result["variant_groups"] == []
    assert {item["column"] for item in result["skipped_columns"]} == {"reference"}
    assert result["skipped_columns"][0]["reason"] == "High cardinality or mostly unique values"


def test_category_consistency_handles_no_text_columns():
    result = inspect_category_consistency(pd.DataFrame({"amount": [1, 2, 3]}))

    assert result["checked_columns"] == []
    assert result["variant_groups"] == []


def test_iqr_outliers_detect_obvious_value_and_explain_bounds():
    df = pd.DataFrame(
        {
            "daily_sales": [10, 11, 12, 13, 14, 15, 16, 17, 18, 1000],
            "customer_id": list(range(10)),
        }
    )
    original = df.copy(deep=True)

    result = inspect_numeric_outliers(df)
    sales = result["columns"][0]

    assert sales["column"] == "daily_sales"
    assert sales["q1"] == pytest.approx(12.25)
    assert sales["median"] == pytest.approx(14.5)
    assert sales["q3"] == pytest.approx(16.75)
    assert sales["upper_bound"] == pytest.approx(23.5)
    assert sales["outlier_count"] == 1
    assert sales["sample_values"] == [1000]
    assert result["total_outlier_values"] == 1
    assert {item["column"] for item in result["skipped_columns"]} == {"customer_id"}
    pd.testing.assert_frame_equal(df, original)


def test_iqr_outlier_check_no_outlier_and_small_dataset_exclusions():
    df = pd.DataFrame(
        {
            "steady_measure": list(range(1, 11)),
            "small_sample": [1, 2, 3, 4, 5, 6, 7, None, None, None],
            "low_variation": [0, 0, 0, 0, 0, 0, 1, 1, 1, 1],
            "active": [True, False] * 5,
        }
    )

    result = inspect_numeric_outliers(df)

    assert len(result["columns"]) == 1
    assert result["columns"][0]["column"] == "steady_measure"
    assert result["total_outlier_values"] == 0
    assert {item["column"] for item in result["skipped_columns"]} == {
        "small_sample",
        "low_variation",
        "active",
    }


def test_structural_and_identifier_checks_surface_neutral_signals():
    df = pd.DataFrame(
        {
            "empty_field": [None] * 26,
            "constant_status": ["ready"] * 26,
            "reference": [f"ref-{number}" for number in range(26)],
            "record_id": list(range(1, 25)) + [24, None],
            "balance": [-1] + [0] * 25,
        }
    )
    original = df.copy(deep=True)

    result = inspect_structure(df)
    identifier = result["identifier_columns"][0]
    numeric_pattern = result["numeric_patterns"][0]

    assert result["empty_columns"] == ["empty_field"]
    assert result["constant_columns"][0]["column"] == "constant_status"
    assert result["high_cardinality_columns"][0]["column"] == "reference"
    assert identifier["column"] == "record_id"
    assert identifier["missing_count"] == 1
    assert identifier["duplicate_value_count"] == 1
    assert identifier["uniqueness_percentage"] == pytest.approx(96.0)
    assert numeric_pattern["column"] == "balance"
    assert numeric_pattern["negative_count"] == 1
    assert numeric_pattern["zero_percentage"] == pytest.approx(25 / 26 * 100)
    pd.testing.assert_frame_equal(df, original)


def test_structural_checks_handle_empty_dataframe():
    result = inspect_structure(pd.DataFrame())

    assert result == {
        "empty_columns": [],
        "constant_columns": [],
        "high_cardinality_columns": [],
        "identifier_columns": [],
        "numeric_patterns": [],
    }
