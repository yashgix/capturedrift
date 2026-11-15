"""Load the pinned session files into typed records."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import DATA_DIR
from .shape import kind, leaves


@dataclass(frozen=True)
class Record:
    """One session record: its event kind and leaf measurements."""

    kind: str
    leaves: dict[str, tuple[int, int]]

    @property
    def keys(self) -> set[tuple[str, str]]:
        """The record's (kind, key path) pairs."""
        return {(self.kind, path) for path in self.leaves}


@dataclass(frozen=True)
class Session:
    """One session file and its records."""

    name: str
    harness: str
    version: str | None
    source: str
    start: str
    records: tuple[Record, ...]


def version_key(version: str) -> tuple[int, ...]:
    """The integers in version, in order, so numeric ordering beats string ordering."""
    return tuple(int(part) for part in re.findall(r"\d+", version or ""))


def read_records(path: Path | str) -> list[dict]:
    """Parse one JSON record per non-blank line."""
    records = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def session_version(harness: str, records: list[dict]) -> str | None:
    """The CLI version recorded by a session, if any."""
    if harness == "codex":
        for record in records:
            if isinstance(record, dict) and record.get("type") == "session_meta":
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    return None
                version = payload.get("cli_version")
                return version if isinstance(version, str) else None
        return None
    for record in records:
        if isinstance(record, dict):
            version = record.get("version")
            if isinstance(version, str):
                return version
    return None


def session_start(records: list[dict]) -> str:
    """The earliest timestamp recorded in a session, or an empty string."""
    stamps = [
        record["timestamp"]
        for record in records
        if isinstance(record, dict) and isinstance(record.get("timestamp"), str)
    ]
    return min(stamps) if stamps else ""


def load_session(name: str, harness: str, source: str, path: Path | str) -> Session:
    """Load one session file and measure each of its records."""
    raw = read_records(path)
    records = tuple(Record(kind(harness, record), leaves(harness, record)) for record in raw)
    return Session(name, harness, session_version(harness, raw), source, session_start(raw), records)


def manifest(data_dir: Path | str = DATA_DIR) -> dict:
    """The parsed MANIFEST.json for a data directory."""
    return json.loads((Path(data_dir) / "MANIFEST.json").read_text(encoding="utf-8"))


def _order(session: Session) -> tuple[str, tuple[int, ...], str, str]:
    return session.harness, version_key(session.version or ""), session.start, session.name


def load(data_dir: Path | str = DATA_DIR) -> list[Session]:
    """Every manifest session, ordered for the experiment."""
    directory = Path(data_dir)
    entries = manifest(directory)["files"]
    sessions = [
        load_session(name, entry["harness"], entry["source"], directory / name) for name, entry in entries.items()
    ]
    sessions.sort(key=_order)
    return sessions
