# Workhorse

Local source similarity review for exported submissions. Workhorse highlights
code worth checking and produces reproducible evidence for a human reviewer.
It does not decide whether someone copied code.

**Python 3.11+ · no runtime dependencies · Python, Java, C, and C++**

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
excluded by language. Existing report files require `--force` to replace.

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

Coverage checks show expected task/author cells missing from the imported
dataset. They cannot tell whether those sources exist on the platform.

## How comparisons work

1. Validate the export and read UTF-8 source files locally.
2. Remove comments and whitespace; normalize identifiers while retaining
   keywords, operators, literal spelling, and Python indentation.
3. Fingerprint token shingles using deterministic winnowing.
4. Group submissions by task and language. Remove known templates and frequent
   corpus fingerprints when there are at least five eligible authors.
5. Use an inverted index to nominate pairs sharing fingerprints. Revisions by
   the same author are not paired. Rank qualifying pairs by containment.
6. Verify token equality for representative matched spans and map them back
   to source lines.

Containment is shared distinct fingerprints divided by the smaller retained
set. Jaccard is shared fingerprints divided by the union. A score is not a
plagiarism probability. Matching boilerplate, short solutions, canonical
algorithms, or a shared allowed source can produce misleading similarities.

The lexical normalizer does not track variable binding or build a syntax tree.
Replacing identifiers may hide meaningful differences. Cross-language
comparisons and semantic equivalence detection are not implemented. Evidence
spans are samples, capped at five and expanded by up to 200 tokens on either
side; they can include adjacent excluded template content.

## Larger datasets

Candidate discovery avoids unconditional all-pairs comparison, but dense
similarity groups can still be expensive. Default guards exclude fingerprint
postings above 500 submissions and stop before exceeding 100,000 candidate
pairs. Exclusions appear in the report; exceeding the candidate budget returns
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

Workhorse makes no network requests and does not fetch platform submissions.
Only import source you are authorized to review. Raw exports and generated
reports are ignored by Git; reports contain identifiers and source excerpts.

MIT licensed.
