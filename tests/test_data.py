"""Tests for session loading against the pinned data and small fixtures."""

import json
import tempfile
import unittest
from pathlib import Path

from capturedrift import DATA_DIR, HARNESSES
from capturedrift.data import (
    Record,
    Session,
    load,
    load_session,
    manifest,
    read_records,
    session_start,
    session_version,
    version_key,
)


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n\n", encoding="utf-8")


class VersionKeyTest(unittest.TestCase):
    def test_orders_versions_numerically(self):
        self.assertEqual(version_key("2.1.145"), (2, 1, 145))
        self.assertEqual(version_key("0.147.0-alpha.1.2"), (0, 147, 0, 1, 2))
        self.assertLess(version_key("2.1.9"), version_key("2.1.10"))

    def test_collects_every_integer(self):
        self.assertEqual(version_key("v1-2.03"), (1, 2, 3))
        self.assertEqual(version_key("none"), ())


class RecordTest(unittest.TestCase):
    def test_keys_are_kind_and_path(self):
        record = Record("user", {"a:str": (1, 0), "b:num": (2, 0)})
        self.assertEqual(record.keys, {("user", "a:str"), ("user", "b:num")})


class ParserTest(unittest.TestCase):
    def test_read_records_skips_blank_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            write_jsonl(path, [{"type": "user"}, {"type": "assistant"}])
            self.assertEqual(read_records(path), [{"type": "user"}, {"type": "assistant"}])

    def test_codex_version_comes_from_first_session_meta(self):
        records = [
            {"type": "event_msg"},
            {"type": "session_meta", "payload": {"cli_version": "0.125.0"}},
            {"type": "session_meta", "payload": {"cli_version": "9.9.9"}},
        ]
        self.assertEqual(session_version("codex", records), "0.125.0")
        self.assertIsNone(session_version("codex", [{"type": "session_meta", "payload": {}}]))
        self.assertIsNone(session_version("codex", [{"type": "event_msg"}]))

    def test_claude_version_is_first_string(self):
        records = [{"version": 3}, {"version": "2.1.1"}, {"version": "9"}]
        self.assertEqual(session_version("claude", records), "2.1.1")
        self.assertIsNone(session_version("claude", [{"version": None}]))

    def test_session_start_is_smallest_timestamp(self):
        records = [
            {"timestamp": "2026-02-01T00:00:00Z"},
            {"timestamp": 4},
            {"timestamp": "2026-01-01T00:00:00Z"},
        ]
        self.assertEqual(session_start(records), "2026-01-01T00:00:00Z")
        self.assertEqual(session_start([{"timestamp": None}]), "")

    def test_load_session_builds_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.jsonl"
            write_jsonl(
                path,
                [
                    {
                        "type": "user",
                        "version": "2.1.7",
                        "timestamp": "2026-01-02T00:00:00Z",
                        "message": {"role": "user", "content": "one two three"},
                    },
                    {
                        "type": "assistant",
                        "version": "2.1.7",
                        "timestamp": "2026-01-01T00:00:00Z",
                        "message": {"content": [{"type": "text", "text": "four five six"}]},
                    },
                ],
            )
            session = load_session("sessions/claude/x.jsonl", "claude", "source", path)
            self.assertIsInstance(session, Session)
            self.assertEqual(session.name, "sessions/claude/x.jsonl")
            self.assertEqual(session.harness, "claude")
            self.assertEqual(session.version, "2.1.7")
            self.assertEqual(session.source, "source")
            self.assertEqual(session.start, "2026-01-01T00:00:00Z")
            self.assertIsInstance(session.records, tuple)
            self.assertEqual([record.kind for record in session.records], ["user", "assistant"])
            self.assertIn(("user", "message.content:str"), session.records[0].keys)
            self.assertIn(("assistant", "message.content[]<text>.text:str"), session.records[1].keys)

    def test_load_sorts_by_harness_version_start_and_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            files = {
                "sessions/claude/z.jsonl": ("2.1.2", "2026-01-01T00:00:00Z"),
                "sessions/claude/a.jsonl": ("2.1.2", "2026-01-01T00:00:00Z"),
                "sessions/claude/b.jsonl": ("2.1.2", "2025-12-01T00:00:00Z"),
                "sessions/claude/m.jsonl": ("2.1.10", "2026-01-01T00:00:00Z"),
            }
            for name, (version, timestamp) in files.items():
                write_jsonl(
                    data_dir / name,
                    [{"type": "user", "version": version, "timestamp": timestamp}],
                )
            write_jsonl(
                data_dir / "sessions/codex/d.jsonl",
                [{"type": "session_meta", "payload": {"cli_version": "0.1.0"}}],
            )
            entries = {
                name: {"harness": "claude", "version": version, "source": "test"}
                for name, (version, _) in files.items()
            }
            entries["sessions/codex/d.jsonl"] = {"harness": "codex", "version": "0.1.0", "source": "test"}
            (data_dir / "MANIFEST.json").write_text(json.dumps({"files": entries}), encoding="utf-8")
            self.assertEqual(manifest(data_dir)["files"], entries)
            sessions = load(data_dir)
            self.assertEqual(
                [session.name for session in sessions],
                [
                    "sessions/claude/b.jsonl",
                    "sessions/claude/a.jsonl",
                    "sessions/claude/z.jsonl",
                    "sessions/claude/m.jsonl",
                    "sessions/codex/d.jsonl",
                ],
            )


class PinnedDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DATA_DIR / "MANIFEST.json").is_file():
            raise AssertionError(f"pinned data missing at {DATA_DIR}; run python tools/fetch_data.py")
        cls.manifest = manifest()
        missing = [name for name in cls.manifest["files"] if not (DATA_DIR / name).is_file()]
        if missing:
            raise AssertionError(f"pinned data files missing under {DATA_DIR}: {missing[0]}")
        cls.sessions = load()
        cls.by_harness = {harness: [s for s in cls.sessions if s.harness == harness] for harness in HARNESSES}

    def test_file_count_and_total_bytes(self):
        self.assertEqual(len(self.manifest["files"]), 40)
        total = 0
        for name, entry in self.manifest["files"].items():
            size = (DATA_DIR / name).stat().st_size
            self.assertEqual(size, entry["bytes"], name)
            total += size
        self.assertEqual(total, 56_092_812)

    def test_per_harness_session_and_record_counts(self):
        self.assertEqual([len(self.by_harness[harness]) for harness in HARNESSES], [35, 5])
        records = [sum(len(session.records) for session in self.by_harness[harness]) for harness in HARNESSES]
        self.assertEqual(records, [15_838, 3_229])

    def test_version_counts_and_ranges(self):
        versions = {harness: {session.version for session in self.by_harness[harness]} for harness in HARNESSES}
        self.assertEqual([len(versions[harness]) for harness in HARNESSES], [22, 4])
        claude = versions["claude"]
        self.assertEqual(min(claude, key=version_key), "2.1.114")
        self.assertEqual(max(claude, key=version_key), "2.1.220")
        codex = versions["codex"]
        self.assertEqual(min(codex, key=version_key), "0.125.0")
        self.assertEqual(max(codex, key=version_key), "0.147.0-alpha.1.2")

    def test_session_versions_match_manifest(self):
        for session in self.sessions:
            self.assertEqual(session.version, self.manifest["files"][session.name]["version"], session.name)
            self.assertIsInstance(session.records, tuple)

    def test_load_is_sorted(self):
        keys = [
            (session.harness, version_key(session.version), session.start, session.name) for session in self.sessions
        ]
        self.assertEqual(keys, sorted(keys))
