# ⚙️ TALOS

[Open the live TALOS app](https://talos-app.streamlit.app/)

TALOS is a Python data profiling project designed to inspect a dataset before it makes its way into analysis. It is inspired by the bronze guardian of Greek mythology: a watchful system at the gate between source data and trusted work.

> A guardian at the gate between messy data and trustworthy analysis.

---

## ✅ Currently implemented

Stage 2 provides CSV intake and structural profiling. Upload a CSV to see:

- filename and readable file size
- row and column counts
- counts of numeric, text, boolean, and pandas-identified datetime columns
- each column's name, pandas dtype, and broad TALOS type
- a preview of the first 10 rows

TALOS reads uploaded file bytes in memory for the current Streamlit session and does not intentionally store them. Please do not upload confidential, sensitive, or personally identifiable information.

TALOS does not yet assess whether values or records are correct. A date-like string, for example, stays classified as text unless pandas has already identified it as a datetime dtype.

---

## 🧠 Why I built it

A large part of real-world analysis happens before the dashboard, chart or model.

Datasets often contain small inconsistencies that can materially affect the reliability of the analysis built on top of them.

TALOS is a portfolio project designed to explore that part of the analytical workflow while developing practical Python skills around:

- data profiling
- validation
- exploratory analysis
- reusable functions
- testing
- application development
- clear technical documentation

---

## 🛠 Tech Stack

- Python
- pandas
- NumPy
- Streamlit
- pytest
- Git
- GitHub

---

## 🧩 Planned Workflow

The later quality-checking stages are planned. They are not implemented in the current app.

```text
CSV
 ↓
Dataset Profile  ← currently implemented
 ↓
Quality Checks  ← planned
 ↓
Issue Summary  ← planned
 ↓
Dataset Integrity Score  ← planned
 ↓
Interactive Report  ← planned
```

---

## 🔍 Planned Checks

### Missing Data

Identify missing values by column and calculate the percentage of affected records.

### Duplicate Records

Detect exact duplicate rows and potentially duplicated identifiers.

### Category Consistency

Flag text values that appear to represent the same category but differ because of:

- capitalisation
- whitespace
- formatting

For example:

```text
Sydney
SYDNEY
sydney
Sydney 
```

### Numerical Outliers

Use simple statistical methods such as the IQR method to identify values worth investigating.

An outlier is not automatically an error. TALOS will identify unusual values without assuming they are incorrect.

### Structural Issues

Potential checks include:

- completely empty columns
- constant columns
- unexpected duplicate identifiers
- unusually high-cardinality fields

---

## 📊 Planned Dataset Integrity Score

TALOS may include a custom Dataset Integrity Score designed to summarise the severity of detected issues.

If implemented, the score will be transparent, deterministic, documented, and explainable. It will be an illustrative project metric rather than an industry-standard data quality measure.

---

## 👹 Planned Demo Dataset

A fictional sample dataset may be added so the later quality checks can be demonstrated without asking users to upload their own data. The sample folder is currently a placeholder.

---

## 📁 Project Structure

```text
TALOS/
├── app.py
├── README.md
├── requirements.txt
├── .gitignore
├── src/
│   ├── __init__.py
│   └── profiler.py
├── data/
│   └── sample/
├── tests/
│   └── test_profiler.py
└── assets/
    └── screenshots/
```

The structure will grow gradually as functionality is added.

---

## 🚧 Current Status

**Stage 2 — Dataset Intake & Profiling**

The app accepts CSV files, reports their basic structure and previews the first ten rows. Empty, malformed, or unreadable files receive a clear message instead of a traceback. Tests cover the loader, type classification, profile output, and file-size formatting.

Quality checks will be added incrementally in a later stage.

---

## 🔮 Future Improvements

Potential later additions include:

- missing-value, duplicate, category-consistency, structural, and outlier checks
- an explainable Dataset Integrity Score
- a fictional demo dataset
- Excel support
- downloadable reports
- configurable validation rules
- database connections
- schema validation
- expanded visualisations

These are deliberately outside Stage 2 so the project remains understandable and maintainable.

---

## 🐈‍⬛ Project Approach

TALOS is intentionally being built with straightforward, readable Python.

The priority is to create something that is useful, explainable, testable, maintainable, and easy to discuss in an interview.

No unnecessary enterprise architecture. No cleverness for the sake of cleverness. Just clear Python doing useful things.
