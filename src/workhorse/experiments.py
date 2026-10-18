"""Compare configuration behavior on one immutable, unlabeled source snapshot."""

from collections import Counter, defaultdict
from dataclasses import replace
import hashlib
import json
from pathlib import Path

from . import __version__
from .compare import Options, compare
from .imports import load_manifest


def _inventory(submissions):
    return sorted(({**item.metadata(),
                    "sha256": hashlib.sha256(item.source.encode()).hexdigest()}
                   for item in submissions), key=lambda row: row["id"])


def _digest(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def compare_configs(manifest: Path, options: Options = Options(), baseline: Path | None = None):
    """Run fixed ablations; never infer accuracy from changes in flag counts.

    Read each source once so later file changes cannot give configurations
    different inputs. Hashes describe the decoded text actually analyzed.
    """
    options.validate()
    if options.normalization != "relationships" or not options.corpus_filter:
        raise ValueError("The selected configuration must use relationships and corpus filtering")
    submissions = load_manifest(manifest)
    baselines = load_manifest(baseline) if baseline else []
    inventory, baseline_inventory = _inventory(submissions), _inventory(baselines)
    presets = {
        "current": options,
        "no_corpus_filter": replace(options, corpus_filter=False),
        "legacy_no_corpus_filter": replace(options, normalization="legacy", corpus_filter=False),
    }
    runs, outcomes = {}, defaultdict(dict)
    for name, settings in presets.items():
        report = compare(submissions, settings, baselines)
        runs[name] = {"options": report["options"], "summary": report["summary"],
                      "groups": report["groups"], "retrieval_groups": report["retrieval_groups"],
                      "analysis": [{"id": row["id"], "status": row["analysis_status"],
                                    "note": row["analysis_note"]}
                                   for row in report["submissions"]]}
        for finding in report["findings"] + report["additional_candidates"]:
            left, right = sorted((finding["left"], finding["right"]))
            key = (finding["task"], finding["language"], left, right)
            outcomes[key][name] = {"category": finding["category"],
                                   "containment": finding["containment"],
                                   "shared_fingerprints": finding["shared_fingerprints"]}
    pairs = []
    for (task, language, left, right), states in sorted(outcomes.items()):
        pairs.append({"task": task, "language": language, "left": left, "right": right,
                      "outcomes": {name: states.get(name, {"category": "not_returned"})
                                   for name in presets}})
    transitions = {}
    for name in presets:
        if name == "current":
            continue
        counts = Counter((pair["outcomes"][name]["category"],
                          pair["outcomes"]["current"]["category"]) for pair in pairs)
        transitions[name] = [{"from": before, "to": after, "pairs": count}
                             for (before, after), count in sorted(counts.items())]
    groups = defaultdict(Counter)
    for item in submissions:
        groups[(item.task, item.language)][item.author] += 1
    possible_pairs = sum((sum(authors.values()) ** 2 - sum(n * n for n in authors.values())) // 2
                         for authors in groups.values())
    return {"schema_version": 1, "document_type": "configuration_comparison",
            "tool_version": __version__, "submissions": inventory,
            "baseline_submissions": baseline_inventory,
            "input_sha256": _digest({"submissions": inventory, "baselines": baseline_inventory}),
            "possible_cross_author_pairs": possible_pairs,
            "runs": runs, "transitions_to_current": transitions, "pairs": pairs,
            "accuracy": {"precision": None, "recall": None, "false_positive_rate": None,
                         "reason": "No independent ground-truth labels were supplied."},
            "interpretation": "These are configuration ablations within one tool version, not a release comparison. "
                              "Fewer flags do not establish fewer false positives or preserved recall. "
                              "not_returned means neither a strict flag nor a broad-only lead; it does not establish "
                              "independent authorship or that detailed comparison occurred. Inspect short/declined "
                              "sources, crowded postings, candidate budgets and retrieval diagnostics. "
                              "Source hashes cover decoded UTF-8 text, not original file bytes. "
                              "Pair counts include revisions; this command does not select one submission per author."}
