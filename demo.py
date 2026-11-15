"""Render the README results block from the experiment's metrics.

With no arguments this prints one summary line from results/metrics.json. With --readme it writes the whole README,
replacing only the region between the results markers with tables built from the metrics and the pinned data.
"""

import argparse
import json
from pathlib import Path

from capturedrift import DATA_DIR, HARNESSES
from capturedrift.data import Session, load
from capturedrift.drift import ALARMS, CUTOFF, top_unseen, versions

LABELS = {"claude": "Claude Code", "codex": "Codex"}
HARNESS_HEADER = (
    "Harness",
    "Cutoff",
    "Sessions",
    "Versions (train)",
    "Versions (test)",
    "Records unseen",
    "Bytes unseen",
    "Text unseen",
    "New keys",
    "New content keys",
    "STS text (all sessions)",
)
VERSION_HEADER = (
    "Harness",
    "Version",
    "Period",
    "Sessions",
    "Records",
    "Shapes",
    "Keys",
    "New keys",
    "Content keys",
    "Records unseen",
    "Bytes unseen",
    "Text unseen",
    "STS text",
)
ALARM_HEADER = (
    "Harness",
    "Alarm",
    "Key precision",
    "Key recall",
    "Key tp",
    "Key fp",
    "Key fn",
    "Version precision",
    "Version recall",
)
UNSEEN_HEADER = ("Harness", "Kind", "Key", "Bytes", "Text bytes")


def percent(value):
    """A share as a percent with one decimal."""
    return f"{value * 100:.1f}%"


def ratio(value):
    """A precision or recall with two decimals."""
    return f"{value:.2f}"


def table(header, rows):
    """A Markdown table with a separator row of --- cells."""
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def version_names(sessions: list[Session]) -> dict[str, list[str]]:
    """{harness: [version, ...]} in numeric version order."""
    return {
        harness: [name for name, _ in versions([item for item in sessions if item.harness == harness])]
        for harness in HARNESSES
    }


def harness_table(metrics):
    """One row per harness: cutoff, counts, the frozen shares, new keys and the STS text share."""
    rows = [
        [
            LABELS[harness],
            CUTOFF[harness],
            metrics["sessions"][index],
            metrics["train_versions"][index],
            metrics["test_versions"][index],
            percent(metrics["frozen_record_share"][index]),
            percent(metrics["frozen_byte_share"][index]),
            percent(metrics["frozen_text_share"][index]),
            metrics["frozen_new_keys"][index],
            metrics["frozen_content_keys"][index],
            percent(metrics["sts_text_share"][index]),
        ]
        for index, harness in enumerate(HARNESSES)
    ]
    return table(HARNESS_HEADER, rows)


def version_table(metrics, names):
    """One row per version, harness order then version order, each with its recorded version name."""
    seen = dict.fromkeys(HARNESSES, 0)
    rows = []
    for index, harness_index in enumerate(metrics["version_harness"]):
        harness = HARNESSES[harness_index]
        name = names[harness][seen[harness]]
        seen[harness] += 1
        rows.append(
            [
                LABELS[harness],
                name,
                "test" if metrics["version_test"][index] else "train",
                metrics["version_sessions"][index],
                metrics["version_records"][index],
                metrics["version_shapes"][index],
                metrics["version_keys"][index],
                metrics["version_new_keys"][index],
                metrics["version_content_keys"][index],
                percent(metrics["version_record_share"][index]),
                percent(metrics["version_byte_share"][index]),
                percent(metrics["version_text_share"][index]),
                percent(metrics["version_sts_text_share"][index]),
            ]
        )
    return table(VERSION_HEADER, rows)


def alarm_table(metrics):
    """One row per harness and alarm: key precision and recall with the counts, then version precision and recall."""
    rows = []
    for index, harness in enumerate(HARNESSES):
        for offset, alarm in enumerate(ALARMS):
            at = index * len(ALARMS) + offset
            rows.append(
                [
                    LABELS[harness],
                    alarm,
                    ratio(metrics["alarm_key_precision"][at]),
                    ratio(metrics["alarm_key_recall"][at]),
                    metrics["alarm_key_tp"][at],
                    metrics["alarm_key_fp"][at],
                    metrics["alarm_key_fn"][at],
                    ratio(metrics["alarm_version_precision"][at]),
                    ratio(metrics["alarm_version_recall"][at]),
                ]
            )
    return table(ALARM_HEADER, rows)


def unseen_table(sessions: list[Session]):
    """The biggest keys each harness's test sessions add, as a table."""
    rows = [
        [LABELS[harness], kind, f"`{path}`", nbytes, text]
        for harness in HARNESSES
        for kind, path, nbytes, text in top_unseen(sessions, harness)
    ]
    return table(UNSEEN_HEADER, rows)


def render(metrics, sessions: list[Session]) -> str:
    """The results block: per-harness, per-version and alarm tables, then the top unseen keys."""
    names = version_names(sessions)
    return "\n".join(
        [
            "### Results",
            "",
            "A parser frozen at each harness's cutoff, measured on the versions that came after it. Shares are over",
            "the held-out (test) sessions; `unseen` means a key that no training session contains.",
            "",
            "#### Per harness",
            "",
            harness_table(metrics),
            "",
            "#### Per version",
            "",
            version_table(metrics, names),
            "",
            "#### Alarms on the held-out version changes",
            "",
            alarm_table(metrics),
            "",
            "#### Biggest keys the test sessions add",
            "",
            unseen_table(sessions),
        ]
    )


def replace_block(text: str, block: str, marker: str = "results") -> str:
    """text with the region between the <!-- marker:start --> and <!-- marker:end --> lines replaced by block."""
    first, last = f"<!-- {marker}:start -->", f"<!-- {marker}:end -->"
    start = text.find(first)
    end = text.find(last)
    if start < 0 or end < 0 or end < start:
        raise ValueError(f"the README needs {first} before {last}")
    head = text[: start + len(first)]
    return head + "\n" + block.strip("\n") + "\n" + text[end:]


def summary(metrics) -> str:
    """One line: files, records, and each harness's unseen text share and STS text share."""
    parts = [f"{metrics['data_files']} sessions, {sum(metrics['records'])} records"]
    parts.extend(
        f"{LABELS[harness]}: {percent(metrics['frozen_text_share'][index])} of held-out text unseen, "
        f"STS keeps {percent(metrics['sts_text_share'][index])}"
        for index, harness in enumerate(HARNESSES)
    )
    return " | ".join(parts)


def parse_args(argv=None):
    """The README template, the output path, and where the metrics and data live."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readme", help="template holding the results markers")
    parser.add_argument("--out", help="where to write the rendered README (default: the template)")
    parser.add_argument("--results", default="results", help="directory holding metrics.json")
    parser.add_argument("--data", default=str(DATA_DIR), help="data directory holding MANIFEST.json")
    return parser.parse_args(argv)


def main(argv=None):
    """Print the headline line, or fill the README's results block from the metrics and the data."""
    arguments = parse_args(argv)
    metrics = json.loads((Path(arguments.results) / "metrics.json").read_text(encoding="utf-8"))
    if arguments.readme is None:
        print(summary(metrics))
        return
    sessions = load(arguments.data)
    template = Path(arguments.readme).read_text(encoding="utf-8")
    path = Path(arguments.out or arguments.readme)
    path.write_text(replace_block(template, render(metrics, sessions)), encoding="utf-8")


if __name__ == "__main__":
    main()
