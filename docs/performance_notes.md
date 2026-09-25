# TALOS local performance check

These timings are local measurements, not a promise about Streamlit Community Cloud or another machine. They exclude network transfer, browser rendering, and the time a person spends reviewing a repair plan.

## Method

Measured on 2026-09-25 with Python 3.12.14, pandas 2.2.3, NumPy 2.3.5, and Streamlit 1.64.0. The timings are means across three consecutive calls in the same process. The 161-row case is the built-in synthetic demo. The larger cases are seeded synthetic frames with category variants, missingness, duplicate rows, numeric patterns, a constant column, and an empty column. The 5,000 and 25,000 base rows include a small appended duplicate sample, so the measured frames contain 5,050 and 25,250 rows.

## Results

| Measured rows | CSV size | Parse | Profile | Inspect | Evidence tables | HTML report | Evidence ZIP | Repair batch | Reinspection |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 161 | 6.9 KB | 1.05 ms | 0.16 ms | 7.90 ms | 3.66 ms | 15.13 ms | 0.91 ms | 3.78 ms | 6.79 ms |
| 5,050 | 215 KB | 4.12 ms | 0.13 ms | 37.73 ms | 5.85 ms | 19.44 ms | 4.10 ms | 8.21 ms | 38.42 ms |
| 25,250 | 1.08 MB | 14.11 ms | 0.12 ms | 168.06 ms | 12.79 ms | 64.79 ms | 17.53 ms | 26.12 ms | 169.54 ms |

The evidence ZIPs were about 8.9 KB, 39.7 KB, and 171.9 KB for these cases. ZIP size depends heavily on repeated text and findings.

## Interpretation

In these synthetic checks, CSV parsing, pandas inspections, reinspection, report generation, and evidence packaging were all below one second at 25,250 rows. Inspection and reinspection took the largest share. TALOS caches findings and prepared evidence by source fingerprint and working-copy revision, shows only a short raw-data preview, caps on-screen duplicate/outlier examples, and keeps full applicable result tables in exports. Larger real files and unusual high-cardinality text should still be profiled in their intended deployment environment.

## Standalone Python workflow

Measured on 2026-09-25 with Python 3.12.14, pandas 2.2.3, and NumPy 2.3.5.
Each timing is the mean of five calls in one process after a warm-up. The core
column is `inspect_dataset(frame)`; `TalosSession.inspect()` measures the public
standalone session API on the same input. Session creation is measured
separately and includes defensive copies plus a CSV-sized profile value. The
session is constructed before timing the inspection call.

The demo measurement uses the checked-in 161-row CSV. The larger frames are
seeded synthetic data with mixed category spellings, missing values, numeric
patterns, a high outlier, a constant column, and an empty column. A 1% sample of
exact duplicate rows is appended, so the measured larger frames contain 5,050
and 25,250 rows.

| Measured rows | Shared core inspection | `TalosSession.inspect()` | Session creation |
| ---: | ---: | ---: | ---: |
| 161 | 4.62 ms | 4.96 ms | 0.66 ms |
| 5,050 | 29.59 ms | 29.98 ms | 12.52 ms |
| 25,250 | 120.30 ms | 121.88 ms | 54.89 ms |

The measured inspection API was within 7.4% of the direct shared-core call at
demo scale and within 1.3% at the two larger sizes. These are local synthetic
measurements; actual CSV parsing, machine load, and dataset shape will affect
end-to-end timings.
