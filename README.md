# Workhorse

Local source similarity review for exported submissions. Workhorse highlights
code worth checking and produces reproducible evidence for a human reviewer.
It does not decide whether someone copied code.

**Python 3.11+ · no runtime dependencies · Python, Java, C, and C++**

Version 0.6 adds a combined function-evidence HTML view, snapshot-consistent
calibration, bounded report reads and persistent MOSS attempt guards.
Version 0.5 adds development-only threshold sweeps, source-family split checks,
and bounded duplicate-function evidence. It includes optional MOSS staging/result
import and isolated-function supporting evidence. Version 0.3 separates broad retrieval leads from binding-supported review
flags. It retains semantically edited-copy candidates without silently
promoting weak evidence, reports declined analyses, scopes allowed templates
by task, and evaluates retrieval separately from strict flags. These changes
do not establish a measured real-world false-positive rate.

## Try it

```bash
python -m pip install -e .
workhorse validate examples/demo/manifest.json
workhorse review examples/demo/manifest.json --output reports/demo
```

Open `reports/demo/report.html` for a searchable comparison report.
`report.json` contains the settings, input metadata, source hashes, coverage,
scores, and representative source-line excerpts. The synthetic demo flags one
renamed pair and leaves its alternative implementation unflagged.

Without installing:

```bash
PYTHONPATH=src python -m workhorse review examples/demo/manifest.json --output reports/demo
```

## Review a bulk export

Arrange locally obtained source files under `task/author/source.ext`:

```text
data/export/
  window-score/
    amber/attempt-001.py
    birch/attempt-002.py
  range-query/
    amber/attempt-003.cpp
```

```bash
workhorse index data/export
workhorse validate data/export/manifest.json
workhorse review data/export/manifest.json --output reports/export
```

Folder indexing derives task and author names from directories and assigns
unique path-based IDs. It never changes the original source files. Use a
handwritten JSON or CSV manifest when you have platform IDs, submission times,
verdicts, or source URLs. See [the input format](docs/input-format.md).

```bash
workhorse review data/export/manifest.json \
  --baseline data/templates/manifest.json \
  --threshold 0.65 --min-tokens 50 --output reports/filtered
```

Baseline manifests identify allowed templates. Their token fingerprints are
excluded by task and language; set a baseline's task to `*` only when it is
permitted across every task. Existing report files require `--force` to replace.

Compare configuration behavior on exactly the same loaded sources:

```bash
workhorse compare-configs data/export/manifest.json --output reports/comparison.json
```

The result shows strict flags, broad leads and pair category changes across
relationship normalization, corpus-filter removal and legacy normalization.
It records input hashes and leaves accuracy metrics unknown without independent
labels. Fewer flags alone do not demonstrate fewer false positives. See
[configuration comparisons](docs/configuration-comparison.md) for interpretation
and limits when working with large exports.

## Record a review and export evidence

```bash
workhorse coverage data/export/manifest.json --task window-score --author amber
workhorse review-init reports/export/report.json --output reviews/export.json
workhorse review-list reviews/export.json --status unreviewed
workhorse review-note reviews/export.json PAIR_KEY \
  --status investigate --reviewer reviewer-a \
  --note "Review the unusual shared branch and constants" \
  --contrary-evidence "Both may have used a permitted template"
workhorse packet reports/export/report.json reviews/export.json \
  --pair PAIR_KEY --output reports/selected-pairs.zip
```

Replace `PAIR_KEY` with a key from `review-list`. Reviewer states are
`unreviewed`, `explained`, and `investigate`; these are human assessments,
not computed verdicts. Notes preserve an append-only history in the workspace
and do not change similarity scores. Workspaces are single-writer local files,
not a multi-user database or a tamper-proof audit system.

Packets require a recorded explanation and matching source hashes. They
contain selected-pair reports, reviewer notes, source references, provenance,
and checksums. They exclude full original source files and do not send anything
externally. Existing packets are never overwritten. Group diagnostics inside
a packet still describe the original full comparison run.
Review workspaces include both strict flags and broad-only leads. The category
is displayed by `review-list` and remains explicit inside an evidence packet;
a human note does not turn a broad lead into a strict engine flag.

Coverage checks show expected task/author cells missing from the imported
dataset. They cannot tell whether those sources exist on the platform.

## How comparisons work

1. Validate the export and read UTF-8 source files locally.
2. Remove comments and whitespace; preserve Python scope/binding identities,
   external names, and API attributes. For C-family code, preserve repeated
   identifier relationships and member names using lexical normalization.
   Retain keywords, operators, literal spelling, and Python indentation.
3. Fingerprint token shingles using deterministic winnowing.
4. Group submissions by task and language. Remove known templates and frequent
   corpus fingerprints when there are at least five eligible authors.
5. Use an inverted index to nominate pairs sharing fingerprints. Revisions by
   the same author are not paired. Rank qualifying pairs by containment.
6. Verify token equality for representative matched spans and map them back
   to source lines.
7. Run a second, flattened-identifier retrieval pass. Additional matches appear
   in `additional_candidates` with their own normalization labels, not in
   `findings` or the strict flag count. Use `--no-broad-retrieval` to disable it.

