"""Command line: structure-only audit and STS normalization."""

import argparse
import json
import sys
from pathlib import Path

from . import HARNESSES
from .data import load_session, read_records, version_key
from .drift import known_keys, mapped_share
from .sts import mapped_keys, normalize


def _round(value):
    """Round a float to six places; leave other values alone."""
    return round(value, 6) if isinstance(value, float) else value


def audit(harness, files):
    """Print structure-only counts and the STS share for these session files."""
    sessions = [load_session(str(path), harness, "", path) for path in files]
    records = [record for session in sessions for record in session.records]
    versions = sorted(
        {session.version for session in sessions if session.version is not None},
        key=version_key,
    )
    sts = mapped_share(sessions, mapped_keys(harness))
    result = {
        "sessions": len(sessions),
        "records": len(records),
        "versions": versions,
        "kinds": len({record.kind for record in records}),
        "keys": len(known_keys(sessions)),
        "sts_byte_share": _round(sts["bytes"]),
        "sts_text_share": _round(sts["text"]),
    }
    print(json.dumps(result, sort_keys=True, indent=1))


def normalize_file(harness, source, target):
    """Write the STS lines for one session file and report how many there are."""
    lines = normalize(harness, read_records(source), Path(source).stem)
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines),
        encoding="utf-8",
    )
    print(len(lines), file=sys.stderr)


def main(argv=None):
    """Parse the command line and run the requested subcommand."""
    parser = argparse.ArgumentParser(prog="capturedrift")
    commands = parser.add_subparsers(dest="command", required=True)

    audit_parser = commands.add_parser("audit", help="print structure-only JSON for session files")
    audit_parser.add_argument("--harness", choices=HARNESSES, required=True)
    audit_parser.add_argument("files", nargs="+")

    normalize_parser = commands.add_parser("normalize", help="write STS lines for one session file")
    normalize_parser.add_argument("--harness", choices=HARNESSES, required=True)
    normalize_parser.add_argument("input")
    normalize_parser.add_argument("output")

    args = parser.parse_args(argv)
    if args.command == "audit":
        audit(args.harness, args.files)
    else:
        normalize_file(args.harness, args.input, args.output)


if __name__ == "__main__":
    main()
