"""Streamlit-independent TALOS dataset workflow and export helpers.

The Streamlit app and Python callers share the same inspection, transformation,
reporting, and evidence functions. This module owns only the glue between those
existing components; it contains no widgets, session state, or UI rendering.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
import uuid

import pandas as pd

from src.evidence import (
    build_comparison_table,
    build_evidence_pack,
    build_evidence_readme,
    build_result_tables,
    build_score_comparison_table,
)
from src.profiler import identify_column_types, load_csv, profile_dataset
from src.quality_checks import (
    inspect_category_consistency,
    inspect_duplicates,
    inspect_missing_values,
    inspect_numeric_outliers,
    inspect_structure,
)
from src.reporting import (
    build_cleaned_csv,
    build_inspection_report_html,
    build_inspection_report_pdf,
    build_transformation_log,
)
from src.scoring import calculate_integrity_score
from src.transformations import (
    TEXT_NORMALISATION_RULES,
    append_ledger_record,
    apply_transformations,
    build_repair_plan,
    build_text_normalisation_plan,
    create_working_copy,
    recommend_text_normalisation_columns,
    reset_working_copy,
)


def inspect_dataset(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Run all current read-only TALOS checks and calculate the integrity score.

    This is the shared inspection entry point for Streamlit and standalone use.
    The supplied DataFrame is read only and is never modified.
    """
    findings: dict[str, dict[str, Any]] = {
        "missing": inspect_missing_values(df),
        "duplicates": inspect_duplicates(df),
        "categories": inspect_category_consistency(df),
        "outliers": inspect_numeric_outliers(df),
        "structure": inspect_structure(df),
    }
    findings["score"] = calculate_integrity_score(
        df,
        findings["missing"],
        findings["duplicates"],
        findings["categories"],
        findings["outliers"],
        findings["structure"],
    )
    return findings


