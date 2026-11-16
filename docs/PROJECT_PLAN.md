# TALOS — Initial Project Plan

Baseline 2026-11-16. Verify current release before updating functionality.

## Phase 0: Existing implementation review
- [ ] Review README, CHANGELOG, version and current tests.
- [ ] Reproduce demo dataset diagnostics and expected scores.

## Phase 1: Calculation and quality validation
- [ ] Confirm scoring, null/duplicate rates and categorical normalisation are consistent.
- [ ] Check large-file edge cases, empty inputs and invalid exports.
- [ ] Ensure inspection output matches repair ledger.

## Phase 2: Product polish
- [ ] Improve readability and evidence explanations.
- [ ] Clarify Forge approvals, reset and data-preservation behaviour.
- [ ] Audit light/dark accessibility.

## Phase 3: Release
- [ ] Run regression suite and compare exported reports.
- [ ] Document changed calculations or limitations.
- [ ] Deploy an incremental release after review.

## Definition of done
Raw data stays untouched; the ledger explains every repair; synthetic demo exercises core issues; all outputs remain inspectable.
