"""Checks for the Vercel adapter against TALOS's real demo dataset."""

import base64
from pathlib import Path

from app import app


DEMO = Path(__file__).parents[1] / "public" / "talos_demo.csv"


def payload():
    return {
        "csv_base64": base64.b64encode(DEMO.read_bytes()).decode("ascii"),
        "filename": "talos_demo.csv",
        "history": [],
    }


def test_demo_inspection_and_approved_repair_are_stateless():
    client = app.test_client()
    source = payload()
    initial_response = client.post("/api/inspect", json=source)
    assert initial_response.status_code == 200
    initial = initial_response.get_json()
    assert initial["summary"]["row_count"] > 0
    assert initial["summary"]["score"] is not None
    assert initial["ledger"] == []

    repair = {"kind": "actions", "actions": [{"type": "remove_exact_duplicates"}]}
    preview_response = client.post("/api/preview", json={**source, "next": repair})
    assert preview_response.status_code == 200
    assert preview_response.get_json()["rows_removed"] > 0

    apply_response = client.post("/api/apply", json={**source, "next": repair})
    assert apply_response.status_code == 200
    changed = apply_response.get_json()
    assert changed["summary"]["row_count"] < initial["summary"]["row_count"]
    assert changed["source_summary"]["row_count"] == initial["summary"]["row_count"]

    # A separate request with no approved history still sees the untouched source.
    again = client.post("/api/inspect", json=source).get_json()
    assert again["summary"]["row_count"] == initial["summary"]["row_count"]

    approved = {**source, "history": [repair]}
    csv_response = client.post("/api/export/csv", json=approved)
    assert csv_response.status_code == 200
    assert csv_response.data.startswith(b"\xef\xbb\xbf") or b"," in csv_response.data

    for format_name, signature in (("html", b"<"), ("pdf", b"%PDF"), ("evidence", b"PK")):
        result = client.post(f"/api/export/{format_name}", json=approved)
        assert result.status_code == 200
        assert result.data.startswith(signature)


def test_text_normalisation_preview_and_apply():
    client = app.test_client()
    source = payload()
    action = {"kind": "text", "columns": ["region"], "rule": "Proper Case", "trim_whitespace": True, "collapse_spaces": True}
    preview = client.post("/api/preview", json={**source, "next": action})
    assert preview.status_code == 200
    assert preview.get_json()["affected_values"] > 0
    changed = client.post("/api/apply", json={**source, "next": action})
    assert changed.status_code == 200
    assert changed.get_json()["ledger"]


def test_rejects_oversized_and_invalid_data():
    client = app.test_client()
    too_large = base64.b64encode(b"x" * 2_000_001).decode("ascii")
    response = client.post("/api/inspect", json={"csv_base64": too_large, "filename": "big.csv"})
    assert response.status_code == 400
    bad = client.post("/api/inspect", json={"csv_base64": "%%", "filename": "bad.csv"})
    assert bad.status_code == 400
