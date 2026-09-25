"""Transparent, illustrative TALOS Dataset Integrity Score calculations."""

import pandas as pd


SCORE_WEIGHTS = {
    "Completeness": 30,
    "Exact duplicates": 20,
    "Category consistency": 15,
    "Structural health": 20,
    "Outlier signal": 15,
}


def _bounded_percentage(value: float) -> float:
    """Keep a percentage-derived component inside the score range."""
    return max(0.0, min(100.0, float(value)))


def score_band(score: int) -> str:
    """Return a short, documented label for an integer score from 0 to 100."""
    if score >= 90:
        return "Clear"
    if score >= 75:
        return "Minor observations"
    if score >= 50:
        return "Review recommended"
    if score >= 25:
        return "Significant issues"
    return "Integrity compromised"


def calculate_integrity_score(
    df: pd.DataFrame,
    missing_analysis: dict[str, object],
    duplicate_analysis: dict[str, object],
    category_analysis: dict[str, object],
    outlier_analysis: dict[str, object],
    structure_analysis: dict[str, object],
) -> dict[str, object]:
    """Combine completed inspection results into an explainable 0–100 score.

    The score is a custom heuristic, not an industry standard. Empty datasets
    return ``score=None`` because giving them a numerical score would imply
    evidence that is not present.
    """
    if df.shape[0] == 0 or df.shape[1] == 0:
        return {
            "score": None,
            "band": "Not assessable",
            "components": [],
            "weights": SCORE_WEIGHTS.copy(),
            "explanation": "TALOS needs at least one row and one column to calculate a meaningful score.",
        }

    column_count = len(df.columns)
    affected_column_percentage = (
        missing_analysis["affected_column_count"] / column_count * 100
    )
    completeness_score = 100 - (
        float(missing_analysis["missing_percentage"])
        + affected_column_percentage
    ) / 2
    normalized_group_count = category_analysis["normalized_group_count"]
    category_score = (
        100.0
        * (1 - category_analysis["inconsistent_group_count"] / normalized_group_count)
        if normalized_group_count
        else 100.0
    )
    structural_issue_count = len(structure_analysis["empty_columns"]) + len(
        structure_analysis["constant_columns"]
    )
    structural_score = 100.0 * (1 - structural_issue_count / column_count)

    component_scores = {
        "Completeness": completeness_score,
        "Exact duplicates": 100 - float(duplicate_analysis["exact_duplicate_percentage"]),
        "Category consistency": category_score,
        "Structural health": structural_score,
        "Outlier signal": 100 - float(outlier_analysis["outlier_percentage"]),
    }

    components = []
    weighted_total = 0.0
    for component_name, weight in SCORE_WEIGHTS.items():
        component_score = _bounded_percentage(component_scores[component_name])
        weighted_points = component_score * weight / 100
        weighted_total += weighted_points
        components.append(
            {
                "component": component_name,
                "weight": weight,
                "score": round(component_score, 1),
                "weighted_points": round(weighted_points, 1),
            }
        )

    score = max(0, min(100, round(weighted_total)))
    return {
        "score": score,
        "band": score_band(score),
        "components": components,
        "weights": SCORE_WEIGHTS.copy(),
        "explanation": (
            "A custom illustrative TALOS heuristic. It summarises the checks shown here; "
            "it is not an industry standard or a verdict on whether data is correct."
        ),
    }
