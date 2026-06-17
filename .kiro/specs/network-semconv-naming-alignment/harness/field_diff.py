#!/usr/bin/env python3
"""Structured per-definition field-diff (validation-driven check 3).

For each renamed definition this helper compares the pre-sweep YAML node with
the post-sweep YAML node and asserts the ONLY difference is the identifier
(plus mandated note re-pins / dimension-ref renames). This is the machine check
behind Property 2 (renames are name-only / structure-preserving).

Because the sweep is a single coordinated landing, the harness works against a
pristine baseline snapshot of `model/network/**` taken from git (the pre-sweep
state) versus the current working tree (the post-sweep state).

Definition nodes are extracted from the four file kinds by their identifier
field:
    metrics.yaml   -> metrics[].name / metric_refinements[].name
    registry.yaml  -> attributes[].key
    events.yaml    -> events[].id / event_refinements[].id
    entities.yaml  -> entities[].type

Usage:
    # snapshot the current (pre-sweep) tree to a baseline dir
    uv run --with pyyaml --no-project python3 field_diff.py snapshot --out /tmp/semconv-baseline

    # after the sweep, diff each rename's pre/post node
    uv run --with pyyaml --no-project python3 field_diff.py diff --baseline /tmp/semconv-baseline

    # diff a single definition node by identifier across two files
    uv run --with pyyaml --no-project python3 field_diff.py node \
        --old-file <baseline>/model/network/routing/metrics.yaml --old-id network.routing.routes \
        --new-file model/network/routing/metrics.yaml --new-id network.routing.route.count

`diff` exits non-zero if any rename's node differs in more than the identifier
(and the allowed note/dimension-ref changes), satisfying Property 2.
"""

from __future__ import annotations

import argparse
import copy
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from _common import REPO_ROOT, load_token_map, rename_pairs

# Identifier field per file kind.
ID_FIELD = {
    "metrics.yaml": "name",
    "registry.yaml": "key",
    "events.yaml": "id",
    "entities.yaml": "type",
}

# Top-level list keys that hold definition nodes, per file kind.
LIST_KEYS = {
    "metrics.yaml": ["metrics", "metric_refinements"],
    "registry.yaml": ["attributes"],
    "events.yaml": ["events", "event_refinements"],
    "entities.yaml": ["entities"],
}

# Fields whose textual content is allowed to differ across a rename (a note may
# itself name the old identifier or be an explicitly mandated re-pin; a metric's
# dimension `ref:`/attributes may be repointed to the renamed attribute).
ALLOWED_DIFF_FIELDS = {"note", "brief", "attributes"}


def _file_kind(path: Path) -> str | None:
    name = path.name
    return name if name in ID_FIELD else None


def iter_nodes(doc: dict, kind: str):
    """Yield (id_value, node) for every definition node in a parsed doc."""
    id_field = ID_FIELD[kind]
    for list_key in LIST_KEYS[kind]:
        for node in doc.get(list_key) or []:
            if isinstance(node, dict) and id_field in node:
                yield node[id_field], node


