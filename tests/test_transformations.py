"""Tests for TALOS user-approved working-copy transformations."""

import pandas as pd
import pytest

from src.quality_checks import (
    inspect_category_consistency,
    inspect_duplicates,
    inspect_missing_values,
    inspect_numeric_outliers,
    inspect_structure,
)
from src.transformations import (
    append_ledger_record,
    apply_transformation,
    apply_transformations,
    build_repair_plan,
    build_suggested_transformations,
    create_working_copy,
    reset_working_copy,
)


def inspect_all(df):
    """Build findings using the same read-only checks as the app."""
    return {
        "missing": inspect_missing_values(df),
        "duplicates": inspect_duplicates(df),
        "categories": inspect_category_consistency(df),
        "outliers": inspect_numeric_outliers(df),
        "structure": inspect_structure(df),
    }


def test_whitespace_normalization_trims_and_collapses_without_changing_source():
    original = pd.DataFrame({"region": ["  North  Shore ", "North   Shore", None]})
    source_copy = original.copy(deep=True)

    working, record = apply_transformation(
        original, {"type": "normalize_whitespace", "column": "region"}
    )

    assert working["region"].tolist()[:2] == ["North Shore", "North Shore"]
    assert record["affected_rows"] == 2
    assert record["before_after"][0] == {
        "before": "  North  Shore ",
        "after": "North Shore",
    }
    pd.testing.assert_frame_equal(original, source_copy)


def test_category_consolidation_uses_selected_canonical_value():
    original = pd.DataFrame({"region": ["Sydney", "SYDNEY", "sydney", "Perth"]})
    source_copy = original.copy(deep=True)

    working, record = apply_transformation(
        original,
        {
            "type": "consolidate_category",
            "column": "region",
            "variants": ["Sydney", "SYDNEY", "sydney"],
            "canonical_value": "SYDNEY",
        },
    )

    assert working["region"].tolist() == ["SYDNEY", "SYDNEY", "SYDNEY", "Perth"]
    assert record["affected_rows"] == 2
    assert record["parameters"]["canonical_value"] == "SYDNEY"
    pd.testing.assert_frame_equal(original, source_copy)


def test_exact_duplicate_removal_does_not_remove_identifier_repeats():
    original = pd.DataFrame(
        {"record_id": [7, 7, 8], "status": ["open", "closed", "open"]}
    )

    working, record = apply_transformation(
        original, {"type": "remove_exact_duplicates"}
    )

    assert len(working) == 3
    assert working["record_id"].tolist() == [7, 7, 8]
    assert record["affected_rows"] == 0


def test_exact_duplicate_removal_keeps_first_copy_and_logs_row_change():
    original = pd.DataFrame({"id": [1, 2, 2], "value": ["a", "b", "b"]})
    source_copy = original.copy(deep=True)

    working, record = apply_transformation(
        original, {"type": "remove_exact_duplicates"}
    )

    assert working.to_dict(orient="records") == [
        {"id": 1, "value": "a"},
        {"id": 2, "value": "b"},
    ]
    assert record["affected_rows"] == 1
    assert record["rows_before"] == 3
    assert record["rows_after"] == 2
    pd.testing.assert_frame_equal(original, source_copy)


@pytest.mark.parametrize(
    ("method", "expected"), [("median", 3.0), ("mean", 8.0), ("custom", 99.0)]
)
def test_numeric_imputation_supports_median_mean_and_custom_value(method, expected):
    original = pd.DataFrame({"amount": [1.0, 3.0, 20.0, None]})
    source_copy = original.copy(deep=True)
    action = {"type": "fill_numeric_missing", "column": "amount", "method": method}
    if method == "custom":
        action["value"] = 99

    working, record = apply_transformation(original, action)

    assert working["amount"].tolist() == [1.0, 3.0, 20.0, expected]
    assert record["affected_rows"] == 1
    pd.testing.assert_frame_equal(original, source_copy)


def test_numeric_imputation_rejects_nonfinite_values_and_all_missing_median():
    with pytest.raises(ValueError, match="finite"):
        apply_transformation(
            pd.DataFrame({"amount": [1.0, None]}),
            {
                "type": "fill_numeric_missing",
                "column": "amount",
                "method": "custom",
                "value": float("inf"),
            },
        )
    with pytest.raises(ValueError, match="no finite observed"):
        apply_transformation(
            pd.DataFrame({"amount": [float("nan"), float("nan")]}),
            {"type": "fill_numeric_missing", "column": "amount", "method": "median"},
        )


def test_text_imputation_supports_custom_and_most_common_values():
    original = pd.DataFrame({"tier": ["silver", "gold", "gold", None]})
    source_copy = original.copy(deep=True)

    custom, custom_record = apply_transformation(
        original,
        {
            "type": "fill_text_missing",
            "column": "tier",
            "method": "custom",
            "value": "unclassified",
        },
    )
    common, common_record = apply_transformation(
        original,
        {"type": "fill_text_missing", "column": "tier", "method": "mode"},
    )

    assert custom.loc[3, "tier"] == "unclassified"
    assert common.loc[3, "tier"] == "gold"
    assert custom_record["parameters"]["method"] == "custom"
    assert common_record["parameters"]["method"] == "mode"
    pd.testing.assert_frame_equal(original, source_copy)


