"""Tests for the README renderer: formats, tables, block replacement, the summary line and the CLI."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from capturedrift.data import Record, Session
from capturedrift.drift import ALARMS, CUTOFF
from capturedrift.run import summarize
from demo import main, percent, ratio, render, replace_block, summary, table, version_names


METRICS = {
    "data_files": 40,
    "records": [10, 5],
    "frozen_text_share": [0.151, 0.0],
    "sts_text_share": [0.42, 0.5],
}


def rec(kind, leaves):
    """A record whose key paths map to (bytes, text bytes)."""
    return Record(kind, leaves)


def session(name, version, records=(), harness="claude"):
    """A session with no source or start time, which these tests never need."""
    return Session(name, harness, version, "test", "", tuple(records))


def fixture():
    """Two versions per harness: a training one, then a test one that adds a content-bearing key."""
    return [
        session("claude-train", "2.1.100", [rec("user", {"a:str": (10, 10)})]),
        session("claude-test", "2.1.200", [rec("user", {"a:str": (10, 10), "e:str": (9000, 9000)})]),
        session(
            "codex-train",
            "0.100.0",
            [rec("response_item/message", {"payload.role:str": (4, 0)})],
            harness="codex",
        ),
        session(
            "codex-test",
            "0.140.0",
            [rec("response_item/message", {"payload.role:str": (4, 0), "payload.new:str": (500, 500)})],
            harness="codex",
        ),
    ]


def write_data(directory):
    """A minimal pinned data directory holding the fixture's versions."""
    entries = {
        "sessions/claude/train.jsonl": ("claude", "2.1.100", {"type": "user", "version": "2.1.100"}),
        "sessions/claude/test.jsonl": ("claude", "2.1.200", {"type": "user", "version": "2.1.200"}),
        "sessions/codex/train.jsonl": ("codex", "0.100.0", {"type": "session_meta", "payload": {"cli_version": "0.100.0"}}),
        "sessions/codex/test.jsonl": ("codex", "0.140.0", {"type": "session_meta", "payload": {"cli_version": "0.140.0"}}),
    }
    files = {}
    for name, (harness, version, record) in entries.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        files[name] = {"harness": harness, "version": version, "source": "test"}
    (directory / "MANIFEST.json").write_text(json.dumps({"files": files}), encoding="utf-8")


class FormatTest(unittest.TestCase):
    def test_shares_are_percent_with_one_decimal(self):
        self.assertEqual(percent(0.1509), "15.1%")
        self.assertEqual(percent(0.0), "0.0%")
        self.assertEqual(percent(1.0), "100.0%")

    def test_precision_and_recall_use_two_decimals(self):
        self.assertEqual(ratio(0.5), "0.50")
        self.assertEqual(ratio(1.0), "1.00")
        self.assertEqual(ratio(2 / 3), "0.67")


class TableTest(unittest.TestCase):
    def test_header_separator_and_cells(self):
        self.assertEqual(table(["a", "b"], [[1, "x"]]).splitlines(), ["| a | b |", "|---|---|", "| 1 | x |"])

    def test_header_only(self):
        self.assertEqual(table(["a", "b", "c"], []).splitlines(), ["| a | b | c |", "|---|---|---|"])


class ReplaceTest(unittest.TestCase):
    def test_only_the_marked_block_changes(self):
        text = "before\n<!-- results:start -->\nold numbers\n<!-- results:end -->\nafter\n"
        self.assertEqual(
            replace_block(text, "new line"),
            "before\n<!-- results:start -->\nnew line\n<!-- results:end -->\nafter\n",
        )

    def test_missing_or_reversed_markers_raise(self):
        with self.assertRaises(ValueError):
            replace_block("no markers here", "x")
        with self.assertRaises(ValueError):
            replace_block("<!-- results:end -->\n<!-- results:start -->\n", "x")


class NamesTest(unittest.TestCase):
    def test_versions_in_numeric_order_per_harness(self):
        self.assertEqual(
            version_names(fixture()),
            {"claude": ["2.1.100", "2.1.200"], "codex": ["0.100.0", "0.140.0"]},
        )


