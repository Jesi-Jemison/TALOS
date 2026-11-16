# TALOS — Project Scope

Baseline: 2026-11-16. This planning note complements existing code, tests, README and CHANGELOG; it does not supersede the published release.

## Product
A Python/Streamlit data-quality workbench that previews datasets, identifies issues and supports inspectable, user-approved cleaning while keeping the original source unchanged.

## Existing scope to preserve
- Intake/preview of CSV data and synthetic demonstration.
- Missingness, duplicates, category variations, empty/constant columns and IQR outliers.
- Dataset Integrity Score with transparent diagnostic definitions.
- Forge workflow for controlled changes and reset.
- HTML dossier, cleaning ledger, evidence exports and normalisation.

## Future candidates
More comprehensive profile metrics, evidence quality, rule configuration, navigation/accessibility improvements and report consistency checks.

## Conceptual entities
Dataset, ProfileRun, QualityIssue, RepairAction, ApprovalLedger, ReportArtifact.

## Integrity requirements
No hidden destructive edits; source and working copy separated; all approved transformations reconstructible; avoid uploading private datasets to a third-party API.

## Known live app
https://talos-app.streamlit.app/
