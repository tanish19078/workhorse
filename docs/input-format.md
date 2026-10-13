# Export format

JSON manifests contain an array of submission records. CSV uses the same
field names in its header.

```json
[
  {
    "id": "submission-001",
    "author": "author-a",
    "task": "window-score",
    "language": "python",
    "path": "sources/submission-001.py",
    "submitted_at": "2026-01-01T10:00:00Z",
    "url": "https://example.org/submissions/submission-001",
    "verdict": "accepted"
  }
]
```

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | Yes | Unique submission identifier within this manifest |
| `author` | Yes | Account or team identifier; same-author revisions are excluded from pairing |
| `task` | Yes | Exact problem identifier used for comparison grouping |
| `language` | Yes | `python`, `java`, `c`, or `cpp`; aliases `py`, `python3`, `c++` accepted |
| `path` | Yes | UTF-8 source file relative to the manifest directory |
| `submitted_at` | No | Exported timestamp; preserve timezone when available |
| `url` | No | HTTP(S) source reference shown in the review report |
| `verdict` | No | Informational exported verdict; comparisons include all supplied verdicts |

All values must be strings. Unknown fields are ignored. Required fields must
be nonempty, IDs must be unique, and sources must be nonempty. Source files
are limited to 1 MiB each; manifests to 10 MiB. Absolute paths and symlinks
resolving outside the manifest directory are rejected.

Times are displayed as provided, not used to infer copying direction. URLs
are references only and are never fetched. Source hashes are SHA-256 of the
decoded source re-encoded as UTF-8, with a leading UTF-8 BOM removed; they are
not byte-for-byte hashes of the original exported files.

Baseline manifests use this same format. Templates apply only to matching
`task` and `language`; use `task: "*"` for explicitly permitted global templates.
This changes the language-wide baseline behavior of versions before 0.3.

Folder indexing scans exactly three levels: `task/author/source.ext`.
Supported extensions: `.py`, `.java`, `.c`, `.cc`, `.cpp`, `.cxx`. Keep the
generated manifest at the export root. Rename it only after generation or
select another root-level filename with `--manifest`.
