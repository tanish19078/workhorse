"""Evaluate review flags against explicit labels without treating them as verdicts."""

from dataclasses import replace
import json
import hashlib
from pathlib import Path

from .compare import Options, compare
from .imports import Submission


def load_cases(path: Path) -> list[dict]:
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("Benchmark exceeds 10 MiB")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema_version") != 1 or not isinstance(document.get("cases"), list):
        raise ValueError("Expected a version 1 labeled benchmark")
    cases = document["cases"]
    if not cases:
        raise ValueError("Benchmark has no cases")
    seen = set()
    task_splits = {}
    family_splits = {}
    source_splits = {}
    for case in cases:
        if not isinstance(case, dict) or any(not isinstance(case.get(k), str) or not case[k].strip()
            for k in ("id", "task", "language", "left", "right", "label", "split", "provenance")):
            raise ValueError("Benchmark cases require identifiers, code, labels, split and provenance")
        if case["id"] in seen or case["split"] not in ("development", "holdout"):
            raise ValueError("Duplicate case ID or invalid split")
        if case["label"] not in ("shared_origin", "independent", "allowed", "ambiguous", "insufficient"):
            raise ValueError("Unknown benchmark label")
        if case["language"] not in ("python", "java", "c", "cpp"):
            raise ValueError("Unsupported benchmark language")
        if "baseline" in case and not isinstance(case["baseline"], str):
            raise ValueError("Benchmark baseline must be source text")
        seen.add(case["id"])
        existing = task_splits.setdefault(case["task"], case["split"])
        if existing != case["split"]:
            raise ValueError("Task appears in both development and holdout splits")
        family = case.get("source_family")
        if family is not None:
            if not isinstance(family, str) or not family.strip():
                raise ValueError("Source family must be a nonempty string")
            if family_splits.setdefault(family.strip(), case["split"]) != case["split"]:
                raise ValueError("Source family crosses development and holdout splits")
        for side in ("left", "right"):
            source_hash = hashlib.sha256(case[side].replace("\r\n", "\n").strip().encode()).hexdigest()
            key = (case["language"], source_hash)
            if source_splits.setdefault(key, case["split"]) != case["split"]:
                raise ValueError("Identical source crosses development and holdout splits")
    return cases


def evaluate(path: Path, options: Options = Options(), *,
             splits=("development", "holdout"), normalizations=("legacy", "relationships")) -> dict:
    options.validate()
    if not splits or any(s not in ("development", "holdout") for s in splits) or len(set(splits)) != len(splits):
        raise ValueError("Select distinct development/holdout splits")
    if not normalizations or any(n not in ("legacy", "relationships") for n in normalizations) or len(set(normalizations)) != len(normalizations):
        raise ValueError("Select distinct supported evaluation normalizations")
    cases = load_cases(path)
    results = []
    for normalization in normalizations:
        for split in splits:
            counts = {"true_positive": 0, "false_positive": 0, "true_negative": 0,
                      "false_negative": 0, "insufficient_cases": 0, "insufficient_flagged": 0}
            counts.update(ambiguous_cases=0, ambiguous_flagged=0)
            retrieval_counts = {"true_positive": 0, "false_positive": 0, "true_negative": 0,
                                "false_negative": 0, "ambiguous_retrieved": 0, "insufficient_retrieved": 0}
            details = []
            for case in cases:
                if case["split"] != split:
                    continue
                submissions = [Submission(side, side, case["task"], case["language"], side, case[side])
                               for side in ("left", "right")]
                baseline = [Submission("base", "base", case["task"], case["language"], "base", case["baseline"])] if case.get("baseline") else []
                report = compare(submissions, replace(options, normalization=normalization), baseline)
                flagged = bool(report["findings"])
                retrieved = flagged or bool(report.get("additional_candidates"))
                label = case["label"]
                if label == "insufficient":
                    counts["insufficient_cases"] += 1
                    counts["insufficient_flagged"] += flagged
                    retrieval_counts["insufficient_retrieved"] += retrieved
                elif label == "ambiguous":
                    counts["ambiguous_cases"] += 1
                    counts["ambiguous_flagged"] += flagged
                    retrieval_counts["ambiguous_retrieved"] += retrieved
                else:
                    key = ("true_positive" if flagged else "false_negative") if label == "shared_origin" else ("false_positive" if flagged else "true_negative")
                    counts[key] += 1
                    retrieval_key = ("true_positive" if retrieved else "false_negative") if label == "shared_origin" else ("false_positive" if retrieved else "true_negative")
                    retrieval_counts[retrieval_key] += 1
                details.append({"id": case["id"], "label": label, "flagged": flagged,
                                "retrieved": retrieved,
                                "retrieval_category": "review_flag" if flagged else "broad_candidate" if retrieved else "none",
                                "provenance": case["provenance"],
                                "containment": report["findings"][0]["containment"] if flagged else None})
            tp, fp, tn, fn = [counts[k] for k in ("true_positive", "false_positive", "true_negative", "false_negative")]
            rtp, rfp, rtn, rfn = [retrieval_counts[k] for k in ("true_positive", "false_positive", "true_negative", "false_negative")]
            results.append({"normalization": normalization, "split": split, "counts": counts,
                            "retrieval_counts": retrieval_counts,
                            "retrieval_precision": rtp / (rtp + rfp) if rtp + rfp else None,
                            "retrieval_recall": rtp / (rtp + rfn) if rtp + rfn else None,
                            "retrieval_false_positive_rate": rfp / (rfp + rtn) if rfp + rtn else None,
                            "precision": tp / (tp + fp) if tp + fp else None,
                            "recall": tp / (tp + fn) if tp + fn else None,
                            "false_positive_rate": fp / (fp + tn) if fp + tn else None,
                            "cases": details})
    return {"schema_version": 1, "benchmark_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "options": options.__dict__, "results": results,
            "interpretation": "Labels describe known construction provenance, not disciplinary findings. "
                              "Synthetic results do not estimate real-world accuracy. Null metrics have no denominator. "
                              "The published fixtures have been inspected and are regression diagnostics, not a fresh blind holdout. "
                              "Do not tune on the holdout split; use separate real problem datasets before calibration."}
