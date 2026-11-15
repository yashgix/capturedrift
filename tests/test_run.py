"""Tests for the experiment summary: metric set, list lengths, determinism and training-only tuning."""

import json
import tempfile
import unittest
from pathlib import Path

from capturedrift import DATA_DIR, HARNESSES
from capturedrift.data import Record, Session, load, manifest
from capturedrift.drift import ALARMS, BYTES_GRID, changes, is_train, score, tune_bytes_min
from capturedrift.run import ALARM_KEYS, HARNESS_KEYS, VERSION_KEYS, main, summarize

METRICS = {
    "data_files",
    "data_bytes",
    "content_min",
    "bytes_min",
    "bytes_grid",
    "train_bytes_f1",
    "sessions",
    "records",
    "versions",
    "train_versions",
    "test_versions",
    "kinds",
    "keys",
    "sts_byte_share",
    "sts_text_share",
    "frozen_new_kinds",
    "frozen_new_keys",
    "frozen_content_keys",
    "frozen_record_share",
    "frozen_byte_share",
    "frozen_text_share",
    "version_harness",
    "version_test",
    "version_sessions",
    "version_records",
    "version_shapes",
    "version_keys",
    "version_new_keys",
    "version_content_keys",
    "version_record_share",
    "version_byte_share",
    "version_text_share",
    "version_sts_text_share",
    "alarm_key_tp",
    "alarm_key_fp",
    "alarm_key_fn",
    "alarm_key_precision",
    "alarm_key_recall",
    "alarm_version_tp",
    "alarm_version_fp",
    "alarm_version_fn",
    "alarm_version_precision",
    "alarm_version_recall",
}


def walk(value):
    """value and every list item nested inside it."""
    yield value
    if isinstance(value, list):
        for item in value:
            yield from walk(item)


def rec(kind, leaves):
    """A record whose key paths map to (bytes, text bytes)."""
    return Record(kind, leaves)


def session(name, version, records=(), harness="claude"):
    """A session with no source or start time, which these tests never need."""
    return Session(name, harness, version, "test", "", tuple(records))


def fixture():
    """One training version, then a test version whose content key only the higher thresholds flag."""
    return [
        session("t1", "2.1.100", [rec("user", {"a:str": (10, 10)})]),
        session("x1", "2.1.200", [rec("user", {"e:str": (9000, 9000), "f:num": (100, 0)})]),
    ]


class FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = fixture()
        cls.result = summarize(cls.sessions, 2, 10_000)

    def test_threshold_ignores_test_versions(self):
        self.assertEqual(self.result["bytes_min"], 1)
        self.assertEqual(self.result["train_bytes_f1"], [0.0, 0.0, 0.0, 0.0, 0.0])
        self.assertEqual(tune_bytes_min([self.sessions])[0], 200)

    def test_harness_counts(self):
        self.assertEqual(self.result["sessions"], [2, 0])
        self.assertEqual(self.result["records"], [2, 0])
        self.assertEqual(self.result["kinds"], [1, 0])
        self.assertEqual(self.result["keys"], [3, 0])
        self.assertEqual(self.result["frozen_new_kinds"], [0, 0])
        self.assertEqual(self.result["frozen_new_keys"], [2, 0])
        self.assertEqual(self.result["frozen_content_keys"], [1, 0])
        self.assertEqual(self.result["frozen_record_share"], [1.0, 0.0])
        self.assertEqual(self.result["frozen_byte_share"], [1.0, 0.0])
        self.assertEqual(self.result["frozen_text_share"], [1.0, 0.0])

    def test_version_rows(self):
        self.assertEqual(self.result["version_harness"], [0, 0])
        self.assertEqual(self.result["version_test"], [0, 1])
        self.assertEqual(self.result["version_sessions"], [1, 1])
        self.assertEqual(self.result["version_records"], [1, 1])
        self.assertEqual(self.result["version_new_keys"], [0, 2])
        self.assertEqual(self.result["version_content_keys"], [0, 1])
        self.assertEqual(self.result["version_record_share"], [0.0, 1.0])
        self.assertEqual(self.result["version_byte_share"], [0.0, 1.0])
        self.assertEqual(self.result["version_text_share"], [0.0, 1.0])

    def test_bytes_alarm_at_the_tuned_threshold(self):
        offset = HARNESSES.index("claude") * len(ALARMS) + ALARMS.index("bytes")
        self.assertEqual(self.result["alarm_key_tp"][offset], 1)
        self.assertEqual(self.result["alarm_key_fp"][offset], 1)
        self.assertEqual(self.result["alarm_key_fn"][offset], 0)
        self.assertEqual(self.result["alarm_key_precision"][offset], 0.5)
        self.assertEqual(self.result["alarm_key_recall"][offset], 1.0)
        self.assertEqual(self.result["alarm_version_tp"][offset], 1)
        self.assertEqual(self.result["alarm_version_fp"][offset], 0)
        self.assertEqual(self.result["alarm_version_fn"][offset], 0)


class PinnedDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DATA_DIR / "MANIFEST.json").is_file():
            raise AssertionError(f"pinned data missing at {DATA_DIR}; run python tools/fetch_data.py")
        cls.entries = manifest()["files"]
        cls.sessions = load()
        cls.result = summarize(
            cls.sessions, len(cls.entries), sum(entry["bytes"] for entry in cls.entries.values())
        )

    def test_metric_names_and_count(self):
        self.assertEqual(set(self.result), METRICS)
        self.assertEqual(len(METRICS), 43)

    def test_numbers_and_grid(self):
        self.assertEqual(self.result["data_files"], 40)
        self.assertEqual(self.result["data_bytes"], 56_092_812)
        self.assertEqual(self.result["content_min"], 200)
        self.assertIn(self.result["bytes_min"], BYTES_GRID)
        self.assertEqual(self.result["bytes_grid"], list(BYTES_GRID))
        self.assertEqual(len(self.result["train_bytes_f1"]), len(BYTES_GRID))
        for value in self.result["train_bytes_f1"]:
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_list_lengths(self):
        for name in HARNESS_KEYS:
            self.assertEqual(len(self.result[name]), len(HARNESSES), name)
        for name in VERSION_KEYS:
            self.assertEqual(len(self.result[name]), 26, name)
        for name in ALARM_KEYS:
            self.assertEqual(len(self.result["alarm_" + name]), len(HARNESSES) * len(ALARMS), name)

    def test_harness_counts(self):
        self.assertEqual(self.result["sessions"], [35, 5])
        self.assertEqual(self.result["records"], [15_838, 3_229])
        self.assertEqual(self.result["versions"], [22, 4])
        train_versions = [
            len({item.version for item in self.sessions if item.harness == harness and is_train(item)})
            for harness in HARNESSES
        ]
        self.assertEqual(self.result["train_versions"], train_versions)
        self.assertEqual(
            [before + after for before, after in zip(train_versions, self.result["test_versions"], strict=True)],
            self.result["versions"],
        )

    def test_version_rows(self):
        self.assertEqual(self.result["version_harness"], [0] * 22 + [1] * 4)
        self.assertEqual(sum(self.result["version_sessions"]), len(self.sessions))
        self.assertEqual(sum(self.result["version_records"]), sum(self.result["records"]))
        self.assertEqual(self.result["version_new_keys"][0], 0)
        self.assertEqual(self.result["version_content_keys"][0], 0)
        self.assertEqual(self.result["version_new_keys"][22], 0)
        self.assertEqual(self.result["version_content_keys"][22], 0)

    def test_alarms_score_held_out_changes(self):
        for index, harness in enumerate(HARNESSES):
            own = [item for item in self.sessions if item.harness == harness]
            test_versions = {item.version for item in own if not is_train(item)}
            held = [change for change in changes(own, self.result["bytes_min"]) if change.version in test_versions]
            for alarm_index, alarm in enumerate(ALARMS):
                expected = score(held, alarm)
                offset = index * len(ALARMS) + alarm_index
                for name in ALARM_KEYS:
                    self.assertEqual(
                        self.result["alarm_" + name][offset],
                        round(expected[name], 6),
                        (harness, alarm, name),
                    )

    def test_threshold_tuned_on_training_versions_only(self):
        trains = [
            [item for item in self.sessions if item.harness == harness and is_train(item)]
            for harness in HARNESSES
        ]
        best, scores = tune_bytes_min(trains)
        self.assertEqual(self.result["bytes_min"], best)
        self.assertEqual(self.result["train_bytes_f1"], [round(value, 6) for value in scores])

    def test_no_tuples_or_sets(self):
        for value in walk(self.result):
            self.assertNotIsInstance(value, (tuple, set))

    def test_main_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a" / "metrics.json"
            second = Path(tmp) / "b" / "metrics.json"
            written = main(DATA_DIR, first)
            again = main(DATA_DIR, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(written, again)
            text = first.read_text(encoding="utf-8")
            self.assertEqual(json.loads(text), written)
            self.assertTrue(text.endswith("\n"))
            lines = text.splitlines()
            self.assertEqual(lines[0], "{")
            self.assertTrue(lines[1].startswith(' "'))
            self.assertFalse(lines[1].startswith('  "'))
            for name in ("bytes_min", "data_files", "data_bytes", "sessions", "records", "versions"):
                self.assertEqual(written[name], self.result[name], name)


if __name__ == "__main__":
    unittest.main()
