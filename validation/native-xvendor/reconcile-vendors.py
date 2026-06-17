#!/usr/bin/env python3
"""Cross-vendor identity reconciliation — the multi-observer rule, across vendors.

`../native-recon` proved the SAME device resolves to ONE identity over two
transports (SNMP vs gNMI). This asks the cross-*vendor* question: when the SAME
identity-derivation rule (sysName -> network.device.id, ifName ->
network.interface.name, over the SAME SNMP OIDs) is applied to a Nokia box and a
Cisco box, does it yield valid, DISTINCT, collision-free, device-scoped identities
— without per-vendor special-casing?

That is the model's cross-vendor identity claim:
  - one vendor-agnostic rule works on both,
  - interface identity is the device-scoped pair (device.id, interface.name), so
    heterogeneous name forms (ethernet-1/1 vs Et0/0) never collide across vendors.
"""
from __future__ import annotations

import os
import subprocess
import sys

TOOLS_IMG = os.environ.get("TOOLS_IMG", "xvendor-snmptools")

VENDORS = [
    {"name": "nokia-srlinux", "net": "srlmgmt", "target": "172.22.22.11"},
    {"name": "cisco-iosxe", "net": "ciscomgmt", "target": "172.30.30.11"},
]
SYSNAME = "1.3.6.1.2.1.1.5.0"        # SNMPv2-MIB::sysName.0  -> network.device.id
IFNAME = "1.3.6.1.2.1.31.1.1.1.1"    # IF-MIB::ifName         -> network.interface.name


def _snmp(net: str, args: list[str]) -> str:
    p = subprocess.run(
        ["docker", "run", "--rm", "--network", net, TOOLS_IMG, *args],
        capture_output=True, text=True,
    )
    return p.stdout


def device_id(v) -> str:
    return _snmp(v["net"], ["snmpget", "-v2c", "-c", "public", "-Oqv", "-t", "5",
                            v["target"], SYSNAME]).strip()


def interfaces(v) -> set[str]:
    out = _snmp(v["net"], ["snmpwalk", "-v2c", "-c", "public", "-Oqv", "-t", "5",
                           v["target"], IFNAME])
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


def main():
    observed = []
    for v in VENDORS:
        observed.append((v["name"], device_id(v), interfaces(v)))

    print("=" * 70)
    print("  cross-vendor identity reconciliation (one rule, two vendors)")
    print("=" * 70)
    for name, did, ifs in observed:
        sample = sorted(ifs)[:4]
        print(f"  [{name}]")
        print(f"     network.device.id      = {did!r}")
        print(f"     network.interface.name = {len(ifs)} ifaces, e.g. {sample}")

    ids = [did for _, did, _ in observed]
    # device-scoped interface identities — the (device.id, ifname) pairs
    scoped = {(did, i) for _, did, ifs in observed for i in ifs}
    total = sum(len(ifs) for _, _, ifs in observed)
    # would interface NAMES alone collide across vendors?
    name_sets = [ifs for _, _, ifs in observed]
    raw_overlap = sorted(set.intersection(*name_sets)) if name_sets else []

    all_have_id = all(ids)
    distinct_ids = len(set(ids)) == len(ids)
    rule_worked = all(len(ifs) > 0 for _, _, ifs in observed)
    collision_free = len(scoped) == total

    print("-" * 70)
    print(f"  same rule produced an id + interfaces on every vendor: {rule_worked}")
    print(f"  device.ids distinct (no cross-vendor clash):           {distinct_ids}  {ids}")
    print(f"  interface NAMES that overlap across vendors:           {raw_overlap or 'none'}")
    print(f"  device-scoped identities (device.id, ifname):          {len(scoped)} of {total}, "
          f"all unique = {collision_free}")
    if raw_overlap:
        print("    (note: names overlap, but the device-scoped pair keeps them distinct —")
        print("     this is exactly why interface identity is scoped by device.id)")
    print("-" * 70)

    ok = all_have_id and distinct_ids and rule_worked and collision_free
    if ok:
        print("  PASS: one vendor-agnostic rule yields valid, distinct, collision-free")
        print("        device-scoped identities across Nokia and Cisco. No per-vendor")
        print("        special-casing; heterogeneous name forms do not fork the model.")
    else:
        print("  FAIL:")
        if not rule_worked:
            print("        the identity rule returned nothing on a vendor (SNMP issue?)")
        if not (all_have_id and distinct_ids):
            print(f"        device.id problem: {ids}")
        if not collision_free:
            print("        device-scoped identity collision detected")
    print("=" * 70)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
