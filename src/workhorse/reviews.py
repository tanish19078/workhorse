"""Human judgments are stored separately from computed similarity scores."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import math
import re
from .io_utils import read_bounded


STATES = ("unreviewed", "explained", "investigate")
MAX_REPORT_BYTES = 50 * 1024 * 1024


def read_json_snapshot(path: Path):
    data = read_bounded(path, MAX_REPORT_BYTES, "Review data exceeds 50 MiB")
    document = json.loads(data)
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Expected a version 1 Workhorse document")
    return document, hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    return read_json_snapshot(path)[0]


def load_report(path: Path, *, with_digest=False):
    report, digest = read_json_snapshot(path)
    if not isinstance(report.get("submissions"), list) or not isinstance(report.get("findings"), list):
        raise ValueError("Invalid Workhorse report")
    ids = set()
    for item in report["submissions"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("sha256"), str):
            raise ValueError("Report submissions need IDs and source hashes")
        if not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]):
            raise ValueError("Invalid source hash in report")
        for field in ("author", "task", "language", "path"):
            if not isinstance(item.get(field), str):
                raise ValueError(f"Report submission missing {field}")
        for field in ("url", "submitted_at", "verdict"):
            if field in item and not isinstance(item[field], str):
                raise ValueError(f"Invalid report submission {field}")
        if item.get("analysis_status", "analyzed") not in ("analyzed", "declined") or not isinstance(item.get("analysis_note", ""), str):
            raise ValueError("Invalid submission analysis diagnostics")
        if item["id"] in ids:
            raise ValueError("Duplicate report submission ID")
        ids.add(item["id"])
    additional = report.get("additional_candidates", [])
    if not isinstance(additional, list):
        raise ValueError("Invalid additional candidate list")
    seen_pairs = set()
    for finding in report["findings"] + additional:
        if not isinstance(finding, dict) or finding.get("left") not in ids or finding.get("right") not in ids:
            raise ValueError("Report finding refers to an unknown submission")
        if finding["left"] == finding["right"]:
            raise ValueError("Report finding must refer to two submissions")
        pair = frozenset((finding["left"], finding["right"]))
        if pair in seen_pairs:
            raise ValueError("Duplicate comparison pair in report")
        seen_pairs.add(pair)
        if finding.get("category", "review_flag") not in ("review_flag", "broad_candidate"):
            raise ValueError("Invalid comparison category")
        if finding.get("evidence_normalization", "legacy") not in ("legacy", "relationships", "raw"):
            raise ValueError("Invalid evidence normalization")
        for field in ("containment", "jaccard"):
            value = finding.get(field)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"Invalid finding {field}")
        for field in ("task", "language"):
            if not isinstance(finding.get(field), str):
                raise ValueError(f"Invalid finding {field}")
        if type(finding.get("shared_fingerprints")) is not int or finding["shared_fingerprints"] < 0:
            raise ValueError("Invalid shared fingerprint count")
        if not isinstance(finding.get("evidence"), list):
            raise ValueError("Finding must contain an evidence list")
        if "cautions" in finding and (not isinstance(finding["cautions"], list)
                                     or any(not isinstance(note, str) for note in finding["cautions"])):
            raise ValueError("Invalid finding cautions")
        if "signals" in finding:
            signals = finding["signals"]
            if not isinstance(signals, dict):
                raise ValueError("Invalid comparison signals")
            for key in ("raw_containment", "rarity_weighted_containment"):
                value = signals.get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError("Invalid comparison signal score")
            for key in ("rarity_basis_authors", "longest_representative_span"):
                if type(signals.get(key)) is not int or signals[key] < 0:
                    raise ValueError("Invalid comparison signal count")
        for block in finding["evidence"]:
            if not isinstance(block, dict) or type(block.get("tokens")) is not int or block["tokens"] < 1:
                raise ValueError("Invalid evidence token count")
            for side in ("left", "right"):
                span = block.get(side)
                if not isinstance(span, dict) or not isinstance(span.get("excerpt"), str):
                    raise ValueError("Invalid evidence excerpt")
                if any(type(span.get(k)) is not int for k in ("start_line", "end_line")):
                    raise ValueError("Invalid evidence line numbers")
                if not 1 <= span["start_line"] <= span["end_line"]:
                    raise ValueError("Invalid evidence line range")
    if not isinstance(report.get("interpretation"), str) or not isinstance(report.get("options"), dict):
        raise ValueError("Report needs interpretation and options")
    summary = report.get("summary")
    if not isinstance(summary, dict) or any(type(summary.get(key)) is not int or summary[key] < 0
        for key in ("submissions", "groups", "candidate_pairs", "flagged_pairs")):
        raise ValueError("Invalid report summary")
    if summary["submissions"] != len(ids) or summary["flagged_pairs"] != len(report["findings"]):
        raise ValueError("Report summary does not match its contents")
    if type(summary.get("additional_candidates", 0)) is not int or summary.get("additional_candidates", 0) != len(additional):
        raise ValueError("Additional candidate summary does not match its contents")
    if any(f.get("category", "review_flag") != "review_flag" for f in report["findings"]):
        raise ValueError("Broad candidates must remain separate from review flags")
    if any(f.get("category") != "broad_candidate" for f in additional):
        raise ValueError("Additional candidates require an explicit broad category")
    groups = report.get("groups")
    if not isinstance(groups, list) or any(not isinstance(group, dict) for group in groups):
        raise ValueError("Invalid report groups")
    for group in groups:
        if any(not isinstance(group.get(k), str) for k in ("task", "language")):
            raise ValueError("Invalid report group identifiers")
        if any(type(group.get(k)) is not int or group[k] < 0 for k in
               ("submissions", "short_sources", "excluded_common_fingerprints",
                "excluded_crowded_fingerprints", "candidate_pairs")):
            raise ValueError("Invalid report group counts")
    return (report, digest) if with_digest else report


def document_digest(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def pair_key(left: dict, right: dict) -> str:
    identity = sorted([(left["id"], left["sha256"]), (right["id"], right["sha256"])])
    return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()[:24]


def save_json(path: Path, document: dict, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    if exclusive:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
        return
    fd, temporary = tempfile.mkstemp(prefix=".workhorse-review-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def init_reviews(report_path: Path, output: Path) -> int:
    report = load_report(report_path)
    submissions = {item["id"]: item for item in report["submissions"]}
    pairs = {}
    for finding in report["findings"] + report.get("additional_candidates", []):
        left, right = submissions[finding["left"]], submissions[finding["right"]]
        key = pair_key(left, right)
        pairs[key] = {"left": left["id"], "right": right["id"],
                      "category": finding.get("category", "review_flag"),
                      "evidence_normalization": finding.get("evidence_normalization", "legacy"),
                      "source_hashes": {left["id"]: left["sha256"], right["id"]: right["sha256"]},
                      "status": "unreviewed", "note": "", "contrary_evidence": "", "history": []}
    save_json(output, {"schema_version": 1, "pairs": pairs}, exclusive=True)
    return len(pairs)


def load_reviews(path: Path) -> dict:
    reviews = read_json(path)
    if not isinstance(reviews.get("pairs"), dict):
        raise ValueError("Expected a review workspace with pairs")
    for key, item in reviews["pairs"].items():
        if not isinstance(key, str) or not isinstance(item, dict) or item.get("status") not in STATES:
            raise ValueError("Invalid review pair or status")
        if not isinstance(item.get("history"), list):
            raise ValueError("Review pair must have a history")
        for field in ("left", "right", "note", "contrary_evidence"):
            if not isinstance(item.get(field), str):
                raise ValueError(f"Invalid review {field}")
        if not isinstance(item.get("source_hashes"), dict):
            raise ValueError("Review pair must have source hashes")
    return reviews


def record_review(path: Path, key: str, status: str, note: str, reviewer: str,
                  contrary_evidence: str = ""):
    if status not in STATES:
        raise ValueError(f"Unknown status; choose {', '.join(STATES)}")
    if not reviewer.strip() or (status != "unreviewed" and not note.strip()):
        raise ValueError("Reviewer is required; explained/investigate states require a note")
    reviews = load_reviews(path)
    if key not in reviews["pairs"]:
        raise ValueError("Unknown pair key; use review-list to find the pair")
    item = reviews["pairs"][key]
    entry = {"status": status, "note": note.strip(), "reviewer": reviewer.strip(),
             "contrary_evidence": contrary_evidence.strip(),
             "recorded_at": datetime.now(timezone.utc).isoformat()}
    item.update({field: entry[field] for field in ("status", "note", "contrary_evidence")})
    item["history"].append(entry)
    save_json(path, reviews)
