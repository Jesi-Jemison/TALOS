"""Read-only quality checks used by the TALOS inspection flow."""
# TALOS FILE VERSION: v1.2.0

import re
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype, is_object_dtype, is_string_dtype


MISSING_SEVERITY_THRESHOLDS = {
    "Minor": 5.0,
    "Review": 20.0,
    "Significant": 40.0,
}

IDENTIFIER_HINTS = {"id", "key", "code", "number", "uuid"}
FREE_TEXT_HINTS = {
    "address", "addresses", "comment", "comments", "description", "descriptions",
    "message", "messages", "note", "notes", "review", "reviews", "text",
}
MAX_CATEGORY_UNIQUE_VALUES = 50
MAX_CATEGORY_UNIQUE_RATIO = 0.8
MIN_HIGH_CARDINALITY_UNIQUE_VALUES = 10
MIN_OUTLIER_VALUES = 8
MIN_OUTLIER_UNIQUE_VALUES = 5
MIN_HIGH_CARDINALITY_ROWS = 20
HIGH_CARDINALITY_RATIO = 0.8
MIN_NUMERIC_PATTERN_VALUES = 5
ZERO_DOMINANCE_RATIO = 0.8


def _name_tokens(column_name: object) -> set[str]:
    """Split a column name into lowercase words for transparent heuristics."""
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(column_name))
    return set(re.findall(r"[a-z0-9]+", name.lower()))


def is_likely_identifier(column_name: object) -> bool:
    """Return whether a name hints that a column may contain identifiers.

    This is only a naming heuristic. It does not establish that values should
    be unique or that every matching column is truly an identifier.
    """
    tokens = _name_tokens(column_name)
    return bool(tokens & IDENTIFIER_HINTS)


def classify_missing_severity(missing_percentage: float) -> str:
    """Assign a readable severity label using the central TALOS thresholds."""
    if missing_percentage <= 0:
        return "Clear"
    if missing_percentage <= MISSING_SEVERITY_THRESHOLDS["Minor"]:
        return "Minor"
    if missing_percentage <= MISSING_SEVERITY_THRESHOLDS["Review"]:
        return "Review"
    if missing_percentage <= MISSING_SEVERITY_THRESHOLDS["Significant"]:
        return "Significant"
    return "Critical"


def _missing_explanation(column_name: object, dtype: object) -> str:
    """Explain a possible effect without assuming the column's business role."""
    tokens = _name_tokens(column_name)

    if is_likely_identifier(column_name):
        return "Missing values in a possible identifier may affect record matching or joins."
    if tokens & {"date", "time", "timestamp", "created", "updated"}:
        return "Missing dates or times may affect time-based analysis."
    if is_numeric_dtype(dtype) and not is_bool_dtype(dtype):
        return "Missing numeric values may affect totals, averages, or other aggregates."
    return "Missing categories or text may reduce the rows available for segmentation."


def inspect_missing_values(df: pd.DataFrame) -> dict[str, object]:
    """Summarise missing cells and per-column severity without changing data."""
    row_count, column_count = df.shape
    total_cells = row_count * column_count
    total_missing_cells = int(df.isna().to_numpy().sum())
    missing_percentage = (
        total_missing_cells / total_cells * 100 if total_cells else 0.0
    )
    column_results = []

    for column_name, series in df.items():
        missing_count = int(series.isna().sum())
        column_percentage = missing_count / row_count * 100 if row_count else 0.0
        column_results.append(
            {
                "column": str(column_name),
                "pandas_dtype": str(series.dtype),
                "missing_count": missing_count,
                "missing_percentage": column_percentage,
                "severity": classify_missing_severity(column_percentage),
                "explanation": _missing_explanation(column_name, series.dtype),
            }
        )

    column_results.sort(
        key=lambda item: (-item["missing_percentage"], item["column"].casefold())
    )
    severity_counts = {
        label: sum(item["severity"] == label for item in column_results)
        for label in ("Clear", "Minor", "Review", "Significant", "Critical")
    }

    return {
        "total_rows": row_count,
        "total_columns": column_count,
        "total_cells": total_cells,
        "total_missing_cells": total_missing_cells,
        "missing_percentage": missing_percentage,
        "affected_column_count": sum(
            item["missing_count"] > 0 for item in column_results
        ),
        "clear_column_count": severity_counts["Clear"],
        "severity_counts": severity_counts,
        "columns": column_results,
    }


