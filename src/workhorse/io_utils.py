"""Size-limited reads with allocation proportional to the input."""
from pathlib import Path


def read_bounded(path: Path, limit: int, error: str) -> bytes:
    """Read in small chunks; enforce the cap even if the file grows while read."""
    if type(limit) is not int or limit < 0:
        raise ValueError("Read limit must be a nonnegative integer")
    data = bytearray()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(min(64 * 1024, limit - len(data) + 1))
            if not chunk:
                return bytes(data)
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError(error)
