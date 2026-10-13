"""Package reviewed pairs with provenance and integrity hashes; no transmission."""

from datetime import datetime, timezone
from html import escape
import hashlib
import json
from pathlib import Path
import zipfile

from . import __version__
from .report import render_html
from .reviews import load_report, load_reviews, pair_key


def export_packet(report_path: Path, workspace_path: Path, keys: list[str], output: Path) -> int:
    if not keys or len(set(keys)) != len(keys):
        raise ValueError("Choose one or more distinct review pair keys")
    if output.suffix.lower() != ".zip":
        raise ValueError("Packet destination must use .zip")
    report = load_report(report_path)
    reviews = load_reviews(workspace_path)
    submissions = {item["id"]: item for item in report["submissions"]}
    findings = {pair_key(submissions[f["left"]], submissions[f["right"]]): f for f in report["findings"]}
    selected = []
    notes = {}
    for key in keys:
        if key not in reviews["pairs"] or key not in findings:
            raise ValueError("Pair is missing or stale; initialize reviews from the current report")
        item = reviews["pairs"][key]
        finding = findings[key]
        expected = {id: submissions[id]["sha256"] for id in (finding["left"], finding["right"])}
        if item["source_hashes"] != expected or {item["left"], item["right"]} != set(expected):
            raise ValueError("Review hashes do not match the current report")
        if item["status"] == "unreviewed" or not item["note"].strip() or not item["history"]:
            raise ValueError("Review the selected pair and record an explanation before export")
        selected.append(finding)
        notes[key] = item
    ids = {f[side] for f in selected for side in ("left", "right")}
    packet_report = {**report, "submissions": [s for s in report["submissions"] if s["id"] in ids],
                     "findings": selected,
                     "summary": {**report["summary"], "submissions": len(ids), "flagged_pairs": len(selected)},
                     "packet_scope": "Selected reviewed pairs only. Group diagnostics refer to the original full run."}
    metadata = {"schema_version": 1, "exporter_version": __version__,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
                "workspace_sha256": hashlib.sha256(workspace_path.read_bytes()).hexdigest(),
                "pairs": notes}
    html = render_html(packet_report)
    annotations = '<section><h2>Human review notes</h2><p>Group diagnostics describe the original full run.</p>'
    for key, item in notes.items():
        annotations += f'<article><h3>{escape(key)} · {escape(item["status"])}</h3>'
        annotations += f'<p>{escape(item["note"])}</p><p>Contrary evidence: {escape(item["contrary_evidence"] or "None recorded; absence is not proof.")}</p></article>'
    html = html.replace("</main>", annotations + "</section></main>")
    members = {"report.json": json.dumps(packet_report, ensure_ascii=False, indent=2),
               "report.html": html,
               "review.json": json.dumps(metadata, ensure_ascii=False, indent=2),
               "README.txt": "Workhorse review packet\n\nSelected reviewed pairs only. Similarity is not a plagiarism finding.\n"
                             "Review notes and contrary evidence are in review.json and report.html.\n"
                             "Full original source files are not included; hashes identify the decoded UTF-8 sources.\n"
                             "Group coverage and candidate counts describe the full original comparison run.\n"
                             "SHA256SUMS verifies packet members, not authenticity or reviewer identity.\n"
                             "This packet contains source excerpts and author/reviewer identifiers. Share only with authorized reviewers.\n"}
    encoded = {name: content.encode("utf-8") for name, content in members.items()}
    encoded["SHA256SUMS"] = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in encoded.items()).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive output never silently replaces an existing packet.
    with output.open("xb") as handle:
        with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in encoded.items():
                archive.writestr(name, content)
    return len(selected)
