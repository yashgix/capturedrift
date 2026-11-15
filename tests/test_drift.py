"""Tests for the drift measurements on small hand-made sessions."""

import unittest

from capturedrift.data import Record, Session, version_key
from capturedrift.drift import (
    ALARMS,
    BYTES_GRID,
    CONTENT_MIN,
    CUTOFF,
    Change,
    changes,
    f1,
    is_train,
    key_totals,
    known_keys,
    mapped_share,
    score,
    shapes,
    share,
    top_unseen,
    tune_bytes_min,
    unseen,
    versions,
)


def rec(kind, leaves):
    """A record whose key paths map to (bytes, text bytes)."""
    return Record(kind, leaves)


def session(name, version, records=(), harness="claude"):
    """A session with no source or start time, which these tests never need."""
    return Session(name, harness, version, "test", "", tuple(records))


def drift_sessions():
    """Four versions: a new kind and a new content key, a key whose text arrives later, then noise."""
    return [
        session("v1", "2.1.140", [rec("user", {"a:str": (100, 100)})]),
        session(
            "v2-first",
            "2.1.150",
            [
                rec("user", {"a:str": (100, 100), "b:str": (120, 120), "d:num": (900, 0)}),
                rec("assistant", {"z:str": (300, 300)}),
            ],
        ),
        session("v2-second", "2.1.150", [rec("user", {"a:str": (10, 0)})]),
        session("v3-first", "2.1.160", [rec("user", {"a:str": (10, 0)})]),
        session("v3-second", "2.1.160", [rec("user", {"e:str": (250, 250), "b:str": (100, 100)})]),
        session("v4-first", "2.1.170", [rec("user", {"a:str": (10, 0), "g:num": (400, 0)})]),
    ]


def tuning_train():
    """Training versions where a low byte threshold catches content and a high one only false positives."""
    return [
        session("t1", "2.1.100", [rec("user", {"a:str": (10, 10)})]),
        session("t2", "2.1.110", [rec("user", {"b:str": (50, 400)})]),
        session("t3", "2.1.140", [rec("user", {"c:str": (500, 500), "d:num": (300, 0)})]),
    ]


def tuning_codex():
    """A second harness's training sessions, pooled with claude's rather than averaged with them."""
    return [
        session("c1", "0.100.0", [rec("user", {"a:str": (10, 10)})], harness="codex"),
        session("c2", "0.130.0", [rec("user", {"w:str": (5000, 5000)})], harness="codex"),
    ]


