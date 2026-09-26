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
    TEXT_NORMALISATION_RULES,
    append_ledger_record,
    apply_transformation,
    apply_transformations,
    build_repair_plan,
    build_outlier_remediation_plan,
    build_text_normalisation_plan,
    build_suggested_transformations,
    create_working_copy,
    normalize_text_value,
    recommend_text_normalisation_columns,
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


@pytest.mark.parametrize(
    ("value", "rule", "expected"),
    [
        ("North Shore", "Leave unchanged", "North Shore"),
        ("North Shore", "lowercase", "north shore"),
        ("North Shore", "UPPERCASE", "NORTH SHORE"),
        ("north shore", "Proper Case", "North Shore"),
        ("nORTH sHORE", "Sentence case", "North shore"),
        ("north SHORE", "camelCase", "northShore"),
        ("North Shore", "snake_case", "north_shore"),
    ],
)
def test_text_normalisation_rules_are_deterministic(value, rule, expected):
    assert rule in TEXT_NORMALISATION_RULES
    assert normalize_text_value(value, rule) == expected


def test_text_normalisation_whitespace_options_are_independent_and_nontext_is_preserved():
    assert normalize_text_value("  North   Shore  ", trim_leading=True) == "North   Shore  "
    assert normalize_text_value("  North   Shore  ", trim_trailing=True) == "  North   Shore"
    assert normalize_text_value("North   Shore", collapse_internal_spaces=True) == "North Shore"
    assert normalize_text_value(123, "UPPERCASE", trim_leading=True) == 123


def test_text_normalisation_can_standardise_common_address_suffix_variants():
    values = ["10 main rd", "10 Main Road", "8 Oak st.", "8 Oak Street", "St. John's"]
    original = pd.DataFrame({"address": values})

    plan = build_text_normalisation_plan(
        original,
        "Proper Case",
        ["address"],
        standardize_address_suffixes=True,
    )

    assert plan["canonical_values"]["address"] == {
        "10 main rd": "10 Main Road",
        "10 Main Road": "10 Main Road",
        "8 Oak st.": "8 Oak Street",
        "8 Oak Street": "8 Oak Street",
        "St. John's": "St. John's",
    }
    assert plan["standardize_address_suffixes"] is True
    assert plan["values_affected"] == 2

    working, record = apply_transformation(
        original, {"type": "normalize_text", "plan": plan}
    )
    assert working["address"].iloc[:4].tolist() == [
        "10 Main Road", "10 Main Road", "8 Oak Street", "8 Oak Street"
    ]
    assert record["parameters"]["standardize_address_suffixes"] is True
    pd.testing.assert_series_equal(original["address"], pd.Series(values, name="address"))


def test_text_plan_precedence_preview_counts_and_approved_copy_preserve_source():
    original = pd.DataFrame(
        {"status": ["  blue  sky  ", "BLUE", "Blue", "other", None]}
    )
    source_copy = original.copy(deep=True)
    plan = build_text_normalisation_plan(
        original,
        "lowercase",
        ["status"],
        column_rules={"status": "UPPERCASE"},
        value_overrides={
            "status": {
                "BLUE": {"mode": "custom", "value": "Preferred"},
                "Blue": {"mode": "rule", "rule": "Sentence case"},
            }
        },
        trim_leading=True,
        trim_trailing=True,
        collapse_internal_spaces=True,
    )

    assert plan["canonical_values"]["status"] == {
        "  blue  sky  ": "BLUE SKY",
        "BLUE": "Preferred",
        "Blue": "Blue",
        "other": "OTHER",
    }
    assert plan["values_affected"] == 3
    assert plan["cells_changed"] == 3
    assert plan["rows_affected"] == 3
    assert plan["manual_override_count"] == 2
    assert len(plan["preview"]) == 3
    pd.testing.assert_frame_equal(original, source_copy)

    working, record = apply_transformation(
        original, {"type": "normalize_text", "plan": plan}
    )
    assert working["status"].tolist() == ["BLUE SKY", "Preferred", "Blue", "OTHER", None]
    assert record["affected_rows"] == 3
    assert record["affected_cells"] == 3
    assert record["parameters"]["selected_columns"] == ["status"]
    assert record["parameters"]["manual_override_count"] == 2
    assert len(record["before_after"]) == 3
    pd.testing.assert_frame_equal(original, source_copy)


