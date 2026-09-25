# ⚙️ TALOS

TALOS is a lightweight Python data quality checker designed to inspect datasets before they make their way into analysis.

The project focuses on identifying common data-quality problems, explaining what they mean, and presenting the results in a clear, usable way.

> A guardian at the gate between messy data and trustworthy analysis.

---

## 🎯 What TALOS will check

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

An outlier is not automatically an error.

TALOS will identify unusual values without assuming they are incorrect.

### Structural Issues

Look for things such as:

- completely empty columns
- constant columns
- unexpected duplicate identifiers
- unusually high-cardinality fields

---

## 📊 Dataset Integrity Score

TALOS will include a custom Dataset Integrity Score designed to summarise the severity of detected issues.

The score will be:

- transparent
- deterministic
- documented
- explainable

It will be an illustrative project metric rather than an industry-standard data quality measure.

---

## 👹 Demo Dataset

TALOS will include a deliberately messy fictional dataset so the application can be tested without requiring users to upload their own data.

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
│   ├── profiler.py
│   ├── quality_checks.py
│   ├── scoring.py
│   └── visualisations.py
│
├── data/
│   └── sample/
│
├── tests/
│
├── assets/
│   └── screenshots/
│
└── docs/
```

The structure will grow gradually as functionality is added.

---

## 🚧 Current Status

TALOS is currently in development.

The first stage is focused on:

- establishing the repository structure
- creating the Streamlit interface
- enabling CSV uploads
- confirming the application runs successfully

Data-quality checks will be added incrementally after the basic application structure is working.

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
