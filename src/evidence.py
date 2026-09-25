"""Portable evidence tables and ZIP packs for TALOS inspections."""

from __future__ import annotations

from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pandas as pd


def build_structure_table(profile: dict[str, Any]) -> pd.DataFrame:
    """Return the visible TALOS profile as a stable export table."""
    return pd.DataFrame(
        profile.get("columns", []),
        columns=["column", "pandas_dtype", "talos_type"],
    ).rename(
        columns={
            "column": "Column",
            "pandas_dtype": "Pandas dtype",
            "talos_type": "TALOS type",
        }
    )


def build_missing_values_table(analysis: dict[str, Any]) -> pd.DataFrame:
    """Return the per-column missingness table, including columns with none."""
    rows = [
        {
            "Column": item["column"],
            "Pandas dtype": item["pandas_dtype"],
            "Missing count": item["missing_count"],
            "Missing percentage": round(float(item["missing_percentage"]), 2),
            "Severity": item["severity"],
            "Explanation": item["explanation"],
        }
        for item in analysis.get("columns", [])
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "Column",
            "Pandas dtype",
            "Missing count",
            "Missing percentage",
            "Severity",
            "Explanation",
        ],
    )


def build_duplicate_rows_table(
    df: pd.DataFrame, analysis: dict[str, Any]
) -> pd.DataFrame:
    """Return every row participating in an exact-duplicate group."""
    used_names = set(map(str, df.columns))

    def unique_name(base: str) -> str:
        candidate = base
        suffix = 2
        while candidate in used_names:
            candidate = f"{base} ({suffix})"
            suffix += 1
        used_names.add(candidate)
        return candidate

    row_number_name = unique_name("TALOS source row (1-based)")
    role_name = unique_name("TALOS duplicate role")
    columns = [row_number_name, role_name, *map(str, df.columns)]
    if not df.shape[1] or not analysis.get("exact_duplicate_row_count"):
        return pd.DataFrame(columns=columns)

    duplicate_mask = df.duplicated(keep=False).to_numpy()
    first_copy_mask = df.duplicated(keep="first").to_numpy()
    positions = np.flatnonzero(duplicate_mask)
    duplicate_rows = df.iloc[positions].copy()
    duplicate_rows.insert(0, role_name, [
        "Repeated row" if first_copy_mask[position] else "First matching row"
        for position in positions
    ])
    duplicate_rows.insert(0, row_number_name, positions + 1)
    return duplicate_rows.reset_index(drop=True)


def build_identifier_findings_table(analysis: dict[str, Any]) -> pd.DataFrame:
    """Return the name-based identifier review signals and examples."""
    rows = []
    for item in analysis.get("identifier_candidates", []):
        examples = "; ".join(
            f"{value['value']} ({value['row_count']} rows)"
            for value in item.get("duplicate_values", [])
        )
        rows.append(
            {
                "Candidate identifier": item["column"],
                "Missing count": item["missing_count"],
                "Repeated values after first": item["duplicate_value_count"],
                "Distinct values": item["unique_count"],
                "Uniqueness percentage": round(float(item["uniqueness_percentage"]), 2),
                "Repeated value examples": examples,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "Candidate identifier",
            "Missing count",
            "Repeated values after first",
            "Distinct values",
            "Uniqueness percentage",
            "Repeated value examples",
        ],
    )


def _proposed_canonical(variants: list[dict[str, Any]]) -> str:
    """Pick the most common observed spelling, resolving ties consistently."""
    return min(
        variants,
        key=lambda item: (
            -int(item["count"]),
            int(str(item["value"]) != " ".join(str(item["value"]).split())),
            (
                0
                if str(item["value"]) == str(item["value"]).title()
                else 1
                if str(item["value"]).isupper()
                else 2
                if str(item["value"]).islower()
                else 3
            ),
            str(item["value"]).casefold(),
            str(item["value"]),
        ),
    )["value"]


def build_category_variants_table(analysis: dict[str, Any]) -> pd.DataFrame:
    """Return one row per observed spelling in each category-variant group."""
    rows = []
    for group in analysis.get("variant_groups", []):
        canonical = _proposed_canonical(group["variants"])
        for variant in group["variants"]:
            rows.append(
                {
                    "Column": group["column"],
                    "Normalized form": group["normalized_value"],
                    "Observed variant": variant["value"],
                    "Count": variant["count"],
                    "Proposed canonical value": canonical,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "Column",
            "Normalized form",
            "Observed variant",
            "Count",
            "Proposed canonical value",
        ],
    )


