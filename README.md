# capturedrift

Detects silent data loss when coding-agent session logs from many Claude Code and Codex versions are captured into
a standard trace schema. Write-up with charts: https://yashgix.github.io/capturedrift/

An importer written against one CLI version keeps running on later versions, and it stops recognising whatever
arrives in shapes it has never seen. Nothing fails: no exception, no dropped-file warning, no log line. The unknown
keys are simply never read. capturedrift puts a number on that, on real public Claude Code and Codex session files
(from public Hugging Face datasets, redacted) that span 22 and 4 CLI versions.

**Main result.** For Codex, a parser frozen at its training version leaves 23.2% to 27.1% of the text in held-out
sessions unread and not found elsewhere in what it kept. For Claude Code the same range is 0.3% to 0.4%, and a fixed
Hugging Face STS mapping misses 10.8% to 32.4% of Claude's held-out text and 11.7% to 15.8% of Codex's. The range
runs from "not matched" to "not matched plus approximate copy", because the approximate-copy match is a heuristic.
The three simple alarms are noisy: precision is low and the 95% intervals are wide (tables below). The data is small
(40 sessions, five of them Codex), so these numbers illustrate a method and do not estimate a population.

```text
$ python -m capturedrift audit --harness codex data/sessions/codex/<dataset>/<rollout>.jsonl
{"keys": 166, "kinds": 18, "records": 2046, "sessions": 1, "sts_byte_share": 0.635644,
 "sts_text_share": 0.795578, "versions": ["0.140.0-alpha.2"]}
```

(`audit` prints the real output as indented JSON, shown on one line here. It never prints session text.)

## The question

A capture product stores raw sessions first and normalizes them later, so the raw log is safe. The importer in
front of it is not: it encodes one version's field layout, and later versions keep the old fields while adding new
ones. This milestone measures, version by version, the gap between what the raw session contains and what such a
frozen parser can see. It is a measurement, not a claim about any particular product's code.

## What this measures

1. **Frozen-parser loss.** How much of the held-out (post-cutoff) content sits in record shapes that no training
   session contains: records, bytes and text bytes, per harness and per version.
