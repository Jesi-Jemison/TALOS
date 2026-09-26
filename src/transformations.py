"""TALOS FILE VERSION: v1.2.0. Copy-returning repairs and approved records."""
# TALOS FILE VERSION: v1.2.0

from __future__ import annotations

import math
import re
from copy import deepcopy
from collections import Counter
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_extension_array_dtype,
    is_integer_dtype,
    is_numeric_dtype,
    is_object_dtype,
    is_string_dtype,
)


TEXT_NORMALISATION_RULES = (
    "Leave unchanged",
    "lowercase",
    "UPPERCASE",
    "Proper Case",
    "Sentence case",
    "camelCase",
    "snake_case",
)

OUTLIER_REMEDIATION_STRATEGIES = {
    "blank", "mean", "median", "custom", "remove_rows", "cap",
    "remove_negative_integers", "remove_negative_integer_outliers",
}

_ADDRESS_SUFFIXES = {
    "rd": "Road",
    "road": "Road",
    "st": "Street",
    "street": "Street",
    "ave": "Avenue",
    "av": "Avenue",
    "avenue": "Avenue",
    "blvd": "Boulevard",
    "boulevard": "Boulevard",
    "dr": "Drive",
    "drive": "Drive",
    "ln": "Lane",
    "lane": "Lane",
    "ct": "Court",
    "court": "Court",
    "pl": "Place",
    "place": "Place",
    "hwy": "Highway",
    "highway": "Highway",
    "pkwy": "Parkway",
    "parkway": "Parkway",
    "cir": "Circle",
    "circle": "Circle",
    "ter": "Terrace",
    "terrace": "Terrace",
    "trl": "Trail",
    "trail": "Trail",
    "sq": "Square",
    "square": "Square",
    "way": "Way",
}

_RISKY_TEXT_COLUMN = re.compile(
    r"(?:^|[_\W])(name|email|e-mail|url|uri|website|link|identifier|id|uuid|guid|"
    r"account|code|token|phone|mobile|address|notes?|comments?|description|message|"
    r"free.?text|body|title|subject)(?:$|[_\W])",
    re.IGNORECASE,
)


def normalize_text_value(
    value: object,
    rule: str = "Leave unchanged",
    *,
    trim_leading: bool = False,
    trim_trailing: bool = False,
    collapse_internal_spaces: bool = False,
    standardize_address_suffixes: bool = False,
) -> object:
    """Apply one deterministic text style and only the selected whitespace rules."""
    if not isinstance(value, str):
        return value
    if rule not in TEXT_NORMALISATION_RULES:
        raise ValueError(f"Unsupported text normalisation rule: {rule!r}.")

    text = value
    if trim_leading:
        text = text.lstrip()
    if trim_trailing:
        text = text.rstrip()
    if collapse_internal_spaces:
        text = re.sub(r"(?<=\S)[ \t\r\n\f\v]+(?=\S)", " ", text)
    if standardize_address_suffixes:
        suffix_match = re.search(
            r"(?i)(?<!\w)([a-z]+)\.?([ \t\r\n\f\v]*)$", text
        )
        if suffix_match:
            canonical_suffix = _ADDRESS_SUFFIXES.get(suffix_match.group(1).casefold())
            if canonical_suffix:
                text = (
                    text[: suffix_match.start(1)]
                    + canonical_suffix
                    + suffix_match.group(2)
                )

    if rule == "Leave unchanged":
        return text
    if rule == "lowercase":
        return text.lower()
    if rule == "UPPERCASE":
        return text.upper()
    if rule == "Proper Case":
        proper = text.title()
        return re.sub(
            r"(?<=\w)(['’])S\b",
            lambda match: match.group(1) + "s",
            proper,
        )
    if rule == "Sentence case":
        lowered = text.lower()
        for index, character in enumerate(lowered):
            if character.isalpha():
                return lowered[:index] + character.upper() + lowered[index + 1 :]
        return lowered

    # Split existing camelCase/acronyms before replacing punctuation with word
    # boundaries. This makes repeated application deterministic.
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    words = re.findall(r"[^\W_]+", separated, flags=re.UNICODE)
    if rule == "snake_case":
        return "_".join(word.lower() for word in words)
    if rule == "camelCase":
        if not words:
            return ""
        return words[0].lower() + "".join(
            word[:1].upper() + word[1:].lower() for word in words[1:]
        )
    raise ValueError(f"Unsupported text normalisation rule: {rule!r}.")


