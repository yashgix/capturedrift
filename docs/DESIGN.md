# Design

How the measurement works, why each piece is shaped the way it is, and where it is weak.

## Goal

Show, on real multi-version session files, that a parser written against one CLI version keeps running on later
versions while silently ignoring whatever arrives in shapes it has never seen — and quantify that gap in records,
bytes and text bytes, together with what a fixed common schema keeps.

The unit of everything is the **key**: a pair of an event kind and a key path. Two sessions that use the same field
in the same kind of record share a key; a field that only the new CLI version writes has a key the frozen parser
has never seen.

## Records and key paths

Each session file is one JSON object per line. A record is measured by walking it from the root with an empty path:

- **Dict key.** The segment is the key itself when it fully matches `[A-Za-z_][A-Za-z0-9_]*`, otherwise `*` — so
  ids, hashes and version strings used as keys collapse into one segment instead of exploding the key space. The
  child path is `path + "." + segment`, or just the segment at the root.
- **List element.** The child path is `path + "[]" + tag`. The tag is `<t>` when the element is a dict whose
  `type` is a string `t` fully matching `[A-Za-z0-9_.:/-]{1,40}`, `<*>` for any other string `type`, and empty
  otherwise. Content blocks therefore group by their block type, and a `tool_use` block is one shape regardless of
  which tool it names.
- **Empty container.** `path + ":{}"` or `path + ":[]"`, always 2 bytes, because an empty object and an empty
  array really are two bytes of compact JSON.
- **Scalar.** `path + ":" + t`, with `t` in `str`, `num`, `bool` or `null` (booleans are `bool`, never `num`).
- Repeated paths are summed, so a text block that appears three times in one record yields three text blocks'
  worth of bytes at one key.

Sizes and text sizes are compact JSON bytes: `len(json.dumps(v, ensure_ascii=False, separators=(",", ":"))
.encode())`. Not the file's raw bytes, not the escaped form — the value's own compact encoding, so the accounting
adds up and non-ASCII text is counted as the UTF-8 it is.

The event **kind** is the record's `type`, plus the subtype when there is one: Codex joins `payload.type`, Claude
prefers `subtype` and falls back to the type of the child record named after the record's own type (which is how
attachment hooks get their own kind). Anything without a string type is `?`.

## Opaque subtrees

Some subtrees are values, not format: tool arguments, tool schemas, tool results and file-keyed maps. The paths
are

- Claude Code: `message.content[]<tool_use>.input`, `toolUseResult`, `snapshot.trackedFileBackups`.
- Codex: `payload.dynamic_tools`, `payload.tools`, `payload.result`, `payload.changes`,
  `payload.invocation.arguments`.

Each is one leaf, `path:json`, carrying the whole subtree's bytes and its nested text bytes. The reason is
mechanical: a tool's argument object is written by a tool, so its keys would otherwise flood the key space with
per-tool noise and drown the format signal the experiment is about. The bytes still count, so nothing disappears
from the totals.

## The text rule

A string counts as text when it has at least three whitespace-separated words. Text bytes are the compact JSON
bytes of every such string found in dict values and list items, recursively; dict keys never count. Three words
skips ids, enum-ish labels, model names, paths and short status strings, which is what we want: the interesting
question is whether *prose and tool output* survive, not whether a one-word field did. It is a heuristic, and the
report says so.

## The frozen parser

The parser stands still at a cutoff: Claude Code 2.1.145 and Codex 0.125.0. Training sessions are those whose
version is numerically at or before the cutoff, compared as tuples of integers extracted from the version string
(`0.147.0-alpha.1.2` → `(0, 147, 0, 1, 2)`) so `2.1.9` sorts before `2.1.10`. Everything after the cutoff is
held out.

The training sessions define the set of keys the frozen parser knows. Anything a held-out session puts outside
that set is invisible to it, and the frozen shares report how much of the held-out records, bytes and text that
is.

## Rolling held-out changes

Per-version shares alone cannot answer "would a check have noticed?", because the parser keeps moving: after each
version it has been taught the version's keys. So changes are computed **rolling**: for each version after a
harness's first, in version order,

- `new` is the set of keys that version's sessions contain and no earlier version contains;
- `content` is the subset of `new` whose text bytes over that version *and every later version in the run* reach
  200. That is the ground truth: a field that arrives and then carries real text for a while, which a frozen
  parser would have been dropping.

The window over later versions matters. A key that appears once and dies is noise; a key whose text arrives one
version after the key itself appears is content, and it is counted as content on the version that introduced it,
which is exactly the version a live check would have flagged.

## Alarms

