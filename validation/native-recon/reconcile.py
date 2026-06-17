#!/usr/bin/env python3
"""Cross-transport reconciliation — the multi-observer rule on a real NOS.

Derives the SAME SR Linux device's identity independently over two genuinely
different management protocols — SNMP (IF-MIB) and gNMI (OpenConfig/YANG) — and
checks they converge on one `network.device.id` and one set of
`network.interface.name` identities.

This is the strong version of engine/reconcile.py: there the two "observers" both
read the same Linux hostname string, so convergence was near-tautological. Here the
observers are different wire protocols with different encodings and different data
models, so agreement is a real result — and the disagreements are informative.

Identity sources:
  SNMP   device.id   = sysName.0                  (1.3.6.1.2.1.1.5.0)
         interfaces  = ifName                     (1.3.6.1.2.1.31.1.1.1.1)
  gNMI   device.id   = /system/name/host-name
         interfaces  = /interface[name=*]/name
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

TARGET = os.environ.get("TARGET", "172.22.22.11")
NET = os.environ.get("NET", "srlmgmt")
SNMP_IMG = os.environ.get("SNMP_IMG", "srlrecon-snmptools")
GNMI_IMG = os.environ.get("GNMI_IMG", "ghcr.io/openconfig/gnmic:latest")
GNMI_USER = os.environ.get("GNMI_USER", "admin")
GNMI_PASS = os.environ.get("GNMI_PASS", "NokiaSrl1!")


def _run(args: list[str]) -> str:
    p = subprocess.run(
        ["docker", "run", "--rm", "--network", NET, *args],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}\n{p.stderr.strip()}")
    return p.stdout


def snmp_identity() -> tuple[str, set[str]]:
    base = [SNMP_IMG, "snmpget", "-v2c", "-c", "public", "-Oqv", TARGET]
    device_id = _run(base + ["1.3.6.1.2.1.1.5.0"]).strip()
    walk = _run([SNMP_IMG, "snmpwalk", "-v2c", "-c", "public", "-Oqv",
                 TARGET, "1.3.6.1.2.1.31.1.1.1.1"])
    ifaces = {ln.strip() for ln in walk.splitlines() if ln.strip()}
    return device_id, ifaces


def _gnmi(path: str) -> list[dict]:
    out = _run([GNMI_IMG, "-a", f"{TARGET}:57400", "-u", GNMI_USER, "-p", GNMI_PASS,
                "--skip-verify", "-e", "json_ietf", "get", "--path", path])
    return json.loads(out)


def _gnmi_values(doc: list[dict]) -> list:
    vals = []
    for entry in doc:
        for upd in entry.get("updates", []):
            for v in (upd.get("values") or {}).values():
                vals.append(v)
    return vals


def _collect_names(obj, out: set[str]) -> None:
    """Recursively collect every `name` leaf — gNMI `get` returns the interface
    list as one nested value, not one update per interface."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "name" and isinstance(v, str):
                out.add(v)
            else:
                _collect_names(v, out)
    elif isinstance(obj, list):
        for x in obj:
            _collect_names(x, out)


def gnmi_identity() -> tuple[str, set[str]]:
    device_id = str(_gnmi_values(_gnmi("/system/name/host-name"))[0]).strip()
    ifaces: set[str] = set()
    _collect_names(_gnmi("/interface[name=*]/name"), ifaces)
    return device_id, ifaces


def main():
    snmp_dev, snmp_if = snmp_identity()
    gnmi_dev, gnmi_if = gnmi_identity()

    # split base interfaces from subinterfaces (names with a dot, e.g. mgmt0.0):
    # SNMP IF-MIB flattens subinterfaces into ifTable; gNMI models them under
    # /interface/subinterface, so they legitimately differ at this level.
    base = lambda s: {i for i in s if "." not in i}
    sub = lambda s: {i for i in s if "." in i}

    snmp_base, gnmi_base = base(snmp_if), base(gnmi_if)
    only_snmp = sorted(snmp_base - gnmi_base)
    only_gnmi = sorted(gnmi_base - snmp_base)
    sub_diff = sorted((sub(snmp_if) ^ sub(gnmi_if)))

    print("=" * 68)
    print("  cross-transport reconciliation: SNMP vs gNMI, same SR Linux device")
    print("=" * 68)
    print(f"  [snmp]  device.id = {snmp_dev!r}   interfaces = {len(snmp_if)}")
    print(f"  [gnmi]  device.id = {gnmi_dev!r}   interfaces = {len(gnmi_if)}")
    print("-" * 68)
    print(f"  device.id converged:          {snmp_dev == gnmi_dev}  -> {snmp_dev!r}")
    print(f"  base interfaces agree:        {snmp_base == gnmi_base}  "
          f"({len(snmp_base & gnmi_base)} shared)")
    if only_snmp:
        print(f"    only in SNMP (base):        {only_snmp}")
    if only_gnmi:
        print(f"    only in gNMI (base):        {only_gnmi}")
    if sub_diff:
        print(f"  subinterface-level diff:      {sub_diff}")
        print("    (expected: SNMP flattens subinterfaces into ifTable; gNMI")
        print("     models them under /interface/subinterface — not an identity fork)")
    print("-" * 68)

    device_ok = snmp_dev == gnmi_dev and snmp_dev != ""
    base_ok = snmp_base == gnmi_base and len(snmp_base) > 0
    if device_ok and base_ok:
        print("  PASS: both protocols resolve the SAME device.id and the SAME set")
        print("        of physical interface identities. The entity does not fork")
        print("        across collection methods.")
        rc = 0
    else:
        print("  FAIL: the two protocols did not converge on one identity.")
        if not device_ok:
            print(f"        device.id: snmp={snmp_dev!r} vs gnmi={gnmi_dev!r}")
        if not base_ok:
            print(f"        base interfaces differ: -snmp={only_snmp} -gnmi={only_gnmi}")
        rc = 1
    print("=" * 68)
    sys.exit(rc)


if __name__ == "__main__":
    main()
