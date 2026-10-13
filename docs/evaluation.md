# False-positive evaluation

Run `workhorse evaluate examples/benchmark/cases.json`. This compares legacy
identifier flattening with the default relationship-preserving normalization
using the same threshold and fingerprint settings.

## Labels and provenance

- `shared_origin`: the right fixture was deliberately derived from the left.
  Semantic edits can still have shared origin, even when behavior changes.
- `independent`: separately constructed synthetic implementations; not evidence
  of independence in a real submission population.
- `allowed`: similarity explained by an explicitly permitted baseline.
- `ambiguous`: construction scenario whose resemblance could also arise
  independently. Do not treat it as an accuracy label.
- `insufficient`: too little distinctive source for an actionable comparison.

Cases require an ID, task, language, both sources, label, split, and provenance.
An optional `baseline` supplies permitted source. Task overlap between
development and holdout splits is rejected. This prevents obvious task leakage,
but does not guarantee independent algorithm families or real-world coverage.

## Metrics

Precision is correct shared-origin flags divided by all flags on labeled
positive/negative cases. Recall is flagged shared-origin cases divided by all
shared-origin cases. False-positive rate divides flagged independent/allowed
cases by all independent/allowed cases. Each metric includes its confusion
counts; absent denominators return null. Ambiguous and insufficient counts are
reported separately.

## Current diagnostic results

At the default 0.5 containment threshold, the ten synthetic fixtures expose:

| Split | Legacy flags on shared-origin cases | Binding-mode flags on shared-origin cases | Negative flags |
| --- | --- | --- | --- |
| Development | 2/2 | 1/2 | 0/2 in both modes |
| Holdout | 2/2 | 2/2 | 0/1 in both modes |

The binding mode misses a source-derived case with deliberately changed
variable relationships. Both modes flag the canonical-loop ambiguity scenario.
Both abstain on the two tiny snippets. These are diagnostic tradeoffs, not proof
that false positives decreased. The holdout split has only one independent negative
example, far too little to estimate a useful population false-positive rate.

## Before calibration

Collect authorized, labeled independent solutions to the same problems,
including identical algorithm choices and small formula solutions. Add known
transformed copies, permitted libraries, and templates. Split entire problems
and source families before tuning, and reserve the holdout set for evaluation.
Report precision, false-positive rate, recall, sample counts, and uncertainty.
Do not tune thresholds to the toy fixtures or use similarity scores as guilt
probabilities. More structural complexity does not remove canonical-code
ambiguity.
