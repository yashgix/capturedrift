"""Fill the generated blocks of docs/index.html from results/metrics.json and results/metrics-v2.json."""

import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from capturedrift import DATA_DIR, HARNESSES  # noqa: E402
from capturedrift.data import load  # noqa: E402
from demo import LABELS, percent, ratio, replace_block, version_names  # noqa: E402

LOSS_ROWS = (
    ("Frozen at the cutoff, held-out", "frozen"),
    ("STS mapping, held-out", "sts_dropped_held_out"),
    ("STS mapping, all sessions", "sts_dropped"),
)


def loss_range(row) -> str:
    """Not matched to not matched plus approximate copy, as `23.2% to 27.1%`."""
    return f"{percent(row['unique_share'])} to {percent(row['unique_share'] + row['approx_share'])}"


def tiles(v2) -> str:
    cells = [
        (f"{LABELS[harness]} · {label}", loss_range(v2["harness"][harness][name]))
        for label, name in LOSS_ROWS[:2]
        for harness in HARNESSES
    ]
    return "\n".join(
        f'<div class="tile"><span class="big">{value}</span><span class="small muted">{escape(label)}</span></div>'
        for label, value in cells
    )


def loss_table(v2) -> str:
    rows = "".join(
        f"<tr><td>{LABELS[harness]}</td><td>{label}</td>"
        + "".join(
            f'<td class="r">{percent(v2["harness"][harness][name][part + "_share"])}</td>'
            for part in ("exact", "approx", "unique")
        )
        + f'<td class="r">{loss_range(v2["harness"][harness][name])}</td></tr>'
        for harness in HARNESSES
        for label, name in LOSS_ROWS
    )
    return (
        '<table><thead><tr><th>Harness</th><th>Parser and sessions</th><th class="r">Exact copy</th>'
        '<th class="r">Approximate copy</th><th class="r">Not matched</th><th class="r">Loss range</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )


def bar(label: str, share: float, kind: str) -> str:
    return (
        f'<div class="b"><span class="name">{escape(label)}</span>'
        f'<span class="track"><span class="fill {kind}" style="width:{share * 100:.2f}%"></span></span>'
        f'<span class="v"><b>{percent(share)}</b></span></div>'
    )


def bars(v1, sessions) -> str:
    """Held-out bytes unseen and text unseen per version, one block per harness."""
    names = version_names(sessions)
    seen = dict.fromkeys(HARNESSES, 0)
    blocks = {harness: [] for harness in HARNESSES}
    for index, harness_index in enumerate(v1["version_harness"]):
        harness = HARNESSES[harness_index]
        name = names[harness][seen[harness]]
        seen[harness] += 1
        if v1["version_test"][index]:
            blocks[harness].append(bar(f"{name} bytes", v1["version_byte_share"][index], "bytes"))
            blocks[harness].append(bar(f"{name} text", v1["version_text_share"][index], "text"))
    return "\n".join(
        f'<h3>{LABELS[harness]}</h3><div class="bars">{"".join(rows)}</div>' for harness, rows in blocks.items()
    )


def interval(pair) -> str:
    value, (low, high) = pair
    return f"{ratio(value)} ({ratio(low)} to {ratio(high)})"


def alarms(v2) -> str:
    rows = "".join(
        f"<tr><td>{LABELS[harness]}</td><td><code>{alarm}</code></td>"
        f'<td class="r">{row["tp"]} / {row["fp"]} / {row["fn"]}</td>'
        f'<td class="r">{interval(row["precision"])}</td><td class="r">{interval(row["recall"])}</td></tr>'
        for harness in HARNESSES
        for alarm, row in sorted(v2["harness"][harness]["kind_alarms"].items())
    )
    return (
        '<table><thead><tr><th>Harness</th><th>Alarm</th><th class="r">tp / fp / fn</th>'
        '<th class="r">Precision (95%)</th><th class="r">Recall (95%)</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )


def headline(v2) -> str:
    """The README headline: each harness's loss range for the frozen parser and for the STS mapping."""
    return "\n".join(
        f"- {LABELS[harness]}: frozen parser {loss_range(v2['harness'][harness]['frozen'])}, "
        f"STS mapping {loss_range(v2['harness'][harness]['sts_dropped_held_out'])}"
        for harness in HARNESSES
    )


def main():
    v1 = json.loads((ROOT / "results/metrics.json").read_text(encoding="utf-8"))
    v2 = json.loads((ROOT / "results/metrics-v2.json").read_text(encoding="utf-8"))
    page = ROOT / "docs/index.html"
    text = page.read_text(encoding="utf-8")
    blocks = {
        "tiles": tiles(v2),
        "loss": loss_table(v2),
        "bars": bars(v1, load(DATA_DIR)),
        "alarms": alarms(v2),
    }
    for name, block in blocks.items():
        text = replace_block(text, block, name)
    page.write_text(text, encoding="utf-8")
    readme = ROOT / "README.md"
    readme.write_text(replace_block(readme.read_text(encoding="utf-8"), headline(v2), "headline"), encoding="utf-8")


if __name__ == "__main__":
    main()