def test_text_plan_requires_selected_columns_and_supported_rules():
    original = pd.DataFrame({"status": ["Open", "closed"]})
    with pytest.raises(ValueError, match="Unknown text column"):
        build_text_normalisation_plan(original, "lowercase", ["missing"])
    with pytest.raises(ValueError, match="supported text rule"):
        build_text_normalisation_plan(
            original, "lowercase", ["status"], column_rules={"status": "bad rule"}
        )


def test_text_recommendations_skip_identifiers_and_long_uncontrolled_values():
    df = pd.DataFrame(
        {
            "region": ["North", "north", "South"],
            "customer_name": ["Ari", "Bea", "Cam"],
            "record_id": ["a1", "a2", "a3"],
            "notes": ["short", "text", "here"],
        }
    )
    assert recommend_text_normalisation_columns(df) == ["region"]


def test_text_normalisation_high_cardinality_plan_scales_linearly_in_row_count():
    values = [f"Customer-{index:05d}" for index in range(25_000)]
    original = pd.DataFrame({"label": values})
    plan = build_text_normalisation_plan(original, "lowercase", ["label"], preview_limit=20)

    assert plan["values_affected"] == 25_000
    assert plan["rows_affected"] == 25_000
    assert len(plan["preview"]) == 20


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

    with pytest.raises(ValueError, match="At least one dataset column"):
        apply_transformation(
            pd.DataFrame({"empty": [None, None]}),
            {"type": "remove_empty_column", "column": "empty"},
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


def test_repair_plan_reports_only_selected_text_columns():
    original = pd.DataFrame({"status": ["open", "OPEN"], "notes": ["leave", "alone"]})
    text_plan = build_text_normalisation_plan(original, "lowercase", ["status"])

    plan = build_repair_plan(
        original,
        [{"type": "normalize_text", "label": "Text normalisation", "plan": text_plan}],
    )

    assert plan["affected_columns"] == ["status"]
    assert plan["estimated_values_changed"] == 1


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


def test_user_selected_columns_preview_remove_only_chosen_fields_and_preserve_source():
    original = pd.DataFrame({"legacy": ["x", "y"], "notes": ["keep", "these"], "amount": [1, 2]})
    source_copy = original.copy(deep=True)
    plan = build_repair_plan(original, [{"type": "remove_columns", "columns": ["legacy", "amount"]}])
    assert list(plan["preview_df"].columns) == ["notes"]
    assert plan["estimated_columns_removed"] == 2
    assert plan["estimated_rows_removed"] == 0
    pd.testing.assert_frame_equal(original, source_copy)

    working, records = apply_transformations(
        original,
        [{"type": "remove_columns", "columns": ["legacy", "amount"], "label": "Remove selected columns"}],
    )
    assert list(working.columns) == ["notes"]
    assert records[0]["parameters"]["columns_removed"] == ["legacy", "amount"]
    assert records[0]["parameters"]["columns_before"] == 3
    assert records[0]["parameters"]["columns_after"] == 1
    pd.testing.assert_frame_equal(original, source_copy)


@pytest.mark.parametrize("columns", [[], ["a", "b"]])
def test_user_selected_column_removal_requires_a_selection_and_keeps_one_column(columns):
    with pytest.raises(ValueError, match="Select at least one|At least one dataset column"):
        apply_transformation(pd.DataFrame({"a": [1], "b": [2]}), {"type": "remove_columns", "columns": columns})


def test_user_selected_column_removal_rejects_stale_column_names():
    with pytest.raises(ValueError, match="no longer exist"):
        apply_transformation(pd.DataFrame({"a": [1], "b": [2]}), {"type": "remove_columns", "columns": ["missing"]})


def _outlier_frame():
    return pd.DataFrame({
        "amount": list(range(1, 11)) + [100, 200],
        "volume": list(range(2, 22, 2)) + [200, 400],
        "label": [f"r{index}" for index in range(12)],
    })


def test_outlier_leave_unchanged_is_the_default_and_creates_no_action():
    original = _outlier_frame()
    source_copy = original.copy(deep=True)
    plan = build_outlier_remediation_plan(original, {"amount": {"strategy": "leave"}})
    assert plan["column_actions"] == []
    assert plan["affected_values"] == 0
    pd.testing.assert_frame_equal(original, source_copy)


def test_negative_integer_removal_targets_whole_negative_values_and_preserves_source():
    original = pd.DataFrame(
        {"amount": [7, 4, -3, -2, -1.5], "record": list("abcde")}
    )
    source_copy = original.copy(deep=True)

    plan = build_outlier_remediation_plan(
        original, {"amount": {"strategy": "remove_negative_integers"}}
    )
    assert plan["affected_values"] == 2
    assert plan["unique_rows_removed"] == 2
    action = plan["column_actions"][0]
    assert action["lower_bound"] is None
    assert action["criteria"] == "negative_integer_values"

    working, record = apply_transformation(
        original, {"type": "remediate_outliers", "plan": plan}
    )
    assert working["amount"].tolist()[-1] == -1.5
    assert not working["amount"].isin([-3, -2]).any()
    assert record["parameters"]["unique_rows_removed"] == 2
    assert record["parameters"]["columns"][0]["criteria"] == "negative_integer_values"
    pd.testing.assert_frame_equal(original, source_copy)


def test_negative_integer_outlier_removal_keeps_positive_and_fractional_outliers():
    original = pd.DataFrame(
        {
            "amount": [*range(1, 11), -100, -200, 100, 200, -100.5],
            "record": list("abcdefghijklmno"),
        }
    )
    source_copy = original.copy(deep=True)

    plan = build_outlier_remediation_plan(
        original, {"amount": {"strategy": "remove_negative_integer_outliers"}}
    )
    assert plan["affected_values"] == 2
    assert plan["unique_rows_removed"] == 2
    assert all(item["before"] in {-100, -200} for item in plan["column_actions"][0]["examples"])

    working, record = apply_transformation(
        original, {"type": "remediate_outliers", "plan": plan}
    )
    assert {-100, -200}.isdisjoint(set(working["amount"]))
    assert {100, 200, -100.5}.issubset(set(working["amount"]))
    assert record["parameters"]["columns"][0]["criteria"] == "negative_integer_iqr_outliers"
    pd.testing.assert_frame_equal(original, source_copy)


@pytest.mark.parametrize(("strategy", "expected"), [("mean", 5.5), ("median", 5.5)])
def test_outlier_mean_and_median_use_only_finite_non_outlier_values(strategy, expected):
    original = _outlier_frame()
    source_copy = original.copy(deep=True)
    plan = build_outlier_remediation_plan(original, {"amount": {"strategy": strategy}})
    action = plan["column_actions"][0]
    assert action["outlier_count"] == 2
    assert action["replacement_value"] == expected
    assert action["lower_bound"] < action["upper_bound"]
    assert action["examples"][0]["before"] == 100
    assert action["examples"][0]["after"] == expected
    working, record = apply_transformation(original, {"type": "remediate_outliers", "plan": plan})
    assert working["amount"].tolist()[-2:] == [expected, expected]
    assert record["parameters"]["columns"][0]["strategy"] == strategy
    assert record["parameters"]["columns"][0]["replacement_value"] == expected
    assert record["before_after"][0]["column"] == "amount"
    assert record["before_after"][0]["row_position"] > 0
    pd.testing.assert_frame_equal(original, source_copy)

    nullable = _outlier_frame()
    nullable["amount"] = nullable["amount"].astype("Int64")
    nullable_plan = build_outlier_remediation_plan(
        nullable, {"amount": {"strategy": strategy}}
    )
    nullable_result, _ = apply_transformation(
        nullable, {"type": "remediate_outliers", "plan": nullable_plan}
    )
    assert nullable_result["amount"].tolist()[-2:] == [expected, expected]
    assert nullable_result["amount"].dtype.name == "Float64"


def test_outlier_blank_uses_missing_values_and_preserves_nullable_numeric_dtype():
    original = _outlier_frame()
    original["amount"] = original["amount"].astype("Int64")
    source_copy = original.copy(deep=True)
    plan = build_outlier_remediation_plan(original, {"amount": {"strategy": "blank"}})
    working, record = apply_transformation(original, {"type": "remediate_outliers", "plan": plan})
    assert working["amount"].dtype == "Int64"
    assert working["amount"].isna().sum() == 2
    assert record["parameters"]["affected_values"] == 2
    pd.testing.assert_frame_equal(original, source_copy)

    native_integers = _outlier_frame()
    plan = build_outlier_remediation_plan(
        native_integers, {"amount": {"strategy": "blank"}}
    )
    blanked, _ = apply_transformation(
        native_integers, {"type": "remediate_outliers", "plan": plan}
    )
    assert blanked["amount"].dtype.name == "Int64"
    assert blanked["amount"].isna().sum() == 2


def test_outlier_custom_value_is_validated_and_per_column_strategies_can_differ():
    original = _outlier_frame()
    source_copy = original.copy(deep=True)
    plan = build_outlier_remediation_plan(original, {
        "amount": {"strategy": "custom", "value": 0},
        "volume": {"strategy": "blank"},
    })
    working, record = apply_transformation(original, {"type": "remediate_outliers", "plan": plan})
    assert working["amount"].tolist()[-2:] == [0, 0]
    assert working["volume"].isna().sum() == 2
    assert [item["strategy"] for item in record["parameters"]["columns"]] == ["custom", "blank"]
    pd.testing.assert_frame_equal(original, source_copy)
    with pytest.raises(ValueError, match="finite"):
        build_outlier_remediation_plan(original, {"amount": {"strategy": "custom", "value": float("nan")}})


def test_outlier_row_removal_unions_overlapping_rows_with_duplicate_index_labels():
    original = _outlier_frame()
    original.index = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 10]
    source_copy = original.copy(deep=True)
    plan = build_outlier_remediation_plan(original, {
        "amount": {"strategy": "remove_rows"},
        "volume": {"strategy": "remove_rows"},
    })
    assert plan["affected_values"] == 4
    assert plan["unique_rows_removed"] == 2
    assert plan["overlap_rows_removed"] == 2
    assert plan["preview_shape"] == [10, 3]
    working, record = apply_transformation(original, {"type": "remediate_outliers", "plan": plan})
    assert len(working) == 10
    assert not working["amount"].isin([100, 200]).any()
    assert record["parameters"]["unique_rows_removed"] == 2
    assert record["parameters"]["overlap_rows_removed"] == 2
    pd.testing.assert_frame_equal(original, source_copy)


