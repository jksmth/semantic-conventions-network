"""Acquire raw source documents — live from the device, or from a cached file.

This is the only place that knows "live vs offline". An adapter declares *what*
documents it needs (a command to run live, a filename to read offline); the
collector fetches them. Live is the default and the honest proof; offline reads
a frozen snapshot for CI that cannot boot the lab.
"""
from __future__ import annotations

import pathlib
import subprocess


def get_live(container: str, argv: list[str]) -> str:
    """Run a command inside the device container and return its stdout."""
    proc = subprocess.run(
        ["docker", "exec", container, *argv],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"live collect failed: docker exec {container} {' '.join(argv)}\n{proc.stderr.strip()}"
        )
    return proc.stdout


def get_cached(fixtures: pathlib.Path, filename: str) -> str:
    return (pathlib.Path(fixtures) / filename).read_text()
