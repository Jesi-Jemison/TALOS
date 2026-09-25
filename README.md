# ⚙️ TALOS

[Open the live TALOS app](https://talos-app.streamlit.app/)

TALOS is a lightweight Python data profiling tool designed to inspect datasets before they make their way into analysis.

The current stage focuses on CSV intake and basic structure. Planned later stages will add checks for common data-quality problems and explain what they mean.

> A guardian at the gate between messy data and trustworthy analysis.

---

## ✅ Currently Implemented — Stage 2

TALOS currently accepts CSV files and displays:

- uploaded filename and readable file size
- row and column counts
- counts of numeric, text, boolean, and pandas-identified datetime columns
- each column's name, pandas dtype, and broad TALOS type
- a preview of the first 10 rows

Uploaded files are processed in memory during the current Streamlit session and are not intentionally stored. Please do not upload confidential, sensitive, or personally identifiable information.

TALOS profiles structure only at this stage. It does not yet assess missing values, duplicates, outliers, or other data-quality issues.

---

## 🎯 What TALOS plans to check

TALOS is being built to identify:

- missing values
- duplicate records
- inconsistent categories
- potential identifier issues
- structural problems
- numerical outliers
- unusual or suspicious values

The goal is not to automatically “fix” data.

TALOS highlights what deserves investigation so the person working with the dataset can decide what action is appropriate.

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

The dataset profile step is implemented. Quality checks, issue summaries, scoring, and reports are planned for later stages.

```text
CSV
 ↓
Dataset Profile
 ↓
Quality Checks
 ↓
Issue Summary
 ↓
Dataset Integrity Score
 ↓
Interactive Report
```

---

## 🔍 Planned Check Details

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

An outlier is not automatically an error.

TALOS will identify unusual values without assuming they are incorrect.

### Structural Issues

Look for things such as:

- completely empty columns
- constant columns
- unexpected duplicate identifiers
- unusually high-cardinality fields

---

## 📊 Planned Dataset Integrity Score

TALOS will include a custom Dataset Integrity Score designed to summarise the severity of detected issues.

The score will be:

- transparent
- deterministic
- documented
- explainable

It will be an illustrative project metric rather than an industry-standard data quality measure.

---

## 👹 Planned Demo Dataset

TALOS will include a deliberately messy fictional dataset so the application can be tested without requiring users to upload their own data. The sample folder is currently a placeholder.

The demo dataset will contain examples of:

- missing data
- duplicates
- inconsistent categories
- suspicious values
- outliers
- structural problems

---

## 🔒 Data Handling

TALOS is intended as a portfolio demonstration tool.

Uploaded files will not be intentionally stored permanently.

Users should not upload confidential, sensitive or personally identifiable information.

---

## 📁 Project Structure

```text
TALOS/
│
├── app.py
├── README.md
├── requirements.txt
├── .gitignore
│
├── src/
│   ├── __init__.py
│   └── profiler.py
│
├── data/
│   └── sample/
│
├── tests/
│   └── test_profiler.py
│
└── assets/
    └── screenshots/
```

The structure will grow gradually as functionality is added.

---

## 🚧 Current Status

**Stage 2 — Dataset Intake & Profiling**

The app accepts CSV files, reports their basic structure and previews the first ten rows. Empty, malformed, or unreadable files receive a clear message instead of a traceback. The test suite covers the loader, column classification, profile output, and file-size formatting.

Data-quality checks have not been implemented and will be added in a later stage.
---

## 🔮 Future Improvements

Potential later additions include:

- Excel support
- downloadable reports
- downloadable cleaned datasets
- configurable validation rules
- database connections
- schema validation
- expanded visualisations

These are deliberately outside the first version so the project remains understandable and maintainable.

---

## 🐈‍⬛ Project Approach

TALOS is intentionally being built with straightforward, readable Python.

The priority is to create something that is:

- useful
- explainable
- testable
- maintainable
- easy to discuss in an interview

No unnecessary enterprise architecture.

No cleverness for the sake of cleverness.

Just clear Python doing useful things.