def inspect_duplicates(df: pd.DataFrame) -> dict[str, object]:
    """Find exact duplicate rows and repeated values in likely ID columns.

    Identifier candidates come from column names only. Repeated values are
    reported for review; this function does not assume uniqueness is required.
    The returned sample DataFrame is a copy, so the source is never modified.
    """
    row_count = len(df.index)
    if df.shape[1]:
        duplicate_row_mask = df.duplicated(keep="first")
        all_duplicate_rows_mask = df.duplicated(keep=False)
    else:
        # Without columns, rows cannot be compared as records.
        duplicate_row_mask = pd.Series(False, index=df.index)
        all_duplicate_rows_mask = pd.Series(False, index=df.index)
    duplicate_row_count = int(duplicate_row_mask.sum())
    identifier_results = []

    for column_name in df.columns:
        if not is_likely_identifier(column_name):
            continue

        series = df[column_name]
        non_missing = series.dropna()
        value_counts = non_missing.value_counts()
        repeated_values = value_counts[value_counts > 1]
        unique_count = int(non_missing.nunique())
        non_missing_count = len(non_missing)
        duplicate_value_count = int(non_missing.duplicated(keep="first").sum())
        duplicate_value_examples = [
            {"value": str(value), "row_count": int(count)}
            for value, count in repeated_values.head(5).items()
        ]

        identifier_results.append(
            {
                "column": str(column_name),
                "non_missing_count": non_missing_count,
                "missing_count": int(series.isna().sum()),
                "unique_count": unique_count,
                "duplicate_value_count": duplicate_value_count,
                "uniqueness_percentage": (
                    unique_count / non_missing_count * 100 if non_missing_count else 0.0
                ),
                "duplicate_values": duplicate_value_examples,
            }
        )

    return {
        "row_count": row_count,
        "exact_duplicate_row_count": duplicate_row_count,
        "exact_duplicate_percentage": (
            duplicate_row_count / row_count * 100 if row_count else 0.0
        ),
        "exact_duplicate_sample": df.loc[all_duplicate_rows_mask].head(5).copy(),
        "identifier_candidates": identifier_results,
        "identifier_candidate_count": len(identifier_results),
        "identifier_candidates_with_repeats": sum(
            item["duplicate_value_count"] > 0 for item in identifier_results
        ),
    }


def _is_text_series(series: pd.Series) -> bool:
    """Return whether a column contains text suitable for category review."""
    if is_object_dtype(series.dtype) or is_string_dtype(series.dtype):
        return True
    if isinstance(series.dtype, pd.CategoricalDtype):
        return all(isinstance(value, str) for value in series.cat.categories)
    return False


def _is_free_text_name(column_name: object) -> bool:
    """Identify common name and free-text column names that need caution."""
    tokens = _name_tokens(column_name)
    return bool(tokens & (FREE_TEXT_HINTS | {"name", "firstname", "lastname"}))


def _normalise_category(value: object) -> str:
    """Trim outer whitespace, collapse internal spaces, and case-fold text."""
    return " ".join(str(value).split()).casefold()


