# Validation harness — network-semconv-naming-alignment

Task 1.2 artifact. Three validation-driven checks the later validation tasks
(13.1, 13.2, 13.3) run against the post-sweep registry. All three consume the
task 1.1 token map at `../rename-token-map.yaml`.

This harness lives under `.kiro/specs/` (not in the registry tree) so Weaver
never tries to resolve it as a model file.

## Prerequisites

- **Docker** — Weaver runs via the pinned `otel/weaver:v0.23.0` image (matching
  the sibling `otel-semantic-conventions` repos; this repo has no Makefile).
- **Python 3** with **PyYAML** — the scanner and field-diff parse the model
  YAML. The interpreter here lacks PyYAML, so run the Python tools through
  `uv run --with pyyaml --no-project` (uv provisions PyYAML ephemerally).

## 1. Weaver resolve / check (task 13.1, Property 11)

The reference-resolution and well-formedness gate over `model/`.

```bash
.kiro/specs/network-semconv-naming-alignment/harness/weaver_check.sh          # registry check
.kiro/specs/network-semconv-naming-alignment/harness/weaver_check.sh resolve  # registry resolve
```

Exit 0 = clean (zero broken refs, zero validation errors). Override the pinned
image with `WEAVER_VERSION=...`.

## 2. Complete-token scan (task 13.2, Property 1)

Per-old-name occurrence counts across model YAML + `examples/*/README.md` +
`docs/conventions.md` + `docs/naming-review.md`, using identifier-boundary
matching (Requirement 11.1) so prefixes never cross-match.

```bash
cd .kiro/specs/network-semconv-naming-alignment/harness
uv run --with pyyaml --no-project python3 token_scan.py                 # baseline counts
uv run --with pyyaml --no-project python3 token_scan.py --show-locations
uv run --with pyyaml --no-project python3 token_scan.py --assert-zero   # post-sweep gate
uv run --with pyyaml --no-project python3 token_scan.py --json
```

Before the sweep, counts are non-zero (the old names still exist). After the
sweep, `--assert-zero` must exit 0 (Property 1; Requirements 11.5/11.6/13.6).

## 3. Structured field-diff (task 13.3, Property 2)

Per-definition pre/post node diff asserting identifier-only difference.

```bash
cd .kiro/specs/network-semconv-naming-alignment/harness

# Option A — snapshot the pre-sweep tree, then diff after the sweep:
uv run --with pyyaml --no-project python3 field_diff.py snapshot --out /tmp/semconv-baseline
# ... apply the rename sweep (tasks 2-11) ...
uv run --with pyyaml --no-project python3 field_diff.py diff --baseline /tmp/semconv-baseline

# Option B — diff against a git ref as the pre-sweep baseline (default HEAD):
uv run --with pyyaml --no-project python3 field_diff.py diff --git-ref HEAD

# Single node:
uv run --with pyyaml --no-project python3 field_diff.py node \
  --old-file /tmp/semconv-baseline/model/network/routing/metrics.yaml --old-id network.routing.routes \
  --new-file ../../../../model/network/routing/metrics.yaml --new-id network.routing.route.count
```

A rename passes when the only field difference is the identifier; `note`,
`brief`, and `attributes` (dimension `ref:` repoints) differences are reported
as `allowed:` and do not fail the check. Any other field change is a
`VIOLATION` and exits non-zero.

## All three at once

```bash
.kiro/specs/network-semconv-naming-alignment/harness/run_all.sh
```

Runs Weaver check, the token scan, and (if a baseline exists) the field-diff,
reporting each result.
