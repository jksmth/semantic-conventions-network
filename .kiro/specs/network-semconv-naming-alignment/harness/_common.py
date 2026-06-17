"""Shared helpers for the network-semconv-naming-alignment validation harness.

This module is consumed by `token_scan.py` and `field_diff.py`. It locates the
repo root, loads the authoritative `rename-token-map.yaml` (the task 1.1
artifact), and exposes the complete-token (identifier-boundary) matching rule
the sweep and re-scan rely on (Requirement 11.1).

It deliberately has no third-party imports at module top level except PyYAML,
which the wrapper scripts provision via `uv run --with pyyaml` when the
interpreter lacks it (see harness/README.md).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

# --- locations -------------------------------------------------------------

# harness/  ->  network-semconv-naming-alignment/  ->  specs/ -> .kiro/ -> <repo root>
HARNESS_DIR = Path(__file__).resolve().parent
SPEC_DIR = HARNESS_DIR.parent
REPO_ROOT = SPEC_DIR.parents[2]  # .kiro/specs/<spec>/harness -> repo root
TOKEN_MAP_PATH = SPEC_DIR / "rename-token-map.yaml"

# The complete identifier character class: chars that are part of, or would
# extend, a dotted semconv name. A real complete-token match must be bounded by
# a non-member on both sides (Requirement 11.1, token_matching rule).
IDENT_CHARS = r"[A-Za-z0-9_.]"


def load_token_map() -> dict:
    """Load and return the parsed rename-token-map.yaml."""
    with TOKEN_MAP_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def rename_pairs(token_map: dict) -> list[dict]:
    """Return the list of {old, new, kind, decision, def_file, ...} rename entries."""
    return list(token_map.get("rename_map") or [])


def old_names(token_map: dict) -> list[str]:
    """Every pre-rename complete-token identifier (rename_map + repointed structural)."""
    names: list[str] = [e["old"] for e in rename_pairs(token_map) if "old" in e]
    # structural repoint/remove entries also carry an `old`/`name` that must
    # vanish from reference sites after the sweep (e.g. network.interface.id).
    for sc in token_map.get("structural_changes") or []:
        if sc.get("type") in {"repoint_reference"} and "old" in sc:
            names.append(sc["old"])
        if sc.get("type") in {"remove_definition"} and "name" in sc:
            names.append(sc["name"])
    # de-dup, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def complete_token_regex(token: str) -> re.Pattern:
    """Build an identifier-boundary-anchored regex for a complete-token match.

    A match requires the character immediately before and after the token to
    NOT be an identifier char (so `network.nat.ports` never matches inside
    `network.nat.port_blocks` or `network.nat.port.count`).
    """
    return re.compile(rf"(?<!{IDENT_CHARS}){re.escape(token)}(?!{IDENT_CHARS})")


def reference_site_files(token_map: dict) -> list[Path]:
    """Resolve every Reference_Site glob from the token map to concrete files."""
    globs = (token_map.get("meta") or {}).get("reference_site_globs") or []
    files: list[Path] = []
    seen: set[Path] = set()
    for pattern in globs:
        for p in sorted(REPO_ROOT.glob(pattern)):
            if p.is_file() and p not in seen:
                seen.add(p)
                files.append(p)
    return files
