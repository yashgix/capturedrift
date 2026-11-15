import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from capturedrift.__main__ import main as cli
from capturedrift.data import Record, Session, session_start, session_version, version_key
from capturedrift.drift import (
    changes,
    is_train,
    key_totals,
    mapped_share,
    score,
    shapes,
    top_unseen,
    tune_bytes_min,
    unseen,
    versions,
)
from capturedrift.shape import is_text, kind, leaves, size, text_size
from capturedrift.sts import epoch_ms, mapped_keys, normalize

TEXT = "one two three"  # 3 words: text
WORD = "x" * 300  # long, but one word: not text


def rec(kind_, **paths):
    return Record(kind_, {p: v for p, v in paths.items()})


def session(name, version, records, harness="claude", start=""):
    return Session(name, harness, version, "src", start, tuple(records))


def leaf(path, b, t=0):
    return {path: (b, t)}


class Shapes(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(
            kind("codex", {"type": "event_msg", "payload": {"type": "token_count"}}), "event_msg/token_count"
        )
        self.assertEqual(kind("codex", {"type": "session_meta", "payload": {"id": "x"}}), "session_meta")
        self.assertEqual(kind("claude", {"type": "system", "subtype": "api_error"}), "system/api_error")
        self.assertEqual(kind("claude", {"type": "attachment", "attachment": {"type": "todo"}}), "attachment/todo")
        self.assertEqual(kind("claude", {"type": "user", "message": {"type": "message"}}), "user")
        self.assertEqual(kind("claude", {"message": {}}), "?")

    def test_paths_tags_and_types(self):
        record = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": TEXT}, {"type": "text", "text": "hi"}, 3]},
            "ok": True,
            "n": None,
            "x": 1.5,
        }
        got = leaves("claude", record)
        self.assertEqual(got["type:str"], (size("assistant"), 0))
        self.assertEqual(got["message.content[]<text>.text:str"], (size(TEXT) + size("hi"), size(TEXT)))
        self.assertEqual(got["message.content[]<text>.type:str"], (2 * size("text"), 0))
        self.assertEqual(got["message.content[]:num"], (1, 0))
        self.assertEqual((got["ok:bool"], got["n:null"], got["x:num"]), ((4, 0), (4, 0), (3, 0)))
        self.assertEqual(len(got), 7)

    def test_odd_keys_and_tags(self):
        got = leaves("claude", {"a-b": 1, "c": [{"type": "has space"}, {"type": 7}], "d": [{}]})
        self.assertIn("*:num", got)
        self.assertIn("c[]<*>.type:str", got)
        self.assertIn("c[].type:num", got)
        self.assertIn("d[]:{}", got)

    def test_empty_containers(self):
        self.assertEqual(leaves("codex", {"a": {}, "b": []}), {"a:{}": (2, 0), "b:[]": (2, 0)})

    def test_opaque_subtrees_are_one_leaf(self):
        block = {"type": "tool_use", "input": {"command": TEXT, "flags": {"deep": WORD}}}
        got = leaves("claude", {"message": {"content": [block]}})
        value = block["input"]
        self.assertEqual(got["message.content[]<tool_use>.input:json"], (size(value), size(TEXT)))
        self.assertFalse(any(".input." in p for p in got))
        codex = leaves("codex", {"payload": {"result": {"Ok": [1, 2]}, "invocation": {"arguments": {"a": 1}}}})
        self.assertEqual(set(codex), {"payload.result:json", "payload.invocation.arguments:json"})

    def test_text_rule(self):
        self.assertTrue(is_text(TEXT))
        self.assertTrue(is_text("a\nb c"))
        self.assertFalse(is_text("two words"))
        self.assertFalse(is_text(WORD))
        self.assertFalse(is_text(5))
        self.assertEqual(text_size({"a": [TEXT, "no"], "b": {"c": TEXT}}), 2 * size(TEXT))
        self.assertEqual(size("é"), 4)


