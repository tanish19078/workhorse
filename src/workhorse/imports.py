"""Load explicitly exported submissions without contacting external services."""

from dataclasses import dataclass
import csv
import json
from pathlib import Path
from urllib.parse import urlsplit


LANGUAGES = {"python": "python", "py": "python", "python3": "python",
             "java": "java", "c": "c", "cpp": "cpp", "c++": "cpp"}
MAX_SOURCE_BYTES = 1_048_576
EXTENSIONS = {".py": "python", ".java": "java", ".c": "c",
              ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp"}


@dataclass(frozen=True)
class Submission:
    id: str
    author: str
    task: str
    language: str
    path: str
    source: str
    submitted_at: str = ""
    url: str = ""
    verdict: str = ""

    def metadata(self) -> dict:
        return {key: value for key, value in self.__dict__.items() if key != "source"}


def load_manifest(path: Path) -> list[Submission]:
    """Read JSON or CSV. Source paths must resolve beneath the manifest folder."""
    path = path.resolve(strict=True)
    if path.stat().st_size > 10 * MAX_SOURCE_BYTES:
        raise ValueError("Manifest exceeds the 10 MiB limit")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        if path.suffix.lower() == ".csv":
            rows = list(csv.DictReader(handle))
        elif path.suffix.lower() == ".json":
            rows = json.load(handle)
        else:
            raise ValueError("Manifest must be .json or .csv")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Manifest must contain a nonempty list of submissions")
    result = []
    seen = set()
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"Row {number}: expected an object")
        required = ("id", "author", "task", "language", "path")
        if any(not isinstance(row.get(k), str) or not row[k].strip() for k in required):
            raise ValueError(f"Row {number}: required nonempty strings: {', '.join(required)}")
        values = {k: row[k].strip() for k in required}
        if values["id"] in seen:
            raise ValueError(f"Row {number}: duplicate submission ID {values['id']}")
        seen.add(values["id"])
        language = LANGUAGES.get(values["language"].lower())
        if language is None:
            raise ValueError(f"Row {number}: unsupported language {values['language']}")
        relative = Path(values["path"])
        if relative.is_absolute():
            raise ValueError(f"Row {number}: source path must be relative")
        source_path = (path.parent / relative).resolve(strict=True)
        if not source_path.is_relative_to(path.parent) or not source_path.is_file():
            raise ValueError(f"Row {number}: source must be a file beneath the manifest folder")
        with source_path.open("rb") as source_handle:
            raw = source_handle.read(MAX_SOURCE_BYTES + 1)
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError(f"Row {number}: source exceeds 1 MiB")
        source = raw.decode("utf-8-sig")
        if not source.strip():
            raise ValueError(f"Row {number}: empty source")
        if source.lstrip().lower().startswith(("<!doctype html", "<html", "<head", "<body")):
            raise ValueError(f"Row {number}: HTML page found instead of source code; check the export")
        optional = {}
        for key in ("submitted_at", "url", "verdict"):
            value = row.get(key, "")
            if not isinstance(value, str):
                raise ValueError(f"Row {number}: {key} must be a string")
            optional[key] = value.strip()
        if optional["url"]:
            parsed = urlsplit(optional["url"])
            if parsed.scheme not in ("https", "http") or not parsed.netloc:
                raise ValueError(f"Row {number}: URL must be an HTTP(S) URL")
        values["language"] = language
        values["path"] = relative.as_posix()
        result.append(Submission(**values, source=source, **optional))
    return result


def create_manifest(root: Path, output: Path) -> int:
    """Index task/author/source.ext exports, without rewriting source files."""
    root = root.resolve(strict=True)
    output = output.resolve()
    if not root.is_dir() or not output.is_relative_to(root):
        raise ValueError("Manifest destination must be inside the export folder")
    if output.suffix.lower() != ".json":
        raise ValueError("Generated manifest must use .json")
    if output.exists():
        raise ValueError("Manifest destination already exists")
    rows = []
    for path in sorted(root.glob("*/*/*")):
        if path.suffix.lower() not in EXTENSIONS:
            continue
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError("Export contains a source outside its folder or a non-file")
        if not resolved.is_relative_to(output.parent):
            raise ValueError("Place the manifest at the export root")
        relative = path.relative_to(root)
        task, author, filename = relative.parts
        rows.append({"id": relative.as_posix(), "task": task, "author": author,
                     "language": EXTENSIONS[path.suffix.lower()],
                     "path": path.relative_to(output.parent).as_posix()})
    if not rows:
        raise ValueError("No supported sources found; use task/author/source.ext")
    # Validate before committing the manifest; failed generation leaves no file.
    import tempfile
    import os
    fd, temporary = tempfile.mkstemp(suffix=".json", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2)
            handle.write("\n")
        load_manifest(Path(temporary))
        # Exclusive creation avoids replacing an export if another process wrote it.
        with output.open("x", encoding="utf-8") as handle:
            handle.write(Path(temporary).read_text(encoding="utf-8"))
    finally:
        Path(temporary).unlink(missing_ok=True)
    return len(rows)
