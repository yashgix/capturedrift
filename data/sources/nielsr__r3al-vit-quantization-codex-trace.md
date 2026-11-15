---
pretty_name: R3AL ViT Quantization — Codex Agent Trace
tags:
  - traces
  - agent-traces
  - codex
  - quantization
  - computer-vision
license: mit
---

# R3AL ViT Quantization — Codex Agent Trace

Codex session trace for installing the R3AL CLI and agent skill, exporting
`google/vit-base-patch16-224` to ONNX, performing dynamic INT8 post-training
quantization on R3AL, and evaluating model size, Apple-arm64 CPU latency, and
prediction fidelity on a 100-image ImageNet validation sample.

The original Codex JSONL format is preserved for Hugging Face's native Agent
Trace viewer. Credential values, email addresses, unrelated Gmail/Slack tab
metadata, and the local home-directory prefix were redacted before publishing.

## Outcome

- FP32 ONNX: 346,397,372 bytes
- INT8 ONNX: 89,432,268 bytes (74.18% smaller)
- CPU latency: 92.51 ms to 37.05 ms (2.50x faster)
- 100-image top-1: 83% to 81%
- 100-image top-5: 95% to 95%
- Top-1 agreement: 97%
- Mean logit cosine similarity: 0.9958

The 100-image evaluation is a regression check, not a publication-grade full
ImageNet benchmark.
