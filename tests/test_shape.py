import json
import unittest

from capturedrift.shape import OPAQUE, is_text, kind, leaves, size, text_size


class SizeTest(unittest.TestCase):
    def test_size_is_compact_json_bytes(self):
        self.assertEqual(size({"a": 1}), 7)
        self.assertEqual(size([1, 2]), 5)
        self.assertEqual(size("é"), 4)
        self.assertLess(size("é"), len(json.dumps("é")))


class KindTest(unittest.TestCase):
    def test_non_string_type_is_unknown(self):
        self.assertEqual(kind("claude", {"type": 3}), "?")
        self.assertEqual(kind("codex", {}), "?")

    def test_codex_uses_payload_type(self):
        self.assertEqual(
            kind("codex", {"type": "response_item", "payload": {"type": "message"}}),
            "response_item/message",
        )
        self.assertEqual(kind("codex", {"type": "response_item", "payload": {"type": 3}}), "response_item")
        self.assertEqual(kind("codex", {"type": "response_item", "payload": "x"}), "response_item")

    def test_claude_uses_subtype_or_named_child(self):
        self.assertEqual(
            kind("claude", {"type": "system", "subtype": "turn_duration"}),
            "system/turn_duration",
        )
        self.assertEqual(
            kind("claude", {"type": "attachment", "attachment": {"type": "hook_success"}}),
            "attachment/hook_success",
        )
        self.assertEqual(kind("claude", {"type": "attachment", "attachment": {"type": 1}}), "attachment")
        self.assertEqual(kind("claude", {"type": "user"}), "user")


class TextTest(unittest.TestCase):
    def test_is_text_needs_three_words(self):
        self.assertTrue(is_text("one two three"))
        self.assertTrue(is_text("  one\ttwo\nthree  "))
        self.assertFalse(is_text("one two"))
        self.assertFalse(is_text(""))
        self.assertFalse(is_text(None))

    def test_text_size_walks_values_and_skips_keys(self):
        value = {"one two three": ["four five six", {"k": "seven eight nine"}, 4]}
        expected = size("four five six") + size("seven eight nine")
        self.assertEqual(text_size(value), expected)
        self.assertEqual(text_size("one two three"), size("one two three"))
        self.assertEqual(text_size("one two"), 0)
        self.assertEqual(text_size(7), 0)


class OpaqueTest(unittest.TestCase):
    def test_paths(self):
        self.assertEqual(
            OPAQUE["claude"],
            ("message.content[]<tool_use>.input", "toolUseResult", "snapshot.trackedFileBackups"),
        )
        self.assertEqual(
            OPAQUE["codex"],
            (
                "payload.dynamic_tools",
                "payload.tools",
                "payload.result",
                "payload.changes",
                "payload.invocation.arguments",
            ),
        )


