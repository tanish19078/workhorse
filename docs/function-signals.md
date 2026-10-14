# Function-level supporting evidence

```bash
PYTHONPATH=src python -m workhorse.function_signals data/export/manifest.json \
  reports/export/report.json --baseline data/templates/manifest.json \
  --output reports/function-signals.json
```

This optional local script examines already retrieved Python pairs. It extracts
top-level functions, normalizes each in isolation with binding relationships,
and reports exact normalized token equality for functions of at least 30 tokens.
Thus inserting an unrelated helper before a copied function no longer shifts
that function's scope identity in this evidence view. Source ranges refer to
the original file. The input report's hashes, task/language and author must
match the manifest before analysis. The output records the original report
hash, baseline provenance, tool/Python versions and external names.

This is a sidecar JSON report, not a new similarity score. Original strict/broad
categories are retained; no pair is promoted. The normal report and review
packet formats are unchanged. Each pair displays up to five matching function
combinations with a total count. Version 0.5 computes that count from indexed
bucket sizes without allocating every duplicate combination. A regression
checks 160,000 combinations while retaining only five excerpts. This adds localized evidence; it does not
increase the retrieval or strict-flag counts reported by evaluation.

Decorated functions, default arguments, annotations, generic type parameters,
and global/nonlocal declarations are declined because isolated parsing could
lose important context. Very short functions and non-Python sources are not
included. Only top-level functions are extracted; no cross-language or runtime
semantic analysis is performed. Source code is never executed. The method does
not discover new pairs absent from the original report.

Supply the same allowed-template manifest used for the initial review. Complete
normalized functions matching a baseline for the task or `*` are excluded.
Partial template fragments and the initial report's corpus filter are not
reapplied inside functions. Surrounding module context, external dependencies,
canonical algorithms and shared public implementations still require inspection.
An exact function match is excerpt evidence, not a conclusion about its origin.

Regressions cover helper insertion, consistent renaming, changed variable
relationships, preserved external API names, contextual-function declines,
source provenance and permitted complete functions. These are correctness
checks, not an estimated false-positive rate on real submissions.
