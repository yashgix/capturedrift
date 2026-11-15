"""Normalize raw session records into the Session Traces Simple Format."""

import json
from datetime import datetime, timedelta, timezone

from .shape import kind

MAPPED = {
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

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MILLISECOND = timedelta(milliseconds=1)
_HARNESS = {"claude": "claude-code", "codex": "codex"}


def mapped_keys(harness):
    """Every (kind, key path) pair the normalizer reads for a harness."""
    return {(event, path) for event, paths in MAPPED[harness].items() for path in paths}


def epoch_ms(stamp):
    """An ISO-8601 timestamp as exact epoch milliseconds, or None."""
    if not isinstance(stamp, str):
        return None
    try:
        value = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (value - _EPOCH) // _MILLISECOND


def _string(value):
    return value if isinstance(value, str) else ""


def _text_values(blocks, block_type, field="text"):
    if not isinstance(blocks, list):
        return []
    return [
        block[field]
        for block in blocks
        if isinstance(block, dict) and block.get("type") == block_type and isinstance(block.get(field), str)
    ]


def _join(values):
    return "\n".join(values)


def _message(role, content, *, reasoning=None, tool_calls=None, tool_call_id=None, model=None, timestamp=None):
    message = {"role": role, "content": content}
    if reasoning is not None:
        message["reasoningContent"] = reasoning
    if tool_calls is not None:
        message["toolCalls"] = tool_calls
    if tool_call_id is not None:
        message["toolCallId"] = tool_call_id
    if model is not None:
        message["model"] = model
    if timestamp is not None:
        message["timestamp"] = timestamp
    return {"type": "message", "message": message}


def _header(harness, records, fallback_id):
    ident = None
    if harness == "claude":
        for record in records:
            if isinstance(record, dict) and isinstance(record.get("sessionId"), str):
                ident = record["sessionId"]
                break
    else:
        for record in records:
            if isinstance(record, dict) and record.get("type") == "session_meta":
                payload = record.get("payload")
                if isinstance(payload, dict) and isinstance(payload.get("id"), str):
                    ident = payload["id"]
                break
    return {"type": "session", "harness": _HARNESS[harness], "id": ident if ident is not None else fallback_id}


def _tool_result_content(block):
    content = block.get("content")
    if isinstance(content, str):
        return content
    return _join(_text_values(content, "text"))


def _claude_user(record, timestamp):
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str):
        return [_message("user", content, timestamp=timestamp)]
    if not isinstance(content, list):
        return []
    out = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            tool_id = block.get("tool_use_id")
            out.append(
                _message(
                    "tool",
                    _tool_result_content(block),
                    tool_call_id=tool_id if isinstance(tool_id, str) else None,
                    timestamp=timestamp,
                )
            )
    texts = _text_values(content, "text")
    if texts:
        out.append(_message("user", _join(texts), timestamp=timestamp))
    return out


def _tool_call(block):
    arguments = block.get("input")
    if arguments is None:
        arguments = {}
    return {
        "id": _string(block.get("id")),
        "function": {
            "name": _string(block.get("name")),
            "arguments": json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
        },
    }


def _claude_assistant(record, timestamp):
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    blocks = message.get("content")
    if not isinstance(blocks, list):
        return []
    texts = _text_values(blocks, "text")
    thoughts = _text_values(blocks, "thinking", "thinking")
    tool_uses = [block for block in blocks if isinstance(block, dict) and block.get("type") == "tool_use"]
    if not texts and not thoughts and not tool_uses:
        return []
    model = message.get("model")
    return [
        _message(
            "assistant",
            _join(texts),
            reasoning=_join(thoughts) if thoughts else None,
            tool_calls=[_tool_call(block) for block in tool_uses] if tool_uses else None,
            model=model if isinstance(model, str) else None,
            timestamp=timestamp,
        )
    ]


def _codex_message(event, payload, timestamp):
    if event == "response_item/message":
        role = payload.get("role")
        if role in ("developer", "system"):
            role = "system"
        if role not in ("user", "assistant", "system"):
            return []
        content = payload.get("content")
        texts = _text_values(content, "input_text") + _text_values(content, "output_text")
        return [_message(role, _join(texts), timestamp=timestamp)]
    if event == "response_item/reasoning":
        texts = _text_values(payload.get("summary"), "summary_text")
        if not texts:
            return []
        return [_message("assistant", "", reasoning=_join(texts), timestamp=timestamp)]
    if event in ("response_item/function_call", "response_item/custom_tool_call"):
        arguments = payload.get("arguments") if event == "response_item/function_call" else payload.get("input")
        tool = {
            "id": _string(payload.get("call_id")),
            "function": {"name": _string(payload.get("name")), "arguments": _string(arguments)},
        }
        return [_message("assistant", "", tool_calls=[tool], timestamp=timestamp)]
    if event in ("response_item/function_call_output", "response_item/custom_tool_call_output"):
        output = payload.get("output")
        content = output if isinstance(output, str) else _join(_text_values(output, "input_text"))
        call_id = payload.get("call_id")
        return [
            _message(
                "tool",
                content,
                tool_call_id=call_id if isinstance(call_id, str) else None,
                timestamp=timestamp,
            )
        ]
    return []


def normalize(harness, records, fallback_id="session"):
    """STS header and message lines for one session's raw records."""
    out = [_header(harness, records, fallback_id)]
    for record in records:
        if not isinstance(record, dict):
            continue
        timestamp = epoch_ms(record.get("timestamp"))
        event = kind(harness, record)
        if harness == "claude":
            if event == "user":
                out.extend(_claude_user(record, timestamp))
            elif event == "assistant":
                out.extend(_claude_assistant(record, timestamp))
        else:
            payload = record.get("payload")
            if isinstance(payload, dict):
                out.extend(_codex_message(event, payload, timestamp))
    return out
