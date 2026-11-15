---
pretty_name: "Agent Manager session — claude-code-1"
license: apache-2.0
language:
  - en
tags:
  - agent-traces
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

# Agent Manager session — claude-code-1

One Claude Code session, exported from [Agent Manager](https://huggingface.co/spaces/lvwerra/agent-manager-template).

> **Access: public.** Anyone with the link can read this trace.

## At a glance

- **2** prompts · **2** assistant turns · **0** tool calls
- Trace: `c3cc0a1c-7826-48a6-8c7b-a0b811496e16.jsonl`

## What's in here

| Path | Contents |
|---|---|
| `c3cc0a1c-7826-48a6-8c7b-a0b811496e16.jsonl` | the session, native Claude Code JSONL |
| `meta/manifest.json` | provenance: harness, session ids, stats, content hash, lineage |
| `meta/briefing.md` | mechanically generated handoff summary |
| `meta/redaction.json` | which redaction rules ran and what they caught |

## Redaction

Before upload the trace passed ruleset v1: token-shaped patterns, **value** matching against
this Space's secret-bearing environment variables, and an email rule. Derived artifacts go
through the same pass. `file-history-snapshot` lines are dropped — they embed full file
contents. Result: nothing matched.

Traces can still contain local paths and command output. Review before relying on this being clean.
