#!/usr/bin/env python3
"""Complete-token occurrence scanner (validation-driven check 2).

Scans every Reference_Site (model YAML under `model/network/**`, every
`examples/*/README.md` + `examples/README.md`, `docs/conventions.md`,
`docs/naming-review.md`) for complete-token occurrences of each pre-rename
identifier from `rename-token-map.yaml`, and reports a per-old-name occurrence
count with file/line locations.

Matching is identifier-boundary anchored (Requirement 11.1) so a prefix never
cross-matches a longer name (`network.nat.ports` does not match inside
`network.nat.port_blocks`).

Usage:
    # before the sweep: shows the baseline (expected non-zero) counts
    uv run --with pyyaml --no-project python3 token_scan.py

    # after the sweep: --assert-zero exits non-zero if ANY old name survives
    uv run --with pyyaml --no-project python3 token_scan.py --assert-zero

    # machine-readable
    uv run --with pyyaml --no-project python3 token_scan.py --json

Property 1 (no pre-rename identifier survives) is satisfied when --assert-zero
returns exit code 0. This is the lockstep completeness / stale-reference guard
(Requirements 11.5, 11.6, 13.6).
"""

from __future__ import annotations

import argparse
import json
import sys

from _common import (
    REPO_ROOT,
    complete_token_regex,
    load_token_map,
    old_names,
    reference_site_files,
)


def scan() -> dict:
    """Return {old_name: [ {file, line, text}, ... ]} for every old name."""
    token_map = load_token_map()
    names = old_names(token_map)
    files = reference_site_files(token_map)

    patterns = {name: complete_token_regex(name) for name in names}
    hits: dict[str, list[dict]] = {name: [] for name in names}

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            for name, pat in patterns.items():
                if pat.search(line):
                    hits[name].append(
                        {"file": rel, "line": lineno, "text": line.strip()}
                    )
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assert-zero",
        action="store_true",
        help="Exit non-zero if any old name has a non-zero occurrence count.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )
    parser.add_argument(
        "--show-locations",
        action="store_true",
        help="Print every file:line occurrence (text report only).",
    )
    args = parser.parse_args()

    hits = scan()
    counts = {name: len(locs) for name, locs in hits.items()}
    total = sum(counts.values())
    surviving = {n: c for n, c in counts.items() if c > 0}

    if args.json:
        print(json.dumps({"counts": counts, "total": total, "hits": hits}, indent=2))
    else:
        print(f"Complete-token scan over {len(reference_site_files(load_token_map()))} Reference_Sites")
        print(f"Old names tracked: {len(counts)}    Total occurrences: {total}\n")
        for name in sorted(counts, key=lambda n: (-counts[n], n)):
            print(f"  {counts[name]:>4}  {name}")
            if args.show_locations:
                for loc in hits[name]:
                    print(f"          {loc['file']}:{loc['line']}: {loc['text']}")

    if args.assert_zero:
        if surviving:
            print(
                f"\nFAIL: {len(surviving)} old name(s) still present "
                f"({sum(surviving.values())} occurrences). Property 1 not satisfied.",
                file=sys.stderr,
            )
            return 1
        print("\nPASS: zero surviving old-name occurrences (Property 1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