class Sessions(unittest.TestCase):
    def test_version_key(self):
        self.assertEqual(version_key("0.147.0-alpha.1.2"), (0, 147, 0, 1, 2))
        self.assertLess(version_key("2.1.99"), version_key("2.1.145"))

    def test_version_and_start(self):
        claude = [{"type": "mode"}, {"version": "2.1.5", "timestamp": "2026-02-01"}, {"version": "2.1.6"}]
        self.assertEqual(session_version("claude", claude), "2.1.5")
        codex = [
            {"type": "x", "payload": {"cli_version": "9"}},
            {"type": "session_meta", "payload": {"cli_version": "1"}},
        ]
        self.assertEqual(session_version("codex", codex), "1")
        self.assertIsNone(session_version("claude", [{"type": "mode"}]))
        self.assertEqual(session_start([{"timestamp": "2026-03-01"}, {"timestamp": "2026-01-01"}, {}]), "2026-01-01")
        self.assertEqual(session_start([{}]), "")


class Sts(unittest.TestCase):
    def test_epoch_ms(self):
        self.assertEqual(epoch_ms("2026-06-10T12:00:00.123Z"), 1781092800123)
        self.assertEqual(epoch_ms("2026-06-10T12:00:00.123"), 1781092800123)
        self.assertEqual(epoch_ms("1970-01-01T00:00:00.001+00:00"), 1)
        self.assertIsNone(epoch_ms("yesterday"))
        self.assertIsNone(epoch_ms(None))

    def test_claude_user(self):
        records = [
            {
                "type": "user",
                "sessionId": "s1",
                "timestamp": "1970-01-01T00:00:01Z",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "out"},
                        {"type": "text", "text": "a"},
                        {
                            "type": "tool_result",
                            "tool_use_id": "t2",
                            "content": [{"type": "text", "text": "b"}, {"type": "text", "text": "c"}],
                        },
                        {"type": "text", "text": "d"},
                    ]
                },
            },
            {"type": "user", "message": {"content": "plain"}},
            {"type": "user", "message": {"content": [{"type": "image"}]}},
            {"type": "attachment", "attachment": {"type": "x"}},
        ]
        self.assertEqual(
            normalize("claude", records),
            [
                {"type": "session", "harness": "claude-code", "id": "s1"},
                {
                    "type": "message",
                    "message": {"role": "tool", "content": "out", "toolCallId": "t1", "timestamp": 1000},
                },
                {
                    "type": "message",
                    "message": {"role": "tool", "content": "b\nc", "toolCallId": "t2", "timestamp": 1000},
                },
                {"type": "message", "message": {"role": "user", "content": "a\nd", "timestamp": 1000}},
                {"type": "message", "message": {"role": "user", "content": "plain"}},
            ],
        )

    def test_claude_assistant(self):
        records = [
            {
                "type": "assistant",
                "message": {
                    "model": "m",
                    "content": [
                        {"type": "thinking", "thinking": "hmm"},
                        {"type": "text", "text": "x"},
                        {"type": "tool_use", "id": "u1", "name": "Bash", "input": {"cmd": "ls é"}},
                        {"type": "tool_use", "id": "u2", "name": "Read"},
                    ],
                },
            },
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "id": "u3", "name": "Grep", "input": {}}]},
            },
            {"type": "assistant", "message": {"content": [{"type": "redacted"}]}},
        ]
        out = normalize("claude", records, "fallback")
        self.assertEqual(out[0]["id"], "fallback")
        self.assertEqual(
            out[1]["message"],
            {
                "role": "assistant",
                "content": "x",
                "reasoningContent": "hmm",
                "toolCalls": [
                    {"id": "u1", "function": {"name": "Bash", "arguments": '{"cmd":"ls é"}'}},
                    {"id": "u2", "function": {"name": "Read", "arguments": "{}"}},
                ],
                "model": "m",
            },
        )
        self.assertEqual(list(out[1]["message"]), ["role", "content", "reasoningContent", "toolCalls", "model"])
        self.assertEqual(
            out[2]["message"],
            {
                "role": "assistant",
                "content": "",
                "toolCalls": [{"id": "u3", "function": {"name": "Grep", "arguments": "{}"}}],
            },
        )
        self.assertEqual(len(out), 3)

    def test_codex(self):
        def item(payload, ts="1970-01-01T00:00:00.002Z"):
            return {"type": "response_item", "timestamp": ts, "payload": payload}

        records = [
            {"type": "session_meta", "payload": {"id": "c1", "cli_version": "1"}},
            item({"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "rules"}]}),
            item(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "o"}, {"type": "input_text", "text": "i"}],
                }
            ),
            item({"type": "message", "role": "tool", "content": []}),
            item({"type": "reasoning", "summary": []}),
            item({"type": "reasoning", "summary": [{"type": "summary_text", "text": "s"}]}),
            item({"type": "function_call", "call_id": "f1", "name": "shell", "arguments": "{}"}),
            item({"type": "custom_tool_call", "call_id": "f2", "name": "apply_patch", "input": "patch"}),
            item({"type": "function_call_output", "call_id": "f1", "output": "done"}),
            item(
                {"type": "custom_tool_call_output", "call_id": "f2", "output": [{"type": "input_text", "text": "ok"}]}
            ),
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "dup"}},
        ]
        msgs = [line["message"] for line in normalize("codex", records)[1:]]
        self.assertEqual(normalize("codex", records)[0], {"type": "session", "harness": "codex", "id": "c1"})
        self.assertEqual(
            msgs,
            [
                {"role": "system", "content": "rules", "timestamp": 2},
                {"role": "assistant", "content": "i\no", "timestamp": 2},
                {"role": "assistant", "content": "", "reasoningContent": "s", "timestamp": 2},
                {
                    "role": "assistant",
                    "content": "",
                    "toolCalls": [{"id": "f1", "function": {"name": "shell", "arguments": "{}"}}],
                    "timestamp": 2,
                },
                {
                    "role": "assistant",
                    "content": "",
                    "toolCalls": [{"id": "f2", "function": {"name": "apply_patch", "arguments": "patch"}}],
                    "timestamp": 2,
                },
                {"role": "tool", "content": "done", "toolCallId": "f1", "timestamp": 2},
                {"role": "tool", "content": "ok", "toolCallId": "f2", "timestamp": 2},
            ],
        )

    def test_mapped_keys(self):
        claude, codex = mapped_keys("claude"), mapped_keys("codex")
        self.assertEqual((len(claude), len(codex)), (13, 22))
        self.assertIn(("assistant", "message.content[]<thinking>.thinking:str"), claude)
        self.assertIn(("assistant", "message.content[]<tool_use>.input:json"), claude)
        self.assertNotIn(("assistant", "message.content[]<thinking>.signature:str"), claude)
        self.assertIn(("response_item/custom_tool_call_output", "payload.output[]<input_text>.text:str"), codex)
        self.assertNotIn(("response_item/reasoning", "payload.encrypted_content:str"), codex)


