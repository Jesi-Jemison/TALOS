# TALOS portfolio summary

**Project release: v1.1.1 · Streamlit Forge controls and report polish.**

## One-line version

TALOS is a Python and Streamlit application that inspects CSV data, explains quality signals, and lets users preview and approve repairs to a separate working copy.

## Short project card

**TALOS — Data Integrity Observation System** is a portfolio project built with Python, pandas, NumPy, Streamlit, and pytest. It profiles CSV structure; checks missingness, duplicates, category variation, outliers, and structural signals; calculates a transparent heuristic score; and exports findings as CSV, a concise PDF, a detailed HTML report, and a ZIP evidence pack. Its Streamlit Forge supports manual column removal and explicit per-column IQR actions alongside its existing repair controls. Every repair is previewed, user-approved, recorded in a transformation ledger, and followed by reinspection. The original DataFrame remains unchanged.

**Live app:** https://talos-app.streamlit.app/  
**Source:** https://github.com/Jesi-Jemison/TALOS

## Resume bullet version

- Built TALOS, a modular Python/Streamlit CSV inspection app with pandas-based quality checks, an explainable weighted integrity score, and a synthetic showcase dataset.
- Designed a safe remediation workflow that previews selected transformations, supports per-column IQR repair and manual field removal, preserves the source DataFrame, records approved changes, reinspects the working copy, and compares before/after findings.
- Added portable CSV evidence, a self-contained printable HTML report, a ZIP evidence pack, session-based themes, and pytest coverage for analysis and app flows.

## Case study

TALOS was built to make data inspection understandable before analysis begins. It loads a CSV into a session, profiles its columns, and reports missing values, exact duplicates, category variants, IQR outliers, identifier signals, and structural patterns using explicit pandas logic. A custom weighted score summarizes those checks while keeping its assumptions visible. The Forge addresses the risk that automatic cleaning can obscure analytical choices: a user selects individual repairs, reviews an estimated plan, and applies the batch to a separate working copy. TALOS then reruns its inspections, compares the working copy with the source, and records the operation and examples in a ledger. The Evidence Vault exports applicable findings, the transformed copy, and a portable HTML/ZIP dossier. Tests cover the analysis functions, export builders, and Streamlit workflows. TALOS is a decision-support example, not a guarantee of correctness or a substitute for business rules.

## Technical skills demonstrated

- Python modules, type-aware functions, error handling, and readable documentation
- pandas CSV intake, missingness, duplicates, grouping, type inspection, and IQR calculations
- Explicit statistical assumptions and a weighted scoring method
- Copy-based transformations, batch previews, reinspection, and audit-friendly records
- Streamlit session state, callbacks, downloadable artifacts, and responsive interface styling
- Unit and application-flow testing with pytest and Streamlit AppTest
- HTML escaping, safe export filenames, in-memory ZIP generation, and synthetic test data
- Performance measurement across increasing dataset sizes
