"""Stateless Vercel interface for TALOS's shared dataset engine.

The browser retains the source CSV and approved action history for this tab.
Each request reconstructs a fresh TALOS session, so no uploaded data is kept
between function invocations or shared with another visitor.
"""

from __future__ import annotations

import base64
import binascii
from io import BytesIO
import math
from pathlib import Path
import tempfile
from typing import Any

from flask import Flask, jsonify, request, send_file, send_from_directory
import numpy as np
import pandas as pd

from src.profiler import load_csv
from src.transformations import build_outlier_remediation_plan, build_suggested_transformations
from src.workflow import TalosSession, summarize_dataset


ROOT = Path(__file__).resolve().parent
MAX_CSV_BYTES = 2_000_000
MAX_HISTORY = 30
MAX_RESPONSE_BYTES = 4_000_000
app = Flask(__name__, static_folder="public", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 3_500_000


def _plain(value: Any) -> Any:
    """Make pandas and NumPy results safe to send as JSON."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, pd.DataFrame):
        return _plain(value.head(20).to_dict(orient="records"))
    if isinstance(value, pd.Series):
        return _plain(value.head(20).tolist())
    if isinstance(value, np.generic):
        return _plain(value.item())
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _session(body: dict[str, Any]) -> TalosSession:
    encoded = body.get("csv_base64")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("Choose a CSV file or load the demo first.")
    if len(encoded) > (MAX_CSV_BYTES * 4 // 3 + 8):
        raise ValueError("This Vercel version accepts CSV files up to 2 MB. Use the Streamlit app for larger files.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("The uploaded CSV could not be decoded.") from exc
    if len(raw) > MAX_CSV_BYTES:
        raise ValueError("This Vercel version accepts CSV files up to 2 MB. Use the Streamlit app for larger files.")
    filename = Path(str(body.get("filename") or "dataset.csv")).name
    if not filename.lower().endswith(".csv"):
        raise ValueError("Please use a CSV file.")
    session = TalosSession(load_csv(raw), source_filename=filename, source_size_bytes=len(raw))
    session.inspect()
    history = body.get("history", [])
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        raise ValueError("The action history is invalid or too long. Reset this tab to start a new session.")
    for entry in history:
        plan = _plan(session, entry)
        session.apply(plan)
        session.reinspect()
    return session


def _plan(session: TalosSession, entry: Any):
    if not isinstance(entry, dict):
        raise ValueError("Choose a valid repair action.")
    if entry.get("kind") == "text":
        return session.preview_text_normalisation(
            columns=entry.get("columns", []),
            default_rule=entry.get("rule", "Leave unchanged"),
            trim_whitespace=bool(entry.get("trim_whitespace", False)),
            collapse_spaces=bool(entry.get("collapse_spaces", False)),
        )
    if entry.get("kind") == "outlier":
        column = str(entry.get("column", ""))
        strategy = str(entry.get("strategy", "leave"))
        choice = {"strategy": strategy}
        if strategy == "custom":
            choice["value"] = entry.get("value")
        remediation = build_outlier_remediation_plan(session.working_df, {column: choice})
        return session.preview({"type": "remediate_outliers", "plan": remediation})
    if entry.get("kind") != "actions":
        raise ValueError("Choose a valid repair action.")
    actions = entry.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 20:
        raise ValueError("Choose between one and twenty repair actions.")
    allowed = {
        "normalize_whitespace", "consolidate_category", "remove_exact_duplicates",
        "remove_rows_with_missing", "fill_numeric_missing", "fill_text_missing",
        "remove_empty_column", "remove_columns", "remediate_outliers",
    }
    if any(not isinstance(action, dict) or action.get("type") not in allowed for action in actions):
        raise ValueError("One of the repair actions is unsupported.")
    return session.preview(actions)


def _snapshot(session: TalosSession) -> dict[str, Any]:
    findings = session.working_findings
    assert findings is not None
    working = session.working_df
    suggestions = build_suggested_transformations(working, findings)
    signals = {
        "missing": findings["missing"]["columns"][:50],
        "category_variants": findings["categories"]["variant_groups"][:30],
        "outliers": findings["outliers"]["columns"][:30],
        "structure": findings["structure"],
        "duplicates": findings["duplicates"]["exact_duplicate_row_count"],
    }
    return _plain({
        "profile": session.profile,
        "source_summary": summarize_dataset(session.original_df, session.original_findings),
        "summary": summarize_dataset(working, findings),
        "score": findings["score"],
        "columns": [str(c) for c in working.columns],
        "sample": working.head(12).replace({np.nan: None}).to_dict(orient="records"),
        "signals": signals,
        "suggestions": suggestions[:40],
        "ledger": session.transformation_ledger,
    })


@app.get("/")
def home():
    return send_from_directory(ROOT / "public", "index.html")


@app.post("/api/inspect")
def inspect():
    session = _session(request.get_json(force=True))
    return jsonify(_snapshot(session))


@app.post("/api/preview")
def preview():
    body = request.get_json(force=True)
    session = _session(body)
    plan = _plan(session, body.get("next"))
    return jsonify(_plain({
        "operation": plan.operation,
        "targets": plan.target_columns,
        "affected_rows": plan.affected_rows,
        "affected_values": plan.affected_values,
        "rows_removed": plan.rows_removed,
        "columns_removed": plan.columns_removed,
        "warnings": plan.warnings,
        "examples": plan.examples,
    }))


@app.post("/api/apply")
def apply():
    body = request.get_json(force=True)
    session = _session(body)
    plan = _plan(session, body.get("next"))
    session.apply(plan)
    session.reinspect()
    return jsonify(_snapshot(session))


@app.post("/api/export/<format_name>")
def export(format_name: str):
    formats = {
        "csv": ("export_cleaned_csv", "text/csv", "cleaned.csv"),
        "log": ("export_transformation_log", "text/csv", "transformation_log.csv"),
        "html": ("export_html_report", "text/html", "report.html"),
        "pdf": ("export_pdf_report", "application/pdf", "report.pdf"),
        "evidence": ("export_evidence_pack", "application/zip", "evidence.zip"),
    }
    if format_name not in formats:
        return jsonify({"error": "Unknown export format."}), 404
    session = _session(request.get_json(force=True))
    method_name, mime, filename = formats[format_name]
    with tempfile.TemporaryDirectory() as temp_dir:
        target = Path(temp_dir) / filename
        getattr(session, method_name)(target)
        content = target.read_bytes()
    if len(content) > MAX_RESPONSE_BYTES:
        return jsonify({"error": "This export exceeds Vercel's response limit. Use the Streamlit app for this dataset."}), 413
    return send_file(BytesIO(content), mimetype=mime, as_attachment=True, download_name=filename)


@app.errorhandler(400)
@app.errorhandler(413)
def request_error(error):
    return jsonify({"error": "The request is too large or invalid for this Vercel version."}), error.code


@app.errorhandler(ValueError)
@app.errorhandler(KeyError)
@app.errorhandler(pd.errors.ParserError)
@app.errorhandler(pd.errors.EmptyDataError)
def user_error(error):
    return jsonify({"error": str(error)}), 400


if __name__ == "__main__":
    app.run(debug=True)