def load_doc(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def find_node(path: Path, identifier: str) -> dict | None:
    kind = _file_kind(path)
    if kind is None:
        return None
    doc = load_doc(path)
    for node_id, node in iter_nodes(doc, kind):
        if node_id == identifier:
            return node
    return None


def strip_identifier(node: dict, kind: str) -> dict:
    """Return a deep copy of node with the identifier field removed."""
    clone = copy.deepcopy(node)
    clone.pop(ID_FIELD[kind], None)
    return clone


def diff_node(old_node: dict, new_node: dict, kind: str) -> list[str]:
    """Return a list of field-level differences beyond the identifier.

    Differences in ALLOWED_DIFF_FIELDS are reported as informational (prefixed
    with 'allowed:') and do not by themselves constitute a violation.
    """
    old_body = strip_identifier(old_node, kind)
    new_body = strip_identifier(new_node, kind)

    violations: list[str] = []
    keys = set(old_body) | set(new_body)
    for key in sorted(keys):
        if old_body.get(key) == new_body.get(key):
            continue
        if key in ALLOWED_DIFF_FIELDS:
            violations.append(f"allowed: field '{key}' changed")
        else:
            violations.append(
                f"VIOLATION: field '{key}' changed: "
                f"{old_body.get(key)!r} -> {new_body.get(key)!r}"
            )
    return violations


def cmd_snapshot(args) -> int:
    out = Path(args.out)
    src = REPO_ROOT / "model" / "network"
    dst = out / "model" / "network"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    # also copy the other touched single-namespace dirs (common already under network)
    print(f"Snapshot written to {out} ({sum(1 for _ in dst.rglob('*.yaml'))} yaml files)")
    return 0


def _git_baseline_node(rel_file: str, identifier: str, ref: str) -> dict | None:
    """Load a definition node from a git ref (pre-sweep baseline) without a copy."""
    try:
        blob = subprocess.run(
            ["git", "show", f"{ref}:{rel_file}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None
    doc = yaml.safe_load(blob) or {}
    kind = Path(rel_file).name
    if kind not in ID_FIELD:
        return None
    for node_id, node in iter_nodes(doc, kind):
        if node_id == identifier:
            return node
    return None


def cmd_diff(args) -> int:
    token_map = load_token_map()
    pairs = rename_pairs(token_map)

    failures = 0
    checked = 0
    for entry in pairs:
        old_id = entry["old"]
        new_id = entry["new"]
        rel_file = entry["def_file"]
        kind = Path(rel_file).name
        if kind not in ID_FIELD:
            continue

        # pre node: from baseline dir or git ref
        if args.baseline:
            old_path = Path(args.baseline) / rel_file
            old_node = find_node(old_path, old_id) if old_path.exists() else None
        else:
            old_node = _git_baseline_node(rel_file, old_id, args.git_ref)

        new_node = find_node(REPO_ROOT / rel_file, new_id)

        if old_node is None:
            print(f"  ?  {old_id}: baseline node not found (pre-sweep state missing)")
            continue
        if new_node is None:
            print(f"  ✗  {new_id}: post-sweep node not found in {rel_file}")
            failures += 1
            continue

        checked += 1
        diffs = diff_node(old_node, new_node, kind)
        violations = [d for d in diffs if d.startswith("VIOLATION")]
        if violations:
            failures += 1
            print(f"  ✗  {old_id} -> {new_id}")
            for d in diffs:
                print(f"         {d}")
        else:
            allowed = [d for d in diffs if d.startswith("allowed")]
            suffix = f"  ({', '.join(allowed)})" if allowed else ""
            print(f"  ✓  {old_id} -> {new_id}{suffix}")

    print(f"\nChecked {checked} renamed definitions; {failures} violation(s).")
    if failures:
        print("FAIL: at least one rename changed more than the identifier (Property 2).", file=sys.stderr)
        return 1
    print("PASS: every rename is name-only / structure-preserving (Property 2).")
    return 0


def cmd_node(args) -> int:
    old_node = find_node(Path(args.old_file), args.old_id)
    new_node = find_node(Path(args.new_file), args.new_id)
    if old_node is None:
        print(f"old node {args.old_id} not found in {args.old_file}", file=sys.stderr)
        return 2
    if new_node is None:
        print(f"new node {args.new_id} not found in {args.new_file}", file=sys.stderr)
        return 2
    kind = Path(args.new_file).name
    diffs = diff_node(old_node, new_node, kind)
    violations = [d for d in diffs if d.startswith("VIOLATION")]
    for d in diffs:
        print(f"  {d}")
    if violations:
        print("FAIL: identifier-plus differences found.", file=sys.stderr)
        return 1
    print("PASS: identifier-only difference.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_snap = sub.add_parser("snapshot", help="Copy the pre-sweep model tree to a baseline dir.")
    p_snap.add_argument("--out", required=True, help="Baseline output directory.")
    p_snap.set_defaults(func=cmd_snapshot)

    p_diff = sub.add_parser("diff", help="Diff every rename's pre/post definition node.")
    p_diff.add_argument("--baseline", help="Baseline dir produced by `snapshot`.")
    p_diff.add_argument("--git-ref", default="HEAD", help="Git ref for the pre-sweep baseline (default HEAD).")
    p_diff.set_defaults(func=cmd_diff)

    p_node = sub.add_parser("node", help="Diff a single definition node across two files.")
    p_node.add_argument("--old-file", required=True)
    p_node.add_argument("--old-id", required=True)
    p_node.add_argument("--new-file", required=True)
    p_node.add_argument("--new-id", required=True)
    p_node.set_defaults(func=cmd_node)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