def recommend_text_normalisation_columns(df: pd.DataFrame) -> list[str]:
    """Return conservative recommendations for short, controlled text fields."""
    recommendations: list[str] = []
    row_count = max(len(df.index), 1)
    distinct_limit = min(100, max(12, int(row_count * 0.05)))
    category_name = re.compile(
        r"(?:^|[_\W])(state|region|category|status|tier|channel|type|country|"
        r"segment|class|group|department|priority|stage|method|source)(?:$|[_\W])",
        re.IGNORECASE,
    )
    for column, series in df.items():
        observed = series.dropna()
        if not len(observed) or not observed.map(lambda value: isinstance(value, str)).all():
            continue
        name = str(column)
        # Case changes can alter identifiers and the meaning of free text even
        # when a field happens to have few distinct values, so keep these names
        # opt-in instead of recommending them as controlled categories.
        if _RISKY_TEXT_COLUMN.search(name):
            continue
        distinct_count = int(observed.nunique(dropna=True))
        if distinct_count > distinct_limit:
            continue
        # Recommend named category fields or clearly low-cardinality columns;
        # uncertain text fields stay opt-in even when they happen to be short.
        if category_name.search(name) or (distinct_count <= 12 and len(name) <= 40):
            recommendations.append(name)
    return recommendations


