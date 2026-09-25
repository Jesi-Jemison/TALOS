"""Tests for TALOS's standard-library command-line entry point."""

from pathlib import Path
import zipfile

from talos_cli import main


def test_cli_inspect_prints_summary(capsys):
    result = main(["inspect", "data/sample/talos_demo.csv"])

    output = capsys.readouterr()
    assert result == 0
    assert "TALOS DATASET INSPECTION" in output.out
    assert "Rows:                 161" in output.out
    assert output.err == ""


def test_cli_output_writes_reports_finding_tables_and_pack(tmp_path, capsys):
    output_directory = tmp_path / "nested" / "talos_output"
    result = main(
        [
            "inspect",
            "data/sample/talos_demo.csv",
            "--output",
            str(output_directory),
        ]
    )

    output = capsys.readouterr()
    assert result == 0
    assert "Written outputs:" in output.out
    assert list(output_directory.glob("*_talos_report.html"))
    assert list(output_directory.glob("*_talos_report.pdf"))
    assert list(output_directory.glob("*_talos_cleaned.csv"))
    assert list(output_directory.glob("*_talos_transformations.csv"))
    assert list((output_directory / "talos_demo_evidence_tables").glob("*.csv"))
    pack_path = next(output_directory.glob("*_talos_evidence_pack.zip"))
    with zipfile.ZipFile(pack_path) as archive:
        assert "talos_evidence_pack/inspection_report.html" in archive.namelist()
    assert output.err == ""


def test_cli_missing_file_returns_concise_input_error(capsys, tmp_path):
    result = main(["inspect", str(tmp_path / "missing.csv")])

    output = capsys.readouterr()
    assert result == 2
    assert "input file not found" in output.err
    assert "Traceback" not in output.err


def test_cli_malformed_and_empty_csv_return_input_errors(capsys, tmp_path):
    malformed = tmp_path / "malformed.csv"
    malformed.write_text('a,b\n"unfinished,1\n', encoding="utf-8")
    assert main(["inspect", str(malformed)]) == 2
    malformed_error = capsys.readouterr().err
    assert "could not read CSV" in malformed_error
    assert "Traceback" not in malformed_error

    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"")
    assert main(["inspect", str(empty)]) == 2
    empty_error = capsys.readouterr().err
    assert "could not read CSV" in empty_error
    assert "Traceback" not in empty_error


def test_cli_rejects_unsupported_file_type_and_invalid_output_path(capsys, tmp_path):
    unsupported = tmp_path / "data.xlsx"
    assert main(["inspect", str(unsupported)]) == 2
    assert "unsupported file type" in capsys.readouterr().err

    csv_path = tmp_path / "small.csv"
    csv_path.write_text("value\n1\n", encoding="utf-8")
    output_file = tmp_path / "already_a_file"
    output_file.write_text("not a directory", encoding="utf-8")
    assert main(["inspect", str(csv_path), "--output", str(output_file)]) == 3
    error = capsys.readouterr().err
    assert "could not write TALOS outputs" in error
    assert "Traceback" not in error

