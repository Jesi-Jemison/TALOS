# Use TALOS from VS Code, Python, or a notebook

TALOS has one Python core shared by the Streamlit app, scripts, notebooks, and
the command-line interface. Start with the repository's synthetic demo CSV;
it contains no real personal information.

## 1. Clone and open the repository

Open a terminal and run:

```bash
git clone https://github.com/Jesi-Jemison/TALOS.git
cd TALOS
```

In VS Code, choose **File → Open Folder** and select the `TALOS` folder. Open a
terminal in VS Code with **Terminal → New Terminal**. The terminal should start
in the repository folder; the commands below assume that location.

## 2. Create and activate a virtual environment

A virtual environment keeps TALOS's Python packages separate from other
projects.

**Windows PowerShell:**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, the same environment can be activated from
Command Prompt:

```bat
.venv\Scripts\activate.bat
```

**macOS or Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

After activation, the terminal prompt usually begins with `(.venv)`. In VS
Code, choose the matching interpreter with **Python: Select Interpreter** from
the Command Palette (`Ctrl+Shift+P`, or `Cmd+Shift+P` on macOS).

## 3. Install requirements

For only the standalone Python API and CLI:

```bash
python -m pip install -r requirements-core.txt
```

For the Streamlit browser app and its tests:

```bash
python -m pip install -r requirements.txt
```

## 4. Run the commented VS Code example

From the repository folder:

```bash
python examples/vscode_workflow.py
```

The script opens `data/sample/talos_demo.csv`, prints findings, previews a text
normalisation plan, applies it to the separate working copy, reinspects, writes
reports and evidence under `output/vscode_workflow/`, and demonstrates reset.
Open that output folder in VS Code to inspect the CSV, HTML, PDF, and ZIP files.

## 5. Run the CLI

Print a summary without writing output files:

```bash
python talos_cli.py inspect data/sample/talos_demo.csv
```

Write reports and finding tables into an output folder:

```bash
python talos_cli.py inspect data/sample/talos_demo.csv --output output/talos_cli
```

The output includes cleaned CSV, transformation log, HTML and PDF reports,
individual original finding CSVs, and an evidence ZIP. The CLI inspects and
exports; programmatic transformations are available through `TalosSession`.

## 6. Use TALOS in your own script

Create a Python file in the repository, for example `my_inspection.py`:

```python
from src.workflow import TalosSession

talos = TalosSession.from_csv("data/sample/talos_demo.csv")
talos.inspect()
print(talos.summary())
print(talos.original_findings["missing"])
```

The same API works in a notebook cell:

```python
from src.workflow import TalosSession

talos = TalosSession.from_csv("my_data.csv")
talos.inspect()
talos.original_findings["missing"]
```

## Preview other repair types

The lower-level `preview()` method uses the same action names and parameters as
the existing TALOS transformation engine. Every action remains a preview until
you call `apply()`:

```python
# Trim whitespace in one text column.
plan = talos.preview({"type": "normalize_whitespace", "column": "region"})
print(plan.summary())
talos.apply(plan)
talos.reinspect()

# Fill a numeric field with its median, or use method="custom" and value=...
plan = talos.preview(
    {"type": "fill_numeric_missing", "column": "annual_spend", "method": "median"}
)

# Fill a text field with its most common value (method="mode") or a supplied
# value (method="custom", value="Unclassified").
plan = talos.preview(
    {"type": "fill_text_missing", "column": "region", "method": "mode"}
)

# Other existing operations include consolidate_category, remove_exact_duplicates,
# remove_rows_with_missing, and remove_empty_column. Their parameters are visible
# in the Streamlit Forge's current repair actions and in src/transformations.py.
```

For multiple coordinated changes, pass a list of action dictionaries to
`preview([...])`. Review the plan and examples before applying it.

Bulk text normalisation is intentionally limited in its recommendations:
columns named like identifiers, names, email addresses, or free-text notes are
not suggested as controlled categories because changing letter case can alter
identity or meaning. You can still select a field explicitly after reviewing
its contents; TALOS adds a warning to that preview.

To start with an existing DataFrame instead, use
`TalosSession.from_dataframe(frame)`. TALOS creates its own deep copies, so
normal scalar values and assignments in the session do not change the caller's
DataFrame. Treat the returned `original_df` and `working_df` values as snapshots;
edit them through a previewed plan and `apply()` so the ledger stays accurate.

## 7. Common path issues

- A relative path such as `"my_data.csv"` is resolved from the **current working
  directory**, which may differ from the folder containing your `.py` file.
- In VS Code, check the path shown in the integrated terminal before running a
  command. Use `pwd` on macOS/Linux or `cd` in Command Prompt/PowerShell.
- For a script-relative file, build a path from the script location with
  `Path(__file__).resolve().parent / "my_data.csv"`.
- Use an absolute path if the input is outside the project. Python accepts
  `Path` objects as well as strings.
- The example uses its own file location to find the repository's demo data,
  so it does not rely on the terminal's current folder.

## 8. Common environment issues

- **`python` is not found:** install Python 3, reopen VS Code, then try `py` on
  Windows or `python3` on macOS/Linux.
- **A package is missing:** activate `.venv` in the current terminal and run the
  matching `pip install -r ...` command again.
- **Imports such as `No module named 'src'` fail:** open the `TALOS` repository
  folder, then run your script from that folder. The example works from other
  working directories because it resolves its own sample path, but your own
  scripts still need the repository root on Python's import path.
- **VS Code uses a different Python:** select `.venv` with **Python: Select
  Interpreter**, then open a fresh terminal so it activates that environment.
- **A CSV cannot be read:** verify that it is a non-empty comma-separated file
  and that the path points to the file, not just its parent folder. TALOS reads
  UTF-8 CSV and falls back to Latin-1 for older exports.
