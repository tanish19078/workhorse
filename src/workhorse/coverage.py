"""Summarize the imported dataset and explicitly missing expected cells."""

from collections import Counter
import hashlib

from .imports import Submission


def coverage(submissions: list[Submission], tasks: list[str] | None = None,
             authors: list[str] | None = None) -> dict:
    expected_tasks = sorted(set(tasks or [s.task for s in submissions]))
    expected_authors = sorted(set(authors or [s.author for s in submissions]))
    cells = []
    for task in expected_tasks:
        for author in expected_authors:
            selected = [s for s in submissions if s.task == task and s.author == author]
            cells.append({"task": task, "author": author, "imported": len(selected),
                          "ids": [s.id for s in selected],
                          "languages": dict(sorted(Counter(s.language for s in selected).items())),
                          "verdicts": dict(sorted(Counter(s.verdict or "unknown" for s in selected).items())),
                          "timestamps_missing": sum(not s.submitted_at for s in selected)})
    hashes = {}
    for item in submissions:
        digest = hashlib.sha256(item.source.encode()).hexdigest()
        hashes.setdefault(digest, []).append(item.id)
    return {"schema_version": 1, "submissions": len(submissions), "cells": cells,
            "missing_cells": [c for c in cells if c["imported"] == 0],
            "duplicate_source_groups": [ids for ids in hashes.values() if len(ids) > 1],
            "unexpected_ids": [s.id for s in submissions if s.task not in expected_tasks or s.author not in expected_authors],
            "interpretation": "Missing cells mean no source was imported for that task/author; "
                              "they do not prove that no submission exists on the original platform. "
                              "Duplicate source hashes include revisions and are not misconduct findings."}
