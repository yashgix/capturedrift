---
license: mit
format: agent-traces
tags:
  - agent-traces
  - claude-code
  - build-small-hackathon
  - tutordesk-ai
  - education
  - indian-education
configs:
  - config_name: build_sessions
    data_files: build_sessions/*.jsonl
---

# TutorDesk AI — Agent Traces

**Sharing is Caring** badge dataset for the [HuggingFace Build Small Hackathon 2026](https://huggingface.co/build-small-hackathon).

## Contents

### `build_sessions/` — Claude Code Build Sessions (native trace viewer)

7 raw Claude Code (Sonnet 4.6) JSONL sessions covering the full build of
TutorDesk AI — from blank repo through Phase 6 completion. Natively rendered by
[HF Data Studio's agent trace viewer](https://huggingface.co/docs/hub/en/agent-traces).

Sessions cover: repo scaffolding, Modal serving architecture, 5-agent pipeline,
Qwen3-4B fine-tuning workflow, MiniCPM-V vision integration, FLUX diagram generation,
Tiny Aya multilingual support, Off-Brand Gradio theme, offline/llama.cpp mode.

Secrets and local paths have been redacted. HF usernames (`naazimsnh02`) are kept as
they are public-facing identifiers.

### `runtime_traces/` — App Agent Runtime Traces

Per-agent records captured during live pipeline runs. Schema: `agent`, `system`,
`user`, `output`, `ts`. Agents: curriculum, question_gen, difficulty, answer, report, grader.

## Related

- Space: [naazimsnh02/tutordesk-ai](https://huggingface.co/spaces/naazimsnh02/tutordesk-ai)
- Model: [naazimsnh02/tutordesk-qwen3-4b](https://huggingface.co/naazimsnh02/tutordesk-qwen3-4b)
