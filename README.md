# capturedrift

Milestone 1: a structure-only measurement of what a coding-agent session parser, frozen at one CLI version, keeps
and silently drops on the versions that come after it.

An importer written against one CLI version keeps running on later versions — it just stops recognising whatever
arrives in shapes it has never seen. Nothing fails: no exception, no dropped-file warning, no log line. The unknown
keys are simply never read. capturedrift puts a number on that, on real public Claude Code and Codex session files
that span many CLI versions.

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
make test                                        # unittest suite
make lint                                        # ruff check + format check
make data-check                                  # verify the pinned files
python experiment.py --out results/metrics.json  # run the experiment
python demo.py                                   # one-line summary of the metrics
make readme                                      # re-render the results block below
```

`python experiment.py --out PATH [--data DIR]` writes the metrics as JSON with sorted keys, indent 1 and a final
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
<!-- results:end -->

## Structure only

The experiment, the `audit` command and this README work on field paths and counts. They read session files to
measure them but never print or store their text. Only `normalize` writes session text, by design, to a file the
user names.

## Layout

```
capturedrift/shape.py   byte sizes, event kinds, key paths, opaque subtrees
their data
capturedrift/data.py    records, sessions, manifest loading and ordering
capturedrift/sts.py     the fixed STS normalizer
their data
capturedrift/drift.py   unseen shares, version changes, alarms, threshold tuning
capturedrift/run.py     the 43 experiment metrics
capturedrift/__main__.py  the audit and normalize subcommands
experiment.py           run the experiment
demo.py                 summary line and README renderer
tests/                  unittest suite
docs/DESIGN.md          method and trade-offs
docs/INTERVIEW.md       five-minute explanation
```

## Limits

- **Small data.** 40 sessions, at most two per version; Codex has 5 sessions and only 3 held-out versions, so its
  numbers illustrate a method rather than estimate a population.
- **Version and source are confounded.** Most versions come from a different dataset, user and setup (for example
  Codex `codex_exec` versus the desktop app), so a new key can mean a format change or a feature first used in
  that data. Both break a frozen importer; this experiment cannot tell them apart.
- **Heuristics.** The text rule (a string with at least three words) and the 200-byte content threshold are
  simple. Images and encrypted reasoning count as bytes, not text.
- **Duplicated content.** Some dropped content appears elsewhere — Claude's `toolUseResult` repeats tool results
  — so "dropped" is an upper bound on loss.
- **Fixed mapping, chosen late.** The STS mapping was written after looking at all versions, so its share is a
  best case for a fixed mapping.
- **Alarms are deliberately myopic.** Each alarm sees only the first session of a version, which is all a live
  check would have on the day the version first appears, so keys that only show up in that version's second
  session are unreachable by construction.
- **Published data only.** Several datasets passed through their uploaders' own anonymization; nothing here can
  undo or improve that.

## Data sources and licenses

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