class SummaryTest(unittest.TestCase):
    def test_one_line_with_the_metrics_numbers(self):
        line = summary(METRICS)
        self.assertNotIn("\n", line)
        self.assertIn("40 sessions", line)
        self.assertIn("15 records", line)
        self.assertIn("15.1%", line)
        self.assertIn("42.0%", line)
        self.assertIn("50.0%", line)


class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = fixture()
        cls.metrics = summarize(cls.sessions, 4, 1000)
        cls.text = render(cls.metrics, cls.sessions)

    def test_version_names_appear_in_order_with_their_period(self):
        self.assertIn("| Claude Code | 2.1.100 | train |", self.text)
        self.assertIn("| Claude Code | 2.1.200 | test |", self.text)
        self.assertIn("| Codex | 0.100.0 | train |", self.text)
        self.assertIn("| Codex | 0.140.0 | test |", self.text)
        self.assertLess(self.text.index("2.1.100"), self.text.index("2.1.200"))
        self.assertLess(self.text.index("0.100.0"), self.text.index("0.140.0"))

    def test_shares_are_formatted(self):
        for harness in ("claude", "codex"):
            self.assertIn(CUTOFF[harness], self.text)
        self.assertIn(percent(self.metrics["frozen_text_share"][0]), self.text)
        self.assertIn(percent(self.metrics["sts_text_share"][1]), self.text)

    def test_every_alarm_has_one_row_per_harness(self):
        for alarm in ALARMS:
            self.assertEqual(self.text.count(f"| {alarm} |"), 2, alarm)
        self.assertIn(ratio(self.metrics["alarm_key_precision"][0]), self.text)

    def test_top_unseen_keys_are_listed(self):
        self.assertIn("`e:str`", self.text)
        self.assertIn("`payload.new:str`", self.text)

    def test_no_trailing_spaces(self):
        self.assertEqual([line for line in self.text.splitlines() if line != line.rstrip()], [])


class MainTest(unittest.TestCase):
    def test_prints_one_line_from_metrics_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp) / "results"
            results.mkdir()
            (results / "metrics.json").write_text(json.dumps(METRICS), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                main(["--results", str(results)])
            self.assertEqual(output.getvalue().strip(), summary(METRICS))
            self.assertEqual(len(output.getvalue().splitlines()), 1)

    def test_writes_the_readme_between_the_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            write_data(data)
            results = root / "results"
            results.mkdir()
            (results / "metrics.json").write_text(json.dumps(summarize(fixture(), 4, 1000)), encoding="utf-8")
            template = root / "README.md"
            template.write_text("# title\n\n<!-- results:start -->\n<!-- results:end -->\n\nfooter\n", encoding="utf-8")
            out = root / "out.md"
            main(
                [
                    "--readme",
                    str(template),
                    "--out",
                    str(out),
                    "--results",
                    str(results),
                    "--data",
                    str(data),
                ]
            )
            text = out.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("# title\n\n<!-- results:start -->\n"))
            self.assertTrue(text.endswith("<!-- results:end -->\n\nfooter\n"))
            self.assertIn("| Version |", text)
            self.assertIn("2.1.200", text)
            self.assertNotIn("<!-- results:start -->\n<!-- results:end -->", text)
            self.assertEqual(template.read_text(encoding="utf-8").count("old numbers"), 0)

    def test_missing_markers_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            write_data(data)
            results = root / "results"
            results.mkdir()
            (results / "metrics.json").write_text(json.dumps(summarize(fixture(), 4, 1000)), encoding="utf-8")
            template = root / "README.md"
            template.write_text("# title only\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                main(
                    [
                        "--readme",
                        str(template),
                        "--out",
                        str(root / "out.md"),
                        "--results",
                        str(results),
                        "--data",
                        str(data),
                    ]
                )


if __name__ == "__main__":
    unittest.main()
