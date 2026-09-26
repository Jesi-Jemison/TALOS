"""A guided TALOS workflow that is safe to run from the repository root."""
# TALOS FILE VERSION: v1.2.0

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

# When Python runs a file inside examples/, it starts with that subfolder on
# sys.path. Adding the repository root lets this uninstalled project import its
# shared core while keeping the example runnable as a normal .py file.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.workflow import TalosSession


# Resolve the sample and output locations from this file so the script works
# even when VS Code's selected working directory is not the repository root.
SAMPLE_CSV = PROJECT_ROOT / "data" / "sample" / "talos_demo.csv"
OUTPUT_DIRECTORY = PROJECT_ROOT / "output" / "vscode_workflow"


def main() -> None:
    """Run the full inspect, preview, apply, export, and reset example."""
    # -----------------------------------------------------------------------
    # 1. LOAD THE SOURCE DATA
    # -----------------------------------------------------------------------
    # TALOS keeps a preserved original_df and a separate working_df. That split
    # gives us a stable reference for comparisons and a safe place to try only
    # repairs that we have previewed and explicitly approved.
    talos = TalosSession.from_csv(SAMPLE_CSV)

    # -----------------------------------------------------------------------
    # 2. INSPECT AND READ THE FIRST SUMMARY
    # -----------------------------------------------------------------------
    # Inspection is read only. TALOS reports signals but does not decide whether
    # a missing value, outlier, or repeated key is wrong for your use case.
    talos.inspect()
    print(talos.summary())

    # Findings are ordinary Python dictionaries, so they can be used in scripts
    # and notebooks without converting them into web-interface objects.
    missing_findings = talos.original_findings["missing"]
    missing_by_column = pd.DataFrame(missing_findings["columns"])
    print("\nMissing values by column:")
    print(missing_by_column.to_string(index=False))

    # The score includes component values and weights, which makes it possible
    # to explain the total instead of treating it as an opaque pass/fail label.
    score_components = pd.DataFrame(talos.original_findings["score"]["components"])
    print("\nIntegrity score components:")
    print(score_components.to_string(index=False))

    # -----------------------------------------------------------------------
    # 3. PREVIEW BULK TEXT NORMALISATION
    # -----------------------------------------------------------------------
    # The preview describes the exact action, affected rows and representative
    # changes. Building it does not change working_df or add a ledger record.
    text_plan = talos.preview_text_normalisation(
        columns=["region", "membership_tier"],
        default_rule="proper",
        # A column rule takes precedence over the global rule for that field.
        column_rules={"region": "UPPERCASE"},
        # A value-level custom mapping takes precedence over both case rules.
        value_overrides={"region": {"NORTH": "North"}},
        trim_whitespace=True,
        collapse_spaces=True,
    )
    print("\n" + text_plan.summary())
    if not text_plan.examples.empty:
        print("\nRepresentative proposed changes:")
        print(text_plan.examples.to_string(index=False))

    # -----------------------------------------------------------------------
    # 4. APPLY ONLY AFTER REVIEW
    # -----------------------------------------------------------------------
    # apply() accepts a plan from this session and revision only. It creates a
    # fresh working copy and records the approved operation in the ledger.
    talos.apply(text_plan)

    # Reinspection refreshes the score and quality signals for the new working
    # revision. The source findings and original DataFrame stay available.
    talos.reinspect()
    print("\nAfter the approved text normalisation:")
    print(talos.summary())

    before_missing = talos.original_findings["missing"]["total_missing_cells"]
    after_missing = talos.working_findings["missing"]["total_missing_cells"]
    comparison = pd.DataFrame(
        [
            {"Measure": "Missing cells", "Original": before_missing, "Working copy": after_missing},
            {
                "Measure": "Integrity score",
                "Original": talos.integrity_score,
                "Working copy": talos.working_integrity_score,
            },
        ]
    )
    print("\nBefore and after:")
    print(comparison.to_string(index=False))

    # The ledger is a normal list of dictionaries and can be converted to a
    # DataFrame for notebooks, custom logging, or a downstream audit step.
    ledger_table = pd.DataFrame(talos.transformation_ledger)
    print("\nApproved transformation ledger:")
    print(ledger_table.to_string(index=False))

    # -----------------------------------------------------------------------
    # 5. SAVE THE CLEANED DATA AND REPORTS
    # -----------------------------------------------------------------------
    # These methods create missing parent folders and return pathlib Paths.
    # The output folder is ignored by Git so running this guide leaves the
    # repository's tracked sample and source files untouched.
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    cleaned_path = talos.export_cleaned_csv(OUTPUT_DIRECTORY / "talos_demo_cleaned.csv")
    html_path = talos.export_html_report(OUTPUT_DIRECTORY / "talos_demo_report.html")
    pdf_path = talos.export_pdf_report(OUTPUT_DIRECTORY / "talos_demo_report.pdf")
    evidence_path = talos.export_evidence_pack(
        OUTPUT_DIRECTORY / "talos_demo_evidence.zip", include_pdf=False
    )
    table_paths = talos.export_evidence_tables(OUTPUT_DIRECTORY / "evidence_tables")
    print("\nCreated files:")
    for output_path in [cleaned_path, html_path, pdf_path, evidence_path, *table_paths]:
        print(f"  {output_path}")

    # -----------------------------------------------------------------------
    # 6. RESET WHEN YOU WANT TO START REVIEW AGAIN
    # -----------------------------------------------------------------------
    # Reset restores the working copy from the untouched source, clears the
    # ledger, and recalculates the source/working inspection state. Files already
    # exported above remain available for review.
    talos.reset()
    print("\nAfter reset:")
    print(talos.summary())


if __name__ == "__main__":
    main()
