"""Loss accounting beyond key shapes: what the normalizer writes, what is only a copy, and what goes quiet.

Everything here is structure and byte counts. Text is only ever compared in memory, never stored or printed.
"""

import argparse
import json
import re
from math import sqrt
from pathlib import Path

from . import DATA_DIR, HARNESSES
from .data import Session, load, read_records
from .drift import (
    CONTENT_MIN,
    Key,
    changes,
    is_train,
    key_totals,
    known_keys,
    mapped_share,
    share,
    tune_bytes_min,
    versions,
)
from .shape import is_text, kind, leaf_values, size
from .sts import mapped_keys, normalize

PAYLOAD = (".text:str", ".thinking:str", "content:str", ".input:json", ".arguments:str", ".input:str", ".output:str")
LINE_NUMBER = re.compile(r"^\s*\d+[→\t]")
COPY_COVERAGE = 0.9
EXACT, APPROX, UNIQUE = range(3)


def load_raw(data_dir=DATA_DIR) -> list[tuple[Session, list[dict]]]:
    """Every session with its raw records, in the order of data.load."""
    return [(session, read_records(Path(data_dir) / session.name)) for session in load(data_dir)]


def payload_bytes(harness: str, records: list[dict], mapped: set[Key]) -> int:
    """Bytes of non-empty content (text, thinking, tool arguments and results) at mapped keys."""
    return sum(
        size(value)
        for record in records
        for path, value in leaf_values(harness, record)
        if path.endswith(PAYLOAD) and value != "" and (kind(harness, record), path) in mapped
    )


def emitted_bytes(harness: str, lines: list[dict]) -> dict[str, int]:
    """Non-empty content bytes normalize wrote, in the units of payload_bytes, and the reasoning part of them."""
    total = reasoning = 0
    for line in lines[1:]:
        message = line["message"]
        total += size(message["content"]) if message["content"] else 0
        thoughts = message.get("reasoningContent")
        reasoning += size(thoughts) if thoughts else 0
        for call in message.get("toolCalls", ()):
            arguments = call["function"]["arguments"]
            if arguments:
                total += size(arguments) if harness == "codex" else len(arguments.encode())
    return {"emitted": total + reasoning, "reasoning": reasoning}


def conservation(harness: str, group: list[tuple[Session, list[dict]]]) -> dict[str, int]:
    """Mapped content bytes in the raw data against the content bytes normalize wrote for these sessions."""
    mapped = mapped_keys(harness)
    out = {"source": 0, "emitted": 0, "reasoning": 0, "bytes": 0}
    for session, records in group:
        out["source"] += payload_bytes(harness, records, mapped)
        out["bytes"] += sum(nbytes for record in session.records for nbytes, _ in record.leaves.values())
        for name, value in emitted_bytes(harness, normalize(harness, records)).items():
            out[name] += value
    return out