class LeavesTest(unittest.TestCase):
    def assertLeaves(self, harness, record, expected):
        self.assertEqual(leaves(harness, record), expected)

    def test_simple_record_paths(self):
        record = {"type": "user", "message": {"role": "user", "content": "one two three"}}
        expected = {
            "type:str": (size("user"), 0),
            "message.role:str": (size("user"), 0),
            "message.content:str": (size("one two three"), size("one two three")),
        }
        self.assertLeaves("claude", record, expected)

    def test_text_block_example_path(self):
        record = {
            "type": "assistant",
            "message": {
                "model": "claude-fable-5",
                "content": [{"type": "text", "text": "hello world foo"}],
            },
        }
        text = size("hello world foo")
        expected = {
            "type:str": (size("assistant"), 0),
            "message.model:str": (size("claude-fable-5"), 0),
            "message.content[]<text>.type:str": (size("text"), 0),
            "message.content[]<text>.text:str": (text, text),
        }
        self.assertLeaves("claude", record, expected)

    def test_wildcard_keys_and_repeated_paths(self):
        record = {"type": "x", "a-b": 1, "c-d": 2, "ok_1": 3}
        expected = {
            "type:str": (size("x"), 0),
            "*:num": (size(1) + size(2), 0),
            "ok_1:num": (size(3), 0),
        }
        self.assertLeaves("claude", record, expected)

    def test_list_tags_group_by_type(self):
        record = {
            "type": "x",
            "items": [
                {"type": "alpha", "v": 1},
                {"type": "bad tag!", "v": 2},
                {"type": "", "v": 3},
                "plain",
                {"v": 4},
            ],
        }
        expected = {
            "type:str": (size("x"), 0),
            "items[]<alpha>.type:str": (size("alpha"), 0),
            "items[]<alpha>.v:num": (size(1), 0),
            "items[]<*>.type:str": (size("bad tag!") + size(""), 0),
            "items[]<*>.v:num": (size(2) + size(3), 0),
            "items[]:str": (size("plain"), 0),
            "items[].v:num": (size(4), 0),
        }
        self.assertLeaves("claude", record, expected)

    def test_empty_containers(self):
        record = {"type": "x", "obj": {}, "arr": []}
        expected = {
            "type:str": (size("x"), 0),
            "obj:{}": (2, 0),
            "arr:[]": (2, 0),
        }
        self.assertLeaves("claude", record, expected)

    def test_empty_root(self):
        self.assertLeaves("claude", {}, {":{}": (2, 0)})

    def test_scalar_types(self):
        record = {"type": "x", "yes": True, "no": False, "nil": None, "n": 1, "f": 1.5}
        expected = {
            "type:str": (size("x"), 0),
            "yes:bool": (size(True), 0),
            "no:bool": (size(False), 0),
            "nil:null": (size(None), 0),
            "n:num": (size(1), 0),
            "f:num": (size(1.5), 0),
        }
        self.assertLeaves("claude", record, expected)

    def test_repeated_paths_are_summed(self):
        record = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "one two three"},
                    {"type": "text", "text": "four five six"},
                ]
            },
        }
        first = size("one two three")
        second = size("four five six")
        expected = {
            "type:str": (size("assistant"), 0),
            "message.content[]<text>.type:str": (size("text") * 2, 0),
            "message.content[]<text>.text:str": (first + second, first + second),
        }
        self.assertLeaves("claude", record, expected)

    def test_claude_opaque_tool_result(self):
        result = {"stdout": "one two three", "n": 1}
        record = {"type": "user", "toolUseResult": result}
        expected = {
            "type:str": (size("user"), 0),
            "toolUseResult:json": (size(result), size("one two three")),
        }
        self.assertLeaves("claude", record, expected)

    def test_claude_opaque_tool_use_input(self):
        tool_input = {"command": "ls -la /tmp"}
        record = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": tool_input},
                ]
            },
        }
        expected = {
            "type:str": (size("assistant"), 0),
            "message.content[]<tool_use>.type:str": (size("tool_use"), 0),
            "message.content[]<tool_use>.id:str": (size("toolu_1"), 0),
            "message.content[]<tool_use>.name:str": (size("Bash"), 0),
            "message.content[]<tool_use>.input:json": (size(tool_input), size("ls -la /tmp")),
        }
        self.assertLeaves("claude", record, expected)

    def test_codex_opaque_invocation_arguments(self):
        arguments = {"a": 1, "b": "one two three"}
        record = {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "invocation": {"arguments": arguments},
            },
        }
        expected = {
            "type:str": (size("response_item"), 0),
            "payload.type:str": (size("function_call"), 0),
            "payload.invocation.arguments:json": (size(arguments), size("one two three")),
        }
        self.assertLeaves("codex", record, expected)

    def test_opaque_paths_are_harness_specific(self):
        record = {"type": "x", "toolUseResult": {"n": 1}}
        expected = {
            "type:str": (size("x"), 0),
            "toolUseResult.n:num": (size(1), 0),
        }
        self.assertLeaves("codex", record, expected)
