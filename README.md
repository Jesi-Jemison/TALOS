# ⚙️ TALOS

[Open the live TALOS app](https://talos-app.streamlit.app/)

TALOS is a Python data inspection tool built around a simple idea: **a watchful guardian should inspect data before it is trusted.** Inspired by the bronze automaton guardian of Greek mythology, TALOS stands between messy source data and reliable analysis.

It accepts a CSV, describes its structure, surfaces quality signals, and explains a custom integrity score. TALOS reports what may deserve attention. It does not silently alter the uploaded data.

## What TALOS inspects

- **Dataset profile:** file name and size, row and column counts, broad column types, column dtypes, and a ten-row preview.
- **Missing values:** counts, percentages, severity bands, and short explanations of possible effects.
- **Duplicate records:** exact repeated rows and name-based possible identifier fields, with repeats reported separately.
- **Category consistency:** case and whitespace variants in suitable text columns. Likely names, free text, and very high-cardinality fields are skipped.
- **Numeric outliers:** values outside the IQR bounds (`Q1 − 1.5 × IQR` and `Q3 + 1.5 × IQR`) for numeric fields that meet minimum sample and variation thresholds.
- **Structural signals:** empty or constant columns, high-cardinality text, possible identifier patterns, and negative or zero-heavy numeric fields.
- **Dataset Integrity Score:** a visible weighted summary of five checks, with the contribution and weight of each component shown.

These are review signals, not automatic proof that a value is wrong. For example, a repeated record, an outlier, or a negative number may be valid in its context. TALOS does not fill missing values, remove duplicates, standardize categories, or otherwise change the uploaded DataFrame.

## Dataset Integrity Score

The score is a **custom illustrative TALOS heuristic**, not an industry standard, certification, or guarantee that a dataset is correct. It ranges from 0 to 100 and is made from these weighted components:

| Component | Weight |
| --- | ---: |
| Completeness | 30% |
| Exact duplicate rows | 20% |
| Category consistency | 15% |
| Structural health | 20% |
| IQR outlier signal | 15% |

Each component is calculated directly from the findings and limited to the 0–100 range. The overall score is the rounded weighted average. A dataset without rows or columns is marked **Not assessable**. The component calculations, score bands, exclusions, and limitations are documented in [the scoring methodology](docs/scoring_methodology.md).

The score intentionally excludes possible identifier repeats, high-cardinality text, negative values, and zero-heavy fields. Their meaning depends on the dataset and cannot be established from a CSV alone.

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

Uploaded CSV bytes are read in memory for the Streamlit session and are not intentionally saved by TALOS. Do not upload confidential, sensitive, or personally identifiable information.

## Project structure

```text
TALOS/
├── app.py                         # Streamlit layout and interaction
├── .streamlit/config.toml         # Dark application theme
├── assets/
│   ├── talos.css                  # Restrained TALOS interface styling
│   └── screenshots/
├── data/sample/                   # Reserved for future sample data
├── docs/
│   └── scoring_methodology.md     # Score calculations and limitations
├── src/
│   ├── profiler.py                # CSV loading and structural profile
│   ├── quality_checks.py          # Read-only data-quality checks
│   └── scoring.py                 # Weighted, explainable score
└── tests/                         # Automated checks for profile, findings, and score
```

The interface stays in `app.py`; reusable profiling, inspection, and scoring logic lives in `src/`. The implementation uses pandas and straightforward Python rather than third-party profiling frameworks.

## Current status

Stages 1 through 8 are implemented: project setup, CSV intake and profiling, missing-value inspection, duplicate and identifier checks, category consistency, IQR outlier checks, structural signals, and the explainable Dataset Integrity Score. Automated tests cover these features, including edge cases and checks that the input data is not modified.

Future work may include user-defined validation rules and reports. Cleaning, transformed downloads, and report generation have not been implemented.

## Project approach

TALOS is built as an entry-to-mid-level Python portfolio project. The priority is clear pandas logic, small functions, descriptive names, direct tests, and methods that can be explained in an interview. Checks remain visible and conservative: when context is missing, TALOS reports a signal and leaves the decision to the analyst.