An alarm may look only at the **first session** of the version, in input order — that is what a live check has on
the day the version first shows up, before the second session of the day exists. Three alarms, all key-level:

| Alarm | Flags | What it models |
|---|---|---|
| `kind` | new keys in that first session whose kind no earlier version has | an "unknown event type" check |
| `any` | every new key in that first session | an "unknown field anywhere" check |
| `bytes` | new keys whose bytes in that first session reach `bytes_min` | the same, with a noise floor |

Scoring is against `content`: key-level true/false positives and false negatives give key precision and recall,
and per change "any flag" versus "any content" gives version precision and recall. Zero denominators give 0.0
rather than an exception, and F1 is 0.0 when both precision and recall are 0.

This design has a built-in ceiling on recall: a content key that only ever appears in a version's second session
cannot be flagged by an alarm that sees only the first. That is not a defect, it is the honest constraint the
comparison encodes — and it is why `any` is reported alongside the other two rather than being replaced by a
stronger detector tuned with hindsight.

## Threshold tuning

`bytes` has one knob, and it is chosen on a grid of 1, 32, 200, 1024 and 8192 bytes, pooling the changes of every
harness's **training-period** sessions into a single key-level F1. Ties go to the smaller threshold, because a
smaller threshold flags more and a tie then costs nothing in precision. Held-out versions never touch the choice:
the threshold that scores the held-out changes was picked without them.

With small training sets the grid is coarse and the winner is often the smallest value; that is reported as it
falls, not smoothed away.

## The STS normalizer

The normalizer is a fixed table per harness and kind: the only paths it reads are listed in `MAPPED`, and every
other leaf is dropped. It emits a session header and message envelopes whose fields appear in a fixed order —
`role`, `content`, then only the applicable ones of `reasoningContent`, `toolCalls`, `toolCallId`, `model`,
`timestamp`.

- **Claude Code user.** Each `tool_result` block becomes a `tool` message, in order, with its string content or
  its text blocks joined and the block's `tool_use_id` as `toolCallId`; a plain string content becomes one `user`
  message, and text blocks are joined into one.
- **Claude Code assistant.** One message when there is any text, thinking or tool_use block: text blocks joined as
  `content` (possibly empty), thinking joined as `reasoningContent`, tool_use blocks as `{id, function: {name,
  arguments}}` with `arguments` the compact JSON of `input` (`{}` when missing), and the model when it is a
  string.
- **Codex.** Messages, reasoning summaries, function and custom tool calls, and their outputs; developer and
  system roles collapse to `system`, outputs become `tool` messages, and everything else is skipped.

Text is joined with `"\n"`. Timestamps become exact epoch milliseconds: parse with `datetime.fromisoformat`, treat
a naive time as UTC, subtract the epoch and floor-divide by one millisecond. Unparseable or absent timestamps are
omitted, not faked.

The normalizer's share is reported two ways, bytes and text, over all of a harness's sessions, both against the
same denominator as the frozen shares. That is what makes the comparison fair: the same byte ruler measures the
loss and the retention.

## Determinism

Every ordering is explicit: sessions by harness, version tuple, start time and name; versions by version tuple;
top unseen keys by text bytes, bytes, kind and path. Metrics are written with sorted keys, indent 1 and a
final newline, and floats are rounded to six places, so two runs produce byte-identical output. No randomness, no
network, no clock.

## Structure only

The experiment, the `audit` command and the README carry paths and counts. They read session text to size it but
never write it anywhere except the metrics' numbers. Only `normalize` writes session text, to a path the user
chooses.

## Trade-offs

- **Key-paths over JSON Schema.** Diffs of full schemas would be finer — value types on every nesting level,
  unions across list items — but they would be unreadable as a table and much more sensitive to a single odd
  record. Key paths are coarse, stable, and enough to answer the question.
- **Two sessions per version.** More data would tighten every share; the selection rule caps files per version to
  keep the repository small and the comparison paired. The cost is that a single unusual session can move a
  version's numbers a lot.
- **First-session alarms.** Deliberate, as above: it models the live check, at the price of built-in false
  negatives.
- **Version and source are confounded.** Most versions come from different datasets and setups, so a new key can
  be a format change or a feature first used by that user. Both hurt a frozen importer, and this design cannot
  separate them.
- **Heuristics.** The three-word text rule and the 200-byte content floor are choices, not truths; opaque
  subtrees count their text but not their internal structure; duplicated content elsewhere in a record makes
  "dropped" an upper bound.
- **A mapping written after the fact.** The STS table was authored with all versions in view, so its share is a best
  case for a fixed mapping, not an estimate of what a mapping written in 2.1.145 would have kept.
