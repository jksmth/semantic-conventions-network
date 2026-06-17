#!/usr/bin/env python3
"""Cross-vendor TOPOLOGY reconciliation — two vendors, one link.

The strongest multi-observer test: a Nokia SR Linux and a Cisco IOS-XE box are
wired together and run LLDP. Each independently reports its view of the adjacency
over a *different* access method (Cisco via SSH CLI, SR Linux via its CLI/state).
We reconcile the two directed views into ONE undirected `network.link`:

    Cisco  : Et0/1        --LLDP-->  srl1 / ethernet-1/1
    SRLinux: ethernet-1/1 --LLDP-->  cr1.lab / Et0/1

If both compose to the same {(device.id, interface.name), (device.id,
interface.name)} pair, the link does not fork across vendors/observers. The two
normalizations needed (strip the domain Cisco adds to sysName; expand Cisco's
`Et0/1` to `Ethernet0/1`) are the real cross-vendor reconciliation work.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

NET = os.environ.get("NET", "xvmgmt")
CR1 = os.environ.get("CR1", "172.40.40.12")
SRL1_CTR = os.environ.get("SRL1_CTR", "clab-xvendor-srl1")
SSH_IMG = os.environ.get("SSH_IMG", "xtopo-ssh")
DATA_PORT_CISCO = "Et0/1"       # the wired data port on Cisco
DATA_PORT_SRL = "ethernet-1/1"  # the wired data port on SR Linux


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True).stdout


def _cisco(cmd: str) -> str:
    ssh = (f"sshpass -p admin ssh -o StrictHostKeyChecking=no "
           f"-o UserKnownHostsFile=/dev/null -o ConnectTimeout=12 admin@{CR1} '{cmd}'")
    return _run(["docker", "run", "--rm", "--network", NET, SSH_IMG, "sh", "-c", ssh])


def _srl(cmd: str) -> str:
    return _run(["docker", "exec", SRL1_CTR, "sr_cli", "-c", cmd])


# --- normalization (the cross-vendor reconciliation glue) ------------------
def norm_dev(d: str) -> str:
    return d.split(".")[0].strip().lower()          # cr1.lab -> cr1


def norm_port(p: str) -> str:
    p = p.strip()
    m = re.match(r"^Et(?:hernet)?(\d.*)$", p, re.I)  # Et0/1 / Ethernet0/1 -> ethernet0/1
    if m:
        return ("ethernet" + m.group(1)).lower()
    return p.lower()


def endpoint(dev: str, port: str) -> tuple[str, str]:
    return (norm_dev(dev), norm_port(port))


# --- observers -------------------------------------------------------------
def cisco_view():
    host = "cr1"
    m = re.search(r"^hostname\s+(\S+)", _cisco("show running-config | include ^hostname"), re.M)
    if m:
        host = m.group(1)
    # `show lldp neighbors` rows: <DeviceID> <LocalIntf> <Hold> <Cap> <PortID>
    nbrs = _cisco("show lldp neighbors")
    for ln in nbrs.splitlines():
        f = ln.split()
        if len(f) >= 5 and f[1].lower().startswith("et") and f[1] == DATA_PORT_CISCO:
            return {
                "observer": "cisco-iosxe",
                "local": endpoint(host, f[1]),
                "remote": endpoint(f[0], f[-1]),
            }
    return None


def srl_view():
    host = "srl1"
    m = re.search(r"system-name\s+(\S+)", _srl("info from state system lldp system-name"))
    if m:
        host = m.group(1)
    out = _srl(f"info from state system lldp interface {DATA_PORT_SRL} neighbor *")
    sysname = re.search(r"system-name\s+(\S+)", out)
    portid = re.search(r"port-id\s+(\S+)", out)
    if sysname and portid:
        return {
            "observer": "nokia-srlinux",
            "local": endpoint(host, DATA_PORT_SRL),
            "remote": endpoint(sysname.group(1), portid.group(1)),
        }
    return None


def main():
    a, b = cisco_view(), srl_view()

    print("=" * 70)
    print("  cross-vendor topology reconciliation (two vendors, one link)")
    print("=" * 70)
    for v in (a, b):
        if v:
            print(f"  [{v['observer']}]  local {v['local']}  --LLDP-->  remote {v['remote']}")
        else:
            print("  [missing observer view]")
    if not a or not b:
        print("-" * 70)
        print("  FAIL: one side reported no LLDP neighbor on the data link.")
        print("        (is Cisco Et0/1 'no shutdown'? has LLDP converged?)")
        print("=" * 70)
        sys.exit(1)

    link_a = frozenset({a["local"], a["remote"]})
    link_b = frozenset({b["local"], b["remote"]})
    mirror = (a["remote"] == b["local"]) and (b["remote"] == a["local"])

    print("-" * 70)
    print(f"  Cisco's link  : {set(link_a)}")
    print(f"  SR Linux's link: {set(link_b)}")
    print(f"  same undirected link: {link_a == link_b}")
    print(f"  proper mirror (each side's remote == other's local): {mirror}")
    print("-" * 70)
    if link_a == link_b and mirror:
        print("  PASS: both vendors independently observe the SAME link and it")
        print("        reconciles to one undirected network.link:")
        ep = sorted(link_a)
        print(f"        {ep[0]}  <-->  {ep[1]}")
        print("        (after normalizing Cisco's domain-suffixed sysName and its")
        print("         Et0/1 -> Ethernet0/1 abbreviation — the cross-vendor glue)")
        sys.exit(0)
    print("  FAIL: the two observers did not reconcile to one link.")
    sys.exit(1)


if __name__ == "__main__":
    main()
