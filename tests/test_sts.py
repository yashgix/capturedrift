"""Tests for the STS normalizer on small synthetic records."""

import json
import unittest

from capturedrift.sts import MAPPED, epoch_ms, mapped_keys, normalize

STAMP = "2026-01-01T00:00:00Z"
MS = 1_767_225_600_000
NL = chr(10)


class EpochMsTest(unittest.TestCase):
    def test_utc_naive_and_offset_are_equal(self):
        self.assertEqual(epoch_ms("2026-01-01T00:00:00Z"), MS)
        self.assertEqual(epoch_ms("2026-01-01T00:00:00"), MS)
        self.assertEqual(epoch_ms("2026-01-01T01:00:00+01:00"), MS)
        self.assertEqual(epoch_ms("2026-01-01T00:00:00.123Z"), MS + 123)

    def test_unparseable_or_non_string_is_none(self):
        self.assertIsNone(epoch_ms("not a date"))
        self.assertIsNone(epoch_ms(None))
        self.assertIsNone(epoch_ms(4))


class HeaderTest(unittest.TestCase):
    def test_claude_uses_first_string_session_id(self):
        records = [{"type": "mode", "sessionId": 3}, {"type": "user", "sessionId": "abc"}]
        self.assertEqual(
            normalize("claude", records)[0],
            {"type": "session", "harness": "claude-code", "id": "abc"},
        )

    def test_codex_uses_first_session_meta_id(self):
        records = [
            {"type": "response_item"},
            {"type": "session_meta", "payload": {"id": "s1"}},
            {"type": "session_meta", "payload": {"id": "s2"}},
        ]
        self.assertEqual(normalize("codex", records)[0]["id"], "s1")

    def test_fallback_id(self):
        self.assertEqual(normalize("claude", [], "fallback")[0]["id"], "fallback")
        self.assertEqual(
            normalize("codex", [{"type": "session_meta", "payload": {}}], "fallback")[0]["id"],
            "fallback",
        )


class ClaudeTest(unittest.TestCase):
    def test_user_record_emits_tool_results_then_text(self):
        record = {
            "type": "user",
            "timestamp": STAMP,
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"},
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_2",
                        "content": [{"type": "text", "text": "one two"}, {"type": "text", "text": "three"}],
                    },
                    {"type": "text", "text": "hello"},
                    {"type": "text", "text": "world"},
                ]
            },
        }
        messages = normalize("claude", [record])[1:]
        self.assertEqual(len(messages), 3)
        self.assertEqual(
            messages[0]["message"],
            {"role": "tool", "content": "ok", "toolCallId": "toolu_1", "timestamp": MS},
        )
        self.assertEqual(messages[1]["message"]["content"], NL.join(["one two", "three"]))
        self.assertEqual(messages[1]["message"]["toolCallId"], "toolu_2")
        self.assertEqual(messages[2]["message"]["content"], NL.join(["hello", "world"]))
        self.assertEqual(list(messages[0]["message"]), ["role", "content", "toolCallId", "timestamp"])

    def test_user_string_content_is_kept(self):
        record = {"type": "user", "message": {"content": "one two three"}}
        self.assertEqual(normalize("claude", [record])[1]["message"], {"role": "user", "content": "one two three"})

    def test_assistant_maps_text_thinking_tools_and_model(self):
        record = {
            "type": "assistant",
            "timestamp": STAMP,
            "message": {
                "model": "claude-test",
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "thinking", "thinking": "reason"},
                    {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "ls"}},
                    {"type": "tool_use", "id": "toolu_2", "name": "Noop"},
                ],
            },
        }
        message = normalize("claude", [record])[1]["message"]
        self.assertEqual(message["content"], "hello")
        self.assertEqual(message["reasoningContent"], "reason")
        self.assertEqual(
            message["toolCalls"],
            [
                {
                    "id": "toolu_1",
                    "function": {
                        "name": "Bash",
                        "arguments": json.dumps({"command": "ls"}, separators=(",", ":")),
                    },
                },
                {"id": "toolu_2", "function": {"name": "Noop", "arguments": "{}"}},
            ],
        )
        self.assertEqual(message["model"], "claude-test")
        self.assertEqual(message["timestamp"], MS)
        self.assertEqual(
            list(message),
            ["role", "content", "reasoningContent", "toolCalls", "model", "timestamp"],
        )

    def test_thinking_only_record_is_kept(self):
        record = {
            "type": "assistant",
            "timestamp": STAMP,
            "message": {
                "content": [{"type": "thinking", "thinking": "one two three"}],
            },
        }
        message = normalize("claude", [record])[1]["message"]
        self.assertEqual(message["content"], "")
        self.assertEqual(message["reasoningContent"], "one two three")
        self.assertEqual(message["timestamp"], MS)


