"""Exact normalized Python function matches for already retrieved review pairs.

Functions are normalized in isolation to avoid module scope-number shifts. This
is supplementary excerpt evidence, never a promotion or an equivalence claim.
"""
import argparse
import ast
import hashlib
import json
import platform
from . import __version__
from pathlib import Path
import symtable

from .imports import load_manifest
from .reviews import load_report
from .tokens import normalize


def functions(source, min_tokens=30):
    if min_tokens < 1:
        raise ValueError("Minimum function tokens must be positive")
    tree = ast.parse(source)
    accepted, declined = [], []
    lines = source.splitlines(keepends=True)
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        parameters = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
        parameters += [p for p in (node.args.vararg, node.args.kwarg) if p]
        if (node.decorator_list or node.args.defaults or any(node.args.kw_defaults)
                or node.returns or any(p.annotation for p in parameters)
                or any(isinstance(n, (ast.Global, ast.Nonlocal)) for n in ast.walk(node))
                or getattr(node, "type_params", [])):
            declined.append({"name": node.name, "line": node.lineno,
                             "reason": "Function has contextual declarations, defaults, annotations, or decorators"})
            continue
        segment = "".join(lines[node.lineno - 1:node.end_lineno])
        try:
            tokens = tuple(t.value for t in normalize(segment, "python"))
            table = symtable.symtable(segment, "<function>", "exec").get_children()[0]
        except (ValueError, SyntaxError):
            declined.append({"name": node.name, "line": node.lineno,
                             "reason": "Function binding analysis declined"})
            continue
        if len(tokens) >= min_tokens:
            external = sorted(n for n in table.get_identifiers() if table.lookup(n).is_global())
            accepted.append({"name": node.name, "start_line": node.lineno,
                             "end_line": node.end_lineno, "tokens": tokens,
                             "external_names": external})
    return accepted, declined


def analyze(manifest, report_path, baseline=None, min_tokens=30):
    submissions = {s.id: s for s in load_manifest(Path(manifest))}
    report = load_report(Path(report_path))
    for metadata in report["submissions"]:
        item = submissions.get(metadata["id"])
        if (item is None or hashlib.sha256(item.source.encode()).hexdigest() != metadata["sha256"]
                or item.task != metadata["task"] or item.language != metadata["language"]
                or item.author != metadata["author"]):
            raise ValueError("Function evidence source does not match report provenance")
    excluded, baseline_sources = {}, []
    for base in load_manifest(Path(baseline)) if baseline else []:
        baseline_sources.append({**base.metadata(), "sha256": hashlib.sha256(base.source.encode()).hexdigest()})
        if base.language == "python":
            fragments, _ = functions(base.source, min_tokens)
            excluded.setdefault(base.task, set()).update(f["tokens"] for f in fragments)
    cache, declines, pairs = {}, [], []
    def fragments(item):
        if item.id not in cache:
            try:
                cache[item.id], notes = functions(item.source, min_tokens)
                declines.extend({"id": item.id, **note} for note in notes)
            except SyntaxError:
                cache[item.id] = []
                declines.append({"id": item.id, "reason": "Invalid Python source"})
        return cache[item.id]
    for candidate in report["findings"] + report.get("additional_candidates", []):
        left, right = (submissions[candidate[side]] for side in ("left", "right"))
        if left.language != "python" or right.language != "python":
            continue
        allowed = excluded.get(left.task, set()) | excluded.get("*", set())
        right_index = {}
        for fragment in fragments(right):
            right_index.setdefault(fragment["tokens"], []).append(fragment)
        matches = []
        for a in fragments(left):
            if a["tokens"] in allowed:
                continue
            for b in right_index.get(a["tokens"], []):
                matches.append({"left": {k: v for k, v in a.items() if k != "tokens"},
                                "right": {k: v for k, v in b.items() if k != "tokens"},
                                "normalized_tokens": len(a["tokens"])})
        if matches:
            pairs.append({"left": left.id, "right": right.id,
                          "category": candidate.get("category", "review_flag"),
                          "matches": matches[:5], "total_matches": len(matches)})
    return {"schema_version": 1, "tool_version": __version__, "python_version": platform.python_version(),
            "baseline_sources": baseline_sources, "report_sha256": hashlib.sha256(Path(report_path).read_bytes()).hexdigest(),
            "min_tokens": min_tokens, "pairs": pairs, "declined_functions": declines,
            "interpretation": "Exact binding-normalized function excerpts; original pair categories are unchanged. "
            "Canonical algorithms can match independently. External names and surrounding module context still require review. "
            "Only top-level Python functions in already retrieved pairs are inspected; absence is not an assessment. "
            "Allowed complete functions are excluded only when --baseline is supplied; partial boilerplate is not removed."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--min-tokens", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = analyze(args.manifest, args.report, args.baseline, args.min_tokens)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as handle:
            json.dump(result, handle, indent=2)
            handle.write("\n")
        print(f"Added function evidence for {len(result['pairs'])} retrieved pairs; categories unchanged.")
    except (ValueError, OSError, KeyError, SyntaxError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
