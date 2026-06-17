#!/usr/bin/env python3
"""Turn a `weaver registry live-check --format json` stream into a verdict.

Weaver streams one JSON object per sample plus a final summary object. The
gate policy:

  - `not_stable` / `improvement` advice is ACCEPTABLE — the whole registry is
    stability=development by construction, so every attribute is expected to
    carry that note.
  - ANY non-registry attribute/metric/event (a name the registry does not
    define), or any advice above `improvement` (a violation), FAILS the gate.

ACCEPTABLE: developer note — `improvement`/`information` advice is fine; only
`violation`/`error` or names the registry does not define fail the gate.
"""
from __future__ import annotations

import json
import pathlib
import sys

FAIL_LEVELS = {"violation", "error"}


def parse_stream(text: str):
    dec = json.JSONDecoder()
    i, n, objs = 0, len(text), []
    while i < n:
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        o, j = dec.raw_decode(text, i)
        objs.append(o)
        i = j
    return objs


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/lc.json"
    objs = parse_stream(pathlib.Path(path).read_text())
    if not objs:
        sys.exit("empty live-check report")
    s = objs[-1]

    non_reg = {
        "attributes": s.get("seen_non_registry_attributes", {}),
        "metrics": s.get("seen_non_registry_metrics", {}),
        "events": s.get("seen_non_registry_events", {}),
    }
    levels = s.get("advice_level_counts", {})
    types = s.get("advice_type_counts", {})

    print("=" * 64)
    print("  network.* live-check verdict")
    print("=" * 64)
    by_type = s.get("total_entities_by_type", {})
    print(f"  samples:     {s.get('total_entities')}  {by_type}")
    print(f"  advisories:  {s.get('total_advisories')}  by-level={levels}  by-type={types}")
    print(f"  clean (no advice): {s.get('no_advice_count')}")
    print(f"  registry coverage: {s.get('registry_coverage', 0) * 100:.1f}%")

    bad_levels = {k: v for k, v in levels.items() if k in FAIL_LEVELS}
    unknown = {k: v for k, v in non_reg.items() if v}

    failed = bool(bad_levels or unknown)
    print("-" * 64)
    if unknown:
        print("  FAIL: telemetry uses names the registry does not define:")
        print("       ", json.dumps(unknown))
    if bad_levels:
        print("  FAIL: violation-level advice present:")
        print("        levels:", bad_levels)
    if not failed:
        print("  PASS: every attribute & metric is registry-defined.")
        print("        only development-stability + optional-attribute notes remain.")
    print("=" * 64)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