2. **What a fixed common schema keeps.** A fixed normalizer into Hugging Face's
   [Session Traces Simple Format](https://huggingface.co/docs/hub/session-traces-format) — the session header,
   the message envelope and `role`, `content`, `reasoningContent`, `toolCalls`, `toolCallId`, `timestamp` (epoch
   ms) and `model` — with exact byte accounting, so the share of bytes and text the mapping reads is a number and
   not an impression.
3. **How well three simple alarms work.** `kind` (a record kind no earlier version had), `any` (any new key in
   the version's first session) and `bytes` (new keys over a size threshold), scored against the new keys that
   actually carry text content on held-out version changes. The one tunable threshold is chosen on training-period
   version changes only.

4. **Loss accounting (version 2).** Which unread text is only a copy of content the parser kept and which is
   not matched at all, what `normalize` actually writes against what its mapping reads, which known keys go quiet, and
   the alarms counted per record kind with intervals. See `SPEC-v2.md`.

Everything is deterministic and needs neither network nor model calls.

## Data

The repository ships the pinned data; nothing is downloaded at test or run time.

- `data/sessions/<harness>/<owner>__<dataset>/<file>.jsonl` — 40 raw session files, 35 Claude Code and 5 Codex,
  from 12 public, ungated Hugging Face datasets at fixed commits: **40 files, 56,092,812 bytes**, 15,838 Claude
  Code records over 22 versions (2.1.114 to 2.1.220) and 3,229 Codex records over 4 versions (0.125.0 to
  0.147.0-alpha.1.2).
- `data/MANIFEST.json` — provenance for every file: harness, version, source dataset, upstream path and sha256,
  released sha256 and bytes, and per-rule redaction counts.
- `data/licenses/` and `data/sources/` — each dataset's license text and its card at the pinned commit.

`python tools/fetch_data.py` restores any missing file from the pinned revision and re-checks every sha256;
`python tools/fetch_data.py --verify` (or `make data-check`) checks the local copies only, without network.

### Selection rule

Raw Claude Code and Codex session files only — no converted, synthetic or re-wrapped exports, and no gated
datasets. Per (harness, CLI version as recorded inside the file), the two sessions with the earliest first
timestamp among files of at most 8 MB, ties broken by dataset then path. Copies of the same Fable 5 material use
one original upload.

### Redaction

`tools/fetch_data.py` replaced home-directory user names, email addresses and token-shaped strings in the
upstream bytes, and credential-shaped text (API keys, `NAME_TOKEN=value` and the like) inside each line's decoded
strings, re-encoding only the lines it changed. Dataset cards got the same credential pass. JSON structure is
unchanged, and the per-rule counts are in the manifest. Some upstream datasets had already been anonymized by
whoever published them; the data here is what was published, once redacted as above.

## Running it

```bash
make test         # unittest suite, own and acceptance tests (Python 3.14, no dependencies)
make lint         # ruff check and format check
make data-check   # verify the pinned files against data/MANIFEST.json, no network
make experiment   # rerun the v1 experiment into results/metrics.json
make loss         # rerun the v2 loss accounting into results/metrics-v2.json
make readme       # re-render the two generated result blocks below
make page         # re-render the generated blocks of docs/index.html
python demo.py    # one-line summary of the metrics
```

Both reruns reproduce `results/` and the generated README blocks byte for byte. `python experiment.py --out PATH [--data DIR]` writes the metrics as JSON with sorted keys, indent 1 and a final
newline. Two runs produce byte-identical files.

## Command line

```bash
python -m capturedrift audit --harness claude data/sessions/claude/.../session.jsonl
python -m capturedrift normalize --harness codex data/sessions/codex/.../rollout.jsonl out.sts.jsonl
```

`audit` prints structure-only JSON: session count, record count, the versions it saw, how many distinct kinds and
keys they hold, and the byte and text shares the STS mapping reads. It never prints session text.

`normalize` writes the STS lines for one session file, one JSON object per line, to the path you name — this is
the only command that writes session text, and only where you point it. The line count goes to stderr.

## Findings

The block below is generated by `python demo.py --readme README.md --out README.md` from `results/metrics.json`
and the pinned data. No number in it is typed by hand.

<!-- results:start -->
### Results

A parser frozen at each harness's cutoff, measured on the versions that came after it. Shares are over
the held-out (test) sessions; `unseen` means a key that no training session contains.

#### Per harness

| Harness | Cutoff | Sessions | Versions (train) | Versions (test) | Records unseen | Bytes unseen | Text unseen | New keys | New content keys | STS text (all sessions) |
|---|---|---|---|---|---|---|---|---|---|---|
| Claude Code | 2.1.145 | 35 | 7 | 15 | 15.1% | 7.6% | 0.4% | 150 | 6 | 44.1% |
| Codex | 0.125.0 | 5 | 1 | 3 | 33.7% | 65.2% | 29.4% | 151 | 18 | 79.5% |

#### Per version

| Harness | Version | Period | Sessions | Records | Shapes | Keys | New keys | Content keys | Records unseen | Bytes unseen | Text unseen | STS text |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Claude Code | 2.1.114 | train | 2 | 915 | 28 | 219 | 0 | 0 | 0.0% | 0.0% | 0.0% | 54.4% |
| Claude Code | 2.1.123 | train | 2 | 652 | 21 | 162 | 5 | 2 | 0.0% | 0.0% | 0.0% | 50.8% |
| Claude Code | 2.1.126 | train | 1 | 180 | 32 | 291 | 151 | 12 | 0.0% | 0.0% | 0.0% | 44.5% |
| Claude Code | 2.1.131 | train | 1 | 899 | 35 | 245 | 33 | 2 | 0.0% | 0.0% | 0.0% | 37.5% |
| Claude Code | 2.1.143 | train | 1 | 1390 | 52 | 311 | 53 | 0 | 0.0% | 0.0% | 0.0% | 44.3% |
| Claude Code | 2.1.144 | train | 1 | 1024 | 37 | 257 | 33 | 1 | 0.0% | 0.0% | 0.0% | 40.5% |
| Claude Code | 2.1.145 | train | 2 | 1677 | 42 | 313 | 14 | 1 | 0.0% | 0.0% | 0.0% | 44.6% |
| Claude Code | 2.1.158 | test | 1 | 510 | 24 | 211 | 12 | 2 | 5.1% | 8.3% | 0.6% | 41.2% |
| Claude Code | 2.1.159 | test | 1 | 72 | 20 | 179 | 16 | 0 | 9.7% | 0.7% | 0.0% | 49.6% |
| Claude Code | 2.1.160 | test | 1 | 35 | 15 | 153 | 0 | 0 | 14.3% | 0.8% | 0.0% | 43.1% |
| Claude Code | 2.1.162 | test | 2 | 2069 | 35 | 258 | 17 | 0 | 2.8% | 0.0% | 0.0% | 42.1% |
| Claude Code | 2.1.167 | test | 1 | 378 | 16 | 160 | 0 | 0 | 0.8% | 0.0% | 0.0% | 46.1% |
| Claude Code | 2.1.168 | test | 2 | 2185 | 56 | 343 | 42 | 2 | 11.0% | 0.7% | 0.6% | 43.4% |
| Claude Code | 2.1.169 | test | 1 | 594 | 33 | 266 | 17 | 1 | 49.5% | 2.1% | 0.1% | 51.0% |
| Claude Code | 2.1.170 | test | 2 | 328 | 30 | 255 | 1 | 0 | 10.7% | 0.5% | 0.0% | 41.4% |
| Claude Code | 2.1.172 | test | 2 | 198 | 29 | 262 | 1 | 0 | 39.4% | 4.2% | 0.6% | 19.9% |
| Claude Code | 2.1.173 | test | 2 | 674 | 26 | 211 | 0 | 0 | 8.3% | 0.2% | 0.0% | 41.6% |
| Claude Code | 2.1.174 | test | 2 | 120 | 25 | 206 | 15 | 0 | 10.8% | 0.6% | 0.0% | 47.6% |
| Claude Code | 2.1.175 | test | 2 | 471 | 24 | 199 | 4 | 0 | 10.6% | 29.0% | 0.0% | 46.7% |
| Claude Code | 2.1.176 | test | 2 | 482 | 37 | 273 | 1 | 0 | 54.8% | 6.1% | 0.0% | 44.3% |
| Claude Code | 2.1.177 | test | 2 | 760 | 43 | 279 | 2 | 0 | 10.5% | 1.5% | 1.8% | 34.7% |
| Claude Code | 2.1.220 | test | 2 | 225 | 25 | 207 | 22 | 1 | 74.7% | 36.7% | 1.4% | 54.6% |
| Codex | 0.125.0 | train | 2 | 617 | 15 | 123 | 0 | 0 | 0.0% | 0.0% | 0.0% | 94.0% |
| Codex | 0.140.0-alpha.2 | test | 1 | 2046 | 23 | 166 | 49 | 7 | 16.8% | 10.6% | 9.5% | 79.6% |
| Codex | 0.145.0 | test | 1 | 14 | 10 | 126 | 38 | 2 | 85.7% | 15.4% | 14.2% | 26.8% |
| Codex | 0.147.0-alpha.1.2 | test | 1 | 552 | 28 | 240 | 64 | 9 | 95.1% | 93.5% | 79.3% | 70.5% |

#### Alarms on the held-out version changes

| Harness | Alarm | Key precision | Key recall | Key tp | Key fp | Key fn | Version precision | Version recall |
|---|---|---|---|---|---|---|---|---|
| Claude Code | kind | 0.03 | 0.50 | 3 | 91 | 3 | 0.50 | 0.75 |
| Claude Code | any | 0.04 | 0.83 | 5 | 126 | 1 | 0.40 | 1.00 |
| Claude Code | bytes | 0.26 | 0.83 | 5 | 14 | 1 | 0.67 | 1.00 |
| Codex | kind | 0.12 | 0.61 | 11 | 79 | 7 | 1.00 | 1.00 |
| Codex | any | 0.12 | 1.00 | 18 | 133 | 0 | 1.00 | 1.00 |
| Codex | bytes | 0.29 | 0.89 | 16 | 40 | 2 | 1.00 | 1.00 |

#### Biggest keys the test sessions add

| Harness | Kind | Key | Bytes | Text bytes |
|---|---|---|---|---|
| Claude Code | system/local_command | `content:str` | 21246 | 21183 |
| Claude Code | attachment/invoked_skills | `attachment.skills[].content:str` | 21100 | 21100 |
| Claude Code | attachment/agent_listing_delta | `attachment.addedLines[]:str` | 4646 | 4646 |
| Claude Code | attachment/nested_memory | `attachment.content.content:str` | 3116 | 3116 |
| Claude Code | system/api_error | `error.connection.message:str` | 1985 | 1985 |
| Claude Code | system/api_error | `error.formatted:str` | 1095 | 1095 |
| Claude Code | user | `message.content[]<tool_result>.content[]<image>.source.data:str` | 1415154 | 0 |
| Claude Code | attachment/queued_command | `attachment.prompt[]<image>.source.data:str` | 117426 | 0 |
| Claude Code | attachment/hook_success | `parentUuid:str` | 14972 | 0 |
| Claude Code | mode | `sessionId:str` | 11248 | 0 |
| Codex | response_item/custom_tool_call_output | `payload.output[]<input_text>.text:str` | 522306 | 522081 |
| Codex | session_meta | `payload.dynamic_tools:json` | 196998 | 108750 |
| Codex | event_msg/mcp_tool_call_end | `payload.result:json` | 4166791 | 90572 |
| Codex | compacted | `payload.replacement_history[]<message>.content[]<input_text>.text:str` | 79105 | 79105 |
| Codex | event_msg/patch_apply_end | `payload.changes:json` | 76881 | 74123 |
| Codex | world_state | `payload.state.host_skills.body:str` | 44406 | 44406 |
| Codex | response_item/function_call_output | `payload.output[]<input_text>.text:str` | 26618 | 26618 |
| Codex | turn_context | `payload.collaboration_mode.settings.developer_instructions:str` | 14070 | 14070 |
| Codex | event_msg/mcp_tool_call_end | `payload.invocation.arguments:json` | 8257 | 7115 |
| Codex | event_msg/web_search_end | `payload.results[]<text_result>.snippet:str` | 5343 | 5291 |
<!-- results:end -->

<!-- loss:start -->
### Loss accounting

Unread text is shown as shares of that population's text bytes. An exact copy is a string that is also in
content the parser kept. An approximate copy has at least 90% of its line bytes in kept content, a
heuristic that can hide a missing long line. Not matched has no exact or approximate counterpart.
Loss lies between Not matched and Not matched plus Approximate copy.

| Harness | Parser and sessions | Exact copy | Approximate copy (heuristic) | Not matched |
|---|---|---|---|---|
| Claude Code | Frozen at the cutoff, held-out | 0.0% | 0.2% | 0.3% |
| Claude Code | STS mapping, held-out | 24.7% | 21.7% | 10.8% |
| Claude Code | STS mapping, all sessions | 24.8% | 20.5% | 10.6% |
| Codex | Frozen at the cutoff, held-out | 2.4% | 3.9% | 23.2% |
| Codex | STS mapping, held-out | 7.7% | 4.1% | 11.7% |
| Codex | STS mapping, all sessions | 6.6% | 3.4% | 10.4% |

Path-based STS text share, which the held-out loss rows above are measured against:

| Harness | Held-out sessions | All sessions |
|---|---|---|
| Claude Code | 42.9% | 44.1% |
| Codex | 76.5% | 79.5% |

#### What the normalizer writes against what its mapping reads

The path-based STS share counts bytes at mapped keys. This table counts what `normalize` wrote.
Reasoning removed subtracts the reasoning bytes. For Claude Code that equals what the normalizer wrote
before the thinking fix (checked against the old code). Empty strings are left out of both sides.

| Harness | Content bytes mapped | Written by normalize | Written / mapped | Reasoning removed (ablation) | Path-based STS bytes | Written content, share of bytes |
|---|---|---|---|---|---|---|
| Claude Code | 10358502 | 10358502 | 100.0% | 95.3% | 29.0% | 27.3% |
| Codex | 3212390 | 3212434 | 100.0% | 99.9% | 33.1% | 31.9% |

| Harness | Version | Written / mapped | Reasoning removed | Thinking blocks empty | Keys gone quiet (mapped) | Kinds new to the harness | New keys in user or assistant |
|---|---|---|---|---|---|---|---|
| Claude Code | 2.1.114 | 100.0% | 80.2% | 0 of 98 | 0 | 0 | 0 |
| Claude Code | 2.1.123 | 100.0% | 67.7% | 10 of 180 | 0 | 0 | 1 |
| Claude Code | 2.1.126 | 100.0% | 100.0% | 12 of 12 | 1 | 10 | 8 |
| Claude Code | 2.1.131 | 100.0% | 100.0% | - | 1 | 1 | 5 |
| Claude Code | 2.1.143 | 100.0% | 100.0% | 111 of 111 | 0 | 2 | 11 |
| Claude Code | 2.1.144 | 100.0% | 100.0% | - | 0 | 2 | 0 |
| Claude Code | 2.1.145 | 100.0% | 100.0% | - | 0 | 0 | 0 |
| Claude Code | 2.1.158 | 100.0% | 100.0% | - | 2 | 0 | 0 |
| Claude Code | 2.1.159 | 100.0% | 100.0% | 7 of 7 | 1 | 2 | 0 |
| Claude Code | 2.1.160 | 100.0% | 100.0% | 4 of 4 | 0 | 0 | 0 |
| Claude Code | 2.1.162 | 100.0% | 100.0% | - | 1 | 1 | 4 |
| Claude Code | 2.1.167 | 100.0% | 100.0% | - | 1 | 0 | 0 |
| Claude Code | 2.1.168 | 100.0% | 100.0% | - | 0 | 2 | 0 |
| Claude Code | 2.1.169 | 100.0% | 100.0% | 66 of 66 | 1 | 1 | 0 |
| Claude Code | 2.1.170 | 100.0% | 100.0% | 29 of 29 | 0 | 0 | 1 |
| Claude Code | 2.1.172 | 100.0% | 100.0% | 22 of 22 | 1 | 0 | 0 |
| Claude Code | 2.1.173 | 100.0% | 100.0% | 32 of 32 | 0 | 0 | 0 |
| Claude Code | 2.1.174 | 100.0% | 100.0% | 18 of 18 | 0 | 1 | 0 |
| Claude Code | 2.1.175 | 100.0% | 100.0% | 78 of 78 | 0 | 0 | 4 |
| Claude Code | 2.1.176 | 100.0% | 100.0% | 47 of 47 | 0 | 0 | 1 |
| Claude Code | 2.1.177 | 100.0% | 100.0% | 37 of 37 | 1 | 0 | 0 |
| Claude Code | 2.1.220 | 100.0% | 100.0% | 31 of 31 | 1 | 1 | 3 |
| Codex | 0.125.0 | 100.0% | 100.0% | - | 0 | 0 | 0 |
| Codex | 0.140.0-alpha.2 | 100.0% | 100.0% | - | 0 | 5 | 0 |
| Codex | 0.145.0 | 100.0% | 100.0% | - | 0 | 1 | 2 |
| Codex | 0.147.0-alpha.1.2 | 100.0% | 99.7% | - | 0 | 3 | 19 |

#### Alarms, counted per record kind

A case is a record kind with new keys in a held-out version. The 95% intervals are Wilson intervals.
Of the new content keys in held-out versions, 0 of 6 (Claude Code) and 3 of 18 (Codex) sit in conversation records, the kinds the
STS mapping reads. The rest are injected records such as attachments and system events.

| Harness | Alarm | Kind tp | fp | fn | Precision (95%) | Recall (95%) |
|---|---|---|---|---|---|---|
| Claude Code | any | 4 | 20 | 1 | 0.17 (0.07 to 0.36) | 0.80 (0.38 to 0.96) |
| Claude Code | bytes | 4 | 7 | 1 | 0.36 (0.15 to 0.65) | 0.80 (0.38 to 0.96) |
| Claude Code | kind | 3 | 4 | 2 | 0.43 (0.16 to 0.75) | 0.60 (0.23 to 0.88) |
| Codex | any | 13 | 15 | 0 | 0.46 (0.30 to 0.64) | 1.00 (0.77 to 1.00) |
| Codex | bytes | 13 | 7 | 0 | 0.65 (0.43 to 0.82) | 1.00 (0.77 to 1.00) |
| Codex | kind | 7 | 2 | 6 | 0.78 (0.45 to 0.94) | 0.54 (0.29 to 0.77) |

#### Biggest unmatched text the normalizer does not write (all sessions)

| Harness | Kind | Not matched text bytes | Approximate copy bytes | Exact copy bytes |
|---|---|---|---|---|
| Claude Code | user | 1692848 | 4397031 | 5459880 |
| Claude Code | attachment/skill_listing | 166008 | 0 | 0 |
| Claude Code | attachment/hook_success | 149679 | 0 | 0 |
| Claude Code | last-prompt | 88697 | 1196 | 33835 |
| Claude Code | attachment/diagnostics | 73822 | 0 | 0 |
| Codex | session_meta | 404066 | 0 | 0 |
| Codex | event_msg/web_search_end | 7512 | 92 | 0 |
| Codex | event_msg/mcp_tool_call_end | 6692 | 589 | 90406 |
| Codex | event_msg/patch_apply_end | 2915 | 74781 | 0 |
| Codex | response_item/web_search_call | 150 | 0 | 0 |

Claude Code records marked as subagent work (isSidechain): 0 in this data.
<!-- loss:end -->

## Structure only

The experiment, the `audit` command and this README work on field paths and counts. They read session files to
measure them but never print or store their text. Only `normalize` writes session text, by design, to a file the
user names.

## Layout

```
capturedrift/shape.py   byte sizes, event kinds, key paths, opaque subtrees
capturedrift/data.py    records, sessions, manifest loading and ordering
capturedrift/sts.py     the fixed STS normalizer
capturedrift/drift.py   unseen shares, version changes, alarms, threshold tuning
capturedrift/run.py     the 43 experiment metrics
capturedrift/__main__.py  the audit and normalize subcommands
experiment.py           run the experiment
demo.py                 summary line and README renderer
tests/                  unittest suite
docs/DESIGN.md          method and trade-offs
docs/INTERVIEW.md       five-minute explanation
SPEC-v2.md              what version 2 adds
```

## Limits

- **Small data.** 40 sessions, at most two per version; Codex has 5 sessions and only 3 held-out versions, so its
  numbers illustrate a method rather than estimate a population.
- **The split is by version, not by date.** Training and held-out are cut at a version number. Session start dates
  are not in version order (the 2.1.123 sessions started before the 2.1.114 ones), so this is not a chronological
  split. It matches the question, since a parser is frozen at a version.
- **Codex training is one version.** Codex training is 0.125.0 alone, so its training period has no version change.
  The byte threshold is tuned on Claude's training changes only.
- **Version and source are confounded.** Most versions come from a different dataset, user and setup (for example
  Codex `codex_exec` versus the desktop app), so a new key can mean a format change or a feature first used in
  that data. Both break a frozen importer; this experiment cannot tell them apart.
- **Heuristics.** The text rule (a string with at least three words) and the 200-byte content threshold are
  simple. Images and encrypted reasoning count as bytes, not text.
- **Duplicated content.** Some dropped content appears elsewhere — Claude's `toolUseResult` repeats tool results
  — so "dropped" is an upper bound on loss.
- **STS share is by path.** The v1 STS byte and text shares count the leaves at mapped key paths. They do not
  measure what `normalize` writes, so the thinking bug did not move them. The loss accounting counts what
  `normalize` writes, and a test fails if that drifts from what the mapping reads.
- **Copies are matched on text.** An exact copy is a string that appears verbatim in kept content. An approximate
  copy has at least 90% of its line bytes (after removing line-number prefixes) in kept content. That is a
  heuristic, so it is reported separately, and loss is only bounded: at least the not matched share, at most that
  plus the approximate share.
- **Quiet keys are noisy.** A known key that stops carrying text is only a hint: with at most two sessions per
  version, a feature simply not used looks the same. The mapped quiet keys are the ones that matter for STS.
- **Thinking text going empty is confounded with source.** Thinking blocks are all empty from 2.1.126, but the
  datasets, models and settings also change. The data cannot say which one caused it.
- **No subagent records in this data.** No record has `isSidechain` true, so how a subagent thread is captured
  is untested on real data. `normalize` writes such records like any other, with no marker, and a test pins that.
- **Codex compacted history is not written.** `compacted` records are dropped by the STS mapping, and a test pins it.
- **Fixed mapping, chosen late.** The STS mapping was written after looking at all versions, so its share is a
  best case for a fixed mapping.
- **Alarms are deliberately myopic.** Each alarm sees only the first session of a version, which is all a live
  check would have on the day the version first appears, so keys that only show up in that version's second
  session are unreachable by construction.
- **Published data only.** Several datasets passed through their uploaders' own anonymization; nothing here can
  undo or improve that.

## Data and licenses

The code is MIT licensed (`LICENSE`).

Every session file comes from one of the datasets below, at the pinned revision, under the license its card
states. CC-BY-4.0 sources are attributed here as that license requires; the full revision hashes and per-file
provenance are in `data/MANIFEST.json`, the license texts in `data/licenses/` and the cards in `data/sources/`.

| Dataset | Harness | Sessions | License | Revision |
|---|---|---|---|---|
| [AlinCiocan/fable-5-claude-code-traces](https://huggingface.co/datasets/AlinCiocan/fable-5-claude-code-traces) | Claude Code | 4 | CC-BY-4.0 | `e33ebbca230a` |
| [armand0e/claude-fable-5-claude-code](https://huggingface.co/datasets/armand0e/claude-fable-5-claude-code) | Claude Code | 5 | MIT | `7388ef96f317` |
| [build-small-hackathon/lost-found-desk-codex-traces](https://huggingface.co/datasets/build-small-hackathon/lost-found-desk-codex-traces) | Codex | 1 | MIT | `939ce900603d` |
| [davanstrien/agent-race-traces](https://huggingface.co/datasets/davanstrien/agent-race-traces) | Claude Code | 1 | CC-BY-4.0 | `4a8ac15d62c3` |
| [kaupane/AstroAgentBench-Traces](https://huggingface.co/datasets/kaupane/AstroAgentBench-Traces) | Claude Code, Codex | 6 | CC-BY-4.0 | `cff96a3f9b27` |
| [naazimsnh02/tutordesk-agent-traces](https://huggingface.co/datasets/naazimsnh02/tutordesk-agent-traces) | Claude Code | 4 | MIT | `4d538090ddd3` |
| [nielsr/r3al-vit-quantization-codex-trace](https://huggingface.co/datasets/nielsr/r3al-vit-quantization-codex-trace) | Codex | 1 | MIT | `364ab50da7fc` |
| [thomwolf/am-session-claude-code-1-c3cc0a](https://huggingface.co/datasets/thomwolf/am-session-claude-code-1-c3cc0a) | Claude Code | 1 | Apache-2.0 | `037d661cb58d` |
| [thomwolf/am-session-codex-check-d17941](https://huggingface.co/datasets/thomwolf/am-session-codex-check-d17941) | Codex | 1 | Apache-2.0 | `d89ae23edfef` |
| [thomwolf/am-session-sharing-design](https://huggingface.co/datasets/thomwolf/am-session-sharing-design) | Claude Code | 1 | Apache-2.0 | `36dd5850a4f0` |
| [trace-commons/agent-traces](https://huggingface.co/datasets/trace-commons/agent-traces) | Claude Code | 13 | CC-BY-4.0 | `112ebd4d03ce` |
| [yellowbeeblackbee/claude-traces](https://huggingface.co/datasets/yellowbeeblackbee/claude-traces) | Claude Code | 2 | CC0-1.0 | `0cad5c49dfb8` |

Session contents may include code, logs and third-party material carrying its own terms; anyone reusing these
files is responsible for checking that their use complies. This project is not affiliated with or endorsed by any
of the tools or datasets named here; product names identify the systems that produced the traces.

Redistribution: every dataset is public, ungated and carries an open license (MIT, Apache-2.0, CC0-1.0 or
CC-BY-4.0) that allows copying with attribution, checked on each dataset's Hugging Face page and card on 15 Nov 2026.
The files here are the published sessions after the redaction described above. Some datasets say their own
anonymization is best effort. If a dataset owner asks for removal, `tools/fetch_data.py` can rebuild the rest from the
manifest, and the pinned files can be dropped from the repository and its history.

## Built with

Built with Arcturus (Claude Code builders, Codex review); reviewed and verified by hand.
