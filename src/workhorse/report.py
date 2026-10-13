"""Self-contained review reports; all imported text is HTML escaped."""

from html import escape
from pathlib import Path
import json
import os
import tempfile
from urllib.parse import urlsplit


def _link(item):
    label = escape(item["id"])
    url = item.get("url", "")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return label
    return f'<a href="{escape(url, quote=True)}" rel="noreferrer">{label}</a>'


def render_html(report: dict) -> str:
    items = {s["id"]: s for s in report["submissions"]}
    cards = []
    for finding in report["findings"] + report.get("additional_candidates", []):
        left, right = items[finding["left"]], items[finding["right"]]
        evidence = []
        for span in finding["evidence"]:
            columns = []
            for side in ("left", "right"):
                block = span[side]
                text = block["excerpt"]
                note = ""
                if len(text) > 6000:
                    text = text[:6000]
                    note = "<p>Preview truncated; full excerpt is in report.json.</p>"
                columns.append(f'<div><p>Lines {block["start_line"]}–{block["end_line"]}</p>'
                               f'<pre>{escape(text)}</pre>{note}</div>')
            evidence.append(f'<details open><summary>{span["tokens"]} matching normalized tokens</summary>'
                            f'<div class="columns">{"".join(columns)}</div></details>')
        search = escape(" ".join(str(x) for x in (left["author"], right["author"], left["id"],
                                                 right["id"], finding["task"])).lower(), quote=True)
        signals = finding.get("signals", {})
        diagnostics = ""
        if signals:
            diagnostics = (f'<p>Original-token containment {signals["raw_containment"]:.1%} · '
                           f'Rarity-weighted containment {signals["rarity_weighted_containment"]:.1%} · '
                           f'{signals["rarity_basis_authors"]} authors in rarity baseline</p>')
        cautions = "".join(f'<li>{escape(note)}</li>' for note in finding.get("cautions", []))
        cards.append(f'''<article data-search="{search}">
<h2>{_link(left)} ↔ {_link(right)}</h2>
<p><strong>{'Broad candidate — not a review flag' if finding.get('category') == 'broad_candidate' else 'Review flag'}</strong> · Evidence normalization: {escape(finding.get('evidence_normalization', report['options'].get('normalization', 'legacy')))}</p>
<p>{escape(left['author'])} ↔ {escape(right['author'])} · {escape(finding['task'])} · {escape(finding['language'])}</p>
<p class="metrics">Containment {finding['containment']:.1%} · Jaccard {finding['jaccard']:.1%} · {finding['shared_fingerprints']} shared fingerprints</p>
{diagnostics}<ul>{cautions}</ul>
<p>Submitted: {escape(left.get('submitted_at') or 'unknown')} / {escape(right.get('submitted_at') or 'unknown')}</p>
{''.join(evidence)}
<p class="muted">Representative spans can include adjacent template code. Compare the original files and alternative explanations before drawing conclusions.</p>
</article>''')
    summary = report["summary"]
    rows = []
    for group in report["groups"]:
        rows.append("<tr>" + "".join(f"<td>{escape(str(group[key]))}</td>" for key in
                    ("task", "language", "submissions", "short_sources", "excluded_common_fingerprints",
                     "excluded_crowded_fingerprints", "candidate_pairs")) + "</tr>")
    content = "".join(cards) or '<p class="empty">No pairs met the selected review thresholds.</p>'
    settings = escape(json.dumps(report["options"], sort_keys=True, indent=2))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Workhorse · source review</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;background:#f5f6fa;color:#182235;margin:0}}main{{max-width:1100px;margin:40px auto;padding:0 24px}}h1{{font-size:38px;margin-bottom:0}}h2{{font-size:21px}}a{{color:#285ca6}}.notice{{padding:18px;background:#fff1cf;border-left:4px solid #a77816}}.stats{{display:flex;gap:24px;flex-wrap:wrap;margin:24px 0}}.stats strong{{font-size:28px;display:block}}article{{background:white;border:1px solid #dae0ea;border-radius:12px;padding:24px;margin:22px 0}}input{{width:100%;box-sizing:border-box;font:inherit;padding:12px;border:1px solid #a8b4c4;border-radius:8px}}.columns{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.columns>div{{min-width:0}}pre{{font:13px/1.5 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#eef1f7;padding:16px;border-radius:8px}}summary{{cursor:pointer;font-weight:600}}.muted{{color:#596579}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{text-align:left;border-bottom:1px solid #cdd6e4;padding:10px}}.tablewrap{{overflow:auto}}[hidden]{{display:none}}@media(max-width:700px){{.columns{{grid-template-columns:1fr}}main{{padding:0 14px}}}}@media print{{input,label{{display:none}}article{{break-inside:avoid}}body{{background:white}}}}</style></head><body><main>
<p class="muted">WORKHORSE / LOCAL REVIEW</p><h1>Source similarity review</h1>
<p class="notice">{escape(report['interpretation'])}</p>
<div class="stats"><div><strong>{summary['submissions']}</strong>submissions</div><div><strong>{summary['groups']}</strong>task/language groups</div><div><strong>{summary['flagged_pairs']}</strong>review flags</div><div><strong>{summary.get('additional_candidates', 0)}</strong>broad-only leads</div></div>
<label for="search">Filter by submission, author, or task</label><input id="search" type="search" placeholder="Search this report" autocomplete="off">
<p id="visible" aria-live="polite"></p>{content}
<h2>Coverage and exclusions</h2><div class="tablewrap"><table><thead><tr><th>Task</th><th>Language</th><th>Sources</th><th>Short sources</th><th>Common hashes</th><th>Crowded hashes</th><th>Candidates</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>Declined analyses</h2><ul>{''.join('<li>' + escape(s['id'] + ': ' + s.get('analysis_note', '')) + '</li>' for s in report['submissions'] if s.get('analysis_status') == 'declined')}</ul>
<details><summary>Reproducible settings</summary><pre>{settings}</pre></details>
<p class="muted">Scores measure distinct retained token fingerprints. Containment divides by the smaller set; Jaccard divides by the union. Neither score is a probability. Review exports contain source excerpts and author identifiers; share only with authorized reviewers.</p>
</main><script>const input=document.getElementById('search');const cards=[...document.querySelectorAll('article')];function filter(){{const query=input.value.toLowerCase().trim();let count=0;for(const card of cards){{card.hidden=!card.dataset.search.includes(query);if(!card.hidden)count++;}}document.getElementById('visible').textContent=count+' review pairs shown';}}input.addEventListener('input',filter);filter();</script></body></html>'''


def write_reports(report: dict, directory: Path, force: bool = False):
    """Check destinations before writing; replace individual files atomically."""
    directory.mkdir(parents=True, exist_ok=True)
    outputs = {directory / "report.json": json.dumps(report, ensure_ascii=False, indent=2) + "\n",
               directory / "report.html": render_html(report)}
    if not force and any(path.exists() for path in outputs):
        raise ValueError("Report files already exist; choose another folder or pass --force")
    for path, content in outputs.items():
        fd, temporary = tempfile.mkstemp(prefix=".workhorse-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
