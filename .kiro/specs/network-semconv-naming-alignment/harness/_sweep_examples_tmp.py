#!/usr/bin/env python3
"""Temp: complete-token sweep of examples/*/README.md + examples/README.md.

Driven by the authoritative rename-token-map.yaml (rename_map + the structural
repoint/remove entries that carry an old->new repoint). Uses the same
identifier-boundary matching rule as the harness so prefixes never cross-match.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO = Path("/Users/jake.smith/code/github/jksmth/semantic-conventions-network")
TOKEN_MAP = REPO / ".kiro/specs/network-semconv-naming-alignment/rename-token-map.yaml"
IDENT = r"[A-Za-z0-9_.]"


def token_re(tok: str) -> re.Pattern:
    return re.compile(rf"(?<!{IDENT}){re.escape(tok)}(?!{IDENT})")


def build_pairs() -> list[tuple[str, str]]:
    tm = yaml.safe_load(TOKEN_MAP.read_text())
    pairs: list[tuple[str, str]] = []
    for e in tm.get("rename_map") or []:
        if "old" in e and "new" in e:
            pairs.append((e["old"], e["new"]))
    for sc in tm.get("structural_changes") or []:
        t = sc.get("type")
        if t == "repoint_reference" and "old" in sc and "new" in sc:
            pairs.append((sc["old"], sc["new"]))
        elif t == "remove_definition" and "name" in sc and "repoint_refs_to" in sc:
            pairs.append((sc["name"], sc["repoint_refs_to"]))
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


def example_files() -> list[Path]:
    files = [REPO / "examples/README.md"]
    files += sorted((REPO / "examples").glob("*/README.md"))
    return [f for f in files if f.is_file()]


def main() -> int:
    pairs = build_pairs()
    patterns = [(old, new, token_re(old)) for old, new in pairs]
    apply = "--apply" in sys.argv

    grand_before = 0
    changed_files: dict[str, dict[str, int]] = {}

    for path in example_files():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO).as_posix()
        per_file: dict[str, int] = {}
        new_text = text
        for old, new, pat in patterns:
            n = len(pat.findall(new_text))
            if n:
                per_file[old] = per_file.get(old, 0) + n
                new_text = pat.sub(lambda m, _new=new: _new, new_text)
        if per_file:
            changed_files[rel] = per_file
            grand_before += sum(per_file.values())
            if apply and new_text != text:
                path.write_text(new_text, encoding="utf-8")

    mode = "APPLIED" if apply else "DRY-RUN"
    print(f"=== {mode} ===")
    for rel in sorted(changed_files):
        total = sum(changed_files[rel].values())
        print(f"\n{rel}  ({total} occurrences)")
        for old in sorted(changed_files[rel], key=lambda o: -changed_files[rel][o]):
            print(f"    {changed_files[rel][old]:>3}  {old}")
    print(f"\nTOTAL old-name occurrences across examples: {grand_before}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