Containment is shared distinct fingerprints divided by the smaller retained
set. Jaccard is shared fingerprints divided by the union. A score is not a
plagiarism probability. Matching boilerplate, short solutions, canonical
algorithms, or a shared allowed source can produce misleading similarities.

Python uses the standard-library AST and symbol table to distinguish local,
global, closure, and comprehension bindings. Unsupported or ambiguous scopes
are declined rather than silently flattened. Declined sources are listed in
the report; lexical retrieval can still nominate them for manual inspection.
Even the broader pass can fail on malformed tokens, so no candidate does not
mean a declined source was adequately analyzed. C-family normalization is lexical
and does not resolve declarations, overloads, or shadowed scopes. Cross-language
comparisons and semantic equivalence detection are not implemented. Evidence
spans are samples, capped at five and expanded by up to 200 tokens on either
side; they can include adjacent excluded template content. Python normalization
does not rewrite names embedded in string tokens, dynamic attribute names,
or every declaration form; these can lower recall. Python runtime version is
recorded because symbol-table representations can vary between releases.

Reports separately show original-token containment, rarity-weighted
containment, and representative match length. Original-token scores include
templates, unlike the filtered main score. Rarity weights use the imported
task/language author corpus and are not meaningful population estimates for
small exports. The scores are correlated diagnostics, not independent votes.

## Evaluate before changing thresholds

```bash
workhorse evaluate examples/benchmark/cases.json --output reports/evaluation.json
workhorse review data/export/manifest.json --normalization legacy --output reports/broad
workhorse review data/export/manifest.json --normalization relationships --output reports/bindings
```

The benchmark has separate development and holdout tasks, explicit construction
provenance, and labels for shared origin, independent fixtures, permitted
templates, insufficient code, and ambiguous scenarios. Ambiguous and
insufficient cases are excluded from precision/recall and counted separately.
Empty denominators produce null metrics. Retrieval precision/recall and strict
flag metrics are reported separately. The published fixtures are inspected
regressions; their historical holdout label is not a fresh blind evaluation.
See [evaluation methodology](docs/evaluation.md).

The legacy mode is broader: changing variable relationships can cause the
binding-aware mode to miss a transformed copy. The default broad pass retains
such matches as additional leads, with the cost of more manual inspection.
Neither normalization can distinguish an independently
written canonical implementation from an identical copied one. Default
thresholds remain heuristics until tested on real labeled problem datasets.

## Larger datasets

Candidate discovery avoids unconditional all-pairs comparison, but dense
similarity groups can still be expensive. Default guards exclude fingerprint
postings above 500 submissions and stop before exceeding 100,000 candidate
pairs across both passes, counting pair visits in each pass. Exclusions appear
in `groups` and `retrieval_groups`; exceeding the candidate budget returns
an error rather than a partial success. Split exports by task or adjust
`--max-posting` and `--max-candidates` to suit your machine.

Corpus filtering uses distinct eligible authors, not revision counts, and
excludes fingerprints occurring in at least 80% of those authors. This can
hide a widespread shared implementation as well as genuine boilerplate.
Compare with and without that filter using `--no-corpus-filter`; known
baseline exclusions and capacity guards still apply. For targeted review,
use a smaller author subset or a known-template baseline. There is no claim
of a validated false-positive rate or performance on an entire platform.

## Development

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src
```

```text
src/workhorse/   imports, normalization, comparison, reports, CLI
tests/          regression and end-to-end tests
examples/demo/  synthetic source fixtures
docs/           input format and review methodology
```

The core comparison engine makes no network requests and does not fetch platform submissions.
The optional MOSS submit command contacts Stanford only when explicitly executed.
Only import source you are authorized to review. Raw exports and generated
reports are ignored by Git; reports contain identifiers and source excerpts.

MIT licensed.

## Supplementary comparison tools

`workhorse-moss` prepares task/language batches locally, previews the command
for your own Stanford Perl client, and imports saved MOSS index pages. Only
`submit --execute` sends one chosen batch to Stanford. Accounts/clients are
not bundled and CI never submits source. See [the MOSS workflow](docs/moss.md).

`workhorse-functions` adds exact binding-normalized Python function excerpts
for already retrieved pairs. Unrelated helper insertion no longer shifts local
scope identities in this evidence view. It checks source provenance, declines
context-sensitive declarations and retains each pair's original category.
See [function supporting evidence](docs/function-signals.md).

Both entry points are also available without installing via
`PYTHONPATH=src python -m workhorse.moss` and
`PYTHONPATH=src python -m workhorse.function_signals`. Their JSON sidecars stay
separate from the normal report and packet. Similarity tools can share biases;
combined scores are not independent votes or plagiarism probabilities. This
release is tested locally with synthetic fixtures and a mocked MOSS client,
not live MOSS submissions or a real labeled contest population.


Use `workhorse-calibrate` to compare a bounded threshold grid on development
cases without scoring holdout outcomes or changing defaults. See
[calibration and split integrity](docs/evaluation.md). Function evidence counts
all duplicate matches while materializing at most five excerpts per pair.

Render function evidence beside the original matched spans:

```bash
workhorse-functions examples/demo/manifest.json reports/demo/report.json \
  --output reports/demo/functions.json --html reports/demo/functions.html
```

The combined view retains strict/broad categories and does not change scores.
