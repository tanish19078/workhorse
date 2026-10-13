# Reviewing a flagged pair

Treat a flag as a lead requiring source inspection, not a finding.

1. Confirm the submission IDs, task, language, and export completeness.
2. Read the matched spans in the original files. Normalized matches can hide
   differences in variable relationships, comments, or APIs.
3. Remove ordinary wrappers, input parsing, standard library calls, and allowed
   templates from the interpretation.
4. Look for distinctive shared details: nonstandard control flow, unusual
   constants, unnecessary operations, matching mistakes, and equivalent
   revisions across attempts.
5. Compare against the problem statement, canonical algorithms, and independent
   submissions. Estimate how constrained the solution is before calling a
   shared pattern unusual.
6. Use timestamps as context only. They do not show communication or determine
   the origin of code.
7. Record both supporting and contrary evidence and ask the relevant reviewer
   to adjudicate. Do not automate accusations or sanctions from a score.

## Reproducibility

Preserve the input export, the exact CLI settings, `report.json`, and the
Workhorse version. Reports include normalized source hashes, input paths,
group coverage, excluded fingerprint counts, and representative excerpts.
They do not include every matching token or the complete original source.

## Expected limitations

- Very short code is skipped by default because it is weak evidence.
- Independent implementations of a common algorithm can match.
- Widespread shared implementations can be removed by corpus filtering.
- A different implementation of the same idea may not match at all.
- Language grouping prevents cross-language findings.
- Lexical normalization is not semantic analysis; Python indentation is kept,
  but variable binding and C-family preprocessing are not interpreted.
- Capacity exclusions lower recall; inspect the diagnostics.
- No flags does not establish originality.
