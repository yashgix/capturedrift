"""Tests for the command line: structure audit and STS normalization."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from capturedrift import DATA_DIR
from capturedrift.__main__ import main
from capturedrift.data import manifest


def write_jsonl(path, records):
    """Write one JSON object per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


class AuditTest(unittest.TestCase):
    def test_audit_counts_and_rounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.jsonl"
            second = Path(tmp) / "second.jsonl"
            write_jsonl(
                first,
                [
                    {
                        "type": "user",
                        "version": "2.1.100",
                        "timestamp": "2026-01-01T00:00:00Z",
                        "message": {"role": "user", "content": "one two three secret text"},
                    }
                ],
            )
            write_jsonl(
                second,
                [
                    {
                        "type": "assistant",
                        "version": "2.1.200",
                        "timestamp": "2026-01-01T00:00:01Z",
                        "message": {
                            "model": "m",
                            "content": [{"type": "text", "text": "four five six"}],
                        },
                    }
                ],
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                main(["audit", "--harness", "claude", str(first), str(second)])
            result = json.loads(output.getvalue())
            self.assertEqual(result["sessions"], 2)
            self.assertEqual(result["records"], 2)
            self.assertEqual(result["versions"], ["2.1.100", "2.1.200"])
            self.assertEqual(result["kinds"], 2)
            self.assertEqual(result["keys"], 11)
            self.assertEqual(result["sts_byte_share"], 0.654412)
            self.assertEqual(result["sts_text_share"], 1.0)
            self.assertNotIn("secret text", output.getvalue())
            self.assertNotIn("four five six", output.getvalue())

    def test_audit_on_a_real_file_is_structure_only(self):
        entries = manifest()["files"]
        names = [name for name, entry in entries.items() if entry["harness"] == "claude"]
        if not names:
            self.fail("no Claude sessions in the manifest")
        name = min(names, key=lambda item: entries[item]["bytes"])
        path = DATA_DIR / name
        if not path.is_file():
            self.fail(f"pinned data missing at {path}; run python tools/fetch_data.py")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main(["audit", "--harness", "claude", str(path)])
        result = json.loads(output.getvalue())
        self.assertEqual(result["sessions"], 1)
        self.assertGreater(result["records"], 0)
        self.assertEqual(result["versions"], [entries[name]["version"]])
        self.assertGreater(result["kinds"], 0)
        self.assertGreater(result["keys"], 0)
        self.assertGreaterEqual(result["sts_byte_share"], 0.0)
        self.assertLessEqual(result["sts_byte_share"], 1.0)
        self.assertGreaterEqual(result["sts_text_share"], 0.0)
        self.assertLessEqual(result["sts_text_share"], 1.0)


class NormalizeTest(unittest.TestCase):
    def test_writes_sts_lines_and_reports_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "session.jsonl"
            target = Path(tmp) / "nested" / "session.sts.jsonl"
            write_jsonl(
                source,
                [
                    {
                        "type": "user",
                        "sessionId": "abc",
                        "timestamp": "2026-01-01T00:00:00Z",
                        "message": {"role": "user", "content": "one two three"},
                    }
                ],
            )
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                main(["normalize", "--harness", "claude", str(source), str(target)])
            lines = target.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(
                json.loads(lines[0]),
                {"type": "session", "harness": "claude-code", "id": "abc"},
            )
            message = json.loads(lines[1])["message"]
            self.assertEqual(message["role"], "user")
            self.assertEqual(message["content"], "one two three")
            self.assertEqual(message["timestamp"], 1_767_225_600_000)
            self.assertEqual(errors.getvalue().strip(), "2")

    def test_codex_header_and_line_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "rollout.jsonl"
            target = Path(tmp) / "rollout.sts.jsonl"
            write_jsonl(
                source,
                [
                    {"type": "session_meta", "payload": {"id": "s1"}},
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "one two three"}],
                        },
                    },
                ],
            )
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                main(["normalize", "--harness", "codex", str(source), str(target)])
            lines = target.read_text(encoding="utf-8").splitlines()
            self.assertEqual(json.loads(lines[0])["id"], "s1")
            self.assertEqual(len(lines), 2)
            self.assertEqual(errors.getvalue().strip(), "2")


if __name__ == "__main__":
    unittest.main()
