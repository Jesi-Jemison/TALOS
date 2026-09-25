# TALOS change log

Release numbers are kept in sequence with the code already published on
`main`. `src.__version__` is the canonical machine-readable version; the README
and this log state the current product release.

## v1.1.1 — Streamlit Forge controls and report polish

This is the patch release after v1.1.0. The supplied work brief used v1.0.3,
but v1.1.0 was already the current `main` release, so this update preserves the
published version sequence.

- Added user-selected column removal with a multi-select, field-context notes,
  resulting-shape preview, last-column protection, working-copy-only updates,
  and ledger entries.
- Added per-column IQR remediation: leave unchanged, replace with missing,
  non-outlier mean, non-outlier median, custom numeric value, remove affected
  rows, or cap to the nearest IQR boundary. Row-removal estimates use the union
  of flagged row positions, and each approved action is reinspected.
- Improved light-theme alert text and backgrounds, table surfaces and headers,
  captions, expander states, and visible keyboard focus.
- Rebuilt the PDF as a concise aggregate report with a dynamic Inspection
  Summary, repair summary, Remaining Signals, before/after measures, compact
  aggregate findings, and the guardian panel aligned at the top content edge.
  Detailed row-level evidence remains in the HTML report, CSV outputs, and ZIP
  Evidence Pack.
- Replaced the generic app hero copy with the TALOS guardian protocol language
  and clarified the Guardian Summary statements.
- Refreshed the README's local Streamlit setup and added versioned project
  release notes.
