from io import BytesIO
from zipfile import ZipFile

import pandas as pd

from src.evidence import (
    build_category_variants_table,
    build_comparison_table,
    build_duplicate_rows_table,
    build_evidence_pack,
    build_evidence_readme,
    build_identifier_findings_table,
    build_integrity_score_table,
    build_missing_values_table,
    build_outlier_rows_table,
    build_result_tables,
    build_structural_findings_table,
)
from src.quality_checks import (
    inspect_category_consistency,
    inspect_duplicates,
    inspect_missing_values,
    inspect_numeric_outliers,
    inspect_structure,
)
from src.scoring import calculate_integrity_score


def inspect_all(df):
    findings = {
        "missing": inspect_missing_values(df),
        "duplicates": inspect_duplicates(df),
        "categories": inspect_category_consistency(df),
        "outliers": inspect_numeric_outliers(df),
        "structure": inspect_structure(df),
    }
    findings["score"] = calculate_integrity_score(
        df,
        findings["missing"],
        findings["duplicates"],
        findings["categories"],
        findings["outliers"],
        findings["structure"],
    )
    return findings


def make_export_frame():
    df = pd.DataFrame(
        {
            "record_id": [1, 2, 2, 4, 5, 6, 7, 8, 9, 10],
            "region": ["NSW", "nsw", " NSW ", "VIC", "vic", None, "NSW", "QLD", "SA", "WA"],
            "amount": [1, 2, 2, 4, 5, 6, 7, 8, 9, 1000],
            "blank": [None] * 10,
            "constant": ["same"] * 10,
        }
    )
    # Two records are exact copies, while record_id also has a non-exact repeat.
    df.loc[len(df)] = df.loc[1]
    return df


def test_missing_category_identifier_and_structural_tables_follow_findings():
    df = make_export_frame()
    findings = inspect_all(df)

    missing = build_missing_values_table(findings["missing"])
    assert len(missing) == len(df.columns)
    assert missing.loc[missing["Column"] == "region", "Missing count"].item() == 1

    identifiers = findings["duplicates"]
    assert identifiers["identifier_candidates"][0]["column"] == "record_id"

    categories = build_category_variants_table(findings["categories"])
    region_variants = categories[categories["Column"] == "region"]
    assert set(region_variants["Observed variant"]) >= {"NSW", "nsw", " NSW "}
    nsw_variants = region_variants[region_variants["Normalized form"] == "nsw"]
    assert set(nsw_variants["Proposed canonical value"]) == {"NSW"}

    structural = build_structural_findings_table(findings["structure"])
    assert {"Empty column", "Constant column"}.issubset(set(structural["Finding type"]))
    assert {"Column", "Finding type", "Explanation", "Supporting metric"} == set(structural.columns)


def test_duplicate_export_contains_all_rows_involved_and_source_positions():
    df = make_export_frame()
    table = build_duplicate_rows_table(df, inspect_duplicates(df))

    assert len(table) == 2
    assert table["TALOS source row (1-based)"].tolist() == [2, 11]
    assert table["TALOS duplicate role"].tolist() == ["First matching row", "Repeated row"]
    assert table["record_id"].tolist() == [2, 2]
    assert "exact_duplicate_row_count" not in table.columns


def test_duplicate_export_does_not_overwrite_colliding_source_columns():
    df = pd.DataFrame(
        {
            "TALOS source row (1-based)": ["a", "a"],
            "TALOS duplicate role": ["b", "b"],
        }
    )
    table = build_duplicate_rows_table(df, inspect_duplicates(df))

    assert len(table.columns) == len(set(table.columns))
    assert table.iloc[0]["TALOS source row (1-based) (2)"] == 1
    assert table.iloc[0]["TALOS source row (1-based)"] == "a"


