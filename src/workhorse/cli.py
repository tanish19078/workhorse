"""Command-line entry point for local exports."""

import argparse
from pathlib import Path
import sys

from . import __version__
from .compare import Options, compare
from .imports import create_manifest, load_manifest
from .report import write_reports
from .reviews import STATES, init_reviews, load_reviews, record_review
from .packets import export_packet
from .coverage import coverage
from .reviews import save_json
from .evaluation import evaluate
import json


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare exported source files locally for human review.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index", help="Create a manifest from task/author/source.ext folders")
    index.add_argument("directory", type=Path)
    index.add_argument("--manifest", default="manifest.json", help="Filename at the export root")
    validate = commands.add_parser("validate", help="Check an export manifest and its source files")
    validate.add_argument("manifest", type=Path)
    inventory = commands.add_parser("coverage", help="Summarize imports and expected task/author gaps")
    inventory.add_argument("manifest", type=Path)
    inventory.add_argument("--task", action="append", help="Expected task; repeat for several")
    inventory.add_argument("--author", action="append", help="Expected author; repeat for several")
    inventory.add_argument("--output", type=Path)
    benchmark = commands.add_parser("evaluate", help="Measure flags against labeled development and holdout cases")
    benchmark.add_argument("benchmark", type=Path)
    benchmark.add_argument("--threshold", type=float, default=0.5)
    benchmark.add_argument("--output", type=Path)
    review = commands.add_parser("review", help="Generate JSON and HTML comparison reports")
    review.add_argument("manifest", type=Path)
    review.add_argument("--output", type=Path, default=Path("reports"))
    review.add_argument("--baseline", type=Path, help="Manifest of known allowed templates")
    review.add_argument("--threshold", type=float, default=0.5, help="Minimum containment (default: 0.5)")
    review.add_argument("--normalization", choices=("relationships", "raw", "legacy"), default="relationships")
    review.add_argument("--min-tokens", type=int, default=30)
    review.add_argument("--min-shared", type=int, default=3)
    review.add_argument("--k", type=int, default=9, help="Tokens per shingle")
    review.add_argument("--window", type=int, default=4, help="Winnowing window")
    review.add_argument("--common-fraction", type=float, default=0.8)
    review.add_argument("--max-candidates", type=int, default=100_000)
    review.add_argument("--max-posting", type=int, default=500)
    review.add_argument("--no-corpus-filter", dest="corpus_filter", action="store_false",
                        help="Keep widespread fingerprints; known baselines still apply")
    review.add_argument("--force", action="store_true", help="Replace existing report files")
    initialize = commands.add_parser("review-init", help="Create a separate reviewer workspace")
    initialize.add_argument("report", type=Path)
    initialize.add_argument("--output", type=Path, required=True)
    listing = commands.add_parser("review-list", help="List pair keys and reviewer states")
    listing.add_argument("workspace", type=Path)
    listing.add_argument("--status", choices=STATES)
    decision = commands.add_parser("review-note", help="Record a human review decision with an audit trail")
    decision.add_argument("workspace", type=Path)
    decision.add_argument("pair")
    decision.add_argument("--status", choices=STATES, required=True)
    decision.add_argument("--note", default="")
    decision.add_argument("--reviewer", required=True)
    decision.add_argument("--contrary-evidence", default="")
    packet = commands.add_parser("packet", help="Export selected reviewed pairs as an evidence ZIP")
    packet.add_argument("report", type=Path)
    packet.add_argument("workspace", type=Path)
    packet.add_argument("--pair", action="append", required=True, help="Pair key; repeat to select several")
    packet.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "evaluate":
            result = evaluate(args.benchmark, Options(threshold=args.threshold))
            if args.output:
                save_json(args.output, result, exclusive=True)
                print(f"Evaluation saved to {args.output}")
            else:
                print(json.dumps(result, indent=2))
            return 0
        if args.command == "packet":
            count = export_packet(args.report, args.workspace, args.pair, args.output)
            print(f"Exported {count} reviewed pairs to {args.output}")
            return 0
        if args.command == "review-init":
            count = init_reviews(args.report, args.output)
            print(f"Created review workspace: {count} pairs in {args.output}")
            return 0
        if args.command == "review-list":
            for key, item in load_reviews(args.workspace)["pairs"].items():
                if args.status is None or item["status"] == args.status:
                    print(f"{key}\t{item['status']}\t{item['left']} ↔ {item['right']}")
            return 0
        if args.command == "review-note":
            record_review(args.workspace, args.pair, args.status, args.note, args.reviewer,
                          args.contrary_evidence)
            print(f"Recorded {args.status} for {args.pair}")
            return 0
        if args.command == "index":
            destination = args.directory / args.manifest
            count = create_manifest(args.directory, destination)
            print(f"Indexed {count} sources: {destination}")
            return 0
        submissions = load_manifest(args.manifest)
        if args.command == "coverage":
            inventory = coverage(submissions, args.task, args.author)
            if args.output:
                save_json(args.output, inventory, exclusive=True)
                print(f"Coverage saved to {args.output}")
            else:
                print(json.dumps(inventory, ensure_ascii=False, indent=2))
            return 0
        if args.command == "validate":
            print(f"Valid export: {len(submissions)} submissions")
            return 0
        options = Options(**{key: getattr(args, key) for key in Options.__dataclass_fields__})
        baselines = load_manifest(args.baseline) if args.baseline else []
        report = compare(submissions, options, baselines)
        write_reports(report, args.output, args.force)
        print(f"Reviewed {len(submissions)} submissions; {report['summary']['flagged_pairs']} pairs met review thresholds.")
        print(f"Reports: {args.output / 'report.html'} and {args.output / 'report.json'}")
        print(report["interpretation"])
        return 0
    except (OSError, ValueError) as exc:
        print(f"workhorse: {exc}", file=sys.stderr)
        return 2