def build_outlier_rows_table(
    df: pd.DataFrame, analysis: dict[str, Any]
) -> pd.DataFrame:
    """Return every flagged numeric cell with its IQR evidence and source row."""
    columns = [
        "Source row (1-based)",
        "Column",
        "Value",
        "Q1",
        "Median",
        "Q3",
        "Lower bound",
        "Upper bound",
        "Outlier status",
    ]
    rows = []
    for item in analysis.get("columns", []):
        name = item["column"]
        if name not in df.columns:
            continue
        numeric_values = pd.to_numeric(df[name], errors="coerce").to_numpy(
            dtype="float64", na_value=np.nan
        )
        lower_bound = float(item["lower_bound"])
        upper_bound = float(item["upper_bound"])
        flagged_positions = np.flatnonzero(
            np.isfinite(numeric_values)
            & ((numeric_values < lower_bound) | (numeric_values > upper_bound))
        )
        for position in flagged_positions:
            value = float(numeric_values[position])
            rows.append(
                {
                    "Source row (1-based)": int(position + 1),
                    "Column": name,
                    "Value": value,
                    "Q1": float(item["q1"]),
                    "Median": float(item["median"]),
                    "Q3": float(item["q3"]),
                    "Lower bound": lower_bound,
                    "Upper bound": upper_bound,
                    "Outlier status": "Below lower bound" if value < lower_bound else "Above upper bound",
                }
            )
    return pd.DataFrame(rows, columns=columns)


def build_structural_findings_table(analysis: dict[str, Any]) -> pd.DataFrame:
    """Flatten structural observations without presenting them as errors."""
    rows = []
    for column in analysis.get("empty_columns", []):
        rows.append({"Column": column, "Finding type": "Empty column", "Explanation": "No non-missing values.", "Supporting metric": "0 usable values"})
    for item in analysis.get("constant_columns", []):
        rows.append({"Column": item["column"], "Finding type": "Constant column", "Explanation": "One distinct value may be intentional or redundant.", "Supporting metric": f"1 distinct value across {item['non_missing_count']} non-missing rows"})
    for item in analysis.get("high_cardinality_columns", []):
        rows.append({"Column": item["column"], "Finding type": "High-cardinality text", "Explanation": "This may be an identifier, free text, or a granular category.", "Supporting metric": f"{item['unique_count']} distinct of {item['non_missing_count']} ({item['uniqueness_percentage']:.1f}% unique)"})
    for item in analysis.get("identifier_columns", []):
        rows.append({"Column": item["column"], "Finding type": "Possible identifier", "Explanation": "Column name suggests an identifier; uniqueness is not assumed.", "Supporting metric": f"{item['duplicate_value_count']} repeated values; {item['missing_count']} missing; {item['uniqueness_percentage']:.1f}% unique"})
    for item in analysis.get("numeric_patterns", []):
        signals = []
        if item["negative_count"]:
            signals.append(f"{item['negative_count']} negative ({item['negative_percentage']:.1f}%)")
        if item["zero_percentage"] >= 80:
            signals.append(f"{item['zero_percentage']:.1f}% zeros")
        if signals:
            rows.append({"Column": item["column"], "Finding type": "Numeric pattern", "Explanation": "Negative or zero-heavy values may be valid in context.", "Supporting metric": "; ".join(signals)})
    return pd.DataFrame(
        rows,
        columns=["Column", "Finding type", "Explanation", "Supporting metric"],
    )


def build_integrity_score_table(analysis: dict[str, Any]) -> pd.DataFrame:
    """Return the explainable component breakdown for a score."""
    rows = [
        {
            "Component": item["component"],
            "Weight": item["weight"],
            "Component score": item["score"],
            "Weighted points": item["weighted_points"],
        }
        for item in analysis.get("components", [])
    ]
    return pd.DataFrame(
        rows,
        columns=["Component", "Weight", "Component score", "Weighted points"],
    )


