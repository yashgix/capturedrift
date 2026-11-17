"""Render the loss block of the README from results/metrics.json and results/metrics-v2.json."""

import argparse
import json
from pathlib import Path

from capturedrift import HARNESSES
from capturedrift.data import version_key
from demo import LABELS, percent, ratio, replace_block, table

CONSERVATION_HEADER = (
    "Harness",
    "Content bytes mapped",
    "Written by normalize",
    "Written / mapped",
    "Reasoning removed (ablation)",
    "Path-based STS bytes",
    "Written content, share of bytes",
)
LOSS_HEADER = ("Harness", "Parser and sessions", "Exact copy", "Approximate copy (heuristic)", "Not matched")
VERSION_HEADER = (
    "Harness",
    "Version",
    "Written / mapped",
    "Reasoning removed",
    "Thinking blocks empty",
    "Keys gone quiet (mapped)",
    "Kinds new to the harness",
    "New keys in user or assistant",
)
ALARM_HEADER = ("Harness", "Alarm", "Kind tp", "fp", "fn", "Precision (95%)", "Recall (95%)")
TOP_HEADER = ("Harness", "Kind", "Not matched text bytes", "Approximate copy bytes", "Exact copy bytes")


def interval(pair) -> str:
    """A share with its Wilson interval, as `0.43 (0.16 to 0.75)`."""
    value, (low, high) = pair
    return f"{ratio(value)} ({ratio(low)} to {ratio(high)})"


def conservation_table(v1, v2) -> str:
    rows = []
    for index, harness in enumerate(HARNESSES):
        sums = {
            key: sum(row[key] for row in v2["harness"][harness]["versions"].values())
            for key in ("source", "emitted", "reasoning", "bytes")
        }
        rows.append(
            (
                LABELS[harness],
                sums["source"],
                sums["emitted"],
                percent(sums["emitted"] / sums["source"]),
                percent((sums["emitted"] - sums["reasoning"]) / sums["source"]),
                percent(v1["sts_byte_share"][index]),
                percent(sums["emitted"] / sums["bytes"]),
            )
        )
    return table(CONSERVATION_HEADER, rows)


def loss_table(v2) -> str:
    rows = []
    for harness in HARNESSES:
        data = v2["harness"][harness]
        for label, name in (
            ("Frozen at the cutoff, held-out", "frozen"),
            ("STS mapping, held-out", "sts_dropped_held_out"),
            ("STS mapping, all sessions", "sts_dropped"),
        ):
            row = data[name]
            cells = (percent(row[part + "_share"]) for part in ("exact", "approx", "unique"))
            rows.append((LABELS[harness], label, *cells))
    return table(LOSS_HEADER, rows)


def retention_table(v2) -> str:
    rows = []
    for harness in HARNESSES:
        shares = v2["harness"][harness]["sts_text_share"]
        rows.append((LABELS[harness], percent(shares["held_out"]), percent(shares["all"])))
    return table(("Harness", "Held-out sessions", "All sessions"), rows)


def version_table(v2) -> str:
    rows = []
    for harness in HARNESSES:
        for version, row in sorted(v2["harness"][harness]["versions"].items(), key=lambda item: version_key(item[0])):
            blocks = f"{row['thinking_empty']} of {row['thinking_blocks']}" if row["thinking_blocks"] else "-"
            rows.append(
                (
                    LABELS[harness],
                    version,
                    percent(row["emitted"] / row["source"]) if row["source"] else "-",
                    percent((row["emitted"] - row["reasoning"]) / row["source"]) if row["source"] else "-",
                    blocks,
                    row["quiet_mapped_keys"],
                    row["new_kinds"],
                    row["new_conversation_keys"],
                )
            )
    return table(VERSION_HEADER, rows)


def alarm_table(v2) -> str:
    rows = []
    for harness in HARNESSES:
        for alarm, row in v2["harness"][harness]["kind_alarms"].items():
            rows.append(
                (
                    LABELS[harness],
                    alarm,
                    row["tp"],
                    row["fp"],
                    row["fn"],
                    interval(row["precision"]),
                    interval(row["recall"]),
                )
            )
    return table(ALARM_HEADER, rows)


def top_table(v2) -> str:
    rows = []
    for harness in HARNESSES:
        kinds = v2["harness"][harness]["sts_dropped"]["kinds"]
        for name, (exact, approx, unique) in sorted(kinds.items(), key=lambda item: (-item[1][2], item[0]))[:5]:
            rows.append((LABELS[harness], name, unique, approx, exact))
    return table(TOP_HEADER, rows)


def render(v1, v2) -> str:
    claude, codex = (v2["harness"][harness] for harness in HARNESSES)
    keys = [data["content_keys"] for data in (claude, codex)]
    return "\n".join(
        [
            "### Loss accounting",
            "",
            "Unread text is shown as shares of that population's text bytes. An exact copy is a string that is also in",
            "content the parser kept. An approximate copy has at least 90% of its line bytes in kept content, a",
            "heuristic that can hide a missing long line. Not matched has no exact or approximate counterpart.",
            "Loss lies between Not matched and Not matched plus Approximate copy.",
            "",
            loss_table(v2),
            "",
            "Path-based STS text share, which the held-out loss rows above are measured against:",
            "",
            retention_table(v2),
            "",
            "#### What the normalizer writes against what its mapping reads",
            "",
            "The path-based STS share counts bytes at mapped keys. This table counts what `normalize` wrote.",
            "Reasoning removed subtracts the reasoning bytes. For Claude Code that equals what an earlier normalizer",
            "wrote when it read thinking text from the wrong field (checked against that code). Empty strings are left",
            "out of both sides.",
            "",
            conservation_table(v1, v2),
            "",
            version_table(v2),
            "",
            "#### Alarms, counted per record kind",
            "",
            "A case is a record kind with new keys in a held-out version. The 95% intervals are Wilson intervals.",
            f"Of the new content keys in held-out versions, {keys[0]['conversation']} of "
            f"{keys[0]['conversation'] + keys[0]['injected']} (Claude Code) and {keys[1]['conversation']} of "
            f"{keys[1]['conversation'] + keys[1]['injected']} (Codex) sit in conversation records, the kinds the",
            "STS mapping reads. The rest are injected records such as attachments and system events.",
            "",
            alarm_table(v2),
            "",
            "#### Biggest unmatched text the normalizer does not write (all sessions)",
            "",
            top_table(v2),
            "",
            f"Claude Code records marked as subagent work (isSidechain): {claude['sidechain_records']} in this data.",
        ]
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readme", default="README.md")
    parser.add_argument("--results", default="results")
    arguments = parser.parse_args(argv)
    results = Path(arguments.results)
    v1 = json.loads((results / "metrics.json").read_text(encoding="utf-8"))
    v2 = json.loads((results / "metrics-v2.json").read_text(encoding="utf-8"))
    readme = Path(arguments.readme)
    readme.write_text(replace_block(readme.read_text(encoding="utf-8"), render(v1, v2), "loss"), encoding="utf-8")


if __name__ == "__main__":
    main()
