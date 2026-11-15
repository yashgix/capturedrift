"""Tests for the loss accounting, on small hand-made records and on the pinned data."""

import tempfile
import unittest
from pathlib import Path

from capturedrift.data import Record, Session
from capturedrift.drift import CONTENT_MIN, changes
from capturedrift.loss import (
    APPROX,
    EXACT,
    PAYLOAD,
    UNIQUE,
    Captured,
    conservation,
    emitted_bytes,
    kind_scores,
    load_raw,
    main,
    new_kinds,
    sidechain_records,
    split_loss,
    thinking_blocks,
    went_quiet,
    wilson,
)
from capturedrift.run import main as run_experiment
from capturedrift.shape import kind, leaf_values, leaves, size
from capturedrift.sts import mapped_keys, normalize
from demo_loss import render

WORDS = "one two three four"


def session(version, raws, harness="claude"):
    """A session built from raw records, the way data.load builds one."""
    records = tuple(Record(kind(harness, raw), leaves(harness, raw)) for raw in raws)
    return Session(f"{harness}-{version}", harness, version, "test", "", records), raws


def assistant(*blocks, **extra):
    return {"type": "assistant", "message": {"content": list(blocks)}, **extra}


THOUGHT = {"type": "thinking", "thinking": WORDS, "signature": "sig"}
SILENT = {"type": "thinking", "thinking": "", "signature": "sig"}
TEXT = {"type": "text", "text": WORDS}


class ConservationTest(unittest.TestCase):
    def test_reasoning_is_written_and_counted(self):
        pair = session("1", [assistant(THOUGHT, TEXT)])
        result = conservation("claude", [pair])
        self.assertEqual(result["source"], result["emitted"])
        self.assertEqual(result["reasoning"], size(WORDS))

    def test_doubled_output_does_not_conserve(self):
        pair = session("1", [assistant(THOUGHT, TEXT)])
        lines = normalize("claude", pair[1])
        single = emitted_bytes("claude", lines)["emitted"]
        self.assertEqual(emitted_bytes("claude", lines + lines[1:])["emitted"], 2 * single)
        self.assertEqual(single, conservation("claude", [pair])["source"])

    def test_a_dropped_field_shows_as_missing_bytes(self):
        raw = assistant({"type": "thinking", "thinking": WORDS})
        lines = normalize("claude", [raw])
        del lines[1]["message"]["reasoningContent"]
        self.assertEqual(emitted_bytes("claude", lines), {"emitted": 0, "reasoning": 0})

    def test_signature_only_thinking_writes_nothing_useful(self):
        pair = session("1", [assistant(SILENT, TEXT)])
        self.assertEqual(thinking_blocks(pair[1]), (1, 1))
        result = conservation("claude", [pair])
        self.assertEqual(result["reasoning"], 0)

    def test_codex_arguments_count_like_the_source(self):
        raw = {
            "type": "response_item",
            "payload": {"type": "function_call", "call_id": "c", "name": "n", "arguments": "{}"},
        }
        result = conservation("codex", [session("1", [raw], "codex")])
        self.assertEqual((result["source"], result["emitted"]), (size("{}"), size("{}")))


class DroppedByDesignTest(unittest.TestCase):
    """Cases the normalizer drops or flattens on purpose. These tests pin the limit, they do not endorse it."""

    def test_codex_compacted_history_is_not_written(self):
        history = [{"type": "message", "content": [{"type": "input_text", "text": WORDS}]}]
        raw = {"type": "compacted", "payload": {"replacement_history": history}}
        self.assertEqual(len(normalize("codex", [raw])), 1)

    def test_sidechain_records_are_written_without_a_marker(self):
        plain = assistant(TEXT)
        side = assistant(TEXT, isSidechain=True)
        self.assertEqual(normalize("claude", [side])[1:], normalize("claude", [plain])[1:])
        self.assertEqual(sidechain_records([plain, side, side]), 2)


class CopyTest(unittest.TestCase):
    def test_exact_numbered_and_different_text(self):
        kept = Captured(["alpha beta gamma\ndelta epsilon zeta"])
        self.assertEqual(kept.match("alpha beta gamma\ndelta epsilon zeta"), EXACT)
        self.assertEqual(kept.match("   1→alpha beta gamma\n   2→delta epsilon zeta"), APPROX)
        self.assertEqual(kept.match("something quite different"), UNIQUE)

    def test_short_matching_lines_do_not_hide_a_long_missing_line(self):
        kept = Captured(["alpha beta gamma"])
        text = "\n".join(["alpha beta gamma"] * 9 + ["delta epsilon " + "z" * 10000])
        self.assertEqual(kept.match(text), UNIQUE)

    def test_split_loss_separates_exact_copy_from_unmatched(self):
        user = {"type": "user", "message": {"content": [{"type": "tool_result", "content": WORDS}]}}
        user["toolUseResult"] = {"stdout": WORDS, "extra": "only here and nowhere else"}
        found = split_loss([user], "claude", mapped_keys("claude"))
        self.assertEqual(found[("user", "toolUseResult:json")], [size(WORDS), 0, size("only here and nowhere else")])


