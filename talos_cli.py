"""Small standard-library command-line interface for TALOS inspections."""
# TALOS FILE VERSION: v1.2.0

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

import pandas as pd

from src.reporting import build_export_filename
from src.workflow import TalosSession


def _build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser without adding third-party CLI dependencies."""
    parser = argparse.ArgumentParser(
        prog="talos",
        description="Inspect a CSV with the TALOS data-integrity checks.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="inspect one CSV dataset")
    inspect.add_argument("csv_path", type=Path, help="path to the source CSV")
    inspect.add_argument(
        "--output",
        type=Path,
        metavar="DIR",
        help="also write reports, finding CSVs, and an evidence ZIP into DIR",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run TALOS CLI and return a process-friendly exit code.

    Exit codes are 0 for success, 2 for invalid input/usage, and 3 when an
    otherwise valid inspection cannot be written to the requested location.
    """
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command != "inspect":  # pragma: no cover - argparse constrains this
        parser.error("choose a supported command")
    csv_path: Path = arguments.csv_path
    if csv_path.suffix.casefold() != ".csv":
        print(
            f"talos: error: unsupported file type for {str(csv_path)!r}; provide a .csv file",
            file=sys.stderr,
        )
        return 2

    try:
        session = TalosSession.from_csv(csv_path)
        session.inspect()
    except FileNotFoundError:
        print(f"talos: error: input file not found: {str(csv_path)!r}", file=sys.stderr)
        return 2
    except PermissionError:
        print(f"talos: error: permission denied reading {str(csv_path)!r}", file=sys.stderr)
        return 2
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeError, ValueError) as exc:
        print(f"talos: error: could not read CSV {str(csv_path)!r}: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"talos: error: could not read {str(csv_path)!r}: {exc.strerror or exc}", file=sys.stderr)
        return 2

    print(session.summary())
    output_directory: Path | None = arguments.output
    if output_directory is None:
        return 0
    try:
        output_directory.mkdir(parents=True, exist_ok=True)
        stem = csv_path.stem or "dataset"
        outputs = [
            session.export_cleaned_csv(
                output_directory / build_export_filename(csv_path.name, "cleaned")
            ),
            session.export_transformation_log(
                output_directory / build_export_filename(csv_path.name, "transformations")
            ),
            session.export_html_report(
                output_directory / build_export_filename(csv_path.name, "report")
            ),
            session.export_pdf_report(
                output_directory / build_export_filename(csv_path.name, "pdf_report")
            ),
            *session.export_evidence_tables(output_directory / f"{stem}_evidence_tables"),
            session.export_evidence_pack(
                output_directory / build_export_filename(csv_path.name, "evidence_pack"),
                include_pdf=False,
            ),
        ]
    except PermissionError:
        print(f"talos: error: permission denied writing to {str(output_directory)!r}", file=sys.stderr)
        return 3
    except (OSError, ValueError, ImportError) as exc:
        print(f"talos: error: could not write TALOS outputs: {exc}", file=sys.stderr)
        return 3

    print("\nWritten outputs:")
    for output_path in outputs:
        print(f"  {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