def test_outlier_export_contains_every_flagged_value_with_bounds_and_row_number():
    df = pd.DataFrame({"amount": list(range(1, 21)) + [1000, -500]})
    findings = inspect_numeric_outliers(df)
    table = build_outlier_rows_table(df, findings)

    assert set(table["Value"]) == {-500.0, 1000.0}
    assert table["Source row (1-based)"].tolist() == [21, 22]
    assert set(table["Outlier status"]) == {"Above upper bound", "Below lower bound"}
    assert {"Q1", "Median", "Q3", "Lower bound", "Upper bound"}.issubset(table.columns)


def test_result_tables_omit_empty_findings_but_keep_profile_and_score():
    df = pd.DataFrame({"amount": [1, 2, 3, 4, 5, 6, 7, 8]})
    profile = {"columns": [{"column": "amount", "pandas_dtype": "int64", "talos_type": "Numeric"}]}
    findings = inspect_all(df)
    tables = build_result_tables(df, profile, findings)

    assert "structure.csv" in tables
    assert "missing_values.csv" in tables
    assert "integrity_score.csv" in tables
    assert "duplicate_rows.csv" not in tables
    assert "identifier_findings.csv" not in tables
    assert "category_variants.csv" not in tables
    assert "outliers.csv" not in tables
    assert "structural_findings.csv" not in tables
    assert list(build_integrity_score_table(findings["score"])["Weight"]) == [30, 20, 15, 20, 15]


def test_applicable_result_tables_cover_the_major_visible_findings():
    df = make_export_frame()
    findings = inspect_all(df)
    profile = {
        "columns": [
            {"column": str(column), "pandas_dtype": str(df[column].dtype), "talos_type": "Text"}
            for column in df.columns
        ]
    }

    tables = build_result_tables(df, profile, findings)
    identifiers = build_identifier_findings_table(findings["duplicates"])

    assert {
        "structure.csv",
        "missing_values.csv",
        "duplicate_rows.csv",
        "identifier_findings.csv",
        "category_variants.csv",
        "outliers.csv",
        "structural_findings.csv",
        "integrity_score.csv",
    }.issubset(tables)
    assert tables["structure.csv"]["Column"].tolist() == list(df.columns)
    assert tables["duplicate_rows.csv"]["record_id"].tolist() == [2, 2]
    assert identifiers.loc[0, "Candidate identifier"] == "record_id"
    assert identifiers.loc[0, "Repeated value examples"]
    assert {"Component", "Weight", "Component score", "Weighted points"}.issubset(
        tables["integrity_score.csv"].columns
    )


def test_comparison_table_includes_required_before_after_signals():
    original = make_export_frame()
    working = original.drop(columns=["blank"]).drop_duplicates()
    table = build_comparison_table(original, working, inspect_all(original), inspect_all(working))

    assert table["Measure"].tolist() == [
        "Rows",
        "Columns",
        "Missing cells",
        "Exact duplicate rows",
        "Category variant groups",
        "IQR outlier values",
        "Empty columns",
        "Integrity score",
    ]
    assert table.loc[table["Measure"] == "Rows", "Original"].item() == 11
    assert table.loc[table["Measure"] == "Rows", "Working copy"].item() == 10


def test_evidence_pack_contains_readme_and_only_supplied_files():
    readme = build_evidence_readme(
        "sample.csv",
        "2026-09-25T10:00:00+00:00",
        {"inspection_report.html": "Full report", "structure.csv": "Column profile"},
    )
    archive_bytes = build_evidence_pack(
        {"README.txt": readme, "inspection_report.html": b"<h1>TALOS</h1>", "structure.csv": b"Column\namount\n"}
    )

    with ZipFile(BytesIO(archive_bytes)) as archive:
        assert archive.namelist() == [
            "talos_evidence_pack/README.txt",
            "talos_evidence_pack/inspection_report.html",
            "talos_evidence_pack/structure.csv",
        ]
        assert "The uploaded source was preserved" in archive.read(
            "talos_evidence_pack/README.txt"
        ).decode("utf-8")


def test_evidence_pack_rejects_unsafe_member_paths():
    try:
        build_evidence_pack({"../private.csv": b"data"})
    except ValueError as error:
        assert "Unsafe" in str(error)
    else:
        raise AssertionError("Path traversal filename should be rejected")