class ConstantTest(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(CUTOFF, {"claude": "2.1.145", "codex": "0.125.0"})
        self.assertEqual(CONTENT_MIN, 200)
        self.assertEqual(ALARMS, ("kind", "any", "bytes"))
        self.assertEqual(BYTES_GRID, (1, 32, 200, 1024, 8192))


class CutoffTest(unittest.TestCase):
    def test_split_is_numeric_and_inclusive(self):
        self.assertTrue(is_train(session("a", "2.1.145")))
        self.assertTrue(is_train(session("b", "2.1.9")))
        self.assertFalse(is_train(session("c", "2.1.146")))
        self.assertTrue(is_train(session("d", "0.125.0", harness="codex")))
        self.assertFalse(is_train(session("e", "0.147.0-alpha.1.2", harness="codex")))


class VersionsTest(unittest.TestCase):
    def test_groups_and_orders_numerically(self):
        groups = versions([session("c", "2.1.10"), session("a", "2.1.9"), session("b", "2.1.10")])
        self.assertEqual([version for version, _ in groups], ["2.1.9", "2.1.10"])
        self.assertEqual([[item.name for item in group] for _, group in groups], [["a"], ["c", "b"]])

    def test_empty(self):
        self.assertEqual(versions([]), [])


class TotalsTest(unittest.TestCase):
    def test_key_totals_sum_bytes_and_text(self):
        sessions = [
            session(
                "a",
                "1",
                [
                    rec("user", {"x:str": (5, 3)}),
                    rec("user", {"x:str": (2, 0), "y:num": (1, 0)}),
                ],
            )
        ]
        self.assertEqual(key_totals(sessions), {("user", "x:str"): [7, 3], ("user", "y:num"): [1, 0]})
        self.assertEqual(known_keys(sessions), {("user", "x:str"), ("user", "y:num")})
        self.assertEqual(key_totals([]), {})

    def test_share_guards_zero(self):
        self.assertEqual(share(1, 4), 0.25)
        self.assertEqual(share(3, 0), 0.0)
        self.assertEqual(share(0, 0), 0.0)

    def test_shapes_counts_distinct_leaf_sets(self):
        sessions = [
            session(
                "a",
                "1",
                [
                    rec("user", {"x:str": (1, 0)}),
                    rec("user", {"x:str": (2, 0)}),
                    rec("user", {"x:str": (1, 0), "y:num": (1, 0)}),
                ],
            ),
            session("b", "2", [rec("assistant", {"x:str": (1, 0)})]),
        ]
        self.assertEqual(shapes(sessions), 3)
        self.assertEqual(shapes([]), 0)


class UnseenTest(unittest.TestCase):
    def test_shares(self):
        known = {("user", "a:str")}
        sessions = [
            session(
                "x",
                "1",
                [
                    rec("user", {"a:str": (10, 4)}),
                    rec("user", {"a:str": (10, 6), "new:str": (20, 10)}),
                ],
            ),
            session("y", "2", [rec("assistant", {"b:num": (5, 0)})]),
        ]
        self.assertEqual(
            unseen(sessions, known),
            {"records": share(2, 3), "bytes": share(25, 45), "text": share(10, 20)},
        )

    def test_known_and_empty_are_zero(self):
        sessions = [session("x", "1", [rec("user", {"a:str": (10, 4)})])]
        self.assertEqual(unseen(sessions, {("user", "a:str")}), {"records": 0.0, "bytes": 0.0, "text": 0.0})
        self.assertEqual(unseen([], set()), {"records": 0.0, "bytes": 0.0, "text": 0.0})


class MappedShareTest(unittest.TestCase):
    def test_shares(self):
        sessions = [session("x", "1", [rec("user", {"a:str": (10, 4), "b:num": (30, 0)})])]
        self.assertEqual(mapped_share(sessions, {("user", "a:str")}), {"bytes": 0.25, "text": 1.0})
        self.assertEqual(mapped_share(sessions, set()), {"bytes": 0.0, "text": 0.0})
        self.assertEqual(mapped_share([], set()), {"bytes": 0.0, "text": 0.0})


class ChangesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = drift_sessions()
        cls.found = changes(cls.sessions, 200)
        cls.by_version = {change.version: change for change in cls.found}

    def test_one_change_per_version_after_the_first(self):
        self.assertEqual([change.version for change in self.found], ["2.1.150", "2.1.160", "2.1.170"])
        self.assertIsInstance(self.found[0], Change)

    def test_new_keys_exclude_every_earlier_version(self):
        self.assertEqual(
            self.by_version["2.1.150"].new,
            {("user", "b:str"), ("user", "d:num"), ("assistant", "z:str")},
        )
        self.assertEqual(self.by_version["2.1.160"].new, {("user", "e:str")})
        self.assertEqual(self.by_version["2.1.170"].new, {("user", "g:num")})

    def test_content_is_real_text_bytes_over_this_and_later_versions(self):
        self.assertEqual(self.by_version["2.1.150"].content, {("user", "b:str"), ("assistant", "z:str")})
        self.assertEqual(self.by_version["2.1.160"].content, {("user", "e:str")})
        self.assertEqual(self.by_version["2.1.170"].content, frozenset())

    def test_content_needs_text_from_later_versions(self):
        early = [item for item in self.sessions if version_key(item.version) <= version_key("2.1.150")]
        self.assertEqual(changes(early, 200)[0].content, {("assistant", "z:str")})

    def test_alarms_only_see_the_first_session(self):
        flags = self.by_version["2.1.150"].flags
        self.assertEqual(flags["kind"], {("assistant", "z:str")})
        self.assertEqual(flags["any"], {("user", "b:str"), ("user", "d:num"), ("assistant", "z:str")})
        self.assertEqual(flags["bytes"], {("user", "d:num"), ("assistant", "z:str")})
        self.assertEqual(self.by_version["2.1.160"].flags["any"], frozenset())
        self.assertEqual(self.by_version["2.1.170"].flags["kind"], frozenset())

    def test_smaller_byte_threshold_flags_more(self):
        flags = changes(self.sessions, 100)[0].flags
        self.assertEqual(flags["bytes"], {("user", "b:str"), ("user", "d:num"), ("assistant", "z:str")})

    def test_single_version_has_no_change(self):
        self.assertEqual(changes([session("only", "2.1.140", [rec("user", {"a:str": (1, 1)})])], 200), [])


class ScoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.found = changes(drift_sessions(), 200)

    def test_kind_alarm(self):
        self.assertEqual(
            score(self.found, "kind"),
            {
                "key_tp": 1,
                "key_fp": 0,
                "key_fn": 2,
                "key_precision": 1.0,
                "key_recall": share(1, 3),
                "version_tp": 1,
                "version_fp": 0,
                "version_fn": 1,
                "version_precision": 1.0,
                "version_recall": 0.5,
            },
        )

    def test_any_alarm(self):
        result = score(self.found, "any")
        self.assertEqual(
            [result[key] for key in ("key_tp", "key_fp", "key_fn", "version_tp", "version_fp", "version_fn")],
            [2, 2, 1, 1, 1, 1],
        )
        self.assertEqual(result["key_precision"], 0.5)
        self.assertEqual(result["key_recall"], share(2, 3))
        self.assertEqual(result["version_precision"], 0.5)
        self.assertEqual(result["version_recall"], 0.5)

    def test_bytes_alarm(self):
        result = score(self.found, "bytes")
        self.assertEqual([result[key] for key in ("key_tp", "key_fp", "key_fn")], [1, 2, 2])
        self.assertEqual(result["key_precision"], share(1, 3))
        self.assertEqual(result["key_recall"], share(1, 3))
        self.assertEqual(result["version_tp"], 1)
        self.assertEqual(result["version_fp"], 1)
        self.assertEqual(result["version_fn"], 1)

    def test_score_has_exactly_ten_keys(self):
        self.assertEqual(
            set(score(self.found, "any")),
            {
                "key_tp",
                "key_fp",
                "key_fn",
                "key_precision",
                "key_recall",
                "version_tp",
                "version_fp",
                "version_fn",
                "version_precision",
                "version_recall",
            },
        )

    def test_empty_changes_give_zero_shares(self):
        result = score([], "any")
        self.assertEqual(result["key_precision"], 0.0)
        self.assertEqual(result["key_recall"], 0.0)
        self.assertEqual(result["version_precision"], 0.0)
        self.assertEqual(result["version_recall"], 0.0)
        self.assertEqual(f1(result), 0.0)


class F1Test(unittest.TestCase):
    def test_harmonic_mean(self):
        self.assertAlmostEqual(f1({"key_precision": 0.5, "key_recall": 0.5}), 0.5)
        self.assertAlmostEqual(f1({"key_precision": 1.0, "key_recall": 1 / 3}), 0.5)
        self.assertEqual(f1({"key_precision": 0.0, "key_recall": 0.0}), 0.0)
        self.assertEqual(f1({"key_precision": 1.0, "key_recall": 0.0}), 0.0)


class TuneTest(unittest.TestCase):
    def test_threshold_ties_go_to_the_smaller(self):
        best, scores = tune_bytes_min([tuning_train()])
        self.assertEqual(best, 1)
        self.assertEqual(len(scores), len(BYTES_GRID))
        self.assertAlmostEqual(scores[0], 0.8)
        self.assertAlmostEqual(scores[1], 0.8)
        self.assertAlmostEqual(scores[2], 0.5)
        self.assertEqual(scores[3:], [0.0, 0.0])

    def test_pools_harnesses_into_one_score(self):
        claude, codex = tuning_train(), tuning_codex()
        best, scores = tune_bytes_min([claude, codex])
        expected = [f1(score(changes(claude, b) + changes(codex, b), "bytes")) for b in BYTES_GRID]
        self.assertEqual(scores, expected)
        self.assertEqual(best, 1)
        self.assertAlmostEqual(scores[0], 6 / 7)


class TopUnseenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = [
            session("train", "2.1.140", [rec("user", {"a:str": (10, 10)})]),
            session(
                "test",
                "2.1.200",
                [
                    rec(
                        "user",
                        {"a:str": (10, 10), "t2:str": (100, 100), "t1:str": (100, 100), "t4:num": (900, 0)},
                    ),
                    rec("assistant", {"t3:str": (50, 100)}),
                ],
            ),
            session("codex-test", "0.140.0", [rec("user", {"k:num": (7, 0)})], harness="codex"),
        ]

    def test_orders_by_text_then_bytes_then_key(self):
        self.assertEqual(
            top_unseen(self.sessions, "claude"),
            [
                ("user", "t1:str", 100, 100),
                ("user", "t2:str", 100, 100),
                ("assistant", "t3:str", 50, 100),
                ("user", "t4:num", 900, 0),
            ],
        )

    def test_known_keys_and_other_harnesses_are_excluded(self):
        keys = {row[1] for row in top_unseen(self.sessions, "claude")}
        self.assertNotIn("a:str", keys)
        self.assertNotIn("k:num", keys)
        self.assertEqual(top_unseen(self.sessions, "codex"), [("user", "k:num", 7, 0)])

    def test_limit(self):
        self.assertEqual(len(top_unseen(self.sessions, "claude", n=2)), 2)
        self.assertEqual(top_unseen(self.sessions, "claude", n=0), [])


if __name__ == "__main__":
    unittest.main()
