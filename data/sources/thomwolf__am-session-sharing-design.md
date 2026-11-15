---
pretty_name: "Agent Manager session — designing session sharing"
license: apache-2.0
language:
  - en
tags:
  - agent-traces
  - claude-code
  - agent-manager
  - coding-agent
  - traces
  - tool-use
configs:
  - config_name: default
    data_files:
      - split: train
        path: "*.jsonl"
---

# Agent Manager session — designing session sharing

> **Access: public.** Anyone with the link can read this trace. Public is the only mode
> where the Hub's trace viewer works for every visitor regardless of account tier.

A single real [Agent Manager](https://huggingface.co/spaces/lvwerra/agent-manager-template)
session, exported as a shareable trace. This is the working session in which the
session-sharing design itself was researched and written — surveying how five coding-agent
harnesses persist sessions, testing what the Hub's trace viewer can do, and producing a
design doc.

## View it

Open **Data Studio** and click the single row: the Hub renders the full session — prompts,
assistant turns, tool calls, token counts, thinking blocks. The repo holds one session, so
it is always `row=0`, which makes it directly embeddable:

```html
<iframe src="https://huggingface.co/datasets/thomwolf/am-session-sharing-design/embed/viewer/default/train?row=0"
        frameborder="0" width="100%" height="700px"></iframe>
```

## What's in here

| Path | Contents |
|---|---|
|  `<session-uuid>.jsonl` | the session, verbatim Claude Code JSONL (a Hub-native trace format) |
| `meta/manifest.json` | provenance: harness + version, session ids, stats, content hash, lineage |
| `meta/briefing.md` | mechanically generated handoff summary — what was asked, tools used, files written |
| `meta/redaction.json` | which redaction rules ran and what they caught |

## Session at a glance

- **Harness**: Claude Code 3.3a · `claude-opus-5[1m]`
- **7** user prompts · **38** assistant turns · **40** tool calls
- **95,795** input / **39,337** output tokens (2.68M cache read)
- Tools: `Bash` ×23, `Read` ×6, `WebSearch` ×4, `WebFetch` ×4, `Skill`, `ToolSearch`, `Write`

## Provenance and redaction

Exported by the phase-1 prototype described in the design doc: locate → redact → assemble
→ publish. Before upload the trace went through redaction ruleset v1 — token-shaped
patterns (`hf_`, `sk-ant-`, `gh?_`, AWS, Google, JWT, private keys), **value** matching
against the Space's actual secret-bearing environment variables, and an email rule.

Result: **no secret matches**, 7 email addresses redacted (shown as `«redacted:email»`),
and 8 `file-history-snapshot`/`delta` lines dropped — those embed full file contents and
are the single worst leak vector in a Claude transcript.

The source code visible in this trace belongs to Agent Manager, which is published as a
[public template Space](https://huggingface.co/spaces/lvwerra/agent-manager-template);
the files quoted here were verified byte-identical to that public copy before publishing.

Traces can still contain local paths, command output and private context. Review before
publishing your own.

## Forking it

The transcript filename is a Claude Code session id, so a recipient can continue this
conversation: place  `<session-uuid>.jsonl` at `<CLAUDE_CONFIG_DIR>/projects/<cwd-slug>/<new-uuid>.jsonl`
and run `claude --resume <new-uuid>`. Always **copy** — `--resume` appends to the
transcript, so resuming a shared artifact in place would mutate the thing that was meant
to be frozen. `meta/manifest.json` records `trace.nativePath` for exactly this.
