"""Suggested, copy-returning dataset transformations for the TALOS Forge."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_numeric_dtype,
    is_object_dtype,
    is_string_dtype,
)


def create_working_copy(original_df: pd.DataFrame) -> pd.DataFrame:
    """Return an independent DataFrame for approved transformations."""
    return original_df.copy(deep=True)


def reset_working_copy(original_df: pd.DataFrame) -> pd.DataFrame:
    """Restore a fresh working copy from the untouched original DataFrame."""
    return create_working_copy(original_df)


def append_ledger_record(
    ledger: list[dict[str, Any]], record: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return a new ledger list containing a copy of one approved record."""
    updated_ledger = deepcopy(ledger)
    updated_ledger.append(deepcopy(record))
    return updated_ledger


def apply_transformations(
    df: pd.DataFrame, actions: list[dict[str, Any]]
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Apply an ordered repair plan to copies and return one record per action.

    The caller receives no partial result if an action fails. The input frame
    remains untouched, so applying the returned result is an explicit UI step.
    """
    working_copy = df.copy(deep=True)
    records = []
    for action in actions:
        working_copy, record = apply_transformation(working_copy, action)
        if action.get("label"):
            record["transformation_type"] = action["label"]
            record["action"] = action["label"]
            record["parameters"]["operation"] = action["type"]
        records.append(record)
    return working_copy, records


def build_repair_plan(
    df: pd.DataFrame, actions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Preview selected actions and summarize their expected scope."""
    preview_df, records = apply_transformations(df, actions)
    value_change_types = {
        "normalize_whitespace",
        "consolidate_category",
        "fill_numeric_missing",
        "fill_text_missing",
    }
    affected_columns = list(
        dict.fromkeys(
            str(action.get("column") or "All columns") for action in actions
        )
    )
    return {
        "selected_count": len(actions),
        "affected_columns": affected_columns,
        "estimated_values_changed": sum(
            record["affected_rows"]
            for action, record in zip(actions, records)
            if action.get("type") in value_change_types
        ),
        "estimated_rows_removed": max(0, len(df.index) - len(preview_df.index)),
        "estimated_columns_removed": max(0, len(df.columns) - len(preview_df.columns)),
        "records": records,
        "preview_df": preview_df,
    }


def normalize_whitespace(value: object) -> object:
    """Trim text and collapse repeated internal whitespace without altering other values."""
    if isinstance(value, str):
        return " ".join(value.split())
    return value


def _contains_only_boolean_values(series: pd.Series) -> bool:
    """Recognize boolean values stored in object columns with missing cells."""
    observed_values = series.dropna()
    return bool(len(observed_values)) and bool(
        observed_values.map(lambda value: isinstance(value, (bool, np.bool_))).all()
    )


def count_whitespace_changes(series: pd.Series) -> int:
    """Count text values that would change under whitespace normalization."""
    return sum(
        isinstance(value, str) and normalize_whitespace(value) != value
        for value in series
    )


def _preferred_category_variant(variants: list[dict[str, Any]]) -> dict[str, Any]:
    """Choose a common, cleanly formatted observed value as the proposal."""
    def rank(item: dict[str, Any]) -> tuple[int, int, int, str, str]:
        value = str(item["value"])
        normalized_whitespace = " ".join(value.split())
        if value == value.title():
            case_preference = 0
        elif value.isupper():
            case_preference = 1
        elif value.islower():
            case_preference = 2
        else:
            case_preference = 3
        return (
            -int(item["count"]),
            int(value != normalized_whitespace),
            case_preference,
            value.casefold(),
            value,
        )

    return min(variants, key=rank)


def build_suggested_transformations(
    df: pd.DataFrame,
    findings: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build conservative proposals from findings already produced by TALOS."""
    suggestions = []
    category_findings = findings["categories"]

    for column in category_findings["checked_columns"]:
        changed_count = count_whitespace_changes(df[column])
        if changed_count:
            suggestions.append(
                {
                    "suggestion_id": f"whitespace:{column}",
                    "title": "Normalize category whitespace",
                    "description": (
                        "Trim leading and trailing spaces and collapse repeated internal spaces. "
                        "Text and letter case are otherwise preserved."
                    ),
                    "affected_count": changed_count,
                    "action": {"type": "normalize_whitespace", "column": column},
                }
            )

    for group in category_findings["variant_groups"]:
        variants = group["variants"]
        # Whitespace-only differences have a narrower proposal above.
        whitespace_normalized = {normalize_whitespace(item["value"]) for item in variants}
        if len(whitespace_normalized) == 1:
            continue

        most_common = _preferred_category_variant(variants)
        column = group["column"]
        normalized_value = group["normalized_value"]
        suggestions.append(
            {
                "suggestion_id": f"category:{column}:{normalized_value}",
                "title": "Consolidate category variants",
                "description": (
                    "Choose an existing representation as the canonical value. "
                    "TALOS proposes the most common spelling; you can select another observed value."
                ),
                "affected_count": sum(item["count"] for item in variants if item["value"] != most_common["value"]),
                "column": column,
                "normalized_value": normalized_value,
                "variants": deepcopy(variants),
                "proposed_canonical": most_common["value"],
                "action": {
                    "type": "consolidate_category",
                    "column": column,
                    "variants": [item["value"] for item in variants],
                    "canonical_value": most_common["value"],
                },
            }
        )

    duplicate_count = findings["duplicates"]["exact_duplicate_row_count"]
    if duplicate_count:
        suggestions.append(
            {
                "suggestion_id": "remove_exact_duplicates",
                "title": "Remove exact duplicate rows",
                "description": (
                    "Keep the first copy of each completely identical row. "
                    "Repeated values in possible identifier columns are not used for this action."
                ),
                "affected_count": duplicate_count,
                "action": {"type": "remove_exact_duplicates"},
            }
        )

    for column in findings["structure"]["empty_columns"]:
        suggestions.append(
            {
                "suggestion_id": f"remove_empty_column:{column}",
                "title": f"Remove empty column: {column}",
                "description": "This column contains no non-missing values. Removing it changes the working copy only.",
                "affected_count": 1,
                "action": {"type": "remove_empty_column", "column": column},
            }
        )

    return suggestions


def _safe_value(value: object) -> object:
    """Convert pandas and NumPy scalars to ordinary Python values for the ledger."""
    if pd.isna(value):
        return "(missing)"
    return value.item() if hasattr(value, "item") else value


def _changed_examples(
    before: pd.Series, after: pd.Series, changed_mask: pd.Series, limit: int = 5
) -> list[dict[str, object]]:
    """Return a few before-and-after values for an approved transformation."""
    examples = []
    for index in before.index[changed_mask][:limit]:
        examples.append(
            {
                "before": _safe_value(before.loc[index]),
                "after": _safe_value(after.loc[index]),
            }
        )
    return examples


def _ledger_record(
    action: dict[str, Any],
    before_df: pd.DataFrame,
    after_df: pd.DataFrame,
    affected_rows: int,
    description: str,
    before_after: list[dict[str, object]] | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the common, human-readable metadata for one transformation."""
    return {
        "transformation_type": action["type"],
        "column": action.get("column", ""),
        "action": action["type"],
        "affected_rows": int(affected_rows),
        "description": description,
        "parameters": parameters or {},
        "before_after": before_after or [],
        "rows_before": len(before_df.index),
        "rows_after": len(after_df.index),
        "columns_before": len(before_df.columns),
        "columns_after": len(after_df.columns),
    }


def apply_transformation(
    df: pd.DataFrame, action: dict[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply one explicit action to a deep copy and return it with ledger metadata.

    This function never mutates ``df``. The caller decides whether the returned
    DataFrame becomes the active working copy.
    """
    action_type = action.get("type")
    column = action.get("column")
    if column is not None and column not in df.columns:
        raise ValueError(f"Column {column!r} does not exist in the dataset.")

    result = df.copy(deep=True)
    record: dict[str, Any]

    if action_type == "normalize_whitespace":
        before = df[column]
        after = before.map(normalize_whitespace)
        changed_mask = before.map(
            lambda value: isinstance(value, str)
            and normalize_whitespace(value) != value
        )
        affected_rows = int(changed_mask.sum())
        result[column] = after
        record = _ledger_record(
            action,
            df,
            result,
            affected_rows,
            "Trimmed outer whitespace and collapsed repeated spaces.",
            _changed_examples(before, after, changed_mask),
            {"preserved_letter_case": True},
        )

    elif action_type == "consolidate_category":
        canonical_value = action["canonical_value"]
        variants = set(action["variants"])
        before = df[column]
        changed_mask = before.map(lambda value: value in variants and value != canonical_value)
        after = before.map(
            lambda value: canonical_value if value in variants else value
        )
        affected_rows = int(changed_mask.sum())
        result[column] = after
        record = _ledger_record(
            action,
            df,
            result,
            affected_rows,
            f"Consolidated observed variants to {canonical_value!r}.",
            _changed_examples(before, after, changed_mask),
            {
                "canonical_value": canonical_value,
                "variants": sorted(str(value) for value in variants),
            },
        )

    elif action_type == "remove_exact_duplicates":
        duplicate_mask = df.duplicated(keep="first")
        affected_rows = int(duplicate_mask.sum())
        result = df.loc[~duplicate_mask].copy(deep=True)
        samples = [
            {str(key): _safe_value(value) for key, value in row.items()}
            for row in df.loc[duplicate_mask].head(5).to_dict(orient="records")
        ]
        record = _ledger_record(
            action,
            df,
            result,
            affected_rows,
            "Removed exact duplicate rows, keeping the first copy.",
            [{"before": row, "after": "(duplicate row removed)"} for row in samples],
            {"keep": "first"},
        )

    elif action_type == "remove_rows_with_missing":
        missing_mask = df[column].isna()
        affected_rows = int(missing_mask.sum())
        result = df.loc[~missing_mask].copy(deep=True)
        removed_samples = [
            {str(key): _safe_value(value) for key, value in row.items()}
            for row in df.loc[missing_mask].head(5).to_dict(orient="records")
        ]
        record = _ledger_record(
            action,
            df,
            result,
            affected_rows,
            f"Removed rows where {column!r} is missing.",
            [
                {"before": row, "after": "(row removed)"}
                for row in removed_samples
            ],
            {"column": column},
        )

    elif action_type == "fill_numeric_missing":
        series = df[column]
        if not is_numeric_dtype(series.dtype) or is_bool_dtype(series.dtype):
            raise ValueError("Numeric imputation requires a non-boolean numeric column.")
        missing_mask = series.isna()
        affected_rows = int(missing_mask.sum())
        if not affected_rows:
            raise ValueError("This column has no missing values to fill.")
        if series.dropna().empty and action["method"] in {"median", "mean"}:
            raise ValueError("This column has no finite observed numeric value to use for imputation.")
        method = action["method"]
        if method == "median":
            fill_value = float(series.median())
        elif method == "mean":
            fill_value = float(series.mean())
        elif method == "custom":
            fill_value = float(action["value"])
            if not math.isfinite(fill_value):
                raise ValueError("A custom numeric fill value must be finite.")
        else:
            raise ValueError("Choose median, mean, or a custom numeric value.")
        if not math.isfinite(fill_value):
            raise ValueError("This column has no finite observed numeric value to use for imputation.")
        before = series
        after = series.astype("float64").fillna(fill_value)
        result[column] = after
        record = _ledger_record(
            action,
            df,
            result,
            affected_rows,
            f"Filled {affected_rows} missing values with the {method} value {fill_value:g}.",
            _changed_examples(before, after, missing_mask),
            {"method": method, "fill_value": fill_value},
        )

    elif action_type == "fill_text_missing":
        series = df[column]
        is_text_column = (
            is_object_dtype(series.dtype)
            or is_string_dtype(series.dtype)
            or isinstance(series.dtype, pd.CategoricalDtype)
        )
        if (
            not is_text_column
            or is_numeric_dtype(series.dtype)
            or is_bool_dtype(series.dtype)
            or _contains_only_boolean_values(series)
        ):
            raise ValueError("Text imputation requires a text or category column.")
        missing_mask = series.isna()
        affected_rows = int(missing_mask.sum())
        if not affected_rows:
            raise ValueError("This column has no missing values to fill.")
        method = action["method"]
        if method == "mode":
            modes = series.dropna().mode()
            if modes.empty:
                raise ValueError("There is no existing value to use as the most common value.")
            fill_value = modes.iloc[0]
        elif method == "custom":
            fill_value = str(action["value"])
        else:
            raise ValueError("Choose a custom value or the most common value.")
        before = series
        after = series.astype("object").fillna(fill_value)
        result[column] = after
        record = _ledger_record(
            action,
            df,
            result,
            affected_rows,
            f"Filled {affected_rows} missing values with {fill_value!r}.",
            _changed_examples(before, after, missing_mask),
            {"method": method, "fill_value": _safe_value(fill_value)},
        )

    elif action_type == "remove_empty_column":
        if not df[column].isna().all():
            raise ValueError("Only a completely empty column can be removed by this suggestion.")
        result = df.drop(columns=[column]).copy(deep=True)
        record = _ledger_record(
            action,
            df,
            result,
            0,
            f"Removed the empty column {column!r}.",
            [{"before": column, "after": "(column removed)"}],
            {"column": column},
        )

    else:
        raise ValueError(f"Unsupported transformation: {action_type!r}.")

    return result, record