class QuietTest(unittest.TestCase):
    def test_a_key_that_empties_is_reported_once_its_kind_still_occurs(self):
        long_text = "word " * CONTENT_MIN
        loud = assistant({"type": "thinking", "thinking": long_text})
        quiet = assistant(SILENT, TEXT)
        sessions = [session("1", [loud])[0], session("2", [quiet])[0]]
        found = went_quiet(sessions, "claude")
        self.assertEqual(found["2"], [("assistant", "message.content[]<thinking>.thinking:str")])
        self.assertEqual(found["1"], [])

    def test_a_kind_that_is_absent_is_not_reported(self):
        loud = assistant({"type": "thinking", "thinking": "word " * CONTENT_MIN})
        other = {"type": "user", "message": {"content": "hi"}}
        sessions = [session("1", [loud])[0], session("2", [other])[0]]
        self.assertEqual(went_quiet(sessions, "claude")["2"], [])


class NewKindsTest(unittest.TestCase):
    def test_only_kinds_no_earlier_version_has_count(self):
        user = {"type": "user", "message": {"content": "hi"}}
        found = new_kinds(
            [
                session("1", [user])[0],
                session("2", [user, assistant(TEXT)])[0],
                session("3", [user, assistant(TEXT, extra=1)])[0],
            ]
        )
        self.assertEqual(found, {"1": 0, "2": 1, "3": 0})


class IntervalTest(unittest.TestCase):
    def test_wilson(self):
        self.assertEqual(wilson(0, 0), [0.0, 1.0])
        low, high = wilson(5, 10)
        self.assertLess(low, 0.5)
        self.assertGreater(high, 0.5)
        self.assertEqual(wilson(10, 10)[1], 1.0)

    def test_kind_scores_count_kinds_not_keys(self):
        loud = "word " * CONTENT_MIN
        first = session("1", [{"type": "user", "message": {"content": "hi"}}])[0]
        second = session(
            "2",
            [{"type": "attachment", "attachment": {"type": "x", "a": loud, "b": loud}}],
        )[0]
        found = changes([first, second], 1)
        scores = kind_scores(found, {"2"}, {"user"})
        self.assertEqual([scores["kind"][name] for name in ("tp", "fp", "fn")], [1, 0, 0])
        self.assertEqual(scores["content_keys"], {"conversation": 0, "injected": 2})


class PinnedDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            cls.result = main(out=Path(tmp) / "metrics-v2.json")

    def test_normalize_writes_the_mapped_content_and_nothing_twice(self):
        """Non-empty content written equals mapped. An empty piece joined to others adds one 2-byte separator."""
        empties = {}
        for session, records in load_raw():
            mapped = mapped_keys(session.harness)
            key = (session.harness, session.version)
            empties[key] = empties.get(key, 0) + sum(
                1
                for record in records
                for path, value in leaf_values(session.harness, record)
                if value == "" and path.endswith(PAYLOAD) and (kind(session.harness, record), path) in mapped
            )
        for harness, data in self.result["harness"].items():
            for version, row in data["versions"].items():
                gap = row["emitted"] - row["source"]
                self.assertTrue(0 <= gap <= 2 * empties[harness, version], (harness, version, gap))
                if not empties[harness, version]:
                    self.assertEqual(gap, 0)

    def test_reasoning_text_is_written_for_old_claude_versions(self):
        rows = self.result["harness"]["claude"]["versions"]
        self.assertGreater(rows["2.1.114"]["reasoning"], 100_000)
        self.assertGreater(rows["2.1.123"]["reasoning"], 100_000)

    def test_thinking_goes_silent_from_2_1_126(self):
        rows = self.result["harness"]["claude"]["versions"]
        self.assertEqual(rows["2.1.126"]["thinking_empty"], rows["2.1.126"]["thinking_blocks"])
        self.assertEqual(rows["2.1.126"]["quiet_mapped_keys"], 1)

    def test_rendered_block_has_every_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = render(run_experiment(out=Path(tmp) / "m.json"), self.result)
        for title in ("Loss accounting", "Alarms, counted per record kind", "Biggest unmatched text"):
            self.assertIn(title, text)
        self.assertIn("| Claude Code | 2.1.126 |", text)

    def test_copy_and_unique_add_up_to_the_frozen_text_share(self):
        frozen = self.result["harness"]["claude"]["frozen"]
        total = frozen["exact_share"] + frozen["approx_share"] + frozen["unique_share"]
        self.assertAlmostEqual(total, 0.004246, places=5)


if __name__ == "__main__":
    unittest.main()
