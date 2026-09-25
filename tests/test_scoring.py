"""Tests for the custom, transparent TALOS score."""

import pandas as pd
import pytest

from src.quality_checks import (
    inspect_category_consistency,
    inspect_duplicates,
    inspect_missing_values,
    inspect_numeric_outliers,
    inspect_structure,
)
from src.scoring import SCORE_WEIGHTS, calculate_integrity_score, score_band


def build_score(df):
    """Run the same inspections the app uses before calculating a score."""
    return calculate_integrity_score(
        df,
        inspect_missing_values(df),
        inspect_duplicates(df),
        inspect_category_consistency(df),
        inspect_numeric_outliers(df),
        inspect_structure(df),
    )


def test_clean_dataset_scores_high_and_is_deterministic():
    df = pd.DataFrame(
        {
            "region": ["north", "south", "north", "south", "east", "west", "east", "west", "north", "south"],
            "daily_sales": [12, 14, 13, 18, 17, 16, 19, 15, 20, 21],
        }
    )

    first = build_score(df)
    second = build_score(df)

    assert first["score"] == 100
    assert first["band"] == "Clear"
    assert first == second
    assert sum(SCORE_WEIGHTS.values()) == 100
    assert sum(item["weighted_points"] for item in first["components"]) == 100


def test_degraded_dataset_scores_lower_with_component_breakdown():
    df = pd.DataFrame(
        {
            "region": ["Sydney", "SYDNEY", "north", "south", "west", "east", "west", "east", "north", None, "Sydney"],
            "daily_sales": [10, 11, 12, 13, 14, 15, 16, 17, 18, 1000, 10],
            "record_id": [1, 1, 3, 4, 5, 6, 7, 8, 9, 10, 1],
            "empty_field": [None] * 11,
            "constant": ["same"] * 11,
        }
    )
    clean = pd.DataFrame(
        {
            "region": ["north", "south", "east", "west", "north", "south", "east", "west", "north", "south"],
            "daily_sales": [10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
            "record_id": list(range(1, 11)),
            "category": ["a", "b", "c", "d", "a", "b", "c", "d", "a", "b"],
        }
    )

    score = build_score(df)
    clean_score = build_score(clean)
    components = {item["component"]: item for item in score["components"]}

    assert 0 <= score["score"] <= 100
    assert score["score"] < clean_score["score"]
    assert set(components) == set(SCORE_WEIGHTS)
    assert components["Completeness"]["score"] < 100
    assert components["Exact duplicates"]["score"] < 100
    assert components["Category consistency"]["score"] < 100
    assert components["Structural health"]["score"] < 100
    assert components["Outlier signal"]["score"] < 100


def test_completeness_accounts_for_missing_cells_and_affected_columns():
    values = {}
    for column_number in range(10):
        column_values = [row_number + column_number * 100 for row_number in range(100)]
        if column_number < 5:
            start = column_number * 16
            for row_number in range(start, start + 16):
                column_values[row_number] = None
        values[f"measure_{column_number}"] = column_values
    spread_missingness = pd.DataFrame(values)

    spread_score = build_score(spread_missingness)
    completeness = next(
        item for item in spread_score["components"]
        if item["component"] == "Completeness"
    )

    assert spread_score["score"] == 91
    assert completeness["score"] == 71.0
    assert inspect_missing_values(spread_missingness)["missing_percentage"] == 8.0


def test_same_missing_cell_rate_scores_lower_when_spread_across_more_columns():
    concentrated = pd.DataFrame(
        {
            **{
                f"measure_{column_number}": [
                    None if column_number == 0 and row_number < 80 else row_number + column_number * 100
                    for row_number in range(100)
                ]
                for column_number in range(10)
            }
        }
    )
    spread = pd.DataFrame(
        {
            f"measure_{column_number}": [
                None if column_number < 5 and row_number < 16 else row_number + column_number * 100
                for row_number in range(100)
            ]
            for column_number in range(10)
        }
    )

    concentrated_score = build_score(concentrated)
    spread_score = build_score(spread)

    assert inspect_missing_values(concentrated)["missing_percentage"] == 8.0
    assert inspect_missing_values(spread)["missing_percentage"] == 8.0
    assert spread_score["score"] < concentrated_score["score"]


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (100, "Clear"),
        (90, "Clear"),
        (89, "Minor observations"),
        (75, "Minor observations"),
        (74, "Review recommended"),
        (50, "Review recommended"),
        (49, "Significant issues"),
        (25, "Significant issues"),
        (24, "Integrity compromised"),
        (0, "Integrity compromised"),
    ],
)
def test_score_band_boundaries(score, expected):
    assert score_band(score) == expected


def test_empty_or_unusable_dataset_is_not_given_a_misleading_score():
    result = build_score(pd.DataFrame())

    assert result["score"] is None
    assert result["band"] == "Not assessable"
    assert result["components"] == []
