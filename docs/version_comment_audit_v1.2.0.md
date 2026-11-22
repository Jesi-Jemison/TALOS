<!-- TALOS FILE VERSION: v1.2.0 -->
# TALOS v1.2.0 version-comment audit

This is a path-by-path audit of tracked project files for the v1.2.0 release.
Text and source files use syntax-safe comments; binary metadata preserves the
decoded artwork. The MIT license and empty Git placeholders are intentionally
unchanged. The prior JPEG screenshots remain v1.1.2 visual references; the
local browser preview blocked localhost, so they are not presented as new-flow
test captures.

| Path | Version marker | Notes |
| --- | --- | --- |
| `.gitignore` | Line comment | `# TALOS FILE VERSION: v1.2.0`; no configuration or dependency semantics changed by the marker. |
| `.streamlit/config.toml` | Line comment | `# TALOS FILE VERSION: v1.2.0`; no configuration or dependency semantics changed by the marker. |
| `CHANGELOG.md` | HTML comment | `<!-- TALOS FILE VERSION: v1.2.0 -->`. |
| `LICENSE` | Exempt — no marker | Preserved verbatim to keep MIT license terms intact. |
| `README.md` | HTML comment | `<!-- TALOS FILE VERSION: v1.2.0 -->`. |
| `app.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `assets/screenshots/.gitkeep` | Exempt — empty placeholder | Zero-byte directory sentinel; adding a comment would make it non-empty without adding project content. |
| `assets/screenshots/talos-demo-column-removal-20260925.jpg` | JPEG COM metadata segment | `TALOS FILE VERSION: v1.2.0`; decoded pixels were compared before/after and are identical. Image content remains a prior-release reference. |
| `assets/screenshots/talos-demo-evidence-20260925.jpg` | JPEG COM metadata segment | `TALOS FILE VERSION: v1.2.0`; decoded pixels were compared before/after and are identical. Image content remains a prior-release reference. |
| `assets/screenshots/talos-demo-forge-20260925.jpg` | JPEG COM metadata segment | `TALOS FILE VERSION: v1.2.0`; decoded pixels were compared before/after and are identical. Image content remains a prior-release reference. |
| `assets/screenshots/talos-demo-forge-20260926.jpg` | JPEG COM metadata segment | `TALOS FILE VERSION: v1.2.0`; decoded pixels were compared before/after and are identical. Image content remains a prior-release reference. |
| `assets/screenshots/talos-demo-normalisation-20260926.jpg` | JPEG COM metadata segment | `TALOS FILE VERSION: v1.2.0`; decoded pixels were compared before/after and are identical. Image content remains a prior-release reference. |
| `assets/screenshots/talos-demo-normalisation-overrides-20260926.jpg` | JPEG COM metadata segment | `TALOS FILE VERSION: v1.2.0`; decoded pixels were compared before/after and are identical. Image content remains a prior-release reference. |
| `assets/screenshots/talos-demo-normalisation-styles-20260926.jpg` | JPEG COM metadata segment | `TALOS FILE VERSION: v1.2.0`; decoded pixels were compared before/after and are identical. Image content remains a prior-release reference. |
| `assets/screenshots/talos-demo-overview-20260925.jpg` | JPEG COM metadata segment | `TALOS FILE VERSION: v1.2.0`; decoded pixels were compared before/after and are identical. Image content remains a prior-release reference. |
| `assets/screenshots/talos-demo-reinspection-20260925.jpg` | JPEG COM metadata segment | `TALOS FILE VERSION: v1.2.0`; decoded pixels were compared before/after and are identical. Image content remains a prior-release reference. |
| `assets/screenshots/talos-demo-score-20260925.jpg` | JPEG COM metadata segment | `TALOS FILE VERSION: v1.2.0`; decoded pixels were compared before/after and are identical. Image content remains a prior-release reference. |
| `assets/screenshots/talos-landing-20260925.jpg` | JPEG COM metadata segment | `TALOS FILE VERSION: v1.2.0`; decoded pixels were compared before/after and are identical. Image content remains a prior-release reference. |
| `assets/screenshots/talos-light-theme-20260925.jpg` | JPEG COM metadata segment | `TALOS FILE VERSION: v1.2.0`; decoded pixels were compared before/after and are identical. Image content remains a prior-release reference. |
| `assets/screenshots/talos-light-theme-20260926.jpg` | JPEG COM metadata segment | `TALOS FILE VERSION: v1.2.0`; decoded pixels were compared before/after and are identical. Image content remains a prior-release reference. |
| `assets/talos-emblem.svg` | XML comment | Comment before the SVG root; vector appearance is unchanged. |
| `assets/talos-sentinel-panel.webp` | WebP XMP metadata chunk | `talos:fileVersion="v1.2.0"`; decoded pixels and dimensions were verified unchanged. |
| `assets/talos.css` | CSS comment | `/* TALOS FILE VERSION: v1.2.0 */`. |
| `data/sample/.gitkeep` | Exempt — empty placeholder | Zero-byte directory sentinel; adding a comment would make it non-empty without adding project content. |
| `data/sample/talos_demo.csv` | Sidecar: `data/sample/talos_demo.csv.version` | The CSV remains valid ordinary CSV with no comment row or prefix. |
| `data/sample/talos_demo.csv.version` | Plain-text `#` sidecar comment | Keeps the CSV payload parseable by normal readers. |
| `docs/demo_dataset_sources.md` | HTML comment | `<!-- TALOS FILE VERSION: v1.2.0 -->`. |
| `docs/performance_notes.md` | HTML comment | `<!-- TALOS FILE VERSION: v1.2.0 -->`. |
| `docs/portfolio_summary.md` | HTML comment | `<!-- TALOS FILE VERSION: v1.2.0 -->`. |
| `docs/scoring_methodology.md` | HTML comment | `<!-- TALOS FILE VERSION: v1.2.0 -->`. |
| `docs/version_comment_audit_v1.2.0.md` | HTML comment | `<!-- TALOS FILE VERSION: v1.2.0 -->`. |
| `docs/vscode_usage.md` | HTML comment | `<!-- TALOS FILE VERSION: v1.2.0 -->`. |
| `examples/vscode_workflow.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `requirements-core.txt` | Line comment | `# TALOS FILE VERSION: v1.2.0`; no configuration or dependency semantics changed by the marker. |
| `requirements-test.txt` | Line comment | `# TALOS FILE VERSION: v1.2.0`; no configuration or dependency semantics changed by the marker. |
| `requirements.txt` | Line comment | `# TALOS FILE VERSION: v1.2.0`; no configuration or dependency semantics changed by the marker. |
| `src/__init__.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `src/evidence.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `src/profiler.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `src/quality_checks.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `src/reporting.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `src/scoring.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `src/theme.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `src/transformations.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `src/workflow.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `talos_cli.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `tests/.gitkeep` | Exempt — empty placeholder | Zero-byte directory sentinel; adding a comment would make it non-empty without adding project content. |
| `tests/test_app_flow.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `tests/test_cli.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `tests/test_evidence.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `tests/test_profiler.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `tests/test_quality_checks.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `tests/test_release_metadata.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `tests/test_reporting.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `tests/test_scoring.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `tests/test_theme.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `tests/test_transformations.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |
| `tests/test_workflow.py` | Python comment after module docstring | `# TALOS FILE VERSION: v1.2.0`; executable behavior is unchanged unless separately described in this release. |

## Repository-view verification

The release commit message is `Release TALOS v1.2.0: guided inspection flow`.
On `feature/guided-inspection-v1.2.0`, GitHub's per-file commit history was
checked for all 54 paths in this release commit. Every path reports the same
message above. The feature branch is available as an open draft pull request;
it has not been merged or deployed. This audit documents comment coverage
separately from that commit metadata view.