def build_score_comparison_table(
    original_score: dict[str, Any], working_score: dict[str, Any]
) -> pd.DataFrame:
    """Compare score components without framing increases as proof of correctness."""
    original = {item["component"]: item for item in original_score.get("components", [])}
    working = {item["component"]: item for item in working_score.get("components", [])}
    rows = []
    for name in dict.fromkeys([*original, *working]):
        before = original.get(name, {})
        after = working.get(name, {})
        original_value = before.get("score")
        working_value = after.get("score")
        rows.append(
            {
                "Component": name,
                "Weight": before.get("weight", after.get("weight", 0)),
                "Original score": original_value,
                "Working-copy score": working_value,
                "Score change": (
                    round(float(working_value) - float(original_value), 1)
                    if original_value is not None and working_value is not None
                    else None
                ),
                "Original weighted points": before.get("weighted_points"),
                "Working-copy weighted points": after.get("weighted_points"),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "Component",
            "Weight",
            "Original score",
            "Working-copy score",
            "Score change",
            "Original weighted points",
            "Working-copy weighted points",
        ],
    )


def build_comparison_table(
    original_df: pd.DataFrame,
    working_df: pd.DataFrame,
    original_findings: dict[str, Any],
    working_findings: dict[str, Any],
) -> pd.DataFrame:
    """Compare key source and working-copy measures using current inspections."""
    measures = [
        ("Rows", len(original_df.index), len(working_df.index)),
        ("Columns", len(original_df.columns), len(working_df.columns)),
        ("Missing cells", original_findings["missing"]["total_missing_cells"], working_findings["missing"]["total_missing_cells"]),
        ("Exact duplicate rows", original_findings["duplicates"]["exact_duplicate_row_count"], working_findings["duplicates"]["exact_duplicate_row_count"]),
        ("Category variant groups", original_findings["categories"]["inconsistent_group_count"], working_findings["categories"]["inconsistent_group_count"]),
        ("IQR outlier values", original_findings["outliers"]["total_outlier_values"], working_findings["outliers"]["total_outlier_values"]),
        ("Empty columns", len(original_findings["structure"]["empty_columns"]), len(working_findings["structure"]["empty_columns"])),
        ("Integrity score", original_findings["score"]["score"], working_findings["score"]["score"]),
    ]
    return pd.DataFrame(
        [
            {
                "Measure": label,
                "Original": "Not assessable" if before is None else before,
                "Working copy": "Not assessable" if after is None else after,
            }
            for label, before, after in measures
        ]
    )


def build_result_tables(
    df: pd.DataFrame,
    profile: dict[str, Any],
    findings: dict[str, Any],
) -> dict[str, pd.DataFrame]:
    """Build all applicable result tables with clear, stable filenames."""
    tables = {
        "structure.csv": build_structure_table(profile),
        "missing_values.csv": build_missing_values_table(findings["missing"]),
        "duplicate_rows.csv": build_duplicate_rows_table(df, findings["duplicates"]),
        "identifier_findings.csv": build_identifier_findings_table(findings["duplicates"]),
        "category_variants.csv": build_category_variants_table(findings["categories"]),
        "outliers.csv": build_outlier_rows_table(df, findings["outliers"]),
        "structural_findings.csv": build_structural_findings_table(findings["structure"]),
        "integrity_score.csv": build_integrity_score_table(findings["score"]),
    }
    return {
        filename: table
        for filename, table in tables.items()
        if not table.empty
    }


def build_evidence_readme(
    source_filename: str,
    created_at: str,
    descriptions: dict[str, str],
) -> bytes:
    """Create the short manifest stored inside an evidence ZIP."""
    lines = [
        "TALOS EVIDENCE PACK",
        "===================",
        f"Source file: {source_filename}",
        f"Created: {created_at}",
        "",
        "The uploaded source was preserved. Approved transformations were applied only to a separate working copy.",
        "Findings are contextual signals under the documented TALOS checks, not proof of data correctness.",
        "",
        "FILES",
        "-----",
    ]
    lines.extend(f"{name}: {description}" for name, description in descriptions.items())
    lines.append("")
    return "\n".join(lines).encode("utf-8")


def build_evidence_pack(files: dict[str, bytes]) -> bytes:
    """Package applicable UTF-8 reports and CSVs into an in-memory ZIP."""
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for filename, contents in files.items():
            if not filename or "/" in filename or "\\" in filename or filename in {".", ".."}:
                raise ValueError(f"Unsafe evidence-pack path: {filename!r}.")
            archive.writestr(f"talos_evidence_pack/{filename}", contents)
    return buffer.getvalue()
