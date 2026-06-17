#!/usr/bin/env python3
"""Reconciliation check — the multi-observer rule, demonstrated not asserted.

Collects from each source (live by default) and checks both methods resolve the
same devices to the same network.device.id and agree on interface identities.
A mismatch would fork the entity across collectors, so it FAILS.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import adapters  # noqa: E402
import mapper  # noqa: E402
import run  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["live", "offline"], default="live")
    ap.add_argument("--fixtures", default=str(ROOT / "fixtures"))
    ap.add_argument("--devices", default=str(ROOT / "labs" / "frr" / "devices.yaml"))
    args = ap.parse_args()

    devices_meta = run.load_devices(args.devices)
    fixtures = pathlib.Path(args.fixtures)

    per_source = {}
    for source in adapters.SOURCES:
        obs = run.observations_for(source, args.mode, fixtures, devices_meta)
        per_source[source] = mapper.identities(obs, run.load_crosswalk(source))

    names = list(per_source)
    print("=" * 64)
    print("  reconciliation: do independent observers converge on one identity?")
    print("=" * 64)
    for s in names:
        d = sorted(per_source[s]["devices"])
        i = sorted(f"{a}:{b}" for a, b in per_source[s]["interfaces"])
        print(f"  [{s}]")
        print(f"     devices     = {d}")
        print(f"     interfaces  = {i}")

    a, b = names[0], names[1]
    dev_a, dev_b = per_source[a]["devices"], per_source[b]["devices"]
    if_a, if_b = per_source[a]["interfaces"], per_source[b]["interfaces"]
    shared_ifaces = if_a & if_b

    print("-" * 64)
    print(f"  device.id converged on both methods:         {sorted(dev_a & dev_b)}")
    print(f"  (device.id, interface.name) on both methods: {sorted(f'{x}:{y}' for x, y in shared_ifaces)}")
    failed = (dev_a != dev_b) or not shared_ifaces
    print("-" * 64)
    if failed:
        print("  FAIL: observers did not converge on a shared identity.")
        print(f"        devices {a}={sorted(dev_a)} vs {b}={sorted(dev_b)}")
    else:
        print("  PASS: both methods resolve the same devices to the same")
        print("        network.device.id, and agree on interface identities.")
    print("=" * 64)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
