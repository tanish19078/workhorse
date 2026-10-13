# Understanding and today's build

## Article in brief

[ZenRows' article](https://www.zenrows.com/blog/bypass-cloudflare), updated
6 May 2026, describes network reputation, client fingerprints, browser signals,
and active challenges as interacting sources of automation detection. It
compares solver services, modified browser automation, and managed scraping
services, emphasizing browser overhead and maintenance when defenses change.
It mentions SeleniumBase UC, but its benchmark percentages are vendor-reported
results, not guarantees for a particular site or results reproduced here.
The article promotes ZenRows' own service; its recommendation should be read
in that commercial context.

[Cloudflare's documentation](https://developers.cloudflare.com/bots/concepts/bot-detection-engines/)
confirms that detection combines multiple engines. Its
[JavaScript detection documentation](https://developers.cloudflare.com/cloudflare-challenges/challenge-types/javascript-detections/)
also explains that passing JavaScript checks does not guarantee a favorable
bot score. Our engineering conclusion: keep collection replaceable and build
the review pipeline independently of browser access. Local deployment alone
does not guarantee access to a protected site.

## Exact tools in Workhorse today

| Tool | Purpose | Status |
| --- | --- | --- |
| `workhorse index` | Turn `task/author/source.ext` folders into a validated manifest | Built |
| `workhorse validate` | Check JSON/CSV records, source paths, encoding, and IDs | Built |
| Token normalizer | Compare renamed identifiers while preserving literals, operators, and source lines | Built: Python, Java, C, C++ |
| Indexed comparison engine | Nominate same-task, same-language pairs without unconditional all-pairs comparison | Built |
| Template filtering | Exclude allowed baseline fingerprints and frequent corpus content | Built; corpus filtering can be disabled |
| `workhorse review` | Produce searchable HTML and reproducible JSON with representative line evidence | Built |
| `workhorse coverage` | Summarize missing expected imports and duplicate source exports | Built |
| Review workspace commands | Store source-bound judgments, notes, and contrary evidence | Built |
| `workhorse packet` | Export selected reviewed pairs, provenance, and integrity checksums | Built |
| Regression suite and CI | Check imports, normalization, grouping, exclusions, escaping, and the full workflow | Tests pass locally; CI configured for Python 3.11–3.13 |

Today's local smoke test processed 1,000 synthetic submissions across 100 tasks
in approximately 0.24 seconds and surfaced the 100 deliberately matching
pairs. This is one small synthetic workload, not a production throughput or
accuracy benchmark.

## Next work, in order

1. **Import validation on a real authorized export.** Map real IDs, tasks,
   timestamps, verdicts, and revisions; reconcile missing source files and
   duplicate exports. Deliver a coverage summary before reviewing matches.
2. **Review workspace validation.** The workspace is built. Validate its
   unreviewed, explained, and investigate states against a real review workflow.
   Human judgments remain separate from computed scores.
3. **Evidence export validation.** Packets are built with selected pairs,
   source hashes, excerpts, explanations, and contrary evidence. Test them
   with authorized reviewers before any external allegation.
4. **Authorized collection adapter.** Once an official API or approved bulk
   export route is available, add a rate-limited, resumable adapter behind the
   same manifest format. Record provenance and failures; do not treat challenge
   HTML as source code. No stealth browser or challenge-bypass adapter is part
   of this build.

All scores are review signals. Similarity cannot establish intent, copying
direction, or a disciplinary outcome. Current comparisons exclude same-author
revisions and do not compare across languages.

## Repository state

Development is on `main`, with focused commits for working features. No real
submission code or contest identifiers are included in the tracked project.
Shell authentication is separate from browser sign-in. Browser editor commits
can publish the source tree, while the original local implementation history
is retained separately. Remote CI results must be verified after publication.
