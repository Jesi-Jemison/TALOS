# TALOS Dataset Integrity Score

The Dataset Integrity Score is a **custom illustrative heuristic designed for TALOS**. It is not an industry standard, certification, or guarantee that a dataset is correct.

The score ranges from 0 to 100. Higher values mean fewer signals in the checks TALOS currently performs. Every component is visible in the app.

## Components and weights

| Component | Weight | Component calculation |
| --- | ---: | --- |
| Completeness | 30% | 100 minus the percentage of missing cells across the dataset |
| Exact duplicates | 20% | 100 minus the percentage of rows that repeat an earlier complete row |
| Category consistency | 15% | 100 minus the percentage of eligible normalized category groups with multiple original spellings |
| Structural health | 20% | 100 minus the percentage of columns that are empty or constant |
| Outlier signal | 15% | 100 minus the percentage of eligible numeric values outside the IQR bounds |

The weights sum to 100%. The overall score is the rounded weighted average:

```text
score = round(sum(component_score × component_weight) / 100)
```

Each component is limited to the 0–100 range before weighting. A dataset with no rows or no columns is marked **Not assessable** instead of receiving a misleading number.

## Check details that affect scoring

- Exact duplicate rows count rows after the first copy. Candidate identifier repeats are reported separately and do not reduce the score because TALOS cannot know whether a field must be unique.
- Category consistency only considers suitable text columns. Likely names and free-text fields are skipped, as are very high-cardinality columns. If no normalized category groups are available, that component defaults to 100; this means no inconsistency was detected in the eligible data, not that every text field was validated.
- Structural health penalizes empty and constant columns. High-cardinality text, candidate identifier uniqueness, negative numbers, and zero-heavy fields are shown as contextual signals but do not affect this component because their meaning depends on the dataset.
- The outlier component counts values outside `Q1 - 1.5 × IQR` or `Q3 + 1.5 × IQR` in eligible numeric columns. An outlier is not automatically an error, so this component is an unusual-value signal rather than an error rate.
- Numeric identifiers, boolean fields, numeric fields with fewer than eight finite values, and fields with fewer than five distinct values are excluded from IQR inspection.

## Score bands

| Score | TALOS label |
| ---: | --- |
| 90–100 | Clear |
| 75–89 | Minor observations |
| 50–74 | Review recommended |
| 25–49 | Significant issues |
| 0–24 | Integrity compromised |

These labels summarize the heuristic only. They do not replace domain rules, source-system knowledge, or human review.

## Limitations

The score depends on simple, visible heuristics and can be influenced by a legitimate outlier, a valid repeated record, or a constant field that is useful for the intended analysis. Conversely, a high score does not prove that values are accurate, representative, current, or fit for a specific purpose. TALOS does not modify the uploaded DataFrame while calculating the score.
