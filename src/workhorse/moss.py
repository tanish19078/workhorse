"""Optional local staging and explicit execution of a user-owned MOSS client.

No credentials or third-party client are bundled. Imports never fetch result URLs.
"""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shlex
import subprocess
from urllib.parse import urljoin, urlsplit

from .imports import load_manifest, MAX_SOURCE_BYTES

EXTENSIONS = {"python": ".py", "cpp": ".cpp", "java": ".java", "c": ".c"}
MOSS_LANGUAGES = {"python": "python", "cpp": "cc", "java": "java", "c": "c"}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def prepare(manifest, output, baseline=None):
    """Snapshot UTF-8 exports using neutral filenames, grouped by task/language."""
    submissions = load_manifest(Path(manifest))
    bases = load_manifest(Path(baseline)) if baseline else []
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    plan = {"schema_version": 1, "groups": [], "notice":
            "Execution sends staged code to Stanford MOSS; result URLs expose copies of that code. "
            "MOSS scores do not establish plagiarism. No submission has been made by prepare."}
    keys = sorted({(s.task, s.language) for s in submissions})
    for number, (task, language) in enumerate(keys, 1):
        group = {"id": f"g{number:04d}", "task": task, "language": language,
                 "files": [], "baselines": []}
        folder = output / group["id"]
        folder.mkdir()
        selected = [s for s in submissions if (s.task, s.language) == (task, language)]
        allowed = [s for s in bases if s.language == language and s.task in (task, "*")]
        for kind, items, prefix in (("files", selected, "s"), ("baselines", allowed, "b")):
            for index, item in enumerate(items, 1):
                name = f"{prefix}{index:06d}{EXTENSIONS[language]}"
                raw = item.source.encode("utf-8")
                (folder / name).write_bytes(raw)
                group[kind].append({"file": name, "sha256": digest(raw), **item.metadata()})
        plan["groups"].append(group)
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    return plan


def checked_group(plan_path, group_id):
    """Reject moved/tampered snapshots, traversal and mismatched file types."""
    plan_path = Path(plan_path).resolve(strict=True)
    if plan_path.stat().st_size > 10 * MAX_SOURCE_BYTES:
        raise ValueError("Plan exceeds 10 MiB")
    plan = json.loads(plan_path.read_text())
    if plan.get("schema_version") != 1 or not re.fullmatch(r"g\d{4}", group_id):
        raise ValueError("Invalid MOSS plan or group ID")
    matches = [g for g in plan["groups"] if g["id"] == group_id]
    if len(matches) != 1:
        raise ValueError("Group must exist exactly once")
    group = matches[0]
    if group["language"] not in EXTENSIONS:
        raise ValueError("Unsupported MOSS language")
    folder = plan_path.parent / group_id
    names = set()
    for kind, prefix in (("files", "s"), ("baselines", "b")):
        for item in group[kind]:
            name = item["file"]
            if not re.fullmatch(prefix + r"\d{6}" + re.escape(EXTENSIONS[group["language"]]), name) or name in names:
                raise ValueError("Invalid or duplicate staged filename")
            names.add(name)
            path = folder / name
            if path.is_symlink() or not path.resolve(strict=True).is_relative_to(plan_path.parent):
                raise ValueError("Staged source escaped the plan folder")
            if path.stat().st_size > MAX_SOURCE_BYTES or digest(path.read_bytes()) != item["sha256"]:
                raise ValueError("Staged source hash mismatch")
    return group, folder


def command(plan_path, group_id, client):
    group, folder = checked_group(plan_path, group_id)
    if len({s["author"] for s in group["files"]}) < 2:
        raise ValueError("MOSS batch requires at least two distinct authors")
    client = Path(client).resolve(strict=True)
    if not client.is_file():
        raise ValueError("Client must be the user-owned MOSS Perl script")
    argv = ["perl", str(client), "-l", MOSS_LANGUAGES[group["language"]]]
    for item in group["baselines"]:
        argv += ["-b", item["file"]]
    argv += [s["file"] for s in group["files"]]
    return argv, folder


def result_url(url):
    parts = urlsplit(url)
    if (parts.scheme not in ("http", "https") or parts.hostname != "moss.stanford.edu"
            or parts.username or parts.password or parts.port not in (None, 80, 443)
            or not parts.path.startswith("/results/") or parts.query or parts.fragment):
        raise ValueError("Expected a Stanford MOSS result URL")
    return url


class IndexParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.row, self.cell, self.link = [], None, None, None
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = {"text": "", "links": []}
        elif tag == "a" and self.cell is not None:
            self.link = dict(attrs).get("href", "")
            self.cell["links"].append(self.link)

    def handle_data(self, data):
        self.text.append(data)
        if self.cell is not None:
            self.cell["text"] += data

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def import_index(plan_path, group_id, html_path, url):
    """Parse a saved MOSS index locally; preserve directional percentages."""
    group, _ = checked_group(plan_path, group_id)
    result_url(url)
    if not urlsplit(url).path.endswith("/"):
        raise ValueError("Use the result directory URL with a trailing slash")
    html_path = Path(html_path)
    if html_path.stat().st_size > 10 * MAX_SOURCE_BYTES:
        raise ValueError("MOSS HTML exceeds 10 MiB")
    raw = html_path.read_bytes()
    parser = IndexParser()
    parser.feed(raw.decode("utf-8-sig"))
    heading = " ".join(parser.text)
    if not all(re.search(pattern, heading, re.I) for pattern in (r"File\s*1", r"File\s*2", r"Lines\s*Matched")):
        raise ValueError("Not a recognized MOSS result index")
    by_name = {s["file"]: s for s in group["files"]}
    pairs, seen, excluded = [], set(), 0
    for row in parser.rows:
        # Ignore headings; reject malformed candidate rows rather than partial success.
        if not any("%" in c["text"] for c in row):
            continue
        if len(row) != 3:
            raise ValueError("Unrecognized MOSS result row")
        sides = []
        for cell in row[:2]:
            match = re.fullmatch(r"\s*(.*?)\s*\((\d+)%\)\s*", cell["text"])
            if not match or int(match[2]) > 100 or len(cell["links"]) != 1:
                raise ValueError("Invalid MOSS percentage or link")
            # Clients can display a source directory prefix, never treat it as a path to open.
            name = match[1].replace("\\", "/").rsplit("/", 1)[-1]
            if name not in by_name:
                raise ValueError("MOSS result references an unknown source")
            link = result_url(urljoin(url, cell["links"][0]))
            if urlsplit(link).path.rsplit("/", 1)[0] != urlsplit(url).path.rstrip("/"):
                raise ValueError("MOSS match link escaped its result run")
            sides.append((by_name[name], int(match[2]), link))
        if not row[2]["text"].strip().isdigit():
            raise ValueError("Invalid MOSS matched line count")
        left, right = sides
        key = tuple(sorted((left[0]["id"], right[0]["id"])))
        if key[0] == key[1] or key in seen or left[2] != right[2]:
            raise ValueError("Duplicate, self, or inconsistent MOSS pair")
        seen.add(key)
        if left[0]["author"] == right[0]["author"]:
            excluded += 1
            continue
        pairs.append({"left": left[0]["id"], "right": right[0]["id"],
                      "left_sha256": left[0]["sha256"], "right_sha256": right[0]["sha256"],
                      "left_percent": left[1], "right_percent": right[1],
                      "matched_lines": int(row[2]["text"].strip()), "match_url": left[2],
                      "category": "external_moss_signal"})
    return {"schema_version": 1, "tool": "MOSS", "group": group_id,
            "task": group["task"], "language": group["language"], "result_url": url,
            "index_sha256": digest(raw), "plan_sha256": digest(Path(plan_path).read_bytes()), "pairs": pairs, "same_author_excluded": excluded,
            "interpretation": "External similarity signals, not verdicts or independent votes. "
            "An empty result does not prove independent authorship. Inspect highlighted code and templates."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("manifest", type=Path)
    prep.add_argument("--baseline", type=Path)
    prep.add_argument("--output", type=Path, required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("plan", type=Path)
    submit.add_argument("--group", required=True)
    submit.add_argument("--client", type=Path, required=True)
    submit.add_argument("--execute", action="store_true", help="Send this one batch to Stanford MOSS")
    imp = sub.add_parser("import")
    imp.add_argument("plan", type=Path)
    imp.add_argument("html", type=Path)
    imp.add_argument("--group", required=True)
    imp.add_argument("--result-url", required=True)
    imp.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "prepare":
            plan = prepare(args.manifest, args.output, args.baseline)
            print(f"Prepared {len(plan['groups'])} local groups. No code sent.")
        elif args.action == "submit":
            argv, folder = command(args.plan, args.group, args.client)
            print("Working directory:", folder)
            print("Command:", shlex.join(argv))
            print("Execution sends source code to Stanford; anyone with the result URL can view it.")
            if args.execute:
                receipt = folder / "submission.json"
                if receipt.exists():
                    raise ValueError("This batch already has a submission receipt; do not submit it twice")
                # Never run a source file, shell, automatic retries, or every group in a loop.
                completed = subprocess.run(argv, cwd=folder, capture_output=True, text=True,
                                           timeout=120, check=True)
                urls = re.findall(r"https?://moss\.stanford\.edu/results/[^\s<>]+", completed.stdout)
                if not urls:
                    raise ValueError("MOSS client returned no result URL; do not retry blindly")
                url = result_url(urls[-1])
                with receipt.open("x") as handle:
                    json.dump({"result_url": url, "plan_sha256": digest(args.plan.read_bytes()),
                               "client_sha256": digest(Path(argv[1]).read_bytes()), "argv": argv}, handle, indent=2)
                    handle.write("\n")
                print(url)
            else:
                print("Dry run. Add --execute only to send this batch's sources to Stanford.")
        else:
            if args.output.exists():
                raise ValueError("Output already exists")
            report = import_index(args.plan, args.group, args.html, args.result_url)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x") as handle:
                json.dump(report, handle, indent=2)
                handle.write("\n")
            print(f"Imported {len(report['pairs'])} external signals locally.")
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
