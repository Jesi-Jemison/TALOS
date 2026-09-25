# ⚙️ TALOS

[Open the live TALOS app](https://talos-app.streamlit.app/)

TALOS is a Python data inspection tool built around a simple idea: **a watchful guardian should inspect data before it is trusted.** Inspired by the bronze automaton of Greek mythology, TALOS stands between messy source data and reliable analysis.

It profiles an uploaded CSV, explains quality signals, proposes possible repairs, and prepares a separate working copy only when the user approves. The original uploaded DataFrame remains untouched.

## What TALOS does

- Profiles file details, dataset dimensions, broad column types, and a ten-row preview.
- Inspects missing values, exact duplicate rows, category variants, IQR outliers, structural signals, and possible identifiers.
- Calculates a transparent, custom Dataset Integrity Score.
- Offers user-controlled transformations in **The Forge**, previews them, and records approved changes in a session-only **Transformation Ledger**.
- Exports the working copy as CSV, the transformation ledger as CSV, and a self-contained **TALOS Inspection Report** as HTML.

Signals are not proof that data is wrong. Repeated records, outliers, negative values, and constant fields can be valid in context. TALOS does not automatically modify data or infer business meaning.

## The Forge and data-state model

The app keeps four distinct pieces of state:

```text
uploaded CSV → original_df → findings and suggestions
                         ↘ working_df → approved transformations → ledger
```

- `original_df` is kept as the source for comparison and reset.
- `working_df` begins as a deep copy and is replaced only after the user previews and approves a transformation.
- Findings are recalculated for the current working copy; the original inspection remains separately available.
- The Transformation Ledger records each approved action and its parameters and examples. Reset restores a fresh copy of `original_df` and clears the ledger.

Supported actions include whitespace normalization, choosing a canonical form for detected category variants, exact duplicate-row removal, user-selected missing-value handling, and removal of completely empty columns. TALOS leaves outliers, identifier repeats, high-cardinality text, and other context-dependent signals alone.

## Dataset Integrity Score

The score is a **custom illustrative TALOS heuristic**, not an industry standard or a guarantee that data is correct. It ranges from 0 to 100 with these weights:

| Component | Weight |
| --- | ---: |
| Completeness | 30% |
| Exact duplicate rows | 20% |
| Category consistency | 15% |
| Structural health | 20% |
| IQR outlier signal | 15% |

The completeness component combines the missing-cell percentage and the share of columns with any missing values, so gaps distributed across many fields are visible in the score. The app shows every component and weight. See [the scoring methodology](docs/scoring_methodology.md) for formulas, bands, exclusions, and limitations.

## Run TALOS locally

```bash
git clone https://github.com/Jesi-Jemison/TALOS.git
cd TALOS
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Run the automated tests with:

```bash
python -m pytest -q
```

## Data handling

CSV bytes, the original DataFrame, working copy, report, and ledger are processed in the Streamlit session. TALOS does not intentionally save them to persistent storage. Do not upload confidential, sensitive, or personally identifiable information.

## Project structure

```text
TALOS/
├── app.py                         # Streamlit layout and interaction
├── .streamlit/config.toml         # Dark application theme
├── assets/
│   ├── talos-emblem.svg           # Original guardian insignia
│   ├── talos.css                  # TALOS interface styling
│   └── screenshots/
├── data/sample/                   # Reserved for future showcase data
├── docs/
│   └── scoring_methodology.md     # Score calculations and limits
├── src/
│   ├── profiler.py                # CSV loading and structural profile
│   ├── quality_checks.py          # Read-only data-quality checks
│   ├── scoring.py                 # Weighted, explainable score
│   ├── transformations.py         # Copy-returning working-copy operations
│   └── reporting.py               # CSV exports and HTML inspection report
└── tests/                         # Profiling, checks, transformations, and reports
```

The interface stays in `app.py`; reusable profiling, inspection, transformation, scoring, and report logic lives in `src/`. The implementation uses pandas and straightforward Python rather than third-party profiling frameworks.

## Current status

Stages 1–11 are implemented: infrastructure, CSV intake and profiling, quality checks, an explainable score, user-approved working-copy transformations, CSV exports, and the HTML Inspection Report. Stage 12 demo mode and Stage 13 final product polish remain future work.

TALOS is an entry-to-mid-level Python portfolio project. The priority is readable pandas logic, explicit functions, tests, and methods that can be explained in an interview. The Forge proposes; the user decides.
