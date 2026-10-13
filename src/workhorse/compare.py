"""Indexed candidate discovery with transparent similarity and matched spans."""

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import math
import platform

from .imports import Submission
from . import __version__
from .tokens import Token, fingerprints, normalize


@dataclass(frozen=True)
class Options:
    threshold: float = 0.5
    min_tokens: int = 30
    min_shared: int = 3
    k: int = 9
    window: int = 4
    common_fraction: float = 0.8
    max_candidates: int = 100_000
    max_posting: int = 500
    corpus_filter: bool = True
    normalization: str = "relationships"

    def validate(self):
        if self.normalization not in ("relationships", "raw", "legacy"):
            raise ValueError("Unknown normalization mode")
        if not 0 <= self.threshold <= 1 or not 0 < self.common_fraction <= 1:
            raise ValueError("Threshold must be in [0, 1]; common fraction in (0, 1]")
        if any(v < 1 for v in (self.min_tokens, self.min_shared, self.k, self.window,
                               self.max_candidates, self.max_posting)):
            raise ValueError("Token, fingerprint and capacity limits must be positive")


def _span(source: str, tokens: list[Token], start: int, end: int) -> dict:
    lines = source.splitlines()
    first = min(tokens[start].line, len(lines))
    last = min(tokens[end - 1].line, len(lines))
    return {"start_line": first, "end_line": last,
            "excerpt": "\n".join(lines[first - 1:last])}


def _evidence(a, b, ta, tb, fa, fb, shared, k):
    """Expand representative shared shingles; no expensive whole-file alignment."""
    spans = []
    occupied = []
    for fingerprint in sorted(shared, key=lambda h: (fa[h], fb[h])):
        i, j = fa[fingerprint], fb[fingerprint]
        if any(start <= i < end for start, end in occupied):
            continue
        # Hashes only nominate candidates; verify token equality before quoting.
        if [t.value for t in ta[i:i + k]] != [t.value for t in tb[j:j + k]]:
            continue
        ia, ib, ea, eb = i, j, i + k, j + k
        for _ in range(200):
            if ia == 0 or ib == 0 or ta[ia - 1].value != tb[ib - 1].value:
                break
            ia -= 1
            ib -= 1
        for _ in range(200):
            if ea == len(ta) or eb == len(tb) or ta[ea].value != tb[eb].value:
                break
            ea += 1
            eb += 1
        occupied.append((ia, ea))
        spans.append({"tokens": ea - ia, "left": _span(a.source, ta, ia, ea),
                      "right": _span(b.source, tb, ib, eb)})
        if len(spans) == 5:
            break
    return spans


