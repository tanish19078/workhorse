# Optional MOSS workflow

Workhorse supplies a local batch preparation script, a dry-run/explicit-submit
wrapper around your own Stanford Perl client, and a saved-index importer.
It does not bundle Stanford's client or an account identifier. The comparison
engine, normal CLI, preparation and import commands make no network requests.
Only `submit --execute` runs the external client and sends staged source code.
No live MOSS submission has been used to validate this integration.

## Obtain your own client

Follow [Stanford's instructions](https://theory.stanford.edu/~aiken/moss/) to
register and obtain the account-specific submission script. Store it outside
Git, for example `data/private/moss.pl`. Install Perl locally. Do not put your
account identifier in repository files or issue comments. The wrapper uses
`-l` and repeated `-b` options; C++ maps to MOSS's `cc` language code. It passes
arguments directly to Perl without a shell. It does not execute exported programs.

Stanford describes MOSS as a non-commercial Internet service, with a limit of
100 submissions per day per user. Results contain copies of submitted code and
are accessible to anyone with the URL. Results typically expire after 14 days
and may disappear sooner. Use only exports you are entitled to send to Stanford.
Similarity percentages are not proof of plagiarism. These statements were
checked against the official page on 2026-10-13.

## Prepare and inspect locally

```bash
PYTHONPATH=src python -m workhorse.moss prepare data/export/manifest.json \
  --baseline data/templates/manifest.json --output data/moss-batch
PYTHONPATH=src python -m workhorse.moss submit data/moss-batch/plan.json \
  --group g0001 --client data/private/moss.pl
```

Omit `--baseline` when there is none. Preparation snapshots UTF-8 source under
neutral numbered filenames. The private plan maps names to original IDs and
SHA-256 hashes. It creates one group per task/language, with task-specific and
explicit `*` global permitted baselines. It never overwrites an existing batch.
Each source file is a separate submission; this is not a multi-file project
adapter. Different attempts by the same author are staged separately; imported
same-author matches are counted and excluded.

Inspect `plan.json` and the displayed command. Submission verifies snapshot
hashes and rejects symlinks/path escapes. It needs at least two distinct authors.
The client receives relative neutral filenames, rather than original author
paths. Code contents may still contain identifying comments or other data;
neutral filenames do not anonymize source contents.

## Explicitly submit one chosen group

```bash
PYTHONPATH=src python -m workhorse.moss submit data/moss-batch/plan.json \
  --group g0001 --client data/private/moss.pl --execute
```

This command transmits that group's sources and applicable baselines. There
is no automatic submission loop or retry. A successful response saves a local
`submission.json` receipt containing the result URL, plan/client hashes and
arguments. A second execution with that receipt present is rejected. A timeout
or failure does not prove that the server received nothing; inspect before
retrying. The wrapper's timeout is 120 seconds and does not manage a global
account quota. CI never submits to MOSS.

## Import a saved index locally

Save the result's HTML index, then supply the **result directory URL ending in
`/`**, not the match or index page URL:

```bash
PYTHONPATH=src python -m workhorse.moss import data/moss-batch/plan.json \
  data/moss-index.html --group g0001 \
  --result-url http://moss.stanford.edu/results/RUN/KEY/ \
  --output reports/moss-signals.json
```

Replace the illustrative URL with the actual one. Import makes no request and
never follows links or runs scripts. It supports the standard table with
`File 1`, `File 2`, and `Lines Matched` headers, two filename/percentage links
and an integer line count per row. It rejects malformed percentages, unknown
filenames, duplicate/self pairs and links outside the specified result run.
Other page formats fail explicitly. A recognized empty table returns an empty
result, not a clean-authorship verdict.

The JSON preserves both directional percentages, matched lines, source hashes,
plan/index hashes and the match link. Its category is `external_moss_signal`.
It stays separate from Workhorse flags and broad candidates; it is not merged
into notes/packets automatically. Compare the highlighted code and permitted
sources yourself and record that evidence in review notes. Two similarity
tools can share biases; their scores are not independent votes. Keep result
URLs and saved pages private alongside raw exports. No source upload or
real-world MOSS accuracy claim is included in this release.
