"""Bounded development-only threshold comparison; never changes defaults."""
import argparse
from dataclasses import replace
import json
import math
from pathlib import Path

from . import __version__
from .compare import Options
from .evaluation import BenchmarkSnapshot, evaluate


def sweep(path, thresholds, options=Options(), max_false_positives=0):
    """Evaluate a user-selected grid, leaving holdout outcomes uncomputed."""
    thresholds = list(thresholds)
    if (not 1 <= len(thresholds) <= 20 or any(type(t) not in (float, int) or
            not math.isfinite(t) or not 0 <= t <= 1 for t in thresholds)
            or len(set(thresholds)) != len(thresholds)):
        raise ValueError("Choose 1–20 distinct finite thresholds in [0, 1]")
    if type(max_false_positives) is not int or max_false_positives < 0:
        raise ValueError("False-positive budget must be a nonnegative integer")
    options.validate()
    snapshot = BenchmarkSnapshot.read(path)
    rows = []
    for threshold in sorted(thresholds):
        evaluation = evaluate(snapshot, replace(options, threshold=threshold),
                              splits=("development",), normalizations=("relationships",))
        row = evaluation["results"][0]
        counts = row["counts"]
        positives = counts["true_positive"] + counts["false_negative"]
        negatives = counts["false_positive"] + counts["true_negative"]
        if not positives or not negatives:
            raise ValueError("Calibration requires labeled positive and negative development cases")
        rows.append({"threshold": threshold, "strict_counts": counts,
                     "retrieval_counts": row["retrieval_counts"],
                     "strict_recall": row["recall"], "strict_precision": row["precision"],
                     "retrieval_recall": row["retrieval_recall"],
                     "retrieval_precision": row["retrieval_precision"],
                     "strict_within_fp_budget": counts["false_positive"] <= max_false_positives,
                     "retrieval_within_fp_budget": row["retrieval_counts"]["false_positive"] <= max_false_positives,
                     "strict_review_pairs": sum(c["flagged"] for c in row["cases"]),
                     "all_review_pairs": sum(c["retrieved"] for c in row["cases"]),
                     "cases": row["cases"]})
    return {"schema_version": 1, "tool_version": __version__,
            "benchmark_sha256": evaluation["benchmark_sha256"],
            "base_options": options.__dict__, "normalization": "relationships",
            "scored_split": "development", "holdout_scored": False,
            "max_false_positives": max_false_positives, "rows": rows,
            "interpretation": "Development-only diagnostic sweep; defaults are unchanged. "
            "Full benchmark split integrity is validated, but holdout outcomes are never computed. "
            "FP budgets count labeled pairs, not estimated population rates. Review totals include ambiguous/insufficient cases. "
            "Select settings before evaluating a genuinely unseen problem/source-family set. "
            "Published synthetic cases cannot certify real-world accuracy."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("--thresholds", type=float, nargs="+", required=True)
    parser.add_argument("--max-false-positives", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("Output already exists")
        report = sweep(args.benchmark, args.thresholds, max_false_positives=args.max_false_positives)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
            handle.write("\n")
        print(f"Compared {len(report['rows'])} thresholds on development cases only. Defaults unchanged.")
    except (ValueError, OSError, TypeError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
