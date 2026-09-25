"""CSV exports and self-contained HTML inspection reports for TALOS."""

from __future__ import annotations

import base64
import html
import json
from datetime import datetime, timezone
from io import StringIO
from pathlib import PurePosixPath
from typing import Any

import pandas as pd


TRANSFORMATION_LOG_COLUMNS = [
    "Transformation type",
    "Column",
    "Chosen action",
    "Affected rows",
    "Description",
    "Parameters",
    "Before and after",
    "Rows before",
    "Rows after",
    "Columns before",
    "Columns after",
]

REPORT_STYLESHEET = """
:root {
  color-scheme: light;
  --ink: #322417;
  --muted: #534638;
  --bronze: #896337;
  --plum: #49365A;
  --line: #B7A98F;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #F3EEE4;
  color: var(--ink);
  font: 15px/1.55 system-ui, -apple-system, Segoe UI, sans-serif;
}
.page { max-width: 1180px; margin: 0 auto; padding: 28px; }
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 30px 34px;
  border: 1px solid #896337;
  border-top: 4px solid #C39A5A;
  border-radius: 14px;
  background: #111017;
  box-shadow: inset 0 0 0 4px rgba(195, 154, 90, .11);
  color: #E8DEFF;
}
.eyebrow { color: #BDA8F2; font-size: 12px; letter-spacing: .16em; text-transform: uppercase; }
h1 { margin: 6px 0; font-size: 34px; }
header p { margin: 0; color: #C4BED0; }
.emblem { width: 92px; height: 92px; }
.emblem-fallback {
  display: grid;
  width: 72px;
  height: 72px;
  place-items: center;
  border: 2px solid #C39A5A;
  border-radius: 50%;
  color: #C39A5A;
  font-size: 38px;
}
section {
  margin-top: 22px;
  padding: 24px;
  border: 1px solid var(--line);
  border-top: 2px solid #B7A98F;
  border-radius: 12px;
  background: #FBF8F1;
  break-inside: avoid;
}
h2 { margin: 0 0 14px; color: var(--plum); font-size: 22px; }
h3 { margin: 22px 0 8px; font-size: 16px; }
.meta-grid, .summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
  gap: 10px;
  margin: 14px 0;
}
.meta-grid div, .summary-grid div {
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: #F6F1E8;
}
.meta-grid span, .summary-grid span { display: block; color: var(--muted); font-size: 12px; }
.meta-grid strong, .summary-grid strong { display: block; margin-top: 4px; font-size: 18px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table-scroll { width: 100%; overflow-x: auto; }
th, td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}
th { color: var(--plum); background: #E8E0D1; }
.empty-row { color: var(--muted); text-align: center; }
.score {
  padding: 14px 18px;
  border-left: 3px solid var(--bronze);
  background: #EFE7DA;
  font-size: 22px;
  font-weight: 650;
}
.note, footer { color: var(--muted); font-size: 13px; }
footer { padding: 18px 4px; font-size: 12px; }
@media print {
  body { background: #fff; }
  .page { max-width: none; padding: 0; }
  section { box-shadow: none; }
  header { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
}
@media (max-width: 700px) {
  .page { padding: 14px; }
  header { padding: 20px; }
  h1 { font-size: 27px; }
  section { padding: 17px; }
}
"""


def build_export_filename(original_filename: str, export_type: str) -> str:
    """Return a safe, predictable TALOS export filename."""
    safe_name = str(original_filename).replace("\\", "/").split("/")[-1]
    stem = PurePosixPath(safe_name).stem or "dataset"
    if stem == ".csv":
        stem = "dataset"
    suffixes = {
        "cleaned": "cleaned.csv",
        "transformations": "transformations.csv",
        "report": "report.html",
        "structure": "structure.csv",
        "missing": "missing_values.csv",
        "duplicates": "duplicate_rows.csv",
        "identifiers": "identifier_findings.csv",
        "categories": "category_variants.csv",
        "outliers": "outliers.csv",
        "structural": "structural_findings.csv",
        "score": "integrity_score.csv",
        "score_comparison": "score_comparison.csv",
        "comparison": "comparison.csv",
        "evidence_pack": "evidence_pack.zip",
    }
    if export_type not in suffixes:
        raise ValueError(f"Unsupported export type: {export_type!r}.")
    return f"{stem}_talos_{suffixes[export_type]}"


