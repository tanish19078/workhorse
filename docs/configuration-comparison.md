# Compare configurations on a bulk export

Run a reproducible ablation before deciding that a change improves detection:

```bash
workhorse compare-configs data/export/manifest.json \
  --output reports/configuration-comparison.json
```

The command reads the export and optional allowed-template baseline once, then
runs three configurations against that same in-memory source snapshot:

| Run | Normalization | Corpus filter |
| --- | --- | --- |
| `current` | Identifier relationships | Enabled |
| `no_corpus_filter` | Identifier relationships | Disabled |
| `legacy_no_corpus_filter` | Flattened identifiers | Disabled |

These are configurations within the installed version, not historical releases.
All other settings come from the same `Options`; CLI overrides are `--threshold`
and `--max-candidates`. Relationship configurations retain the separate broad
retrieval pass. Legacy normalization has no extra retrieval pass. Supplied known
templates are excluded in every run, even when corpus filtering is disabled.

```bash
workhorse compare-configs data/export/manifest.json \
  --baseline data/templates/manifest.json --threshold 0.65 \
  --max-candidates 200000 --output reports/comparison-with-templates.json
```

Without `--output`, JSON goes to stdout. Existing outputs are never replaced.
If any configuration exceeds its candidate budget or otherwise fails, the
command fails without writing a success document. It does not silently omit a
failed configuration. Split large exports by problem/language or explicitly
increase the budget; record this choice when comparing experiments.

## Read the results

- `runs` contains complete options, strict and broad candidate counts, group
  diagnostics, and analyzed/declined status for each source.
- `pairs` contains the union of returned pairs, canonically ordered by IDs,
  with each run's category and score. Scores use different retained fingerprint
  sets and normalization; they are not calibrated probabilities.
- `transitions_to_current` counts category changes from each alternative run to
  the selected current configuration. A strict flag can become a broad lead;
  that is different from disappearing from the returned results.
- `possible_cross_author_pairs` counts all same-problem, same-language pairs
  with different authors, including short/declined sources. It includes multiple
  revisions; select one revision per team/problem beforehand if desired.
- `input_sha256` binds sorted metadata and decoded-source hashes for both the
  export and baseline. It is a reproducibility digest, not a signature. Source
  hashes cover decoded UTF-8 text, not original bytes (a UTF-8 BOM is removed by
  the importer).

`not_returned` means neither a strict flag nor a broad-only lead was returned.
It does not mean the pair was exhaustively compared or independently authored.
Inspect short sources, declined analyses, crowded postings and candidate counts.
The JSON contains metadata and source hashes but no source text/excerpts; keep
it private if its submission IDs, author IDs or URLs are sensitive.

## Measure accuracy separately

Five flags becoming one means four fewer flags. Without independent labels,
the removed flags could be false positives, missed copies, or a mixture.
`accuracy.precision`, `accuracy.recall` and `accuracy.false_positive_rate` remain
`null` in this command. It does not use reviewer suspicion as ground truth.

Use blind independent review of flagged, borderline and sampled unflagged
pairs. Keep uncertain cases unresolved, document the sampling probabilities,
and use a separate holdout grouped by problem/source family. Use `workhorse
evaluate` with independently labeled cases for accuracy metrics, and inspect
retrieval misses as well as strict flags. Avoid tuning on the holdout.