def build_text_normalisation_plan(
    df: pd.DataFrame,
    global_rule: str,
    selected_columns: list[str] | tuple[str, ...],
    *,
    column_rules: dict[str, str] | None = None,
    value_overrides: dict[str, dict[str, dict[str, str]]] | None = None,
    trim_leading: bool = False,
    trim_trailing: bool = False,
    collapse_internal_spaces: bool = False,
    standardize_address_suffixes: bool = False,
    preview_limit: int = 100,
) -> dict[str, Any]:
    """Preview text mappings without mutating ``df`` or expanding row controls."""
    if global_rule not in TEXT_NORMALISATION_RULES:
        raise ValueError(f"Unsupported text normalisation rule: {global_rule!r}.")
    columns = list(dict.fromkeys(str(column) for column in selected_columns))
    missing_columns = [column for column in columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Unknown text column(s): {', '.join(missing_columns)}.")
    invalid_column_rules = {
        column: rule
        for column, rule in (column_rules or {}).items()
        if column not in columns or rule not in TEXT_NORMALISATION_RULES
    }
    if invalid_column_rules:
        raise ValueError("Column rules must target selected columns and use a supported text rule.")

    provided_overrides = deepcopy(value_overrides or {})
    overrides = {column: provided_overrides.get(column, {}) for column in columns}
    mapping: dict[str, dict[str, str]] = {}
    rows_affected_mask = pd.Series(False, index=df.index, dtype=bool)
    preview_rows: list[dict[str, Any]] = []
    changed_distinct_values = 0
    changed_cells = 0
    manual_override_count = 0

    whitespace_options = {
        "trim_leading": bool(trim_leading),
        "trim_trailing": bool(trim_trailing),
        "collapse_internal_spaces": bool(collapse_internal_spaces),
    }
    for column in columns:
        series = df[column]
        column_rule = (column_rules or {}).get(column, global_rule)
        counts = Counter(value for value in series.array if isinstance(value, str))
        per_value = {
            value: override
            for value, override in overrides.get(column, {}).items()
            if value in counts
        }
        if per_value:
            overrides[column] = per_value
        else:
            overrides.pop(column, None)
        resolved: dict[str, str] = {}
        for value in sorted(counts, key=lambda item: (item.casefold(), item)):
            override = per_value.get(value, {})
            mode = override.get("mode", "default")
            if mode == "custom":
                target = str(override.get("value", ""))
                manual_override_count += 1
            elif mode == "rule":
                value_rule = override.get("rule", column_rule)
                if value_rule not in TEXT_NORMALISATION_RULES:
                    raise ValueError(f"Unsupported value-level text rule: {value_rule!r}.")
                target = str(
                    normalize_text_value(
                        value,
                        value_rule,
                        **whitespace_options,
                        standardize_address_suffixes=standardize_address_suffixes,
                    )
                )
                manual_override_count += 1
            elif mode == "default":
                target = str(
                    normalize_text_value(
                        value,
                        column_rule,
                        **whitespace_options,
                        standardize_address_suffixes=standardize_address_suffixes,
                    )
                )
            else:
                raise ValueError(f"Unsupported override mode: {mode!r}.")
            resolved[value] = target
            if target != value:
                changed_distinct_values += 1
                changed_cells += counts[value]
                if len(preview_rows) < max(0, int(preview_limit)):
                    preview_rows.append(
                        {
                            "Column": column,
                            "Original": value,
                            "Default output": str(
                                normalize_text_value(
                                    value,
                                    column_rule,
                                    **whitespace_options,
                                    standardize_address_suffixes=standardize_address_suffixes,
                                )
                            ),
                            "Final output": target,
                            "Rows": counts[value],
                        }
                    )
        # Mark affected rows once per column. Mapping the full Series inside the
        # distinct-value loop makes high-cardinality columns quadratic.
        rows_affected_mask |= series.map(
            lambda item: isinstance(item, str) and resolved.get(item, item) != item
        )
        mapping[column] = resolved

    row_count = int(rows_affected_mask.sum())
    return {
        "global_rule": global_rule,
        "selected_columns": columns,
        "column_rules": {column: (column_rules or {}).get(column, global_rule) for column in columns},
        "value_overrides": overrides,
        "whitespace": whitespace_options,
        "standardize_address_suffixes": bool(standardize_address_suffixes),
        "canonical_values": mapping,
        "preview": pd.DataFrame(
            preview_rows,
            columns=["Column", "Original", "Default output", "Final output", "Rows"],
        ),
        "values_affected": changed_distinct_values,
        "cells_changed": changed_cells,
        "rows_affected": row_count,
        "manual_override_count": manual_override_count,
        "override_count": manual_override_count,
    }


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
        "normalize_text",
        "consolidate_category",
        "fill_numeric_missing",
        "fill_text_missing",
        "remediate_outliers",
    }
    affected_column_names: list[str] = []
    for action in actions:
        if action.get("type") == "normalize_text":
            text_columns = action.get("plan", {}).get("selected_columns", [])
            affected_column_names.extend(
                str(column) for column in text_columns
            )
        elif action.get("type") == "remove_columns":
            affected_column_names.extend(str(column) for column in action.get("columns", []))
        elif action.get("type") == "remediate_outliers":
            affected_column_names.extend(
                str(item["column"])
                for item in action.get("plan", {}).get("column_actions", [])
            )
        else:
            affected_column_names.append(str(action.get("column") or "All columns"))
    affected_columns = list(dict.fromkeys(affected_column_names))
    return {
        "selected_count": sum(
            int(action.get("plan", {}).get("selected_count", 1))
            if action.get("type") == "remediate_outliers"
            else 1
            for action in actions
        ),
        "affected_columns": affected_columns,
        "estimated_values_changed": sum(
            int(record.get("parameters", {}).get("affected_values", record["affected_rows"]))
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


def build_outlier_remediation_plan(
    df: pd.DataFrame,
    strategies: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Prepare explicit IQR actions per column without mutating the frame.

    Mean and median use only finite, non-outlier observations. Row positions
    are tracked internally so duplicate DataFrame index labels cannot inflate
    or duplicate the row-removal estimate.
    """
    from src.quality_checks import inspect_numeric_outliers

    findings = inspect_numeric_outliers(df)
    eligible = {item["column"]: item for item in findings["columns"]}
    column_actions: list[dict[str, Any]] = []
    removal_positions: set[int] = set()
    affected_positions: set[int] = set()
    affected_values = 0

    for column, choice in strategies.items():
        strategy = str(choice.get("strategy", "leave"))
        if strategy == "leave":
            continue
        negative_strategy = strategy in {
            "remove_negative_integers",
            "remove_negative_integer_outliers",
        }
        if column not in df.columns:
            raise ValueError(f"{column!r} is not an eligible IQR outlier column.")
        if strategy not in OUTLIER_REMEDIATION_STRATEGIES:
            raise ValueError(f"Unsupported outlier strategy: {strategy!r}.")

        series = df[column]
        finding = eligible.get(column)
        if negative_strategy:
            if is_bool_dtype(series.dtype) or not is_numeric_dtype(series.dtype):
                raise ValueError(f"{column!r} is not a numeric field.")
        elif finding is None:
            raise ValueError(f"{column!r} is not an eligible IQR outlier column.")
        values = pd.to_numeric(series, errors="coerce").to_numpy(
            dtype="float64", na_value=np.nan
        )
        finite = np.isfinite(values)
        lower = float(finding["lower_bound"]) if finding is not None else None
        upper = float(finding["upper_bound"]) if finding is not None else None
        if negative_strategy:
            negative_integers = finite & (values < 0) & (values == np.trunc(values))
            if strategy == "remove_negative_integers":
                mask = negative_integers
            elif finding is not None:
                mask = negative_integers & ((values < lower) | (values > upper))
            else:
                mask = np.zeros(len(values), dtype=bool)
        else:
            mask = finite & ((values < lower) | (values > upper))
        positions = np.flatnonzero(mask)
        if not len(positions):
            continue

        replacement: float | None = None
        replacement_method = ""
        non_outliers = values[finite & ~mask]
        if strategy in {"mean", "median"}:
            if not len(non_outliers):
                raise ValueError(
                    f"No finite non-outlier values are available for {strategy} replacement in {column!r}."
                )
            replacement = float(
                np.mean(non_outliers) if strategy == "mean" else np.median(non_outliers)
            )
            replacement_method = strategy
        elif strategy == "custom":
            raw_value = choice.get("value")
            if isinstance(raw_value, (bool, np.bool_)):
                raise ValueError("A custom outlier replacement must be numeric, not boolean.")
            try:
                replacement = float(raw_value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"Enter a numeric replacement value for {column!r}.") from error
            if not math.isfinite(replacement):
                raise ValueError("A custom outlier replacement must be finite.")
            replacement_method = "custom"
        elif strategy == "cap":
            replacement_method = "nearest IQR boundary"

        selected_positions = {int(position) for position in positions}
        affected_positions.update(selected_positions)
        removes_rows = strategy in {
            "remove_rows",
            "remove_negative_integers",
            "remove_negative_integer_outliers",
        }
        if removes_rows:
            removal_positions.update(selected_positions)
        affected_values += len(positions)

        if strategy == "cap":
            replacements = [
                lower if values[position] < lower else upper
                for position in positions[:5]
            ]
        elif replacement is not None:
            replacements = [replacement] * min(5, len(positions))
        elif strategy == "blank":
            replacements = ["(missing)"] * min(5, len(positions))
        else:
            replacements = ["(row removed)"] * min(5, len(positions))
        examples = [
            {
                "column": str(column),
                "row_position": int(position) + 1,
                "before": _safe_value(series.iloc[position]),
                "after": after,
            }
            for position, after in zip(positions[:5], replacements)
        ]
        column_actions.append(
            {
                "column": str(column),
                "strategy": strategy,
                "outlier_count": int(len(positions)),
                "outlier_percentage": (
                    float(finding["outlier_percentage"])
                    if finding is not None and not negative_strategy
                    else float(len(positions) / int(finite.sum()) * 100)
                ),
                "lower_bound": lower,
                "upper_bound": upper,
                "replacement_method": replacement_method,
                "replacement_value": replacement,
                "rows_affected": int(len(positions)),
                "rows_removed": int(len(positions)) if removes_rows else 0,
                "criteria": (
                    "negative_integer_values"
                    if strategy == "remove_negative_integers"
                    else "negative_integer_iqr_outliers"
                    if strategy == "remove_negative_integer_outliers"
                    else "iqr_outliers"
                ),
                "examples": examples,
            }
        )

    unique_rows_removed = len(removal_positions)
    return {
        "column_actions": column_actions,
        "selected_count": len(column_actions),
        "affected_values": affected_values,
        "unique_rows_affected": len(affected_positions),
        "unique_rows_removed": unique_rows_removed,
        "overlap_rows_removed": max(
            0, sum(item["rows_removed"] for item in column_actions) - unique_rows_removed
        ),
        "preview_shape": [len(df.index) - unique_rows_removed, len(df.columns)],
    }


def apply_outlier_remediation_plan(
    df: pd.DataFrame, plan: dict[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply an approved multi-column IQR plan to a defensive working copy."""
    actions = list(plan.get("column_actions", []))
    if not actions:
        raise ValueError("The outlier remediation plan has no selected actions.")

    result = df.copy(deep=True)
    removal_mask = np.zeros(len(df.index), dtype=bool)
    touched_positions: set[int] = set()
    aggregate_examples: list[dict[str, Any]] = []
    total_values = 0
    ledger_columns: list[dict[str, Any]] = []

    for item in actions:
        column = item["column"]
        if column not in df.columns:
            raise ValueError(f"Column {column!r} no longer exists.")
        series = df[column]
        values = pd.to_numeric(series, errors="coerce").to_numpy(
            dtype="float64", na_value=np.nan
        )
        strategy = item["strategy"]
        finite = np.isfinite(values)
        if strategy in {
            "remove_negative_integers",
            "remove_negative_integer_outliers",
        }:
            negative_integers = finite & (values < 0) & (values == np.trunc(values))
            if strategy == "remove_negative_integers":
                mask = negative_integers
            else:
                lower = item.get("lower_bound")
                upper = item.get("upper_bound")
                if lower is None or upper is None:
                    raise ValueError("Negative integer outlier bounds are missing from the approved plan.")
                lower = float(lower)
                upper = float(upper)
                mask = negative_integers & ((values < lower) | (values > upper))
        else:
            lower = float(item["lower_bound"])
            upper = float(item["upper_bound"])
            mask = finite & ((values < lower) | (values > upper))
        positions = np.flatnonzero(mask)
        if len(positions) != int(item["outlier_count"]):
            raise ValueError(
                f"The numeric findings for {column!r} changed after the plan was prepared. Review the plan again."
            )
        touched_positions.update(int(position) for position in positions)
        total_values += len(positions)

        if strategy in {
            "remove_rows",
            "remove_negative_integers",
            "remove_negative_integer_outliers",
        }:
            removal_mask[positions] = True
        elif strategy == "blank":
            if is_extension_array_dtype(series.dtype):
                result[column] = series.mask(mask, pd.NA)
            elif is_integer_dtype(series.dtype):
                result[column] = series.convert_dtypes().mask(mask, pd.NA)
            else:
                result[column] = series.astype("float64").mask(mask, np.nan)
        elif strategy in {"mean", "median", "custom"}:
            replacement = float(item["replacement_value"])
            if not math.isfinite(replacement):
                raise ValueError("Outlier replacement values must be finite.")
            if is_integer_dtype(series.dtype) and not replacement.is_integer():
                result[column] = series.astype("Float64").mask(mask, replacement)
            else:
                result[column] = series.mask(mask, replacement)
        elif strategy == "cap":
            capped = values.copy()
            capped[mask & (values < lower)] = lower
            capped[mask & (values > upper)] = upper
            result[column] = pd.Series(capped, index=series.index, name=series.name)
        else:
            raise ValueError(f"Unsupported outlier strategy: {strategy!r}.")

        examples = deepcopy(item.get("examples", []))
        if len(aggregate_examples) < 10:
            aggregate_examples.extend(examples[: 10 - len(aggregate_examples)])
        ledger_columns.append(
            {
                key: item.get(key)
                for key in (
                    "column", "strategy", "outlier_count", "outlier_percentage",
                    "lower_bound", "upper_bound", "replacement_method", "replacement_value",
                    "rows_affected", "rows_removed", "criteria",
                )
            }
        )

    unique_rows_removed = int(removal_mask.sum())
    for example in aggregate_examples:
        if removal_mask[int(example["row_position"]) - 1]:
            example["after"] = "(row removed by selected numeric action)"
    if unique_rows_removed:
        result = result.iloc[np.flatnonzero(~removal_mask)].copy(deep=True)

    record = _ledger_record(
        {
            "type": "remediate_outliers",
            "column": ", ".join(item["column"] for item in actions),
        },
        df,
        result,
        len(touched_positions),
        "Applied the approved per-column numeric remediation to the working copy.",
        aggregate_examples,
        {
            "columns": ledger_columns,
            "affected_values": total_values,
            "unique_rows_removed": unique_rows_removed,
            "rows_removed_by_column_total": sum(item["rows_removed"] for item in actions),
            "overlap_rows_removed": max(
                0, sum(item["rows_removed"] for item in actions) - unique_rows_removed
            ),
        },
    )
    return result, record


def apply_text_normalisation_plan(
    df: pd.DataFrame, plan: dict[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply a previously previewed lexical plan to a new working-copy frame."""
    result = df.copy(deep=True)
    selected_columns = list(plan.get("selected_columns", []))
    canonical_values = plan.get("canonical_values", {})
    if any(column not in df.columns for column in selected_columns):
        raise ValueError("A selected text-normalisation column no longer exists.")

    changed_cells = 0
    changed_rows = pd.Series(False, index=df.index, dtype=bool)
    examples: list[dict[str, Any]] = []
    for column in selected_columns:
        before = df[column]
        mapping = canonical_values.get(column, {})
        after = before.astype(object).map(
            lambda value: mapping.get(value, value) if isinstance(value, str) else value
        )
        changed_mask = before.map(
            lambda value: isinstance(value, str)
            and mapping.get(value, value) != value
        )
        changed_cells += int(changed_mask.sum())
        changed_rows |= changed_mask
        if len(examples) < 10:
            for original in before.loc[changed_mask].drop_duplicates().tolist():
                if len(examples) >= 10:
                    break
                examples.append(
                    {
                        "column": str(column),
                        "before": _safe_value(original),
                        "after": _safe_value(mapping.get(original, original)),
                    }
                )
        result[column] = after

    settings = {
        "global_rule": plan.get("global_rule", "Leave unchanged"),
        "selected_columns": selected_columns,
        "column_rules": plan.get("column_rules", {}),
        "whitespace": plan.get("whitespace", {}),
        "standardize_address_suffixes": bool(
            plan.get("standardize_address_suffixes", False)
        ),
        "manual_override_count": int(plan.get("manual_override_count", 0)),
        "value_overrides": plan.get("value_overrides", {}),
        "affected_values": int(plan.get("values_affected", 0)),
        "affected_cells": changed_cells,
        "affected_rows": int(changed_rows.sum()),
    }
    # Keep the ledger useful without letting a large manual mapping dominate it.
    override_items = [
        {"column": column, "original": original, **deepcopy(override)}
        for column, values in settings["value_overrides"].items()
        for original, override in values.items()
        if override.get("mode", "default") in {"custom", "rule"}
    ]
    settings["value_overrides"] = override_items[:200]
    settings["omitted_value_overrides"] = max(0, len(override_items) - 200)
    action = {"type": "normalize_text", "column": ", ".join(selected_columns)}
    record = _ledger_record(
        action,
        df,
        result,
        int(changed_rows.sum()),
        "Applied the approved text style and whitespace rules to the selected text columns.",
        examples,
        settings,
    )
    record["affected_cells"] = changed_cells
    return result, record


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
    if action_type == "normalize_text":
        plan = action.get("plan")
        if not isinstance(plan, dict):
            raise ValueError("A previewed text-normalisation plan is required.")
        return apply_text_normalisation_plan(df, plan)

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
        if len(df.columns) <= 1:
            raise ValueError("At least one dataset column must remain.")
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

    elif action_type == "remove_columns":
        columns = list(dict.fromkeys(action.get("columns", [])))
        if not columns:
            raise ValueError("Select at least one column to remove.")
        missing_columns = [name for name in columns if name not in df.columns]
        if missing_columns:
            raise ValueError(
                "Column(s) no longer exist: " + ", ".join(map(str, missing_columns))
            )
        if len(columns) >= len(df.columns):
            raise ValueError("At least one dataset column must remain.")
        result = df.drop(columns=columns).copy(deep=True)
        record = _ledger_record(
            action,
            df,
            result,
            0,
            f"Removed {len(columns)} user-selected column(s) from the working copy.",
            [{"before": str(name), "after": "(column removed)"} for name in columns[:10]],
            {
                "columns_removed": [str(name) for name in columns],
                "columns_removed_count": len(columns),
                "columns_before": len(df.columns),
                "columns_after": len(result.columns),
            },
        )

    elif action_type == "remediate_outliers":
        plan = action.get("plan")
        if not isinstance(plan, dict) or not plan.get("column_actions"):
            raise ValueError("A previewed per-column outlier remediation plan is required.")
        result, record = apply_outlier_remediation_plan(df, plan)

    else:
        raise ValueError(f"Unsupported transformation: {action_type!r}.")

    return result, record
