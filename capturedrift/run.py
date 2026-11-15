"""The experiment: what a parser frozen at a harness's training versions silently misses later.

Every share is a plain ratio and byte counts stay exact. The one tunable threshold is chosen on training
versions only, so no held-out version change is ever scored with a threshold that has seen it.
"""

import json
from pathlib import Path

from . import DATA_DIR, HARNESSES
from .data import Session, load, manifest
from .drift import (
    ALARMS,
    BYTES_GRID,
    CONTENT_MIN,
    changes,
    is_train,
    key_totals,
    known_keys,
    mapped_share,
    score,
    shapes,
    tune_bytes_min,
    unseen,
    versions,
)
from .sts import mapped_keys

HARNESS_KEYS = (
    "sessions",
    "records",
    "versions",
    "train_versions",
    "test_versions",
    "kinds",
    "keys",
    "sts_byte_share",
    "sts_text_share",
    "frozen_new_kinds",
    "frozen_new_keys",
    "frozen_content_keys",
    "frozen_record_share",
    "frozen_byte_share",
    "frozen_text_share",
)
VERSION_KEYS = (
    "version_harness",
    "version_test",
    "version_sessions",
    "version_records",
    "version_shapes",
    "version_keys",
    "version_new_keys",
    "version_content_keys",
    "version_record_share",
    "version_byte_share",
    "version_text_share",
    "version_sts_text_share",
)
ALARM_KEYS = (
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
)


def _round(value):
    """Floats to six decimal places, lists elementwise, everything else untouched."""
    if isinstance(value, list):
        return [_round(item) for item in value]
    return round(value, 6) if isinstance(value, float) else value


def _kinds(sessions: list[Session]) -> set[str]:
    """The record kinds those sessions contain."""
    return {record.kind for session in sessions for record in session.records}


def _harness_row(harness: str, own: list[Session], train: list[Session], test: list[Session], train_keys: set) -> dict:
    """Counts, the STS share over everything, and what the training keys never saw."""
    new_keys = known_keys(test) - train_keys
    test_totals = key_totals(test)
    frozen = unseen(test, train_keys)
    sts = mapped_share(own, mapped_keys(harness))
    return {
        "sessions": len(own),
        "records": sum(len(session.records) for session in own),
        "versions": len({session.version for session in own}),
        "train_versions": len({session.version for session in train}),
        "test_versions": len({session.version for session in test}),
        "kinds": len(_kinds(own)),
        "keys": len(known_keys(own)),
        "sts_byte_share": sts["bytes"],
        "sts_text_share": sts["text"],
        "frozen_new_kinds": len(_kinds(test) - _kinds(train)),
        "frozen_new_keys": len(new_keys),
        "frozen_content_keys": sum(1 for key in new_keys if test_totals[key][1] >= CONTENT_MIN),
        "frozen_record_share": frozen["records"],
        "frozen_byte_share": frozen["bytes"],
        "frozen_text_share": frozen["text"],
    }


def _version_rows(index: int, harness: str, own: list[Session], train_keys: set, found: list) -> list[dict]:
    """One row per version of a harness in version order; training versions have nothing unseen by definition."""
    by_version = {change.version: change for change in found}
    mapped = mapped_keys(harness)
    rows = []
    for _version, group in versions(own):
        change = by_version.get(_version)
        frozen = unseen(group, train_keys)
        rows.append(
            {
                "version_harness": index,
                "version_test": 0 if is_train(group[0]) else 1,
                "version_sessions": len(group),
                "version_records": sum(len(session.records) for session in group),
                "version_shapes": shapes(group),
                "version_keys": len(known_keys(group)),
                "version_new_keys": len(change.new) if change else 0,
                "version_content_keys": len(change.content) if change else 0,
                "version_record_share": frozen["records"],
                "version_byte_share": frozen["bytes"],
                "version_text_share": frozen["text"],
                "version_sts_text_share": mapped_share(group, mapped)["text"],
            }
        )
    return rows


def _alarm_rows(found: list, test_versions: set) -> list[dict]:
    """One row per alarm, scored over the held-out version changes only."""
    held = [change for change in found if change.version in test_versions]
    rows = []
    for alarm in ALARMS:
        result = score(held, alarm)
        rows.append({"alarm_" + name: result[name] for name in ALARM_KEYS})
    return rows


def summarize(sessions: list[Session], files: int, data_bytes: int) -> dict:
    """The experiment's metrics for these sessions; files and data_bytes come from the manifest."""
    by_harness = {harness: [session for session in sessions if session.harness == harness] for harness in HARNESSES}
    trains = [[session for session in by_harness[harness] if is_train(session)] for harness in HARNESSES]
    bytes_min, grid_scores = tune_bytes_min(trains)
    result = {
        "data_files": files,
        "data_bytes": data_bytes,
        "content_min": CONTENT_MIN,
        "bytes_min": bytes_min,
        "bytes_grid": list(BYTES_GRID),
        "train_bytes_f1": list(grid_scores),
    }
    harness_rows, version_rows, alarm_rows = [], [], []
    for index, harness in enumerate(HARNESSES):
        own = by_harness[harness]
        train = [session for session in own if is_train(session)]
        test = [session for session in own if not is_train(session)]
        train_keys = known_keys(train)
        found = changes(own, bytes_min)
        harness_rows.append(_harness_row(harness, own, train, test, train_keys))
        version_rows.extend(_version_rows(index, harness, own, train_keys, found))
        alarm_rows.extend(_alarm_rows(found, {session.version for session in test}))
    for name in HARNESS_KEYS:
        result[name] = [row[name] for row in harness_rows]
    for name in VERSION_KEYS:
        result[name] = [row[name] for row in version_rows]
    for name in ALARM_KEYS:
        result["alarm_" + name] = [row["alarm_" + name] for row in alarm_rows]
    return {name: _round(value) for name, value in result.items()}


def main(data_dir: str | Path = DATA_DIR, out: str | Path = "results/metrics.json") -> dict:
    """Run the experiment on data_dir, write the metrics to out, and return exactly what was written."""
    directory = Path(data_dir)
    entries = manifest(directory)["files"]
    result = summarize(load(directory), len(entries), sum(entry["bytes"] for entry in entries.values()))
    text = json.dumps(result, sort_keys=True, indent=1) + "\n"
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return json.loads(text)