def inspect_category_consistency(df: pd.DataFrame) -> dict[str, object]:
    """Find likely text categories that differ only by case or whitespace.

    Likely names and free-text fields are skipped, as are columns with more
    than 50 values, or at least 10 unique values with a unique-value ratio
    above 80 percent. No values are merged or changed.
    """
    checked_columns = []
    skipped_columns = []
    variant_groups = []
    normalized_group_count = 0
    variant_occurrence_count = 0

    for column_name, series in df.items():
        if not _is_text_series(series):
            continue

        values = series.dropna()
        unique_count = int(values.nunique())
        non_missing_count = len(values)

        if _is_free_text_name(column_name):
            skipped_columns.append(
                {"column": str(column_name), "reason": "Name or free-text field"}
            )
            continue
        if unique_count < 2:
            skipped_columns.append(
                {"column": str(column_name), "reason": "Fewer than two distinct values"}
            )
            continue
        unique_ratio = unique_count / non_missing_count if non_missing_count else 0.0
        is_mostly_unique = (
            unique_count >= MIN_HIGH_CARDINALITY_UNIQUE_VALUES
            and unique_ratio > MAX_CATEGORY_UNIQUE_RATIO
        )
        if unique_count > MAX_CATEGORY_UNIQUE_VALUES or is_mostly_unique:
            skipped_columns.append(
                {"column": str(column_name), "reason": "High cardinality or mostly unique values"}
            )
            continue

        checked_columns.append(str(column_name))
        grouped_counts: dict[str, Counter[str]] = defaultdict(Counter)
        for value in values:
            grouped_counts[_normalise_category(value)][str(value)] += 1

        normalized_group_count += len(grouped_counts)
        for normalized_value, original_counts in grouped_counts.items():
            if len(original_counts) < 2:
                continue

            variants = [
                {"value": value, "count": count}
                for value, count in sorted(
                    original_counts.items(), key=lambda item: item[0].casefold()
                )
            ]
            variant_occurrence_count += sum(item["count"] for item in variants)
            variant_groups.append(
                {
                    "column": str(column_name),
                    "normalized_value": normalized_value,
                    "variants": variants,
                }
            )

    return {
        "checked_columns": checked_columns,
        "skipped_columns": skipped_columns,
        "normalized_group_count": normalized_group_count,
        "inconsistent_group_count": len(variant_groups),
        "column_count_with_variants": len({item["column"] for item in variant_groups}),
        "variant_occurrence_count": variant_occurrence_count,
        "variant_groups": variant_groups,
    }


def inspect_numeric_outliers(df: pd.DataFrame) -> dict[str, object]:
    """Flag potential numeric outliers with the IQR rule, without changing data.

    Boolean and likely identifier fields are excluded. A numeric column must
    have at least eight finite values and at least five distinct values to be
    considered. These rules reduce misleading results on tiny or categorical
    fields; they do not establish that a flagged value is incorrect.
    """
    column_results = []
    skipped_columns = []
    total_eligible_values = 0
    total_outlier_values = 0

    for column_name, series in df.items():
        if is_bool_dtype(series.dtype):
            skipped_columns.append(
                {"column": str(column_name), "reason": "Boolean field"}
            )
            continue
        if not is_numeric_dtype(series.dtype):
            continue
        if is_likely_identifier(column_name):
            skipped_columns.append(
                {"column": str(column_name), "reason": "Possible identifier field"}
            )
            continue

        finite_values = series.dropna()
        finite_mask = finite_values.map(np.isfinite)
        values = finite_values[finite_mask]
        usable_count = len(values)
        unique_count = int(values.nunique())

        if usable_count < MIN_OUTLIER_VALUES:
            skipped_columns.append(
                {"column": str(column_name), "reason": "Fewer than 8 usable numeric values"}
            )
            continue
        if unique_count < MIN_OUTLIER_UNIQUE_VALUES:
            skipped_columns.append(
                {"column": str(column_name), "reason": "Low-variation numeric field"}
            )
            continue

        first_quartile = float(values.quantile(0.25))
        median = float(values.median())
        third_quartile = float(values.quantile(0.75))
        interquartile_range = third_quartile - first_quartile
        lower_bound = first_quartile - 1.5 * interquartile_range
        upper_bound = third_quartile + 1.5 * interquartile_range
        outlier_mask = (values < lower_bound) | (values > upper_bound)
        outlier_values = values[outlier_mask]
        outlier_count = len(outlier_values)

        total_eligible_values += usable_count
        total_outlier_values += outlier_count
        column_results.append(
            {
                "column": str(column_name),
                "usable_value_count": usable_count,
                "q1": first_quartile,
                "median": median,
                "q3": third_quartile,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
                "outlier_count": outlier_count,
                "outlier_percentage": outlier_count / usable_count * 100,
                "sample_values": [value.item() if hasattr(value, "item") else value for value in outlier_values.head(5)],
            }
        )

    column_results.sort(
        key=lambda item: (-item["outlier_percentage"], item["column"].casefold())
    )
    return {
        "eligible_column_count": len(column_results),
        "total_eligible_values": total_eligible_values,
        "total_outlier_values": total_outlier_values,
        "outlier_percentage": (
            total_outlier_values / total_eligible_values * 100
            if total_eligible_values
            else 0.0
        ),
        "columns": column_results,
        "skipped_columns": skipped_columns,
    }