def test_outlier_capping_uses_the_nearest_iqr_boundary():
    original = _outlier_frame()
    plan = build_outlier_remediation_plan(original, {"amount": {"strategy": "cap"}})
    upper = plan["column_actions"][0]["upper_bound"]
    working, record = apply_transformation(original, {"type": "remediate_outliers", "plan": plan})
    assert working["amount"].tolist()[-2:] == [upper, upper]
    assert record["parameters"]["columns"][0]["replacement_method"] == "nearest IQR boundary"


def test_combined_outlier_column_plan_reports_union_shape_reinspection_ledger_and_reset():
    from src.workflow import inspect_dataset

    original = _outlier_frame()
    source_copy = original.copy(deep=True)
    outlier_plan = build_outlier_remediation_plan(original, {
        "amount": {"strategy": "remove_rows"},
        "volume": {"strategy": "remove_rows"},
    })
    actions = [
        {"type": "remediate_outliers", "plan": outlier_plan},
        {"type": "remove_columns", "columns": ["label"]},
    ]
    plan = build_repair_plan(original, actions)
    assert plan["estimated_rows_removed"] == 2
    assert plan["estimated_columns_removed"] == 1
    assert plan["preview_df"].shape == (10, 2)
    assert plan["estimated_values_changed"] == 4
    pd.testing.assert_frame_equal(original, source_copy)

    working, records = apply_transformations(original, actions)
    ledger = append_ledger_record(append_ledger_record([], records[0]), records[1])
    findings = inspect_dataset(working)
    assert findings["outliers"]["total_outlier_values"] == 0
    assert ledger[0]["parameters"]["columns"][0]["lower_bound"] is not None
    assert ledger[1]["parameters"]["columns_removed"] == ["label"]
    pd.testing.assert_frame_equal(reset_working_copy(original), source_copy)
    pd.testing.assert_frame_equal(original, source_copy)
