"""Drift measurements: what a parser frozen at one CLI version never sees, and how well simple alarms catch it.

Unseen shares compare test sessions against the keys of the training sessions. Content is a new key's text bytes
over its version and every later version. Alarms only get to look at the first session of a version, which is what
a live check would have on the day the version first shows up.
"""

from dataclasses import dataclass

from .data import Session, version_key

CUTOFF = {"claude": "2.1.145", "codex": "0.125.0"}
CONTENT_MIN = 200
ALARMS = ("kind", "any", "bytes")
BYTES_GRID = (1, 32, 200, 1024, 8192)

Key = tuple[str, str]


def is_train(session: Session) -> bool:
    """Whether a session's version is at or before its harness's cutoff; the rest is held out."""
    return version_key(session.version) <= version_key(CUTOFF[session.harness])


def versions(sessions: list[Session]) -> list[tuple[str, list[Session]]]:
    """(version, its sessions) ordered by version_key, sessions kept in input order."""
    grouped: dict[str, list[Session]] = {}
    for session in sessions:
        grouped.setdefault(session.version, []).append(session)
    return sorted(grouped.items(), key=lambda item: version_key(item[0]))


def key_totals(sessions: list[Session]) -> dict[Key, list[int]]:
    """{key: [bytes, text bytes]} summed over every record of every session."""
    totals: dict[Key, list[int]] = {}
    for session in sessions:
        for record in session.records:
            for path, (nbytes, text) in record.leaves.items():
                key = (record.kind, path)
                entry = totals.get(key)
                if entry is None:
                    totals[key] = [nbytes, text]
                else:
                    entry[0] += nbytes
                    entry[1] += text
    return totals


def known_keys(sessions: list[Session]) -> set[Key]:
    """Every key those sessions contain."""
    return set(key_totals(sessions))


def share(part, whole) -> float:
    """part / whole, or 0.0 when whole is 0."""
    return part / whole if whole else 0.0


def unseen(sessions: list[Session], known: set[Key]) -> dict[str, float]:
    """Shares of records with a key outside known, and of all leaf bytes and text bytes at such keys."""
    records = unseen_records = 0
    bytes_total = bytes_unseen = text_total = text_unseen = 0
    for session in sessions:
        for record in session.records:
            records += 1
            outside = False
            for path, (nbytes, text) in record.leaves.items():
                bytes_total += nbytes
                text_total += text
                if (record.kind, path) not in known:
                    outside = True
                    bytes_unseen += nbytes
                    text_unseen += text
            unseen_records += outside
    return {
        "records": share(unseen_records, records),
        "bytes": share(bytes_unseen, bytes_total),
        "text": share(text_unseen, text_total),
    }


def mapped_share(sessions: list[Session], mapped: set[Key]) -> dict[str, float]:
    """Share of bytes and text bytes at keys the normalizer reads."""
    bytes_total = bytes_mapped = text_total = text_mapped = 0
    for session in sessions:
        for record in session.records:
            for path, (nbytes, text) in record.leaves.items():
                bytes_total += nbytes
                text_total += text
                if (record.kind, path) in mapped:
                    bytes_mapped += nbytes
                    text_mapped += text
    return {"bytes": share(bytes_mapped, bytes_total), "text": share(text_mapped, text_total)}


def shapes(sessions: list[Session]) -> int:
    """The number of distinct (kind, leaf-path set) record shapes."""
    return len({(record.kind, frozenset(record.leaves)) for session in sessions for record in session.records})


@dataclass(frozen=True)
class Change:
    """One version change: its new keys, the content-bearing ones, and the keys each alarm flags."""

    version: str
    new: frozenset[Key]
    content: frozenset[Key]
    flags: dict[str, frozenset[Key]]


def changes(sessions: list[Session], bytes_min: int) -> list[Change]:
    """One Change per version after the first, each compared with every earlier version of sessions."""
    grouped = versions(sessions)
    totals = [key_totals(group) for _, group in grouped]
    suffix_text: list[dict[Key, int]] = [{} for _ in grouped]
    running: dict[Key, int] = {}
    for index in range(len(grouped) - 1, -1, -1):
        for key, value in totals[index].items():
            running[key] = running.get(key, 0) + value[1]
        suffix_text[index] = dict(running)
    out: list[Change] = []
    earlier: set[Key] = set()
    earlier_kinds: set[str] = set()
    for index, (version, group) in enumerate(grouped):
        if index:
            first = key_totals([group[0]])
            new = set(totals[index]) - earlier
            out.append(
                Change(
                    version,
                    frozenset(new),
                    frozenset(key for key in new if suffix_text[index].get(key, 0) >= CONTENT_MIN),
                    {
                        "kind": frozenset(key for key in new & set(first) if key[0] not in earlier_kinds),
                        "any": frozenset(new & set(first)),
                        "bytes": frozenset(key for key in new & set(first) if first[key][0] >= bytes_min),
                    },
                )
            )
        earlier.update(totals[index])
        earlier_kinds.update(key[0] for key in totals[index])
    return out


def score(changes: list[Change], alarm: str) -> dict[str, float | int]:
    """Key-level and version-level alarm counts and shares over the held-out changes."""
    key_tp = key_fp = key_fn = 0
    version_tp = version_fp = version_fn = 0
    for change in changes:
        flagged = change.flags[alarm]
        content = change.content
        key_tp += len(flagged & content)
        key_fp += len(flagged - content)
        key_fn += len(content - flagged)
        if flagged and content:
            version_tp += 1
        elif flagged:
            version_fp += 1
        elif content:
            version_fn += 1
    return {
        "key_tp": key_tp,
        "key_fp": key_fp,
        "key_fn": key_fn,
        "key_precision": share(key_tp, key_tp + key_fp),
        "key_recall": share(key_tp, key_tp + key_fn),
        "version_tp": version_tp,
        "version_fp": version_fp,
        "version_fn": version_fn,
        "version_precision": share(version_tp, version_tp + version_fp),
        "version_recall": share(version_tp, version_tp + version_fn),
    }


def f1(score: dict) -> float:
    """Harmonic mean of a score's key precision and recall, 0.0 when both are 0."""
    precision, recall = score["key_precision"], score["key_recall"]
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def tune_bytes_min(trains: list[list[Session]]) -> tuple[int, list[float]]:
    """(best threshold, [bytes-alarm f1 per BYTES_GRID]) on training sessions only, ties to the smaller."""
    scores = []
    for threshold in BYTES_GRID:
        pooled = [change for sessions in trains for change in changes(sessions, threshold)]
        scores.append(f1(score(pooled, "bytes")))
    best = 0
    for index in range(1, len(scores)):
        if scores[index] > scores[best]:
            best = index
    return BYTES_GRID[best], scores


def top_unseen(sessions: list[Session], harness: str, n: int = 10) -> list[tuple[str, str, int, int]]:
    """The harness's test keys unseen in training, as (kind, path, bytes, text), biggest text first."""
    own = [session for session in sessions if session.harness == harness]
    known = known_keys([session for session in own if is_train(session)])
    test = [session for session in own if not is_train(session)]
    rows = [
        (kind, path, value[0], value[1])
        for (kind, path), value in key_totals(test).items()
        if (kind, path) not in known
    ]
    rows.sort(key=lambda row: (-row[3], -row[2], row[0], row[1]))
    return rows[:n]