def _strings(value):
    """Every string inside value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _lines(text: str) -> list[str]:
    return [LINE_NUMBER.sub("", line).strip() for line in text.splitlines() if line.strip()]


class Captured:
    """The strings a parser did keep, for telling a copy of kept content from content it does not have."""

    def __init__(self, values):
        self.whole = set()
        self.lines = set()
        for text in values:
            self.whole.add(text)
            self.lines.update(_lines(text))

    def match(self, text: str) -> int:
        """EXACT when text was kept verbatim, APPROX when 90% of its line bytes were (a heuristic), else UNIQUE."""
        if text in self.whole:
            return EXACT
        lines = _lines(text)
        kept = sum(len(line) for line in lines if line in self.lines)
        return APPROX if lines and share(kept, sum(len(line) for line in lines)) >= COPY_COVERAGE else UNIQUE


def split_loss(records: list[dict], harness: str, kept: set[Key]) -> dict[tuple[str, str], list[int]]:
    """{(kind, path): [exact, approximate, unmatched text bytes]} at keys outside kept, for one session."""
    leaves = [
        (kind(harness, record), path, value) for record in records for path, value in leaf_values(harness, record)
    ]
    captured = Captured(text for name, path, value in leaves if (name, path) in kept for text in _strings(value))
    out: dict[tuple[str, str], list[int]] = {}
    for name, path, value in leaves:
        if (name, path) in kept:
            continue
        for text in filter(is_text, _strings(value)):
            out.setdefault((name, path), [0, 0, 0])[captured.match(text)] += size(text)
    return out


def loss_split(raw, harness: str, kept: set[Key]) -> dict[str, list[int]]:
    """{kind: [exact, approximate, unmatched text bytes]} at keys outside kept, summed over raw sessions."""
    per_kind: dict[str, list[int]] = {}
    for _, records in raw:
        for (name, _), amounts in split_loss(records, harness, kept).items():
            entry = per_kind.setdefault(name, [0, 0, 0])
            for index, amount in enumerate(amounts):
                entry[index] += amount
    return per_kind


def thinking_blocks(records: list[dict]) -> tuple[int, int]:
    """(thinking blocks, those whose thinking text is empty) in Claude records."""
    blocks = [
        block
        for record in records
        if isinstance(record.get("message"), dict) and isinstance(record["message"].get("content"), list)
        for block in record["message"]["content"]
        if isinstance(block, dict) and block.get("type") == "thinking"
    ]
    return len(blocks), sum(1 for block in blocks if not block.get("thinking"))


def sidechain_records(records: list[dict]) -> int:
    """Records a Claude subagent wrote (isSidechain true); STS has no field to mark them."""
    return sum(1 for record in records if record.get("isSidechain") is True)


def went_quiet(sessions: list[Session], harness: str) -> dict[str, list[Key]]:
    """Per version, keys that carried text in the version before and carry none now though their kind still occurs."""
    out: dict[str, list[Key]] = {}
    previous: dict[Key, list[int]] = {}
    for version, group in versions(sessions):
        totals = key_totals(group)
        kinds = {name for name, _ in totals}
        out[version] = sorted(
            key
            for key, (_, text) in previous.items()
            if text >= CONTENT_MIN and key[0] in kinds and totals.get(key, (0, 0))[1] == 0
        )
        previous = totals
    return out


def new_kinds(sessions: list[Session]) -> dict[str, int]:
    """Per version, how many record kinds no earlier version has; 0 for the first version."""
    seen: set[str] = set()
    out = {}
    for version, group in versions(sessions):
        kinds = {record.kind for session in group for record in session.records}
        out[version] = len(kinds - seen) if seen else 0
        seen |= kinds
    return out


def wilson(hits: int, total: int, z: float = 1.96) -> list[float]:
    """Wilson 95% interval for hits out of total; [0, 1] when total is 0."""
    if not total:
        return [0.0, 1.0]
    p = hits / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [round(max(0.0, centre - half), 6), round(min(1.0, centre + half), 6)]


def kind_scores(found: list, held: set[str], conversation: set[str]) -> dict:
    """Per alarm, kind-level counts over held-out changes: a (version, kind) with new keys is one case."""
    out = {}
    for alarm in ("kind", "any", "bytes"):
        tp = fp = fn = 0
        for change in found:
            if change.version not in held:
                continue
            truth = {name for name, _ in change.content}
            flagged = {name for name, _ in change.flags[alarm]}
            tp, fp, fn = tp + len(truth & flagged), fp + len(flagged - truth), fn + len(truth - flagged)
        out[alarm] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": [round(share(tp, tp + fp), 6), wilson(tp, tp + fp)],
            "recall": [round(share(tp, tp + fn), 6), wilson(tp, tp + fn)],
        }
    held_content = [key for change in found if change.version in held for key in change.content]
    out["content_keys"] = {
        "conversation": sum(1 for name, _ in held_content if name in conversation),
        "injected": sum(1 for name, _ in held_content if name not in conversation),
    }
    out["new_conversation_keys"] = {
        change.version: sum(1 for name, _ in change.new if name in conversation) for change in found
    }
    return out


def _text_total(sessions: list[Session]) -> int:
    return sum(text for _, text in key_totals(sessions).values())


def _loss_row(raw, harness: str, kept: set[Key], total: int) -> dict:
    """Exact, approximate and unmatched text bytes outside kept, with their shares of total text bytes."""
    kinds = loss_split(raw, harness, kept)
    out = {"kinds": kinds}
    for index, name in enumerate(("exact", "approx", "unique")):
        out[name] = sum(entry[index] for entry in kinds.values())
        out[name + "_share"] = round(share(out[name], total), 6)
    return out


def _version_row(harness: str, group: list[tuple[Session, list[dict]]], quiet: list[Key], new: dict) -> dict:
    """Conservation, thinking, quiet-key and new-kind counts for one version."""
    sessions = [session for session, _ in group]
    records = [record for _, raw in group for record in raw]
    blocks, empty = thinking_blocks(records) if harness == "claude" else (0, 0)
    mapped = mapped_keys(harness)
    return {
        **conservation(harness, group),
        "thinking_blocks": blocks,
        "thinking_empty": empty,
        "quiet_keys": len(quiet),
        "quiet_mapped_keys": sum(1 for key in quiet if key in mapped),
        "sessions": len(sessions),
    } | new


def summarize_loss(raw: list[tuple[Session, list[dict]]], bytes_min: int) -> dict:
    """The loss metrics, per harness: frozen-parser and STS loss split into copy and unique, plus per version rows."""
    out = {"bytes_min": bytes_min, "harness": {}}
    for harness in HARNESSES:
        own = [(session, records) for session, records in raw if session.harness == harness]
        sessions = [session for session, _ in own]
        test = [(session, records) for session, records in own if not is_train(session)]
        train_keys = known_keys([session for session in sessions if is_train(session)])
        found = changes(sessions, bytes_min)
        conversation = {name for name, _ in mapped_keys(harness)}
        quiet = went_quiet(sessions, harness)
        fresh = new_kinds(sessions)
        scores = kind_scores(found, {session.version for session, _ in test}, conversation)
        rows = {}
        for version, _ in versions(sessions):
            members = [(s, r) for s, r in own if s.version == version]
            new = {
                "new_kinds": fresh[version],
                "new_conversation_keys": scores["new_conversation_keys"].get(version, 0),
            }
            rows[version] = _version_row(harness, members, quiet[version], new)
        out["harness"][harness] = {
            "frozen": _loss_row(test, harness, train_keys, _text_total([s for s, _ in test])),
            "sts_dropped": _loss_row(own, harness, mapped_keys(harness), _text_total(sessions)),
            "sts_dropped_held_out": _loss_row(test, harness, mapped_keys(harness), _text_total([s for s, _ in test])),
            "sts_text_share": {
                "all": round(mapped_share(sessions, mapped_keys(harness))["text"], 6),
                "held_out": round(mapped_share([s for s, _ in test], mapped_keys(harness))["text"], 6),
            },
            "sidechain_records": sum(sidechain_records(records) for _, records in own),
            "kind_alarms": {alarm: scores[alarm] for alarm in ("kind", "any", "bytes")},
            "content_keys": scores["content_keys"],
            "versions": rows,
        }
    return out


def main(data_dir=DATA_DIR, out="results/metrics-v2.json") -> dict:
    """Run the loss accounting on data_dir and write it to out as sorted, indented JSON."""
    trains = [[s for s in load(data_dir) if s.harness == harness and is_train(s)] for harness in HARNESSES]
    result = summarize_loss(load_raw(data_dir), tune_bytes_min(trains)[0])
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Loss accounting for the pinned session data.")
    parser.add_argument("--out", default="results/metrics-v2.json")
    main(out=parser.parse_args().out)
