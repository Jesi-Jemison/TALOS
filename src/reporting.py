"""TALOS v1.1.1 CSV exports and concise PDF / detailed HTML inspection reports."""

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
.talos-table-wrap, .table-scroll { width: 100%; max-width: 100%; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; table-layout: auto; font-size: 13px; }
.talos-table-wrap--wide table, .table-scroll table { min-width: 760px; }
.talos-table--profile th:nth-child(1) { width: 42%; }
.talos-table--integrity-score th:nth-child(1) { width: 34%; }
.talos-table--integrity-score th:nth-child(2),
.talos-table--integrity-score th:nth-child(3),
.talos-table--integrity-score th:nth-child(4) { width: 22%; }
.talos-table--missing-values th:nth-child(1) { width: 16%; }
.talos-table--missing-values th:nth-child(6) { width: 34%; }
.talos-table--category-variants th:nth-child(3) { width: 52%; }
.talos-table--transformation-ledger th:nth-child(4),
.talos-table--transformation-ledger th:nth-child(5),
.talos-table--transformation-ledger th:nth-child(6) { width: 24%; }
.talos-table--comparison th:first-child { width: 50%; }
th, td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
  word-break: normal;
  overflow-wrap: break-word;
  hyphens: none;
}
th { color: var(--plum); background: #E8E0D1; }
th.compact-cell, td.compact-cell { white-space: nowrap; }
th.long-cell, td.long-cell { min-width: 11rem; max-width: 25rem; white-space: normal; }
td.long-token { overflow-wrap: anywhere; }
.report-note { color: var(--muted); font-size: 12px; }
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
  @page { size: A4 landscape; margin: 12mm; }
  body { background: #fff; }
  .page { max-width: none; padding: 0; }
  section { box-shadow: none; break-inside: auto; }
  h2, h3 { break-after: avoid; }
  .talos-table-wrap, .table-scroll { overflow: visible; }
  table { font-size: 9pt; }
  th, td { padding: 5pt 6pt; }
  thead { display: table-header-group; }
  tr { break-inside: avoid; }
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
        "pdf_report": "report.pdf",
        "structure": "structure.csv",
        "missing": "missing_values.csv",
        "duplicates": "duplicate_rows.csv",
        "identifiers": "identifier_findings.csv",
        "categories": "category_variants.csv",
        "outliers": "outliers.csv",
        "structural": "structural_findings.csv",
        "score": "integrity_score.csv",
        "working-structure": "working_structure.csv",
        "working-missing": "working_missing_values.csv",
        "working-duplicates": "working_duplicate_rows.csv",
        "working-identifiers": "working_identifier_findings.csv",
        "working-categories": "working_category_variants.csv",
        "working-outliers": "working_outliers.csv",
        "working-structural": "working_structural_findings.csv",
        "working-score": "working_integrity_score.csv",
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


def _table_cell_class(header: str, value: object = "") -> str:
    """Select compact or narrative wrapping for a known table field."""
    normalized = header.casefold()
    compact_terms = (
        "%", "count", "rows", "columns", "weight", "score", "points", "severity",
        "dtype", "type", "status", "uniqueness", "outlier", "q1", "q3", "median",
        "bound", "missing", "affected", "position", "source row",
    )
    long_terms = (
        "explanation", "effect", "description", "observed", "variant", "before and after",
        "parameters", "limitations", "canonical", "signal",
    )
    classes = []
    if any(term in normalized for term in compact_terms):
        classes.append("compact-cell")
    elif any(term in normalized for term in long_terms):
        classes.append("long-cell")
    text = str(value)
    if len(text) > 36 and not any(character.isspace() for character in text):
        classes.append("long-token")
    return " ".join(classes)


def _render_table(
    headers: list[str], rows: list[list[object]], table_name: str = "", wide: bool | None = None
) -> str:
    """Create an escaped, responsive HTML table with field-aware wrapping."""
    wide = len(headers) >= 6 if wide is None else wide
    wrapper_class = "talos-table-wrap talos-table-wrap--wide" if wide else "talos-table-wrap"
    header_html = "".join(
        f'<th class="{_table_cell_class(str(value))}">{_escape(value)}</th>'
        for value in headers
    )
    if not rows:
        body_html = (
            f'<tr><td class="empty-row" colspan="{len(headers)}">No findings recorded.</td></tr>'
        )
    else:
        body_html = "".join(
            "<tr>"
            + "".join(
                f'<td class="{_table_cell_class(str(header), value)}">{_escape(value)}</td>'
                for header, value in zip(headers, row)
            )
            + "</tr>"
            for row in rows
        )
    table_class = f"talos-table--{table_name}" if table_name else ""
    table_attribute = f' class="{_escape(table_class)}"' if table_class else ""
    return (
        f'<div class="{wrapper_class}"><table{table_attribute}><thead><tr>{header_html}</tr></thead>'
        f"<tbody>{body_html}</tbody></table></div>"
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
          'missing-values',
      )}
      <h3>Exact duplicate rows and identifier signals</h3>
      <p>{duplicates['exact_duplicate_row_count']} exact duplicate rows ({duplicates['exact_duplicate_percentage']:.1f}% of rows).</p>
      {_render_table(
          ['Possible identifier', 'Missing', 'Repeated values', 'Uniqueness'],
          duplicate_rows,
      )}
      <h3>Category variants</h3>
      {_render_table(['Column', 'Normalized form', 'Observed values'], category_rows, 'category-variants')}
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
            'transformation-ledger',
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
        ["Column", "Pandas type", "TALOS type"], columns, "profile"
    )
    original_score_table = _render_table(
        ["Component", "Weight", "Component score", "Weighted points"],
        _score_rows(original_findings),
        "integrity-score",
    )
    original_inspection = _findings_sections(
        original_findings, "Original dataset inspection"
    )
    comparison_table = _render_table(
        ["Measure", "Original", "Working copy"], comparison_rows, "comparison"
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
        "integrity-score",
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
    <div><div class="eyebrow">Guardian protocol · Data inspection</div>
      <h1>TALOS Inspection Report</h1>
      <p>Raw data enters. Nothing passes unchecked.</p>
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
  <footer>Generated by TALOS v1.1.1 · The original uploaded DataFrame was not mutated; approved changes belong to a separate working copy.</footer>
</main></body></html>"""


def build_inspection_report_pdf(
    profile: dict[str, Any],
    original_findings: dict[str, Any],
    working_findings: dict[str, Any],
    original_summary: dict[str, Any],
    working_summary: dict[str, Any],
    ledger: list[dict[str, Any]],
    guardian_image: bytes | None = None,
    original_evidence_tables: dict[str, pd.DataFrame] | None = None,
    working_evidence_tables: dict[str, pd.DataFrame] | None = None,
    created_at: str | None = None,
) -> bytes:
    """Build the concise, aggregate TALOS report; detailed rows stay in evidence exports."""
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        Image,
        NextPageTemplate,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    created_at = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    page_size = landscape(A4)
    page_width, page_height = page_size
    buffer = BytesIO()
    left_margin = right_margin = 13 * mm
    bottom_margin = 12 * mm
    later_top_margin = 14 * mm
    available_width = page_width - left_margin - right_margin
    doc = BaseDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=0,
        bottomMargin=bottom_margin,
        title=f"TALOS Inspection Report — {profile.get('file_name', 'dataset.csv')}",
        author="TALOS",
        pageCompression=1,
    )
    first_frame = Frame(
        left_margin, bottom_margin, available_width, page_height - bottom_margin,
        id="first", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    later_frame = Frame(
        left_margin, bottom_margin, available_width,
        page_height - bottom_margin - later_top_margin,
        id="later", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )

    ink = colors.HexColor("#322417")
    muted = colors.HexColor("#534638")
    bronze = colors.HexColor("#896337")
    bronze_light = colors.HexColor("#C39A5A")
    plum = colors.HexColor("#49365A")
    line = colors.HexColor("#B7A98F")
    pale = colors.HexColor("#F3EEE4")
    paper = colors.HexColor("#FBF8F1")
    dark = colors.HexColor("#111017")

    def draw_footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.line(left_margin, 9 * mm, page_width - right_margin, 9 * mm)
        canvas.setFillColor(muted)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(left_margin, 5.5 * mm, "Original data preserved · Findings require contextual review")
        canvas.drawRightString(page_width - right_margin, 5.5 * mm, f"Page {document.page}")
        canvas.restoreState()

    def draw_later(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(dark)
        canvas.rect(0, page_height - 9 * mm, page_width, 9 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#E1BF78"))
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(left_margin, page_height - 6 * mm, "TALOS  ·  INSPECTION REPORT")
        canvas.restoreState()
        draw_footer(canvas, document)

    doc.addPageTemplates(
        [
            PageTemplate(id="First", frames=first_frame, onPage=draw_footer),
            PageTemplate(id="Later", frames=later_frame, onPage=draw_later),
        ]
    )

    base = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TalosTitleV111", parent=base["Title"], fontName="Helvetica-Bold",
        fontSize=20, leading=23, textColor=colors.HexColor("#F1E8D4"),
        alignment=TA_LEFT, spaceAfter=5,
    )
    section_style = ParagraphStyle(
        "TalosSectionV111", parent=base["Heading2"], fontName="Helvetica-Bold",
        fontSize=13.5, leading=16, textColor=plum, spaceBefore=9, spaceAfter=5,
        keepWithNext=True,
    )
    subhead_style = ParagraphStyle(
        "TalosSubheadV111", parent=base["Heading3"], fontName="Helvetica-Bold",
        fontSize=9, leading=11, textColor=bronze, spaceBefore=6, spaceAfter=3,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "TalosBodyV111", parent=base["BodyText"], fontName="Helvetica",
        fontSize=8.5, leading=11, textColor=ink, splitLongWords=1, spaceAfter=3,
    )
    small_style = ParagraphStyle(
        "TalosSmallV111", parent=body_style, fontSize=7.2, leading=9,
        textColor=muted,
    )
    header_style = ParagraphStyle(
        "TalosTableHeaderV111", parent=body_style, fontName="Helvetica-Bold",
        fontSize=7.4, leading=9, textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "TalosTableCellV111", parent=body_style, fontSize=7.3, leading=9,
    )
    score_value_style = ParagraphStyle(
        "TalosScoreValueV111", parent=body_style, fontName="Helvetica-Bold",
        fontSize=10, leading=12, textColor=colors.HexColor("#F1E8D4"),
    )

    def plain(value: object, limit: int = 1400) -> str:
        if isinstance(value, (dict, list, tuple)):
            value = json.dumps(value, ensure_ascii=False, default=str)
        text = str(value if value is not None else "")
        if len(text) > limit:
            text = text[: limit - 1] + "…"
        return html.escape(text, quote=False).replace("\n", "<br/>")

    def paragraph(value: object, style: ParagraphStyle = cell_style) -> Paragraph:
        return Paragraph(plain(value), style)

    def data_table(
        headers: list[str], rows: list[list[object]], *, widths: list[float] | None = None
    ) -> Table:
        cells = [[paragraph(value, header_style) for value in headers]]
        cells.extend(
            [paragraph(value) for value in row[: len(headers)]] for row in rows
        )
        if not rows:
            cells.append([paragraph("No findings recorded.", small_style)] + [""] * (len(headers) - 1))
        table = Table(
            cells,
            colWidths=widths or [available_width / max(1, len(headers))] * len(headers),
            repeatRows=1,
            splitByRow=1,
            hAlign="LEFT",
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), plum),
                    ("GRID", (0, 0), (-1, -1), 0.35, line),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [paper, pale]),
                ]
            )
        )
        return table

    def table_section(title: str, headers: list[str], rows: list[list[object]]) -> list[object]:
        return [Paragraph(title, subhead_style), data_table(headers, rows)]

    def score_text(findings: dict[str, Any]) -> str:
        score = findings["score"].get("score")
        return "Not assessable" if score is None else f"{score} / 100"

    def signal_names(findings: dict[str, Any]) -> list[str]:
        signals: list[str] = []
        if findings["missing"]["total_missing_cells"]:
            signals.append("missing values")
        if findings["duplicates"]["exact_duplicate_row_count"]:
            signals.append("exact duplicate rows")
        if findings["categories"]["inconsistent_group_count"]:
            signals.append("category variants")
        if findings["outliers"]["total_outlier_values"]:
            signals.append("IQR outliers")
        structure = findings["structure"]
        if any(
            structure.get(key)
            for key in (
                "empty_columns", "constant_columns", "high_cardinality_columns",
                "identifier_columns", "numeric_patterns",
            )
        ):
            signals.append("structural signals")
        return signals

    def approved_change_count(items: list[dict[str, Any]]) -> int:
        total = 0
        for item in items:
            parameters = item.get("parameters", {})
            operation = parameters.get("operation", item.get("transformation_type", ""))
            if operation == "remediate_outliers":
                total += len(parameters.get("columns", [])) or 1
            elif operation == "remove_columns":
                total += int(parameters.get("columns_removed_count", 1))
            elif operation == "normalize_text":
                total += len(parameters.get("selected_columns", [])) or 1
            else:
                total += 1
        return total

    def repair_summaries(items: list[dict[str, Any]]) -> list[str]:
        bullets: list[str] = []
        strategy_names = {
            "blank": "replaced with missing values",
            "mean": "replaced with non-outlier mean",
            "median": "replaced with non-outlier median",
            "custom": "replaced with a custom value",
            "remove_rows": "removed affected rows",
            "cap": "capped to the nearest IQR boundary",
        }
        for item in items:
            parameters = item.get("parameters", {})
            operation = parameters.get("operation", "")
            if operation == "remediate_outliers":
                for column in parameters.get("columns", []):
                    strategy = strategy_names.get(column.get("strategy"), column.get("strategy", "updated"))
                    bullets.append(
                        f"{column.get('outlier_count', 0):,} {column.get('column', 'field')} IQR values {strategy}"
                    )
            elif operation == "remove_columns":
                count = int(parameters.get("columns_removed_count", 0))
                names = ", ".join(map(str, parameters.get("columns_removed", [])[:4]))
                suffix = f": {names}" if names else ""
                bullets.append(f"{count:,} selected column{'s' if count != 1 else ''} removed{suffix}")
            elif operation == "normalize_text":
                count = int(parameters.get("affected_values", 0))
                fields = ", ".join(map(str, parameters.get("selected_columns", [])[:4]))
                bullets.append(f"{count:,} text values normalised" + (f" across {fields}" if fields else ""))
            else:
                label = str(item.get("transformation_type", item.get("action", "Approved repair")))
                column = str(item.get("column", ""))
                affected = int(item.get("affected_rows", 0))
                if column:
                    bullets.append(f"{label}: {affected:,} rows · {column}")
                else:
                    bullets.append(f"{label}: {affected:,} rows")
        return bullets

    source_signals = signal_names(original_findings)
    if source_signals:
        signal_text = ", ".join(source_signals[:3])
        if len(source_signals) > 3:
            signal_text += f", and {len(source_signals) - 3} additional signal group(s)"
        signal_sentence = f"The main review signals were {signal_text}."
    else:
        signal_sentence = "No configured review signals were detected."

    rows_count = int(original_summary.get("row_count", profile.get("row_count", 0)))
    columns_count = int(original_summary.get("column_count", profile.get("column_count", 0)))
    if ledger:
        transformation_count = approved_change_count(ledger)
        unresolved = len(signal_names(working_findings))
        summary_text = (
            f"TALOS inspected {rows_count:,} rows across {columns_count:,} columns. "
            f"{transformation_count:,} user-approved transformation(s) were applied to the working copy. "
            f"The Dataset Integrity Score changed from {score_text(original_findings)} to "
            f"{score_text(working_findings)}. {unresolved:,} review signal group(s) remain."
        )
    else:
        summary_text = (
            f"TALOS inspected {rows_count:,} rows across {columns_count:,} columns. "
            f"The dataset scored {score_text(original_findings)}. {signal_sentence} "
            "No transformations were applied; the working copy remains identical to the original source."
        )

    story: list[object] = []
    hero_left = Paragraph(
        "TALOS INSPECTION REPORT<br/>"
        "<font size='9' color='#E8DEFF'>Raw data enters. Nothing passes unchecked.</font><br/>"
        f"<font size='7' color='#E1BF78'>GUARDIAN ACTIVE · Source: {plain(profile.get('file_name', 'dataset.csv'))}</font>",
        title_style,
    )
    guardian: object = Paragraph("TALOS GUARDIAN", small_style)
    if guardian_image:
        try:
            from PIL import Image as PILImage

            panel = PILImage.open(BytesIO(guardian_image)).convert("RGB")
            panel.thumbnail((900, 338), PILImage.Resampling.LANCZOS)
            compact_image = BytesIO()
            panel.save(compact_image, format="JPEG", quality=86, optimize=True)
            compact_image.seek(0)
            guardian = Image(compact_image, width=137, height=51.4, kind="proportional", hAlign="RIGHT")
        except Exception:
            guardian = Paragraph("TALOS GUARDIAN", small_style)
    hero = Table(
        [[hero_left, guardian]],
        colWidths=[available_width - 145, 145],
        hAlign="LEFT",
    )
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), dark),
                ("BOX", (0, 0), (-1, -1), 1.25, bronze),
                ("LINEABOVE", (0, 0), (-1, 0), 2, bronze_light),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.extend([hero, Spacer(1, 6), NextPageTemplate("Later")])

    story.append(Paragraph("Inspection Summary", section_style))
    summary_box = Table([[paragraph(summary_text, body_style)]], colWidths=[available_width])
    summary_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), pale),
                ("BOX", (0, 0), (-1, -1), 0.9, bronze),
                ("LINEBEFORE", (0, 0), (0, -1), 3, bronze),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(summary_box)

    story.append(Paragraph("Source Profile", section_style))
    source_rows = [
        ["Filename", profile.get("file_name", "")],
        ["File size", profile.get("file_size", "")],
        ["Source rows", f"{rows_count:,}"],
        ["Source columns", f"{columns_count:,}"],
        ["Report created", created_at],
    ]
    story.append(data_table(["Profile item", "Value"], source_rows, widths=[available_width * .28, available_width * .72]))

    story.append(Paragraph("Integrity Score", section_style))
    initial_score = score_text(original_findings)
    current_score = score_text(working_findings)
    score_panel = Table(
        [[paragraph("Source", header_style), paragraph(initial_score, score_value_style), paragraph("Current working copy", header_style), paragraph(current_score, score_value_style)]],
        colWidths=[available_width * .18, available_width * .22, available_width * .32, available_width * .28],
    )
    score_panel.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), dark),
                ("BOX", (0, 0), (-1, -1), 1, bronze),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(score_panel)
    story.append(Paragraph(
        "The Dataset Integrity Score is a custom TALOS heuristic, not an industry standard or proof of suitability.",
        small_style,
    ))

    story.append(Paragraph("Key Findings", section_style))
    aggregate_rows = [
        ["Missing cells", f"{original_summary.get('missing_cells', 0):,}", f"{working_summary.get('missing_cells', 0):,}"],
        ["Exact duplicate rows", f"{original_summary.get('duplicate_rows', 0):,}", f"{working_summary.get('duplicate_rows', 0):,}"],
        ["Category variant groups", f"{original_summary.get('category_variant_groups', 0):,}", f"{working_summary.get('category_variant_groups', 0):,}"],
        ["IQR outlier values", f"{original_summary.get('outlier_values', 0):,}", f"{working_summary.get('outlier_values', 0):,}"],
        ["Structural signals", f"{original_summary.get('structural_signals', 0):,}", f"{working_summary.get('structural_signals', 0):,}"],
    ]
    story.append(data_table(
        ["Signal group", "Source", "Current working copy"], aggregate_rows,
        widths=[available_width * .43, available_width * .26, available_width * .31],
    ))

    story.append(Paragraph("Transformations / Repairs Applied", section_style))
    if ledger:
        bullets = repair_summaries(ledger)
        story.append(Paragraph(f"{approved_change_count(ledger):,} approved transformations", body_style))
        for bullet in bullets[:10]:
            story.append(Paragraph("• " + plain(bullet), body_style))
        if len(bullets) > 10:
            story.append(Paragraph(
                f"{len(bullets) - 10:,} additional repair summaries are available in the Transformation Ledger export.",
                small_style,
            ))
    else:
        story.append(Paragraph("No transformations were approved. The working copy matches the source.", body_style))

    remaining_rows = [
        ["Missing values", f"{working_summary.get('missing_cells', 0):,}"],
        ["Exact duplicate rows", f"{working_summary.get('duplicate_rows', 0):,}"],
        ["Category variant groups", f"{working_summary.get('category_variant_groups', 0):,}"],
        ["IQR outlier values", f"{working_summary.get('outlier_values', 0):,}"],
        ["Structural signals", f"{working_summary.get('structural_signals', 0):,}"],
    ]
    remaining_rows = [row for row in remaining_rows if int(row[1].replace(",", "")) > 0]
    story.append(Paragraph("Remaining Signals", section_style))
    if remaining_rows:
        story.append(data_table(["Current signal group", "Count"], remaining_rows))
    else:
        story.append(Paragraph("No configured review signal groups remain in the working copy.", body_style))

    story.append(Paragraph("Before vs After", section_style))
    comparison_rows = [
        ["Rows", f"{original_summary.get('row_count', 0):,}", f"{working_summary.get('row_count', 0):,}"],
        ["Columns", f"{original_summary.get('column_count', 0):,}", f"{working_summary.get('column_count', 0):,}"],
        ["Missing cells", f"{original_summary.get('missing_cells', 0):,}", f"{working_summary.get('missing_cells', 0):,}"],
        ["Exact duplicate rows", f"{original_summary.get('duplicate_rows', 0):,}", f"{working_summary.get('duplicate_rows', 0):,}"],
        ["IQR outlier values", f"{original_summary.get('outlier_values', 0):,}", f"{working_summary.get('outlier_values', 0):,}"],
        ["Integrity score", initial_score, current_score],
    ]
    story.append(data_table(
        ["Measure", "Source", "Working copy"], comparison_rows,
        widths=[available_width * .43, available_width * .26, available_width * .31],
    ))

    story.append(Paragraph("Detailed Aggregate Findings", section_style))
    missing_rows = [
        [item["column"], f"{item['missing_count']:,}", f"{item['missing_percentage']:.1f}%", item["severity"]]
        for item in working_findings["missing"]["columns"] if item["missing_count"]
    ]
    category_rows = [
        [group["column"], group["normalized_value"], "; ".join(
            f"{variant['value']} ({variant['count']:,})" for variant in group["variants"][:5]
        )]
        for group in working_findings["categories"]["variant_groups"]
    ]
    outlier_rows = [
        [item["column"], f"{item['outlier_count']:,}", f"{item['outlier_percentage']:.1f}%",
         f"{item['lower_bound']:,.5g}", f"{item['upper_bound']:,.5g}"]
        for item in working_findings["outliers"]["columns"] if item["outlier_count"]
    ]
    structure = working_findings["structure"]
    structural_rows = (
        [[column, "Empty column"] for column in structure["empty_columns"]]
        + [[item["column"], "Constant column"] for item in structure["constant_columns"]]
        + [[item["column"], f"High-cardinality text · {item['uniqueness_percentage']:.1f}% unique"] for item in structure["high_cardinality_columns"]]
        + [[item["column"], "Possible identifier"] for item in structure["identifier_columns"]]
        + [[item["column"], f"{item['negative_count']:,} negative · {item['zero_percentage']:.1f}% zero"] for item in structure["numeric_patterns"] if item["negative_count"] or item["zero_percentage"] >= 80]
    )
    sections = [
        ("Missing values by field", ["Field", "Missing", "Missing %", "TALOS signal"], missing_rows),
        ("Category variant groups", ["Field", "Normalized form", "Observed variants and counts"], category_rows),
        ("Numeric IQR signals", ["Field", "Outliers", "Outlier %", "Lower bound", "Upper bound"], outlier_rows),
        ("Structural findings", ["Field", "Signal"], structural_rows),
    ]
    for title, headers, rows in sections:
        shown = rows[:15]
        story.extend(table_section(title, headers, shown))
        if len(rows) > len(shown):
            story.append(Paragraph(
                f"Showing {len(shown):,} of {len(rows):,} aggregate field/group rows. Full details remain available in CSV and the Evidence Pack.",
                small_style,
            ))
    story.append(Paragraph(
        "Row-level duplicate and outlier examples are intentionally kept out of this concise PDF. "
        "Use the HTML report, CSV exports, or Evidence Pack for detailed evidence.",
        small_style,
    ))

    story.append(Paragraph("Limitations", section_style))
    for note in (
        "Findings are contextual signals. TALOS does not understand the business meaning of a field.",
        "An outlier is not automatically an error; possible identifiers are inferred from column names.",
        "Transformations require user approval and affect a separate working copy. The original dataset remains unchanged.",
    ):
        story.append(Paragraph("• " + plain(note), body_style))

    doc.build(story)
    return buffer.getvalue()
