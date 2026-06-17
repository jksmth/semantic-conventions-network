#!/usr/bin/env python3
"""Read-only validation guards for tasks 13.4 and 13.5.

Task 13.4 — Stability guard (Property 10):
    Every signal affected by Requirements 1-11 is at `development` stability.
    Any other stability (e.g. `stable`) on an affected signal is a failure.

Task 13.5 — Non-over-reach / keep-inventory guard (Property 3 + Property 9):
    The full keep inventory (from rename-token-map.yaml `keep_inventory`) is
    UNCHANGED (still present with its original names), the two QoS depth gauges
    are separate with no current-vs-max selecting attribute, the neighbor
    namespace is intact with no `network.peer` replacement, and NO deprecation
    residue exists for any old name (no `deprecated` markers, no alias/duplicate
    definitions for pre-rename identifiers).

These guards are READ-ONLY assertions over the current `model/network/**` tree.
They never edit the model.

Run:
    cd .kiro/specs/network-semconv-naming-alignment/harness
    uv run --with pyyaml --no-project python3 guards_13_4_13_5.py
    uv run --with pyyaml --no-project python3 guards_13_4_13_5.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from _common import (
    REPO_ROOT,
    load_token_map,
    old_names,
    rename_pairs,
)

NETWORK_ROOT = REPO_ROOT / "model" / "network"


# --------------------------------------------------------------------------
# Model loading / signal extraction
# --------------------------------------------------------------------------

def _model_files() -> list[Path]:
    return sorted(NETWORK_ROOT.glob("**/*.yaml"))


def _iter_signals(doc: dict, path: Path):
    """Yield (kind, name, stability, node) for every signal in a parsed doc.

    kinds: metric (name:), event (id:), attribute (key:), entity (type:).
    """
    if not isinstance(doc, dict):
        return
    for node in doc.get("metrics") or []:
        if isinstance(node, dict) and "name" in node:
            yield "metric", node["name"], node.get("stability"), node
    # events live under either `events:` or `event_refinements:`
    for coll in ("events", "event_refinements"):
        for node in doc.get(coll) or []:
            if isinstance(node, dict) and "id" in node:
                yield "event", node["id"], node.get("stability"), node
    # attribute groups: top-level `attributes:` list of {key: ...}
    for node in doc.get("attributes") or []:
        if isinstance(node, dict) and "key" in node:
            yield "attribute", node["key"], node.get("stability"), node
    # entities
    for node in doc.get("entities") or []:
        if isinstance(node, dict) and "type" in node:
            yield "entity", node["type"], node.get("stability"), node
    # `groups:` style (defensive — older semconv layout)
    for node in doc.get("groups") or []:
        if not isinstance(node, dict):
            continue
        for attr in node.get("attributes") or []:
            if isinstance(attr, dict) and "id" in attr and "ref" not in attr:
                yield "attribute", attr["id"], attr.get("stability"), attr


def load_all_signals() -> list[dict]:
    """Return a flat list of every defined signal across model/network/**."""
    signals: list[dict] = []
    for path in _model_files():
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for kind, name, stability, node in _iter_signals(doc, path):
            signals.append(
                {
                    "kind": kind,
                    "name": name,
                    "stability": stability,
                    "file": rel,
                    "node": node,
                }
            )
    return signals


def signal_names(signals: list[dict]) -> set[str]:
    return {s["name"] for s in signals}


# --------------------------------------------------------------------------
# Guard 13.4 — stability (Property 10)
# --------------------------------------------------------------------------

def guard_stability(signals: list[dict]) -> dict:
    """Assert every signal affected by Req 1-11 is at `development`.

    The set of "affected" signals is the union of:
      - every NEW name from the rename_map (the renamed signals),
      - every additive/structural name introduced by the decisions,
    that is actually present in the current tree.

    We also report the whole-tree stability distribution as a superset check
    (the spec is a single coordinated landing at development stability).
    """
    token_map = load_token_map()
    by_name: dict[str, dict] = {}
    for s in signals:
        by_name.setdefault(s["name"], s)

    # affected = new names from rename_map + additive structural names
    affected: set[str] = set()
    for e in rename_pairs(token_map):
        if "new" in e:
            affected.add(e["new"])
    for sc in token_map.get("structural_changes") or []:
        if sc.get("type") in {"add_definition"} and "name" in sc:
            affected.add(sc["name"])
        if sc.get("type") == "repoint_reference" and "new" in sc:
            affected.add(sc["new"])

    affected_present = sorted(n for n in affected if n in by_name)
    affected_missing = sorted(n for n in affected if n not in by_name)

    # Failures: any affected (present) signal whose stability != development
    failures = []
    for name in affected_present:
        stab = by_name[name]["stability"]
        if stab != "development":
            failures.append(
                {"name": name, "stability": stab, "file": by_name[name]["file"]}
            )

    # Whole-tree superset check
    non_dev = [
        {"name": s["name"], "kind": s["kind"], "stability": s["stability"], "file": s["file"]}
        for s in signals
        if s["stability"] != "development"
    ]

    return {
        "guard": "13.4 stability (Property 10)",
        "affected_present_count": len(affected_present),
        "affected_missing": affected_missing,
        "affected_failures": failures,
        "tree_total_signals": len(signals),
        "tree_non_development": non_dev,
        "passed": not failures and not non_dev,
    }


# --------------------------------------------------------------------------
# Guard 13.5 — keep inventory (Property 3) + deprecation residue (Property 9)
# --------------------------------------------------------------------------

def _expand_keep_names(keep: dict) -> dict[str, list[str]]:
    """Return {category: [literal names]} for concrete (non-prefix) keep names."""
    cats: dict[str, list[str]] = {}
    cats["monotonic_counters"] = list(keep.get("monotonic_counters") or [])
    cats["already_correct_count"] = list(keep.get("already_correct_count") or [])
    cats["qos_depth_gauges"] = list(keep.get("qos_depth_gauges") or [])
    cats["already_dotted_limit_attrs"] = list(keep.get("already_dotted_limit_attrs") or [])
    cats["per_domain_state_leaves"] = list(keep.get("per_domain_state_leaves") or [])
    cats["sub_entity_id_keys"] = list(keep.get("sub_entity_id_keys") or [])
    cats["interface_mtu_key"] = list(keep.get("interface_mtu_key") or [])
    # FDB keep items: drop the wildcard prefix entry, keep the literals
    fdb = [n for n in (keep.get("fdb_keep_items") or []) if not n.endswith("*")]
    cats["fdb_keep_items"] = fdb
    return cats


def guard_keep_inventory(signals: list[dict]) -> dict:
    token_map = load_token_map()
    keep = token_map.get("keep_inventory") or {}
    names_present = signal_names(signals)

    # raw text of all model files for prefix / leaf / substring checks
    file_texts: dict[str, str] = {}
    for path in _model_files():
        try:
            file_texts[path.relative_to(REPO_ROOT).as_posix()] = path.read_text(
                encoding="utf-8"
            )
        except (OSError, UnicodeDecodeError):
            continue
    all_text = "\n".join(file_texts.values())

    results: dict[str, dict] = {}

    # ---- concrete fully-qualified keep names must be PRESENT as definitions --
    cats = _expand_keep_names(keep)
    for cat, names in cats.items():
        missing = [n for n in names if n not in names_present]
        # Some keep names are attribute *definitions* whose `key:` lives in a
        # registry; metric/event names live under name:/id:. names_present
        # already unions all four kinds, so a literal must appear there.
        results[cat] = {
            "expected": names,
            "missing": missing,
            "passed": not missing,
        }

    # ---- QoS depth gauges: two SEPARATE gauges, no current-vs-max selector ---
    qos = guard_qos_depth(signals)
    results["qos_depth_gauges_detail"] = qos

    # ---- acceptable snake_case leaves: present as a leaf segment somewhere ----
    snake = [n for n in (keep.get("acceptable_snake_case_leaves") or []) if not n.endswith("*")]
    snake_missing = []
    for leaf in snake:
        # leaf appears as a dotted leaf segment `.leaf` or standalone key
        token = f".{leaf}"
        if token not in all_text and f"{leaf}" not in all_text:
            snake_missing.append(leaf)
    results["acceptable_snake_case_leaves"] = {
        "expected": snake,
        "missing": snake_missing,
        "passed": not snake_missing,
    }

    # ---- FDB previous_interface.* prefix present -----------------------------
    prev_iface_present = "network.l2.mac.previous_interface." in all_text
    results["fdb_previous_interface_prefix"] = {
        "expected_prefix": "network.l2.mac.previous_interface.*",
        "present": prev_iface_present,
        "passed": prev_iface_present,
    }

    # ---- neighbor namespace intact + no network.peer replacement -------------
    neighbor = guard_neighbor_namespace(signals, all_text)
    results["neighbor_namespace"] = neighbor

    return {
        "guard": "13.5 keep-inventory (Property 3)",
        "categories": results,
        "passed": all(
            v.get("passed", True) for v in results.values()
        ),
    }


def guard_qos_depth(signals: list[dict]) -> dict:
    """Both QoS depth gauges exist as separate gauges with no stat selector."""
    depth = next(
        (s for s in signals if s["name"] == "network.qos.queue.depth"), None
    )
    depth_max = next(
        (s for s in signals if s["name"] == "network.qos.queue.depth.max"), None
    )
    problems: list[str] = []
    if depth is None:
        problems.append("network.qos.queue.depth missing")
    if depth_max is None:
        problems.append("network.qos.queue.depth.max missing")

    # both must be gauges
    for sig, label in ((depth, "depth"), (depth_max, "depth.max")):
        if sig is not None:
            instr = sig["node"].get("instrument")
            if instr != "gauge":
                problems.append(f"{label} instrument={instr!r} (expected gauge)")

    # neither may carry a stat / current-vs-max selecting attribute
    forbidden_tokens = ("stat", "statistic", "current_max", "current_vs_max", "min_max")
    for sig, label in ((depth, "depth"), (depth_max, "depth.max")):
        if sig is None:
            continue
        for attr in sig["node"].get("attributes") or []:
            ref = (attr.get("ref") or attr.get("id") or "").lower()
            if any(tok in ref for tok in forbidden_tokens):
                problems.append(f"{label} carries selecting attribute {ref!r}")

    return {
        "depth_present": depth is not None,
        "depth_max_present": depth_max is not None,
        "separate_gauges": depth is not None and depth_max is not None,
        "problems": problems,
        "passed": not problems,
    }


def guard_neighbor_namespace(signals: list[dict], all_text: str) -> dict:
    neighbor_names = sorted(n for n in signal_names(signals) if n.startswith("network.neighbor"))
    # network.peer must not appear as a REPLACEMENT for network.neighbor — i.e.
    # it must not be used as a definition (key:/name:/id:/type:) or as a model
    # ref: standing in for a neighbour concept. Explanatory PROSE that mentions
    # network.peer (e.g. notes affirming it is deliberately NOT used, or that
    # reference the upstream Stable socket attrs network.peer.address/.port) is
    # NOT a replacement and must not trip the guard.
    structural_prefixes = ("key:", "name:", "id:", "type:", "ref:")
    peer_replacement_hits = []
    peer_prose_mentions = []
    for path in _model_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "network.peer" not in line:
                continue
            stripped = line.strip()
            # strip a leading YAML list dash to inspect the field key
            field = stripped[1:].strip() if stripped.startswith("- ") else stripped
            is_structural = field.startswith(structural_prefixes)
            hit = {
                "file": path.relative_to(REPO_ROOT).as_posix(),
                "line": lineno,
                "text": stripped,
            }
            if is_structural:
                peer_replacement_hits.append(hit)
            else:
                peer_prose_mentions.append(hit)
    return {
        "neighbor_name_count": len(neighbor_names),
        "neighbor_present": len(neighbor_names) > 0,
        "network_peer_replacement_uses": peer_replacement_hits,
        "network_peer_prose_mentions": peer_prose_mentions,
        "passed": len(neighbor_names) > 0 and not peer_replacement_hits,
    }


def guard_deprecation_residue(signals: list[dict]) -> dict:
    """Property 9: no deprecation residue and no alias/duplicate for old names."""
    token_map = load_token_map()
    olds = set(old_names(token_map))

    problems: list[dict] = []

    # 1. No `deprecated` marker anywhere in the tree
    deprecated_hits: list[dict] = []
    for path in _model_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            low = line.lower()
            if "deprecated" in low:
                deprecated_hits.append(
                    {"file": path.relative_to(REPO_ROOT).as_posix(), "line": lineno, "text": line.strip()}
                )

    # 2. No defined signal still carries a pre-rename identifier (alias/dup)
    defined = signal_names(signals)
    surviving_old_defs = sorted(olds & defined)

    passed = not deprecated_hits and not surviving_old_defs
    return {
        "guard": "13.5 deprecation residue (Property 9)",
        "deprecated_markers": deprecated_hits,
        "surviving_old_definitions": surviving_old_defs,
        "passed": passed,
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def run() -> dict:
    signals = load_all_signals()
    return {
        "stability": guard_stability(signals),
        "keep_inventory": guard_keep_inventory(signals),
        "deprecation_residue": guard_deprecation_residue(signals),
    }


def _print_report(report: dict) -> None:
    stab = report["stability"]
    keep = report["keep_inventory"]
    dep = report["deprecation_residue"]

    print("=" * 72)
    print("TASK 13.4 — Stability guard (Property 10)")
    print("=" * 72)
    print(f"  affected signals present : {stab['affected_present_count']}")
    if stab["affected_missing"]:
        print(f"  (not present in tree)    : {stab['affected_missing']}")
    print(f"  total signals in tree    : {stab['tree_total_signals']}")
    if stab["affected_failures"]:
        print("  AFFECTED FAILURES:")
        for f in stab["affected_failures"]:
            print(f"    - {f['name']}: stability={f['stability']!r} ({f['file']})")
    if stab["tree_non_development"]:
        print("  NON-DEVELOPMENT SIGNALS:")
        for f in stab["tree_non_development"]:
            print(f"    - {f['name']} [{f['kind']}]: stability={f['stability']!r} ({f['file']})")
    print(f"  RESULT: {'PASS' if stab['passed'] else 'FAIL'}\n")

    print("=" * 72)
    print("TASK 13.5 — Keep-inventory / non-over-reach guard (Property 3)")
    print("=" * 72)
    for cat, res in keep["categories"].items():
        if cat in ("qos_depth_gauges_detail", "neighbor_namespace", "fdb_previous_interface_prefix"):
            continue
        status = "PASS" if res.get("passed", True) else "FAIL"
        n = len(res.get("expected", []))
        print(f"  [{status}] {cat}: {n} name(s) checked")
        if res.get("missing"):
            print(f"           MISSING: {res['missing']}")
    qos = keep["categories"]["qos_depth_gauges_detail"]
    print(f"  [{'PASS' if qos['passed'] else 'FAIL'}] qos depth gauges: "
          f"separate={qos['separate_gauges']}, no-selector={not qos['problems']}")
    if qos["problems"]:
        print(f"           PROBLEMS: {qos['problems']}")
    prev = keep["categories"]["fdb_previous_interface_prefix"]
    print(f"  [{'PASS' if prev['passed'] else 'FAIL'}] fdb previous_interface.* prefix present={prev['present']}")
    nb = keep["categories"]["neighbor_namespace"]
    print(f"  [{'PASS' if nb['passed'] else 'FAIL'}] neighbor namespace: "
          f"{nb['neighbor_name_count']} names, "
          f"network.peer replacement-uses={len(nb['network_peer_replacement_uses'])}, "
          f"prose-mentions={len(nb['network_peer_prose_mentions'])} (allowed)")
    if nb["network_peer_replacement_uses"]:
        for h in nb["network_peer_replacement_uses"]:
            print(f"           REPLACEMENT network.peer -> {h['file']}:{h['line']}: {h['text']}")
    print(f"  RESULT: {'PASS' if keep['passed'] else 'FAIL'}\n")

    print("=" * 72)
    print("TASK 13.5 — Deprecation-residue guard (Property 9)")
    print("=" * 72)
    print(f"  `deprecated` markers      : {len(dep['deprecated_markers'])}")
    for h in dep["deprecated_markers"]:
        print(f"    - {h['file']}:{h['line']}: {h['text']}")
    print(f"  surviving old definitions : {len(dep['surviving_old_definitions'])}")
    for n in dep["surviving_old_definitions"]:
        print(f"    - {n}")
    print(f"  RESULT: {'PASS' if dep['passed'] else 'FAIL'}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    report = run()
    # node objects are not JSON-serializable; strip them for JSON output
    if args.json:
        def _strip(o):
            if isinstance(o, dict):
                return {k: _strip(v) for k, v in o.items() if k != "node"}
            if isinstance(o, list):
                return [_strip(v) for v in o]
            return o
        print(json.dumps(_strip(report), indent=2))
    else:
        _print_report(report)

    all_pass = (
        report["stability"]["passed"]
        and report["keep_inventory"]["passed"]
        and report["deprecation_residue"]["passed"]
    )
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