class CodexTest(unittest.TestCase):
    def test_message_maps_developer_to_system_input_first(self):
        record = {
            "type": "response_item",
            "timestamp": STAMP,
            "payload": {
                "type": "message",
                "role": "developer",
                "content": [
                    {"type": "output_text", "text": "hi"},
                    {"type": "input_text", "text": "there"},
                ],
            },
        }
        message = normalize("codex", [record])[1]["message"]
        self.assertEqual(message, {"role": "system", "content": NL.join(["there", "hi"]), "timestamp": MS})
        self.assertEqual(list(message), ["role", "content", "timestamp"])

    def test_reasoning_calls_and_outputs(self):
        records = [
            {
                "type": "response_item",
                "timestamp": STAMP,
                "payload": {
                    "type": "reasoning",
                    "summary": [
                        {"type": "summary_text", "text": "a"},
                        {"type": "summary_text", "text": "b"},
                    ],
                },
            },
            {
                "type": "response_item",
                "timestamp": STAMP,
                "payload": {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "shell",
                    "arguments": "raw",
                },
            },
            {
                "type": "response_item",
                "timestamp": STAMP,
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "c2",
                    "name": "apply",
                    "input": "patch",
                },
            },
            {
                "type": "response_item",
                "timestamp": STAMP,
                "payload": {"type": "function_call_output", "call_id": "c1", "output": "ok"},
            },
            {
                "type": "response_item",
                "timestamp": STAMP,
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "c2",
                    "output": [
                        {"type": "input_text", "text": "one"},
                        {"type": "input_text", "text": "two"},
                    ],
                },
            },
        ]
        messages = normalize("codex", records)[1:]
        self.assertEqual(len(messages), 5)
        self.assertEqual(
            messages[0]["message"],
            {"role": "assistant", "content": "", "reasoningContent": NL.join(["a", "b"]), "timestamp": MS},
        )
        self.assertEqual(
            messages[1]["message"]["toolCalls"],
            [{"id": "c1", "function": {"name": "shell", "arguments": "raw"}}],
        )
        self.assertEqual(
            messages[2]["message"]["toolCalls"],
            [{"id": "c2", "function": {"name": "apply", "arguments": "patch"}}],
        )
        self.assertEqual(
            messages[3]["message"],
            {"role": "tool", "content": "ok", "toolCallId": "c1", "timestamp": MS},
        )
        self.assertEqual(
            messages[4]["message"],
            {
                "role": "tool",
                "content": NL.join(["one", "two"]),
                "toolCallId": "c2",
                "timestamp": MS,
            },
        )
        self.assertEqual(list(messages[1]["message"]), ["role", "content", "toolCalls", "timestamp"])

    def test_unknown_roles_and_records_are_skipped(self):
        records = [
            {"type": "response_item", "payload": {"type": "message", "role": "critic", "content": []}},
            {"type": "response_item", "payload": {"type": "reasoning", "summary": []}},
            {"type": "event_msg", "payload": {"type": "task_started"}},
        ]
        self.assertEqual(len(normalize("codex", records)), 1)


class SkipTest(unittest.TestCase):
    def test_claude_records_without_mapped_content_are_skipped(self):
        records = [
            {"type": "mystery"},
            {"type": "assistant", "message": {"content": [{"type": "text"}]}},
            {"type": "user", "message": {"content": []}},
        ]
        self.assertEqual(len(normalize("claude", records)), 1)


class MappedKeysTest(unittest.TestCase):
    def test_matches_mapped_table(self):
        for harness in MAPPED:
            expected = {(event, path) for event, paths in MAPPED[harness].items() for path in paths}
            self.assertEqual(mapped_keys(harness), expected)

    def test_complete_mapping_tables_against_specification(self):
        expected = {
            "claude": {
                "user": (
                    "message.content:str",
                    "message.content[]<text>.text:str",
                    "message.content[]<tool_result>.tool_use_id:str",
                    "message.content[]<tool_result>.content:str",
                    "message.content[]<tool_result>.content[]<text>.text:str",
                    "timestamp:str",
                ),
                "assistant": (
                    "message.content[]<text>.text:str",
                    "message.content[]<thinking>.thinking:str",
                    "message.content[]<tool_use>.id:str",
                    "message.content[]<tool_use>.name:str",
                    "message.content[]<tool_use>.input:json",
                    "message.model:str",
                    "timestamp:str",
                ),
            },
            "codex": {
                "response_item/message": (
                    "payload.role:str",
                    "payload.content[]<input_text>.text:str",
                    "payload.content[]<output_text>.text:str",
                    "timestamp:str",
                ),
                "response_item/reasoning": (
                    "payload.summary[]<summary_text>.text:str",
                    "timestamp:str",
                ),
                "response_item/function_call": (
                    "payload.call_id:str",
                    "payload.name:str",
                    "payload.arguments:str",
                    "timestamp:str",
                ),
                "response_item/custom_tool_call": (
                    "payload.call_id:str",
                    "payload.name:str",
                    "payload.input:str",
                    "timestamp:str",
                ),
                "response_item/function_call_output": (
                    "payload.call_id:str",
                    "payload.output:str",
                    "payload.output[]<input_text>.text:str",
                    "timestamp:str",
                ),
                "response_item/custom_tool_call_output": (
                    "payload.call_id:str",
                    "payload.output:str",
                    "payload.output[]<input_text>.text:str",
                    "timestamp:str",
                ),
            },
        }
        self.assertEqual(MAPPED, expected)

    def test_claude_user_path(self):
        self.assertIn(("user", "message.content:str"), mapped_keys("claude"))


if __name__ == "__main__":
    unittest.main()
