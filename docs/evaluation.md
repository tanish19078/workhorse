# Evaluating retrieval and review flags

Run `workhorse evaluate examples/benchmark/cases.json`. The 19 synthetic
regression scenarios compare legacy flattening with binding-aware normalization
at the same 0.5 threshold. The latter also runs a broad retrieval pass by default.

## Labels and provenance

- `shared_origin`: one source was deliberately derived from another, including
  renaming, semantic edits, and an unrelated helper added before copied code.
- `independent`: separately constructed synthetic algorithm implementations;
  not an observed real submission population or proof of independent authorship.
- `allowed`: similarity explained by an explicitly permitted baseline.
- `ambiguous`: a canonical structure that could arise independently. This
  scenario does not supply an accuracy label and is counted separately.
- `insufficient`: snippets too short for distinctive comparison.

Eight new pairs use different implementations of binary search, Fibonacci,
prefix sums, deduplication, minimum, factorial, odd counting, and reversal.
Their stated equivalence was checked on the included sample inputs when
authoring the fixtures. Evaluation only parses/compares source; it never runs
submitted programs or the fixture sample checks.

Version 0.5 rejects overlap in tasks, declared source families, and exact source
text across development/holdout (after CRLF and boundary whitespace normalization).
It found that `canonical-independent` reused development-template source; that
ambiguous case now belongs to development with the same `source_family` as
`allowed-template`. Other assignments are unchanged. This correction does not
change labeled confusion totals because ambiguous cases have no accuracy label. All published scenarios have now been inspected. These
results are regression diagnostics, not a fresh blind holdout or population
accuracy estimate.

## Separate stages and metrics

`findings` contains strict flags under the selected normalization.
`additional_candidates` contains leads found only by broader flattened-name
retrieval. They retain that category through review notes and evidence exports.
Strict metrics count only flags; retrieval metrics count either category.
Retrieval false positives represent additional inspection work, not automatic
accusations. Ambiguous/insufficient scenarios are excluded from both sets of
precision/recall metrics and reported separately. Missing denominators return
null, and all rates include their underlying confusion counts.

## Current default results

| Cohort | Known-origin strict flags | Known-origin retrieved | Negative strict flags | Negative retrieved |
| --- | --- | --- | --- | --- |
| Historical development | 1/3 | 3/3 | 0/2 | 0/2 |
| Historical holdout | 2/2 | 2/2 | 0/9 | 1/9 |
| Total diagnostic cases | 3/5 | 5/5 | 0/11 | 1/11 |

Broader retrieval restores the semantically edited and helper-prefixed copies.
The independent factorial pair is a broad-only lead, not a strict flag. The
canonical-loop ambiguity remains flagged; no syntax score can establish its
origin. Both short snippets are skipped. Thresholds were not tuned to produce
these counts. Nineteen scenarios are far too few to certify real-world results.

## Next calibration requirement

Collect authorized real independent solutions to the same tasks, including
identical algorithm choices, libraries, templates, and small formulas. Add
known transformations and split whole problems/source families before tuning.
Measure both inspection workload and missed origins, with sample counts and
uncertainty. Keep a new unseen evaluation set. Similarity scores are not guilt
probabilities, and the unit test count is not an accuracy metric.

## Development-only threshold sweep

```bash
workhorse-calibrate examples/benchmark/cases.json \
  --thresholds 0.35 0.5 0.65 0.8 --max-false-positives 0 \
  --output reports/calibration.json
```

Without installing, use `PYTHONPATH=src python -m workhorse.calibration`.
The command accepts 1–20 distinct finite thresholds. It validates split
integrity across the whole input but computes only development outcomes, using
binding-aware flags and optional broad retrieval. It leaves defaults unchanged
and makes no automatic best-setting selection. Each row includes confusion
counts, per-case outcomes, separate strict/retrieval FP-budget checks and total
review workload including ambiguous/insufficient examples. Budgets are absolute
counts in the labeled development set, not real-world rate guarantees. A set
without both labeled positive and negative development cases is rejected.

The current four-point sweep produces strict known-origin counts of 2/3 at
0.35 versus 1/3 at 0.5, 0.65 and 0.8. Retrieval is 3/3 throughout, with no labeled
negative matches among only two development negatives. The canonical ambiguity
still matches at every threshold. This tiny inspected set does not justify
lowering production defaults. Choose settings on representative development
cases, then evaluate once on genuinely unseen whole source families/problems.

Benchmark output records the source file SHA-256. `source_family` is optional
for older inputs but recommended for every case, shared across derived sources
and renamed or edited variants. Exact-source checks alone cannot discover all
related sources. Baseline template text is not automatically treated as a
solution-family identifier; record known provenance explicitly.
