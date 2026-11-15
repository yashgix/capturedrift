# capturedrift v2: loss accounting

v1 (`SPEC.md`) is unchanged and its acceptance tests still pass. v2 adds a second result file,
`results/metrics-v2.json`, written by `python -m capturedrift.loss`. Nothing in `results/metrics.json` changes.

## Why
A review of v1 found two weaknesses. The STS shares counted bytes at mapped key paths, so a normalizer bug (it read
thinking text from the wrong field) did not move them. And "unseen" or "dropped" text included copies of kept content,
for example Claude's `toolUseResult`, which repeats the tool result already read.

## What v2 adds
- `shape.leaf_values(harness, record)`: the leaf walk that `leaves` already used, now yielding the raw values.
  `leaves` is unchanged in behaviour.
- Conservation, per harness and version: content bytes at mapped keys (paths ending in text, thinking, content,
  input, arguments or output) against content bytes `normalize` writes (`content`, `reasoningContent`, tool call
  arguments, measured with `size`). Written without reasoning shows what the thinking bug wrote.
- Copy and unique text, for the frozen parser's unseen keys on held-out sessions and for the STS mapping's unmapped keys
  over all sessions. A string is a copy when it matches kept content exactly, or when at least 90% of its non-empty
  lines do after stripping `N→` or `N<tab>` line-number prefixes. The rest is unique. Shares use the same total text
  bytes as the v1 shares, so copy plus unique equals the v1 unseen text share.
- Thinking blocks per Claude version, and how many have empty text.
- Quiet keys: per version, keys with at least `CONTENT_MIN` text bytes in the version before, no text now, and whose
  record kind still occurs. Reported as counts, with a mapped-only count.
- Alarm scores per record kind: a (version, kind) with new keys is one case. Wilson 95% intervals. The byte threshold
  is the v1 one, chosen on training versions only.
- New content keys split into conversation kinds (the kinds the STS mapping reads) and injected kinds.
- `isSidechain` record count, and tests that pin the compacted-history and sidechain behaviour.

## What it deliberately does not change
No v1 behaviour. Sidechain records and Codex compacted history stay unmapped, stated as limits in the README.