class Drift(unittest.TestCase):
    def test_cutoff_is_inclusive(self):
        self.assertTrue(is_train(session("a", "2.1.145", [])))
        self.assertFalse(is_train(session("a", "2.1.158", [])))
        self.assertTrue(is_train(session("a", "0.125.0", [], harness="codex")))
        self.assertFalse(is_train(session("a", "0.140.0-alpha.2", [], harness="codex")))

    def test_versions_order(self):
        s = [session("a", "2.1.10", []), session("b", "2.1.9", []), session("c", "2.1.10", [])]
        self.assertEqual([(v, [x.name for x in g]) for v, g in versions(s)], [("2.1.9", ["b"]), ("2.1.10", ["a", "c"])])

    def test_unseen_and_mapped_shares(self):
        r1 = Record("user", {"a:str": (10, 10), "b:num": (5, 0)})
        r2 = Record("user", {"a:str": (20, 0)})
        r3 = Record("assistant", {"a:str": (15, 15)})
        s = [session("s", "1", [r1, r2, r3])]
        got = unseen(s, {("user", "a:str")})
        self.assertAlmostEqual(got["records"], 2 / 3)
        self.assertAlmostEqual(got["bytes"], 20 / 50)
        self.assertAlmostEqual(got["text"], 15 / 25)
        self.assertEqual(unseen([], set()), {"records": 0.0, "bytes": 0.0, "text": 0.0})
        shares = mapped_share(s, {("user", "a:str")})
        self.assertAlmostEqual(shares["bytes"], 30 / 50)
        self.assertAlmostEqual(shares["text"], 10 / 25)
        self.assertEqual(key_totals(s)[("user", "a:str")], [30, 10])

    def test_shapes(self):
        a = Record("user", {"a:str": (1, 0)})
        b = Record("user", {"a:str": (9, 0)})
        c = Record("user", {"a:str": (1, 0), "b:num": (1, 0)})
        d = Record("assistant", {"a:str": (1, 0)})
        self.assertEqual(shapes([session("s", "1", [a, b, c, d])]), 3)

    def _history(self):
        old = Record("user", {"a:str": (10, 0)})
        first = Record("user", {"a:str": (1, 0), "new_small:str": (5, 5), "new_big:str": (500, 0)})
        later_kind = Record("hook", {"type:str": (300, 300)})
        return [
            session("v1", "1.0.0", [old]),
            session("v2a", "1.0.1", [first]),
            session("v2b", "1.0.1", [later_kind]),
            session(
                "v3", "1.0.2", [Record("user", {"new_small:str": (300, 300)}), Record("tool", {"x:str": (900, 0)})]
            ),
        ]

    def test_changes_truth_and_first_session_alarms(self):
        found = changes(self._history(), bytes_min=200)
        self.assertEqual([c.version for c in found], ["1.0.1", "1.0.2"])
        c1, c2 = found
        self.assertEqual(
            c1.new, {("user", "new_small:str"), ("user", "new_big:str"), ("hook", "type:str")}
        )  # the second session's keys are new too
        self.assertEqual(c1.content, {("user", "new_small:str"), ("hook", "type:str")})  # text counted from v1.0.1 on
        self.assertEqual(c1.flags["any"], {("user", "new_small:str"), ("user", "new_big:str")})  # first session only
        self.assertEqual(c1.flags["kind"], frozenset())
        self.assertEqual(c1.flags["bytes"], {("user", "new_big:str")})
        self.assertEqual(c2.new, {("tool", "x:str")})
        self.assertEqual(c2.content, frozenset())
        self.assertEqual(c2.flags["kind"], {("tool", "x:str")})

    def test_score(self):
        found = changes(self._history(), bytes_min=200)
        self.assertEqual(
            score(found, "any"),
            {
                "key_tp": 1,
                "key_fp": 2,
                "key_fn": 1,
                "key_precision": 1 / 3,
                "key_recall": 0.5,
                "version_tp": 1,
                "version_fp": 1,
                "version_fn": 0,
                "version_precision": 0.5,
                "version_recall": 1.0,
            },
        )
        empty = score(found[1:], "any")
        self.assertEqual((empty["key_precision"], empty["key_recall"], empty["version_recall"]), (0.0, 0.0, 0.0))

    def test_tune_picks_best_threshold_ties_low(self):
        base = session("v1", "1.0.0", [Record("user", {"a:str": (1, 0)})])
        first = session("v2", "1.0.1", [Record("user", {"big:str": (300, 300), "meta:num": (50, 0)})])
        best, f1s = tune_bytes_min([[base, first]])
        self.assertEqual(best, 200)
        self.assertEqual([round(f, 6) for f in f1s], [0.666667, 0.666667, 1.0, 0.0, 0.0])
        self.assertEqual(tune_bytes_min([[base]]), (1, [0.0] * 5))

    def test_top_unseen(self):
        train = session("t", "2.1.100", [Record("user", {"a:str": (1, 0)})])
        test = session(
            "u",
            "2.1.200",
            [
                Record("user", {"a:str": (99, 99), "b:str": (50, 40), "c:str": (70, 40), "d:num": (900, 0)}),
            ],
        )
        got = top_unseen([train, test], "claude", n=3)
        self.assertEqual(got, [("user", "c:str", 70, 40), ("user", "b:str", 50, 40), ("user", "d:num", 900, 0)])
        self.assertEqual(top_unseen([train, test], "codex"), [])


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.file = self.tmp / "abc.jsonl"
        lines = [
            {"type": "user", "version": "2.1.1", "message": {"content": "secret words here"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "reply"}]}},
        ]
        self.file.write_text("".join(json.dumps(x) + "\n" for x in lines) + "\n")

    def test_normalize_writes_sts(self):
        out = self.tmp / "out.jsonl"
        with contextlib.redirect_stderr(io.StringIO()):
            cli(["normalize", "--harness", "claude", str(self.file), str(out)])
        lines = [json.loads(x) for x in out.read_text().splitlines()]
        self.assertEqual(lines[0], {"type": "session", "harness": "claude-code", "id": "abc"})
        self.assertEqual([x["message"]["role"] for x in lines[1:]], ["user", "assistant"])

    def test_audit_is_structure_only(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli(["audit", "--harness", "claude", str(self.file)])
        self.assertNotIn("secret", buf.getvalue())
        got = json.loads(buf.getvalue())
        self.assertEqual((got["sessions"], got["records"], got["versions"], got["kinds"]), (1, 2, ["2.1.1"], 2))
        self.assertEqual(
            set(got), {"sessions", "records", "versions", "kinds", "keys", "sts_byte_share", "sts_text_share"}
        )
