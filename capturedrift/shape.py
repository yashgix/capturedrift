"""Record shapes: sizes, event kinds and key paths."""

import json
import re

OPAQUE = {
    "claude": (
        "message.content[]<tool_use>.input",
        "toolUseResult",
        "snapshot.trackedFileBackups",
    ),
    "codex": (
        "payload.dynamic_tools",
        "payload.tools",
        "payload.result",
        "payload.changes",
        "payload.invocation.arguments",
    ),
}

_FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TAG = re.compile(r"[A-Za-z0-9_.:/-]{1,40}")
_OPAQUE = {harness: frozenset(paths) for harness, paths in OPAQUE.items()}


def size(value):
    """Bytes of value as compact JSON, without ASCII escaping."""
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def is_text(value):
    """A string with at least three whitespace-separated words."""
    return isinstance(value, str) and len(value.split()) >= 3


def text_size(value):
    """Bytes of every is_text string inside value, recursing through values and items only."""
    if isinstance(value, str):
        return size(value) if is_text(value) else 0
    if isinstance(value, dict):
        return sum(text_size(item) for item in value.values())
    if isinstance(value, list):
        return sum(text_size(item) for item in value)
    return 0


def kind(harness, record):
    """The record's event kind, or '?' when its type is not a string."""
    if not isinstance(record, dict):
        return "?"
    name = record.get("type")
    if not isinstance(name, str):
        return "?"
    if harness == "codex":
        payload = record.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("type"), str):
            return f"{name}/{payload['type']}"
        return name
    if harness == "claude":
        subtype = record.get("subtype")
        if isinstance(subtype, str):
            return f"{name}/{subtype}"
        inner = record.get(name)
        if isinstance(inner, dict) and isinstance(inner.get("type"), str):
            return f"{name}/{inner['type']}"
    return name


def leaves(harness, record):
    """{key path: (bytes, text bytes)} for every leaf in record, summing repeated paths."""
    out = {}
    _walk(record, "", _OPAQUE.get(harness, frozenset()), out)
    return out


def _walk(value, path, opaque, out):
    if path in opaque:
        _add(out, path + ":json", size(value), text_size(value))
        return
    if isinstance(value, dict):
        if not value:
            _add(out, path + ":{}", 2, 0)
            return
        for key, child in value.items():
            segment = key if _FIELD.fullmatch(key) else "*"
            child_path = path + "." + segment if path else segment
            _walk(child, child_path, opaque, out)
        return
    if isinstance(value, list):
        if not value:
            _add(out, path + ":[]", 2, 0)
            return
        for item in value:
            _walk(item, path + "[]" + _tag(item), opaque, out)
        return
    if isinstance(value, bool):
        leaf = "bool"
    elif isinstance(value, (int, float)):
        leaf = "num"
    elif isinstance(value, str):
        leaf = "str"
    elif value is None:
        leaf = "null"
    else:
        leaf = "?"
    n = size(value)
    _add(out, path + ":" + leaf, n, n if is_text(value) else 0)


def _tag(value):
    if isinstance(value, dict) and isinstance(value.get("type"), str):
        name = value["type"]
        return f"<{name}>" if _TAG.fullmatch(name) else "<*>"
    return ""


def _add(out, path, nbytes, text):
    old = out.get(path)
    out[path] = (nbytes, text) if old is None else (old[0] + nbytes, old[1] + text)