def compare(submissions: list[Submission], options: Options = Options(),
            baselines: list[Submission] | None = None) -> dict:
    options.validate()
    groups = defaultdict(list)
    token_lists = []
    all_fingerprints = []
    raw_fingerprints = []
    for index, item in enumerate(submissions):
        try:
            tokens = normalize(item.source, item.language, options.normalization)
        except ValueError as exc:
            raise ValueError(f"Submission {item.id}: {exc}") from exc
        token_lists.append(tokens)
        all_fingerprints.append(fingerprints(tokens, options.k, options.window))
        raw_fingerprints.append(set(fingerprints(normalize(item.source, item.language, "raw"), options.k, options.window)))
        groups[(item.task, item.language)].append(index)
    baseline_hashes = defaultdict(set)
    for item in baselines or []:
        baseline_hashes[item.language].update(fingerprints(
            normalize(item.source, item.language, options.normalization), options.k, options.window))
    findings = []
    diagnostics = []
    candidates_total = 0
    for (task, language), indexes in sorted(groups.items()):
        eligible = [i for i in indexes if len(token_lists[i]) >= options.min_tokens]
        posting = defaultdict(list)
        for i in eligible:
            for fingerprint in all_fingerprints[i]:
                posting[fingerprint].append(i)
        common = set(baseline_hashes[language])
        # Count independent authors, not multiple revisions of one author's template.
        authors = {submissions[i].author for i in eligible}
        if options.corpus_filter and len(authors) >= 5:
            for fingerprint, members in posting.items():
                if len({submissions[i].author for i in members}) >= math.ceil(len(authors) * options.common_fraction):
                    common.add(fingerprint)
        crowded = {h for h, members in posting.items() if len(members) > options.max_posting}
        excluded = common | crowded
        retained = {i: set(all_fingerprints[i]) - excluded for i in eligible}
        frequencies = {h: len({submissions[i].author for i in members}) for h, members in posting.items()}
        weights = {h: 1 + math.log((len(authors) + 1) / (count + 1)) for h, count in frequencies.items()}
        counts = defaultdict(int)
        for fingerprint, members in sorted(posting.items()):
            if fingerprint in excluded:
                continue
            for offset, i in enumerate(members):
                for j in members[offset + 1:]:
                    if submissions[i].author == submissions[j].author:
                        continue
                    pair = (i, j)
                    if pair not in counts and candidates_total + len(counts) >= options.max_candidates:
                        raise ValueError("Candidate limit exceeded; split the export by task or increase --max-candidates")
                    counts[pair] += 1
        candidates_total += len(counts)
        for (i, j), count in sorted(counts.items()):
            if count < options.min_shared:
                continue
            left, right = retained[i], retained[j]
            shared = left & right
            containment = len(shared) / min(len(left), len(right))
            if containment < options.threshold:
                continue
            raw_left, raw_right = raw_fingerprints[i], raw_fingerprints[j]
            raw_containment = len(raw_left & raw_right) / min(len(raw_left), len(raw_right)) if raw_left and raw_right else 0
            weighted = sum(weights[h] for h in shared) / min(sum(weights[h] for h in left), sum(weights[h] for h in right))
            spans = _evidence(submissions[i], submissions[j], token_lists[i], token_lists[j],
                              all_fingerprints[i], all_fingerprints[j], shared, options.k)
            cautions = []
            if len(authors) < 10:
                cautions.append("Small author corpus: fingerprint rarity is not a reliable population baseline.")
            if min(len(left), len(right)) < 10:
                cautions.append("Few distinct retained fingerprints: a high percentage may describe little code.")
            if spans and max(span["tokens"] for span in spans) < 30:
                cautions.append("Only short representative matches; inspect whether the algorithm forces this structure.")
            findings.append({"left": submissions[i].id, "right": submissions[j].id,
                             "task": task, "language": language,
                             "containment": round(containment, 6),
                             "jaccard": round(len(shared) / len(left | right), 6),
                             "shared_fingerprints": len(shared),
                             "left_fingerprints": len(left), "right_fingerprints": len(right),
                             "signals": {"raw_containment": round(raw_containment, 6),
                                         "rarity_weighted_containment": round(weighted, 6),
                                         "rarity_basis_authors": len(authors),
                                         "longest_representative_span": max((s["tokens"] for s in spans), default=0)},
                             "cautions": cautions, "evidence": spans})
        diagnostics.append({"task": task, "language": language, "submissions": len(indexes),
                            "eligible": len(eligible), "short_sources": len(indexes) - len(eligible),
                            "excluded_common_fingerprints": len(set(posting) & common),
                            "excluded_crowded_fingerprints": len(crowded),
                            "candidate_pairs": len(counts)})
    findings.sort(key=lambda f: (-f["containment"], -f["shared_fingerprints"], f["left"], f["right"]))
    metadata = []
    for index, item in enumerate(submissions):
        metadata.append({**item.metadata(), "sha256": hashlib.sha256(item.source.encode()).hexdigest(),
                         "normalized_tokens": len(token_lists[index])})
    return {"schema_version": 1, "tool_version": __version__, "python_version": platform.python_version(), "options": options.__dict__, "submissions": metadata,
            "summary": {"submissions": len(submissions), "groups": len(groups),
                        "candidate_pairs": candidates_total, "flagged_pairs": len(findings)},
            "groups": diagnostics, "findings": findings,
            "interpretation": "Similarity is a review signal, not a plagiarism probability or finding. "
                              "No flags does not establish independent authorship. "
                              "Evidence spans are representative, not a complete alignment."}
