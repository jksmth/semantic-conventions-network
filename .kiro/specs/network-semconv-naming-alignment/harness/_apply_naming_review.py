#!/usr/bin/env python3
"""One-shot: apply complete-token renames to docs/naming-review.md (task 11.3).

Reuses the authoritative rename-token-map.yaml and the harness complete-token
(identifier-boundary) matching rule so prefixes never cross-match. Builds the
old->new mapping from rename_map PLUS the structural repoint/remove entries
(network.interface.id -> network.interface.name; the folded interface state
attrs -> the shared network.admin.state / network.oper.state).

Prints a per-old-name occurrence count and rewrites the file in place.
"""

from __future__ import annotations

from _common import (
    REPO_ROOT,
    complete_token_regex,
    load_token_map,
    rename_pairs,
)


def build_old_to_new(token_map: dict) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for e in rename_pairs(token_map):
        if "old" in e and "new" in e:
            mapping[e["old"]] = e["new"]
    for sc in token_map.get("structural_changes") or []:
        t = sc.get("type")
        if t == "repoint_reference" and "old" in sc and "new" in sc:
            mapping[sc["old"]] = sc["new"]
        elif t == "remove_definition" and "name" in sc and "repoint_refs_to" in sc:
            mapping[sc["name"]] = sc["repoint_refs_to"]
    return mapping


def main() -> int:
    token_map = load_token_map()
    mapping = build_old_to_new(token_map)

    target = REPO_ROOT / "docs" / "naming-review.md"
    text = target.read_text(encoding="utf-8")

    # Replace longest old-names first as defensive ordering (boundaries already
    # prevent cross-match, but this is harmless and deterministic).
    counts: dict[str, int] = {}
    for old in sorted(mapping, key=len, reverse=True):
        new = mapping[old]
        pat = complete_token_regex(old)
        text, n = pat.subn(new, text)
        counts[old] = n

    target.write_text(text, encoding="utf-8")

    total = sum(counts.values())
    print(f"Applied {len(mapping)} rename tokens to docs/naming-review.md")
    print(f"Total token occurrences replaced: {total}\n")
    for old in sorted(counts, key=lambda k: (-counts[k], k)):
        if counts[old]:
            print(f"  {counts[old]:>3}  {old}  ->  {mapping[old]}")
    print("\n-- old names with zero occurrences in this file --")
    for old in sorted(counts):
        if not counts[old]:
            print(f"    0  {old}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