def summarize_dataset(
    df: pd.DataFrame, findings: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Collect the compact metrics used by reports and standalone summaries."""
    structure = findings["structure"]
    signal_groups = (
        "empty_columns",
        "constant_columns",
        "high_cardinality_columns",
        "identifier_columns",
        "numeric_patterns",
    )
    return {
        "row_count": len(df.index),
        "column_count": len(df.columns),
        "missing_cells": findings["missing"]["total_missing_cells"],
        "duplicate_rows": findings["duplicates"]["exact_duplicate_row_count"],
        "category_variant_groups": findings["categories"]["inconsistent_group_count"],
        "outlier_values": findings["outliers"]["total_outlier_values"],
        "empty_columns": len(structure["empty_columns"]),
        "structural_signals": sum(len(structure.get(key, [])) for key in signal_groups),
        "score": findings["score"]["score"],
    }


def _normalise_rule(rule: str) -> str:
    """Accept concise Python-facing rule names and TALOS's existing labels."""
    aliases = {
        "unchanged": "Leave unchanged",
        "leave unchanged": "Leave unchanged",
        "lower": "lowercase",
        "lowercase": "lowercase",
        "upper": "UPPERCASE",
        "uppercase": "UPPERCASE",
        "proper": "Proper Case",
        "title": "Proper Case",
        "proper case": "Proper Case",
        "sentence": "Sentence case",
        "sentence case": "Sentence case",
        "camel": "camelCase",
        "camelcase": "camelCase",
        "snake": "snake_case",
        "snake_case": "snake_case",
    }
    try:
        result = aliases[str(rule).casefold()]
    except KeyError as exc:
        if rule in TEXT_NORMALISATION_RULES:
            return rule
        raise ValueError(
            f"Unsupported text normalisation rule {rule!r}. "
            f"Choose one of: {', '.join(TEXT_NORMALISATION_RULES)}."
        ) from exc
    return result


def _plan_examples(records: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """Flatten ledger examples into one small, readable preview table."""
    rows: list[dict[str, Any]] = []
    for record in records:
        for example in record.get("before_after", []):
            row = {"Operation": record.get("transformation_type", "")}
            if isinstance(example, Mapping):
                if "column" in example:
                    row["Column"] = example["column"]
                    row.update({key: value for key, value in example.items() if key != "column"})
                else:
                    row["Column"] = record.get("column", "")
                    row.update(example)
            rows.append(row)
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class TransformationPlan:
    """Immutable preview metadata for a single TALOS apply operation.

    ``examples`` returns a copy so editing the displayed preview cannot alter
    the approved action. Plans are tied to both their creating session and its
    current data revision; a plan cannot be applied twice or to another state.
    """

    operation: str
    target_columns: tuple[str, ...]
    parameters: Mapping[str, Any]
    affected_rows: int
    affected_values: int
    affected_cells: int
    rows_removed: int
    columns_removed: int
    warnings: tuple[str, ...]
    _actions: tuple[dict[str, Any], ...] = field(repr=False)
    _examples: pd.DataFrame = field(repr=False)
    _owner_token: str = field(repr=False)
    _base_revision: int = field(repr=False)

    @property
    def examples(self) -> pd.DataFrame:
        """Return a copy of the before/after examples for review."""
        return self._examples.copy(deep=True)

    @property
    def actions(self) -> tuple[dict[str, Any], ...]:
        """Return copies of the approved actions for inspection."""
        return tuple(deepcopy(self._actions))

    def summary(self) -> str:
        """Render the preview as a compact terminal-friendly string."""
        operation_label = self.operation.replace("_", " ").title()
        targets = ", ".join(self.target_columns) or "All columns"
        lines = [
            "TALOS TRANSFORMATION PREVIEW",
            "-----------------------------",
            f"Operation:          {operation_label}",
            f"Target columns:     {targets}",
            f"Rows affected:      {self.affected_rows:,} (cumulative per action)",
            f"Values affected:    {self.affected_values:,}",
            f"Cells affected:     {self.affected_cells:,} (cumulative per action)",
        ]
        if self.rows_removed:
            lines.append(f"Rows removed:       {self.rows_removed:,}")
        if self.columns_removed:
            lines.append(f"Columns removed:    {self.columns_removed:,}")
        if self.warnings:
            lines.append("Review notes:")
            lines.extend(f"  - {warning}" for warning in self.warnings)
        return "\n".join(lines)


class TalosSession:
    """Manage an original dataset and an explicitly transformed working copy.

    Use :meth:`from_csv` or :meth:`from_dataframe` to create a session. Findings
    are calculated only when :meth:`inspect` is called. Transformation previews
    are read only; :meth:`apply` is the only operation that changes the working
    copy. Call :meth:`reinspect` after applying changes before relying on current
    working-copy findings or exporting comparison reports.
    """

    def __init__(
        self,
        dataframe: pd.DataFrame,
        *,
        source_filename: str = "dataframe.csv",
        source_size_bytes: int | None = None,
    ) -> None:
        """Create a session from a copied DataFrame.

        Args:
            dataframe: The source values. TALOS copies the frame before keeping it.
            source_filename: Display name used in reports and export filenames.
            source_size_bytes: Original CSV byte size when loaded from a file.
                DataFrame inputs use their CSV serialization size when omitted.

        Raises:
            TypeError: If ``dataframe`` is not a pandas DataFrame.
        """
        if not isinstance(dataframe, pd.DataFrame):
            raise TypeError("dataframe must be a pandas DataFrame.")
        self._original_df = create_working_copy(dataframe)
        self._working_df = create_working_copy(self._original_df)
        self.source_filename = Path(str(source_filename)).name or "dataframe.csv"
        self._source_size_bytes = (
            len(build_cleaned_csv(self._original_df))
            if source_size_bytes is None
            else int(source_size_bytes)
        )
        self.profile: dict[str, Any] = profile_dataset(
            self._original_df, self.source_filename, self._source_size_bytes
        )
        self.revision = 0
        self._session_token = uuid.uuid4().hex
        self._original_findings: dict[str, dict[str, Any]] | None = None
        self._working_findings: dict[str, dict[str, Any]] | None = None
        self._inspected_revision: int | None = None
        self._transformation_ledger: list[dict[str, Any]] = []

    @classmethod
    def from_csv(cls, path: str | Path) -> TalosSession:
        """Load a CSV file using TALOS's existing UTF-8/Latin-1 reader.

        Args:
            path: Path to a CSV file.

        Returns:
            A session whose source filename and byte size reflect the input.

        Raises:
            OSError: If the file cannot be read.
            ValueError: If the input is empty or cannot be parsed as CSV.
        """
        csv_path = Path(path)
        file_contents = csv_path.read_bytes()
        dataframe = load_csv(file_contents)
        return cls(
            dataframe,
            source_filename=csv_path.name,
            source_size_bytes=len(file_contents),
        )

    @classmethod
    def from_dataframe(
        cls, dataframe: pd.DataFrame, *, filename: str = "dataframe.csv"
    ) -> TalosSession:
        """Create a session from a DataFrame without mutating the caller's frame.

        The source and working copies use pandas deep-copy semantics. As with
        pandas itself, Python objects nested inside object-dtype cells are not
        recursively copied; normal scalar CSV values are fully independent.
        """
        return cls(dataframe, source_filename=filename)

    @property
    def original_df(self) -> pd.DataFrame:
        """Return a defensive DataFrame copy of the preserved source."""
        return self._original_df.copy(deep=True)

    @property
    def working_df(self) -> pd.DataFrame:
        """Return a defensive DataFrame copy of the current working state."""
        return self._working_df.copy(deep=True)

    @property
    def original_findings(self) -> dict[str, dict[str, Any]] | None:
        """Return source findings, or ``None`` until the first inspection."""
        return deepcopy(self._original_findings)

    @property
    def working_findings(self) -> dict[str, dict[str, Any]] | None:
        """Return current working findings, or ``None`` while stale/uninspected."""
        if self._inspected_revision != self.revision:
            return None
        return deepcopy(self._working_findings)

    @property
    def transformation_ledger(self) -> list[dict[str, Any]]:
        """Return a copy of the ordered approved transformation records."""
        return deepcopy(self._transformation_ledger)

    @property
    def integrity_score(self) -> int | float | None:
        """Return the original dataset's score, or ``None`` before inspection."""
        if self._original_findings is None:
            return None
        return self._original_findings["score"]["score"]

    @property
    def working_integrity_score(self) -> int | float | None:
        """Return the current working score, or ``None`` if reinspection is due."""
        findings = self.working_findings
        return None if findings is None else findings["score"]["score"]

    @property
    def needs_reinspection(self) -> bool:
        """Whether current working-copy findings have not been refreshed."""
        return self._inspected_revision != self.revision

    def inspect(self) -> dict[str, dict[str, Any]]:
        """Inspect both source and working copies using the shared TALOS checks.

        Returns:
            A deep copy of the source findings. The same results are also
            available through ``original_findings`` and ``working_findings``.
        """
        self._original_findings = inspect_dataset(self._original_df)
        # The initial working copy is identical to the source. Reusing this
        # read-only result avoids doubling the first inspection cost.
        if self._working_df.equals(self._original_df):
            self._working_findings = deepcopy(self._original_findings)
        else:
            self._working_findings = inspect_dataset(self._working_df)
        self._inspected_revision = self.revision
        return deepcopy(self._original_findings)

    def reinspect(self) -> dict[str, dict[str, Any]]:
        """Re-run checks on the current working copy and refresh its score."""
        if self._original_findings is None:
            self._original_findings = inspect_dataset(self._original_df)
        self._working_findings = inspect_dataset(self._working_df)
        self._inspected_revision = self.revision
        return deepcopy(self._working_findings)

    def summary(self) -> str:
        """Return a concise terminal summary for source and working-copy state."""
        if self._original_findings is None:
            self.inspect()
        assert self._original_findings is not None
        original = summarize_dataset(self._original_df, self._original_findings)
        lines = [
            "TALOS DATASET INSPECTION",
            "------------------------",
            f"File:                 {self.source_filename}",
            f"Rows:                 {original['row_count']:,}",
            f"Columns:              {original['column_count']:,}",
            f"Integrity score:      {_format_score(original['score'], self._original_findings['score'].get('band'))}",
            f"Missing cells:        {original['missing_cells']:,}",
            f"Duplicate rows:       {original['duplicate_rows']:,}",
            f"Category variants:    {original['category_variant_groups']:,}",
            f"Outlier values:       {original['outlier_values']:,}",
            f"Structural signals:   {original['structural_signals']:,}",
        ]
        current = self.working_findings
        if current is None:
            if self._transformation_ledger:
                lines.extend(
                    [
                        "Working copy:         Reinspection needed after approved changes",
                        f"Approved actions:     {len(self._transformation_ledger):,}",
                    ]
                )
        elif self._transformation_ledger:
            working = summarize_dataset(self._working_df, current)
            lines.extend(
                [
                    "",
                    "WORKING COPY",
                    f"Integrity score:      {_format_score(working['score'], current['score'].get('band'))}",
                    f"Missing cells:        {working['missing_cells']:,}",
                    f"Duplicate rows:       {working['duplicate_rows']:,}",
                    f"Approved actions:     {len(self._transformation_ledger):,}",
                ]
            )
        return "\n".join(lines)

    def preview(
        self, actions: Mapping[str, Any] | Sequence[Mapping[str, Any]]
    ) -> TransformationPlan:
        """Preview one or more existing TALOS actions without changing state.

        Action dictionaries use the same ``type`` and parameters accepted by
        ``src.transformations.apply_transformation``. For example, whitespace
        cleanup uses ``{"type": "normalize_whitespace", "column": "region"}``.

        Raises:
            ValueError: If an action is unsupported or invalid for this dataset.
        """
        if isinstance(actions, Mapping):
            supplied_actions = [dict(actions)]
        else:
            supplied_actions = [dict(action) for action in actions]
        if not supplied_actions:
            raise ValueError("At least one transformation action is required.")
        action_copies = tuple(deepcopy(supplied_actions))
        repair_preview = build_repair_plan(self._working_df, list(action_copies))
        records = repair_preview["records"]
        operations = [str(action.get("type", "unknown")) for action in action_copies]
        operation = operations[0] if len(set(operations)) == 1 else "batch"
        targets: list[str] = []
        for action in action_copies:
            if action.get("type") == "normalize_text":
                selected = action.get("plan", {}).get("selected_columns", [])
                targets.extend(str(column) for column in selected)
            else:
                targets.append(str(action.get("column") or "All columns"))
        targets = list(dict.fromkeys(targets))
        affected_rows = sum(int(record.get("affected_rows", 0)) for record in records)
        affected_values = int(repair_preview["estimated_values_changed"])
        value_operations = {
            "normalize_whitespace",
            "normalize_text",
            "consolidate_category",
            "fill_numeric_missing",
            "fill_text_missing",
        }
        affected_cells = sum(
            int(record.get("affected_cells", record.get("affected_rows", 0)))
            for action, record in zip(action_copies, records)
            if action.get("type") in value_operations
        )
        warnings: list[str] = []
        if repair_preview["estimated_rows_removed"]:
            warnings.append("This plan removes rows from the working copy.")
        if repair_preview["estimated_columns_removed"]:
            warnings.append("This plan removes columns from the working copy.")
        if any(item in operations for item in ("fill_numeric_missing", "fill_text_missing")):
            warnings.append("Imputation changes missing values; review its business meaning before applying.")
        parameters = {
            "actions": [_public_action(action) for action in action_copies],
            "estimated_rows_removed": int(repair_preview["estimated_rows_removed"]),
            "estimated_columns_removed": int(repair_preview["estimated_columns_removed"]),
            "affected_cells": affected_cells,
        }
        return TransformationPlan(
            operation=operation,
            target_columns=tuple(targets),
            parameters=parameters,
            affected_rows=affected_rows,
            affected_values=affected_values,
            affected_cells=affected_cells,
            rows_removed=int(repair_preview["estimated_rows_removed"]),
            columns_removed=int(repair_preview["estimated_columns_removed"]),
            warnings=tuple(warnings),
            _actions=action_copies,
            _examples=_plan_examples(records),
            _owner_token=self._session_token,
            _base_revision=self.revision,
        )

    def preview_text_normalisation(
        self,
        *,
        columns: Sequence[str],
        default_rule: str = "Leave unchanged",
        column_rules: Mapping[str, str] | None = None,
        value_overrides: Mapping[str, Mapping[str, Any]] | None = None,
        trim_whitespace: bool = False,
        collapse_spaces: bool = False,
    ) -> TransformationPlan:
        """Build a non-mutating bulk text-normalisation preview.

        ``value_overrides`` accepts either direct mappings such as
        ``{"state": {"nsw": "NSW"}}`` or TALOS's explicit override records
        (``{"mode": "rule", "rule": "UPPERCASE"}``).
        """
        global_rule = _normalise_rule(default_rule)
        normalized_column_rules = {
            column: _normalise_rule(rule)
            for column, rule in (column_rules or {}).items()
        }
        converted_overrides: dict[str, dict[str, dict[str, str]]] = {}
        for column, mappings in (value_overrides or {}).items():
            converted_overrides[str(column)] = {}
            for observed_value, override in mappings.items():
                if isinstance(override, Mapping) and set(override).intersection(
                    {"mode", "rule", "value"}
                ):
                    mode = str(override.get("mode", "custom"))
                    if mode == "rule":
                        converted_overrides[str(column)][str(observed_value)] = {
                            "mode": "rule",
                            "rule": _normalise_rule(str(override.get("rule", default_rule))),
                        }
                    elif mode == "custom":
                        converted_overrides[str(column)][str(observed_value)] = {
                            "mode": "custom",
                            "value": str(override.get("value", "")),
                        }
                    elif mode == "default":
                        converted_overrides[str(column)][str(observed_value)] = {"mode": "default"}
                    else:
                        raise ValueError(f"Unsupported override mode {mode!r}.")
                else:
                    converted_overrides[str(column)][str(observed_value)] = {
                        "mode": "custom",
                        "value": str(override),
                    }

        text_plan = build_text_normalisation_plan(
            self._working_df,
            global_rule,
            list(columns),
            column_rules=normalized_column_rules,
            value_overrides=converted_overrides,
            trim_leading=trim_whitespace,
            trim_trailing=trim_whitespace,
            collapse_internal_spaces=collapse_spaces,
        )
        action = {
            "type": "normalize_text",
            "label": "Text normalisation · " + ", ".join(text_plan["selected_columns"]),
            "plan": text_plan,
        }
        preview = self.preview(action)
        recommended = set(recommend_text_normalisation_columns(self._working_df))
        # The shared recommender keeps identifiers and free-text fields opt-in;
        # explicit requests remain possible, but TALOS asks the user to review.
        risky = [column for column in preview.target_columns if column not in recommended]
        if risky:
            preview = TransformationPlan(
                operation=preview.operation,
                target_columns=preview.target_columns,
                parameters=preview.parameters,
                affected_rows=preview.affected_rows,
                affected_values=preview.affected_values,
                affected_cells=preview.affected_cells,
                rows_removed=preview.rows_removed,
                columns_removed=preview.columns_removed,
                warnings=(
                    *preview.warnings,
                    "These fields are not recommended controlled categories (identifier/free-text safeguards); "
                    "review their meaning before applying: "
                    + ", ".join(risky),
                ),
                _actions=preview._actions,
                _examples=preview._examples,
                _owner_token=preview._owner_token,
                _base_revision=preview._base_revision,
            )
        return preview

    def apply(self, plan: TransformationPlan) -> pd.DataFrame:
        """Apply a plan created by this session and append records to the ledger.

        The original dataset is never changed. Applying a plan marks working
        findings stale; call :meth:`reinspect` before reading its new score.

        Raises:
            TypeError: If ``plan`` is not a :class:`TransformationPlan`.
            ValueError: If the plan belongs to another session or an older revision.
        """
        if not isinstance(plan, TransformationPlan):
            raise TypeError("plan must be a TransformationPlan created by preview().")
        if plan._owner_token != self._session_token:
            raise ValueError("This transformation plan belongs to another TALOS session.")
        if plan._base_revision != self.revision:
            raise ValueError("This transformation plan is stale; preview it again on the current working copy.")
        updated_df, records = apply_transformations(
            self._working_df, list(deepcopy(plan._actions))
        )
        updated_ledger = deepcopy(self._transformation_ledger)
        for record in records:
            updated_ledger = append_ledger_record(updated_ledger, record)
        self._working_df = updated_df
        self._transformation_ledger = updated_ledger
        self.revision += 1
        return self.working_df

    def reset(self) -> pd.DataFrame:
        """Restore the original working copy, clear the ledger, and reinspect."""
        self._working_df = reset_working_copy(self._original_df)
        self._transformation_ledger = []
        self.revision += 1
        self._original_findings = inspect_dataset(self._original_df)
        self._working_findings = deepcopy(self._original_findings)
        self._inspected_revision = self.revision
        return self.working_df

    def export_cleaned_csv(self, path: str | Path) -> Path:
        """Write the current working copy as a UTF-8 CSV and return its path."""
        return _write_bytes(path, build_cleaned_csv(self._working_df))

    def export_transformation_log(self, path: str | Path) -> Path:
        """Write the approved transformation ledger as UTF-8 CSV."""
        contents = build_transformation_log(self._transformation_ledger).to_csv(index=False).encode("utf-8")
        return _write_bytes(path, contents)

    def export_evidence_tables(self, directory: str | Path) -> list[Path]:
        """Write current original/working evidence tables into a directory.

        Comparison tables and the transformation log are included when useful.
        Empty finding tables are omitted, matching the Streamlit Evidence Vault.
        """
        self._ensure_current_inspection()
        output_directory = Path(directory)
        output_directory.mkdir(parents=True, exist_ok=True)
        original_findings = self._required_original_findings()
        working_findings = self._required_working_findings()
        original_tables = build_result_tables(
            self._original_df, self.profile, original_findings
        )
        working_profile = {"columns": identify_column_types(self._working_df)}
        working_tables = build_result_tables(
            self._working_df, working_profile, working_findings
        )
        tables: dict[str, pd.DataFrame] = {
            f"original_{name}": table for name, table in original_tables.items()
        }
        tables["before_after_comparison.csv"] = build_comparison_table(
            self._original_df, self._working_df, original_findings, working_findings
        )
        tables["score_comparison.csv"] = build_score_comparison_table(
            original_findings["score"], working_findings["score"]
        )
        if self._transformation_ledger:
            tables.update({f"working_{name}": table for name, table in working_tables.items()})
            tables["transformation_ledger.csv"] = build_transformation_log(
                self._transformation_ledger
            )
        return [_write_bytes(output_directory / name, _frame_csv(table)) for name, table in tables.items() if not table.empty]

    def export_html_report(self, path: str | Path) -> Path:
        """Generate and save a self-contained HTML report for current state."""
        report, _pdf, _created_at = self._build_reports()
        return _write_bytes(path, report.encode("utf-8"))

    def export_pdf_report(self, path: str | Path) -> Path:
        """Generate and save a structured PDF report (requires ReportLab)."""
        _html, pdf, _created_at = self._build_reports(include_pdf=True)
        assert pdf is not None
        return _write_bytes(path, pdf)

    def export_evidence_pack(
        self, path: str | Path, *, include_pdf: bool = True
    ) -> Path:
        """Write a ZIP of reports, applicable finding CSVs, and comparison files.

        The original source file itself is not included; the archive contains
        findings, the approved working copy, and a record of approved changes.
        """
        report_html, report_pdf, created_at = self._build_reports(include_pdf=include_pdf)
        original_findings = self._required_original_findings()
        working_findings = self._required_working_findings()
        original_tables = build_result_tables(
            self._original_df, self.profile, original_findings
        )
        working_tables = build_result_tables(
            self._working_df,
            {"columns": identify_column_types(self._working_df)},
            working_findings,
        )
        files: dict[str, bytes] = {
            "inspection_report.html": report_html.encode("utf-8"),
            "cleaned_dataset.csv": build_cleaned_csv(self._working_df),
        }
        descriptions = {
            "inspection_report.html": "Complete, self-contained TALOS inspection report.",
            "cleaned_dataset.csv": "The current user-approved working copy, without a DataFrame index.",
        }
        if report_pdf is not None:
            files["inspection_report.pdf"] = report_pdf
            descriptions["inspection_report.pdf"] = "Printable PDF copy of the inspection report."
        table_descriptions = {
            "structure.csv": "Column names, pandas dtypes, and TALOS types.",
            "missing_values.csv": "Per-column missing counts, percentages, severity, and explanation.",
            "duplicate_rows.csv": "Rows involved in exact duplicate groups.",
            "identifier_findings.csv": "Name-based identifier review signals.",
            "category_variants.csv": "Observed category variants and proposed canonical values.",
            "outliers.csv": "Flagged numeric values with source rows and IQR bounds.",
            "structural_findings.csv": "Structural and numeric review signals.",
            "integrity_score.csv": "Original integrity-score components and weights.",
        }
        for filename, table in original_tables.items():
            files[filename] = _frame_csv(table)
            descriptions[filename] = table_descriptions.get(filename, "Original inspection evidence table.")
        if self._transformation_ledger:
            log = build_transformation_log(self._transformation_ledger)
            files["transformation_ledger.csv"] = _frame_csv(log)
            descriptions["transformation_ledger.csv"] = "Ordered approved transformation records and examples."
            for filename, table in working_tables.items():
                working_filename = f"working_{filename}"
                files[working_filename] = _frame_csv(table)
                descriptions[working_filename] = f"Working-copy {table_descriptions.get(filename, 'inspection evidence table').lower()}"
        comparison = build_comparison_table(
            self._original_df, self._working_df, original_findings, working_findings
        )
        files["before_after_comparison.csv"] = _frame_csv(comparison)
        descriptions["before_after_comparison.csv"] = "Original and current working-copy metrics."
        score_comparison = build_score_comparison_table(
            original_findings["score"], working_findings["score"]
        )
        if not score_comparison.empty:
            files["score_comparison.csv"] = _frame_csv(score_comparison)
            descriptions["score_comparison.csv"] = "Original and working-copy score components."
        files["README.txt"] = build_evidence_readme(
            self.source_filename, created_at, descriptions
        )
        return _write_bytes(path, build_evidence_pack(files))

    def _build_reports(
        self,
        *,
        include_pdf: bool = False,
    ) -> tuple[str, bytes | None, str]:
        """Prepare current report inputs from shared reporting/evidence code."""
        self._ensure_current_inspection()
        original_findings = self._required_original_findings()
        working_findings = self._required_working_findings()
        original_summary = summarize_dataset(self._original_df, original_findings)
        working_summary = summarize_dataset(self._working_df, working_findings)
        original_tables = build_result_tables(self._original_df, self.profile, original_findings)
        working_tables = build_result_tables(
            self._working_df,
            {"columns": identify_column_types(self._working_df)},
            working_findings,
        )
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        report = build_inspection_report_html(
            self.profile,
            original_findings,
            working_findings,
            original_summary,
            working_summary,
            self._transformation_ledger,
            original_evidence_tables=original_tables,
            working_evidence_tables=working_tables,
            created_at=created_at,
        )
        pdf = None
        if include_pdf:
            pdf = build_inspection_report_pdf(
                self.profile,
                original_findings,
                working_findings,
                original_summary,
                working_summary,
                self._transformation_ledger,
                original_evidence_tables=original_tables,
                working_evidence_tables=working_tables,
                created_at=created_at,
            )
        return report, pdf, created_at

    def _ensure_current_inspection(self) -> None:
        """Ensure report metrics exist and belong to the current working revision."""
        if self._original_findings is None:
            self.inspect()
        elif self.needs_reinspection:
            self.reinspect()

    def _required_original_findings(self) -> dict[str, dict[str, Any]]:
        self._ensure_current_inspection()
        assert self._original_findings is not None
        return self._original_findings

    def _required_working_findings(self) -> dict[str, dict[str, Any]]:
        self._ensure_current_inspection()
        assert self._working_findings is not None
        return self._working_findings


def _format_score(score: Any, band: Any = None) -> str:
    """Format a score while preserving TALOS's unassessable state."""
    if score is None:
        return "Not assessable"
    text = f"{score} / 100"
    return f"{text} · {band}" if band else text


def _public_action(action: Mapping[str, Any]) -> dict[str, Any]:
    """Return readable action parameters without duplicating a preview table."""
    public = {key: deepcopy(value) for key, value in action.items() if key != "plan"}
    plan = action.get("plan")
    if isinstance(plan, Mapping):
        public["plan"] = {
            key: deepcopy(plan[key])
            for key in (
                "global_rule",
                "selected_columns",
                "column_rules",
                "value_overrides",
                "whitespace",
                "values_affected",
                "cells_changed",
                "rows_affected",
                "manual_override_count",
            )
            if key in plan
        }
    return public


def _frame_csv(frame: pd.DataFrame) -> bytes:
    """Serialize an evidence table with the app's UTF-8 CSV convention."""
    return frame.to_csv(index=False).encode("utf-8")


def _write_bytes(path: str | Path, contents: bytes) -> Path:
    """Write bytes, creating parent directories, and return the destination."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(contents)
    return destination