def test_text_imputation_rejects_nontext_and_handles_all_missing_custom_value():
    with pytest.raises(ValueError, match="text or category"):
        apply_transformation(
            pd.DataFrame({"flag": [True, None]}),
            {
                "type": "fill_text_missing",
                "column": "flag",
                "method": "custom",
                "value": "unknown",
            },
        )
    working, record = apply_transformation(
        pd.DataFrame({"label": [None, None]}),
        {
            "type": "fill_text_missing",
            "column": "label",
            "method": "custom",
            "value": "unclassified",
        },
    )
    assert working["label"].tolist() == ["unclassified", "unclassified"]
    assert record["affected_rows"] == 2


def test_remove_rows_with_missing_previews_examples_and_keeps_source():
    original = pd.DataFrame({"region": ["north", None, "south"], "value": [1, 2, 3]})
    source_copy = original.copy(deep=True)

    working, record = apply_transformation(
        original, {"type": "remove_rows_with_missing", "column": "region"}
    )

    assert working["region"].tolist() == ["north", "south"]
    assert record["affected_rows"] == 1
    assert record["before_after"][0]["after"] == "(row removed)"
    pd.testing.assert_frame_equal(original, source_copy)


def test_empty_column_removal_requires_an_actually_empty_column():
    original = pd.DataFrame({"empty": [None, None], "value": [1, 2]})
    working, record = apply_transformation(
        original, {"type": "remove_empty_column", "column": "empty"}
    )
    assert list(working.columns) == ["value"]
    assert record["columns_after"] == 1

    with pytest.raises(ValueError, match="completely empty"):
        apply_transformation(
            original, {"type": "remove_empty_column", "column": "value"}
        )


def test_suggestions_follow_findings_and_do_not_fix_contextual_signals():
    df = pd.DataFrame(
        {
            "region": ["Sydney", "SYDNEY", "north ", "north", "west", "east", "west", "east", "north", "south"],
            "record_id": [1, 1, 3, 4, 5, 6, 7, 8, 9, 10],
            "empty": [None] * 10,
            "amount": [10, 11, 12, 13, 14, 15, 16, 17, 18, 1000],
        }
    )

    suggestions = build_suggested_transformations(df, inspect_all(df))
    action_types = [item["action"]["type"] for item in suggestions]

    assert "normalize_whitespace" in action_types
    assert "consolidate_category" in action_types
    assert "remove_empty_column" in action_types
    assert "fill_numeric_missing" not in action_types
    assert "remove_identifier_duplicates" not in action_types
    assert "replace_outliers" not in action_types


def test_whitespace_only_variants_propose_narrow_whitespace_cleanup():
    df = pd.DataFrame({"region": ["Sydney", " Sydney ", "Sydney  ", "Perth"]})
    suggestions = build_suggested_transformations(df, inspect_all(df))

    assert [item["action"]["type"] for item in suggestions] == ["normalize_whitespace"]


def test_working_copy_reset_and_ledger_are_independent():
    original = pd.DataFrame({"region": ["north ", "south"]})
    working = create_working_copy(original)
    working.loc[0, "region"] = "north"
    record = {"action": "normalize", "parameters": {"case_sensitive": True}}
    ledger = []
    updated_ledger = append_ledger_record(ledger, record)
    record["parameters"]["case_sensitive"] = False
    restored = reset_working_copy(original)

    assert original.loc[0, "region"] == "north "
    assert restored.loc[0, "region"] == "north "
    assert ledger == []
    assert updated_ledger[0]["parameters"]["case_sensitive"] is True


def test_repair_plan_applies_only_selected_actions_and_estimates_scope():
    original = pd.DataFrame(
        {
            "region": ["North ", "north", "South", "South"],
            "amount": [10.0, None, 30.0, 40.0],
            "empty": [None, None, None, None],
        }
    )
    source_copy = original.copy(deep=True)
    actions = [
        {
            "type": "fill_numeric_missing",
            "column": "amount",
            "method": "median",
            "label": "Fill with median · amount",
        },
        {
            "type": "remove_empty_column",
            "column": "empty",
            "label": "Remove empty column · empty",
        },
    ]

    plan = build_repair_plan(original, actions)

    assert plan["selected_count"] == 2
    assert plan["affected_columns"] == ["amount", "empty"]
    assert plan["estimated_values_changed"] == 1
    assert plan["estimated_rows_removed"] == 0
    assert plan["estimated_columns_removed"] == 1
    assert plan["preview_df"].loc[1, "amount"] == 30
    assert "region" in plan["preview_df"].columns
    assert all(record["parameters"]["operation"] == action["type"] for action, record in zip(actions, plan["records"]))
    pd.testing.assert_frame_equal(original, source_copy)


def test_batch_failure_returns_no_partial_frame_and_keeps_source_untouched():
    original = pd.DataFrame({"amount": [1.0, None], "text": ["kept", None]})
    source_copy = original.copy(deep=True)
    actions = [
        {"type": "fill_numeric_missing", "column": "amount", "method": "median"},
        {"type": "remove_empty_column", "column": "text"},
    ]

    with pytest.raises(ValueError, match="completely empty"):
        apply_transformations(original, actions)

    pd.testing.assert_frame_equal(original, source_copy)