def build_cleaned_csv(df: pd.DataFrame) -> bytes:
    """Serialize a working copy as UTF-8 CSV without an index column."""
    buffer = StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def build_transformation_log(ledger: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert ledger records to a clear, flat table suitable for CSV export."""
    rows = []
    for record in ledger:
        rows.append(
            {
                "Transformation type": record.get("transformation_type", ""),
                "Column": record.get("column", ""),
                "Chosen action": record.get("action", ""),
                "Affected rows": record.get("affected_rows", 0),
                "Description": record.get("description", ""),
                "Parameters": json.dumps(
                    record.get("parameters", {}), ensure_ascii=False, default=str
                ),
                "Before and after": json.dumps(
                    record.get("before_after", []), ensure_ascii=False, default=str
                ),
                "Rows before": record.get("rows_before", ""),
                "Rows after": record.get("rows_after", ""),
                "Columns before": record.get("columns_before", ""),
                "Columns after": record.get("columns_after", ""),
            }
        )
    return pd.DataFrame(rows, columns=TRANSFORMATION_LOG_COLUMNS)


def _escape(value: object) -> str:
    """Escape values from uploaded data before placing them in HTML."""
    return html.escape(str(value), quote=True)


def _render_table(headers: list[str], rows: list[list[object]]) -> str:
    """Create an escaped HTML table from simple header and row values."""
    header_html = "".join(f"<th>{_escape(value)}</th>" for value in headers)
    if not rows:
        body_html = (
            f'<tr><td class="empty-row" colspan="{len(headers)}">No findings recorded.</td></tr>'
        )
    else:
        body_html = "".join(
            "<tr>" + "".join(f"<td>{_escape(value)}</td>" for value in row) + "</tr>"
            for row in rows
        )
    return (
        f"<table><thead><tr>{header_html}</tr></thead>"
        f"<tbody>{body_html}</tbody></table>"
    )


def _score_rows(findings: dict[str, Any]) -> list[list[object]]:
    score = findings.get("score", {})
    return [
        [
            item["component"],
            f"{item['weight']}%",
            f"{item['score']:.1f}",
            f"{item['weighted_points']:.1f}",
        ]
        for item in score.get("components", [])
    ]


def _render_evidence_table(
    heading: str, table: pd.DataFrame | None, row_limit: int = 500
) -> str:
    """Render escaped row-level evidence, limiting very large HTML sections."""
    if table is None or table.empty:
        return ""
    shown = table.head(row_limit)
    table_html = shown.to_html(
        index=False,
        escape=True,
        border=0,
        classes=["evidence-table"],
        na_rep="",
    )
    note = ""
    if len(table.index) > row_limit:
        note = (
            f'<p class="note">Showing the first {row_limit:,} of {len(table.index):,} rows. '
            "The evidence pack includes the complete CSV table.</p>"
        )
    return (
        f'<h3>{_escape(heading)}</h3><div class="table-scroll">'
        f"{table_html}</div>{note}"
    )


def _findings_sections(findings: dict[str, Any], heading: str) -> str:
    """Render the inspection summaries without embedding source-data rows."""
    missing = findings["missing"]
    missing_rows = [
        [
            item["column"],
            item["pandas_dtype"],
            item["missing_count"],
            f"{item['missing_percentage']:.1f}%",
            item["severity"],
            item["explanation"],
        ]
        for item in missing["columns"]
    ]

    duplicates = findings["duplicates"]
    duplicate_rows = [
        [
            item["column"],
            item["missing_count"],
            item["duplicate_value_count"],
            f"{item['uniqueness_percentage']:.1f}%",
        ]
        for item in duplicates["identifier_candidates"]
    ]

    categories = findings["categories"]
    category_rows = [
        [
            group["column"],
            group["normalized_value"],
            "; ".join(f"{item['value']} ({item['count']})" for item in group["variants"]),
        ]
        for group in categories["variant_groups"]
    ]

    outliers = findings["outliers"]
    outlier_rows = [
        [
            item["column"],
            item["outlier_count"],
            f"{item['outlier_percentage']:.1f}%",
            f"{item['q1']:.3g}",
            f"{item['median']:.3g}",
            f"{item['q3']:.3g}",
            f"{item['lower_bound']:.3g}",
            f"{item['upper_bound']:.3g}",
        ]
        for item in outliers["columns"]
    ]

    structure = findings["structure"]
    structural_rows = [
        [column, "Empty column"] for column in structure["empty_columns"]
    ] + [
        [item["column"], "Constant column"] for item in structure["constant_columns"]
    ] + [
        [
            item["column"],
            f"High-cardinality text ({item['uniqueness_percentage']:.1f}% unique)",
        ]
        for item in structure["high_cardinality_columns"]
    ] + [
        [
            item["column"],
            f"Possible identifier ({item['duplicate_value_count']} repeated values)",
        ]
        for item in structure["identifier_columns"]
    ] + [
        [
            item["column"],
            f"{item['negative_count']} negative; {item['zero_percentage']:.1f}% zeros",
        ]
        for item in structure["numeric_patterns"]
        if item["negative_count"] or item["zero_percentage"] >= 80
    ]

    return f"""
    <section>
      <h2>{_escape(heading)}</h2>
      <div class="summary-grid">
        <div><span>Missing cells</span><strong>{missing['total_missing_cells']}</strong></div>
        <div><span>Exact duplicate rows</span><strong>{duplicates['exact_duplicate_row_count']}</strong></div>
        <div><span>Category variant groups</span><strong>{categories['inconsistent_group_count']}</strong></div>
        <div><span>IQR outlier values</span><strong>{outliers['total_outlier_values']}</strong></div>
      </div>
      <h3>Missing values</h3>
      {_render_table(
          ['Column', 'Pandas type', 'Missing', 'Missing %', 'Severity', 'Possible effect'],
          missing_rows,
      )}
      <h3>Exact duplicate rows and identifier signals</h3>
      <p>{duplicates['exact_duplicate_row_count']} exact duplicate rows ({duplicates['exact_duplicate_percentage']:.1f}% of rows).</p>
      {_render_table(
          ['Possible identifier', 'Missing', 'Repeated values', 'Uniqueness'],
          duplicate_rows,
      )}
      <h3>Category variants</h3>
      {_render_table(['Column', 'Normalized form', 'Observed values'], category_rows)}
      <h3>Numeric outliers</h3>
      {_render_table(
          ['Column', 'Outliers', 'Outlier %', 'Q1', 'Median', 'Q3', 'Lower IQR bound', 'Upper IQR bound'],
          outlier_rows,
      )}
      <h3>Structural and numeric signals</h3>
      {_render_table(['Column', 'Signal'], structural_rows)}
    </section>
    """


def build_inspection_report_html(
    profile: dict[str, Any],
    original_findings: dict[str, Any],
    working_findings: dict[str, Any],
    original_summary: dict[str, Any],
    working_summary: dict[str, Any],
    ledger: list[dict[str, Any]],
    emblem_svg: str = "",
    original_evidence_tables: dict[str, pd.DataFrame] | None = None,
    working_evidence_tables: dict[str, pd.DataFrame] | None = None,
    created_at: str | None = None,
) -> str:
    """Build a self-contained, escaped, printable HTML report."""
    created_at = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    score = original_findings["score"]
    score_text = (
        "Not assessable"
        if score["score"] is None
        else f"{score['score']} / 100 · {score['band']}"
    )
    score_explanation = score.get("explanation", "")
    columns = [
        [item["column"], item["pandas_dtype"], item["talos_type"]]
        for item in profile["columns"]
    ]
    ledger_rows = [
        [
            item.get("transformation_type", ""),
            item.get("column", ""),
            item.get("affected_rows", 0),
            item.get("description", ""),
            json.dumps(item.get("parameters", {}), ensure_ascii=False, default=str),
            json.dumps(item.get("before_after", []), ensure_ascii=False, default=str),
        ]
        for item in ledger
    ]
    emblem_data_uri = ""
    if emblem_svg:
        encoded_emblem = base64.b64encode(emblem_svg.encode("utf-8")).decode("ascii")
        emblem_data_uri = f"data:image/svg+xml;base64,{encoded_emblem}"
    emblem_html = (
        f'<img class="emblem" src="{emblem_data_uri}" alt="TALOS bronze guardian emblem">'
        if emblem_data_uri
        else '<div class="emblem-fallback" role="img" aria-label="TALOS guardian emblem">T</div>'
    )
    if ledger:
        ledger_section = _render_table(
            [
                "Transformation",
                "Column",
                "Affected rows",
                "Action",
                "Parameters",
                "Before and after examples",
            ],
            ledger_rows,
        )
    else:
        ledger_section = "<p>No transformations were approved. The working copy matches the original.</p>"

    original_score = original_summary.get("score")
    current_score = working_summary.get("score")
    comparison_rows = [
        ["Rows", original_summary["row_count"], working_summary["row_count"]],
        ["Columns", original_summary["column_count"], working_summary["column_count"]],
        ["Missing cells", original_summary["missing_cells"], working_summary["missing_cells"]],
        [
            "Exact duplicate rows",
            original_summary["duplicate_rows"],
            working_summary["duplicate_rows"],
        ],
        [
            "Category variant groups",
            original_summary.get("category_variant_groups", 0),
            working_summary.get("category_variant_groups", 0),
        ],
        [
            "IQR outlier values",
            original_summary.get("outlier_values", 0),
            working_summary.get("outlier_values", 0),
        ],
        [
            "Empty columns",
            original_summary.get("empty_columns", 0),
            working_summary.get("empty_columns", 0),
        ],
        [
            "Integrity score",
            original_score if original_score is not None else "Not assessable",
            current_score if current_score is not None else "Not assessable",
        ],
    ]
    profile_table = _render_table(
        ["Column", "Pandas type", "TALOS type"], columns
    )
    original_score_table = _render_table(
        ["Component", "Weight", "Component score", "Weighted points"],
        _score_rows(original_findings),
    )
    original_inspection = _findings_sections(
        original_findings, "Original dataset inspection"
    )
    comparison_table = _render_table(
        ["Measure", "Original", "Working copy"], comparison_rows
    )
    working_score = working_findings["score"]
    working_score_text = (
        "Not assessable"
        if working_score["score"] is None
        else f"{working_score['score']} / 100 · {working_score['band']}"
    )
    working_score_table = _render_table(
        ["Component", "Weight", "Component score", "Weighted points"],
        _score_rows(working_findings),
    )
    working_sections = f"""
      <section><h2>Current working-copy integrity score</h2>
        <div class="score">{_escape(working_score_text)}</div>
        <p class="note">A higher score means fewer signals under these checks. It does not establish suitability or correctness.</p>
        {working_score_table}
      </section>
      {_findings_sections(working_findings, 'Current working-copy inspection')}
    """

    def render_row_evidence(
        tables: dict[str, pd.DataFrame] | None, label: str
    ) -> str:
        if not tables:
            return ""
        sections = []
        table_labels = {
            "duplicate_rows.csv": "Exact duplicate records",
            "outliers.csv": "Flagged numeric values",
        }
        for filename, title in table_labels.items():
            rendered = _render_evidence_table(title, tables.get(filename))
            if rendered:
                sections.append(rendered)
        if not sections:
            return ""
        return (
            f"<section><h2>{_escape(label)} row-level evidence</h2>"
            + "".join(sections)
            + "</section>"
        )

    original_row_evidence = render_row_evidence(
        original_evidence_tables, "Original inspection"
    )
    working_row_evidence = render_row_evidence(
        working_evidence_tables, "Working-copy reinspection"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TALOS Inspection Report — {_escape(profile['file_name'])}</title>
  <style>{REPORT_STYLESHEET}</style>
</head>
<body><main class="page">
  <header>
    <div><div class="eyebrow">Data integrity observation system</div>
      <h1>TALOS Inspection Report</h1>
      <p>The guardian's findings, recorded.</p>
    </div>
    {emblem_html}
  </header>
  <section><h2>Source file</h2><div class="meta-grid">
    <div><span>Filename</span><strong>{_escape(profile['file_name'])}</strong></div>
    <div><span>File size</span><strong>{_escape(profile['file_size'])}</strong></div>
    <div><span>Rows</span><strong>{profile['row_count']}</strong></div>
    <div><span>Columns</span><strong>{profile['column_count']}</strong></div>
    <div><span>Report created</span><strong>{_escape(created_at)}</strong></div>
  </div></section>
  <section><h2>Structural profile</h2>{profile_table}</section>
  <section>
    <h2>Dataset Integrity Score</h2>
    <div class="score">{_escape(score_text)}</div>
    <p class="note">{_escape(score_explanation)}</p>
    {original_score_table}
    <p class="note">The Dataset Integrity Score is a custom TALOS heuristic and is not an industry-standard data quality measure.</p>
  </section>
  {original_inspection}
  {original_row_evidence}
  {working_sections}
  {working_row_evidence}
  <section>
    <h2>Original and working-copy comparison</h2>
    <p>Fewer findings do not automatically mean the dataset is more suitable for its intended use.</p>
    {comparison_table}
  </section>
  <section><h2>Transformation Ledger</h2>{ledger_section}</section>
  <section><h2>Limitations</h2><ul>
    <li>Findings are contextual signals. TALOS does not understand the business meaning of a field.</li>
    <li>Outliers are not automatically errors; possible identifiers are inferred from column names.</li>
    <li>Transformations are user-approved and applied to a separate working copy.</li>
    <li>The original uploaded dataset remains unchanged by TALOS.</li>
  </ul></section>
  <footer>Generated by TALOS · The original uploaded DataFrame was not mutated; approved changes belong to a separate working copy.</footer>
</main></body></html>"""