def inspect_structure(df: pd.DataFrame) -> dict[str, object]:
    """Report empty, constant, high-cardinality, ID, and numeric patterns.

    These are review signals, not proof of incorrect data. The function only
    reads the DataFrame and returns summaries; it does not change any values.
    """
    empty_columns = []
    constant_columns = []
    high_cardinality_columns = []
    identifier_columns = []
    numeric_patterns = []

    for column_name, series in df.items():
        name = str(column_name)
        non_missing = series.dropna()
        non_missing_count = len(non_missing)
        unique_count = int(non_missing.nunique())

        if non_missing_count == 0:
            empty_columns.append(name)
        elif unique_count == 1:
            constant_columns.append(
                {
                    "column": name,
                    "non_missing_count": non_missing_count,
                    "unique_count": unique_count,
                }
            )

        if _is_text_series(series) and non_missing_count >= MIN_HIGH_CARDINALITY_ROWS:
            uniqueness_percentage = unique_count / non_missing_count * 100
            if uniqueness_percentage > HIGH_CARDINALITY_RATIO * 100:
                high_cardinality_columns.append(
                    {
                        "column": name,
                        "unique_count": unique_count,
                        "non_missing_count": non_missing_count,
                        "uniqueness_percentage": uniqueness_percentage,
                    }
                )

        if is_likely_identifier(column_name):
            duplicate_value_count = int(non_missing.duplicated(keep="first").sum())
            identifier_columns.append(
                {
                    "column": name,
                    "missing_count": int(series.isna().sum()),
                    "non_missing_count": non_missing_count,
                    "unique_count": unique_count,
                    "duplicate_value_count": duplicate_value_count,
                    "uniqueness_percentage": (
                        unique_count / non_missing_count * 100 if non_missing_count else 0.0
                    ),
                }
            )

        if (
            is_bool_dtype(series.dtype)
            or not is_numeric_dtype(series.dtype)
            or is_likely_identifier(column_name)
        ):
            continue

        finite_values = non_missing[non_missing.map(np.isfinite)]
        if len(finite_values) < MIN_NUMERIC_PATTERN_VALUES:
            continue

        negative_count = int((finite_values < 0).sum())
        zero_count = int((finite_values == 0).sum())
        zero_percentage = zero_count / len(finite_values) * 100
        if negative_count or zero_percentage >= ZERO_DOMINANCE_RATIO * 100:
            numeric_patterns.append(
                {
                    "column": name,
                    "usable_value_count": len(finite_values),
                    "negative_count": negative_count,
                    "negative_percentage": negative_count / len(finite_values) * 100,
                    "zero_count": zero_count,
                    "zero_percentage": zero_percentage,
                }
            )

    return {
        "empty_columns": empty_columns,
        "constant_columns": constant_columns,
        "high_cardinality_columns": high_cardinality_columns,
        "identifier_columns": identifier_columns,
        "numeric_patterns": numeric_patterns,
    }
