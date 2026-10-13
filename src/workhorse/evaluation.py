"""Evaluate review flags against explicit labels without treating them as verdicts."""

from dataclasses import replace
import json
from pathlib import Path

from .compare import Options, compare
from .imports import Submission


def evaluate(path: Path, options: Options = Options()) -> dict:
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
    results = []
    for normalization in ("legacy", "relationships"):
        for split in ("development", "holdout"):
            counts = {"true_positive": 0, "false_positive": 0, "true_negative": 0,
                      "false_negative": 0, "insufficient_cases": 0, "insufficient_flagged": 0}
            counts.update(ambiguous_cases=0, ambiguous_flagged=0)
            details = []
            for case in cases:
                if case["split"] != split:
                    continue
                submissions = [Submission(side, side, case["task"], case["language"], side, case[side])
                               for side in ("left", "right")]
                baseline = [Submission("base", "base", case["task"], case["language"], "base", case["baseline"])] if case.get("baseline") else []
                report = compare(submissions, replace(options, normalization=normalization), baseline)
                flagged = bool(report["findings"])
                label = case["label"]
                if label == "insufficient":
                    counts["insufficient_cases"] += 1
                    counts["insufficient_flagged"] += flagged
                elif label == "ambiguous":
                    counts["ambiguous_cases"] += 1
                    counts["ambiguous_flagged"] += flagged
                else:
                    key = ("true_positive" if flagged else "false_negative") if label == "shared_origin" else ("false_positive" if flagged else "true_negative")
                    counts[key] += 1
                details.append({"id": case["id"], "label": label, "flagged": flagged,
                                "provenance": case["provenance"],
                                "containment": report["findings"][0]["containment"] if flagged else None})
            tp, fp, tn, fn = [counts[k] for k in ("true_positive", "false_positive", "true_negative", "false_negative")]
            results.append({"normalization": normalization, "split": split, "counts": counts,
                            "precision": tp / (tp + fp) if tp + fp else None,
                            "recall": tp / (tp + fn) if tp + fn else None,
                            "false_positive_rate": fp / (fp + tn) if fp + tn else None,
                            "cases": details})
    return {"schema_version": 1, "options": options.__dict__, "results": results,
            "interpretation": "Labels describe known construction provenance, not disciplinary findings. "
                              "Synthetic results do not estimate real-world accuracy. Null metrics have no denominator. "
                              "Do not tune on the holdout split; use separate real problem datasets before calibration."}
