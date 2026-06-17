"""Linux iproute2 adapter: `ip -j -s link` -> IR.

A different subsystem from FRR (kernel netlink), different field names, and the
byte/packet counters FRR's CLI lacks. device_id is the kernel hostname — the
SAME documented id source FRR uses, so the two observers converge.
"""
from __future__ import annotations

import json

from ir import Observation, Record

SOURCE = "linux-iproute2"

DOCS = {
    "hostname": {
        "live": ["cat", "/proc/sys/kernel/hostname"],
        "fixture": "{tag}.linux-hostname.txt",
    },
    "links": {
        "live": ["ip", "-j", "-s", "link"],
        "fixture": "{tag}.linux.links.json",
    },
}


def container(tag: str) -> str:
    return f"netlab-{tag}"


def parse(docs: dict[str, str], meta: dict) -> Observation:
    device_id = docs["hostname"].strip()
    obs = Observation(source=SOURCE, device_id=device_id)
    obs.records.append(Record(kind="device", index=None, fields=dict(meta)))

    for link in json.loads(docs["links"]):
        name = link.get("ifname")
        if not name:
            continue
        stats = link.get("stats64", {})
        rx, tx = stats.get("rx", {}), stats.get("tx", {})
        obs.records.append(
            Record(
                kind="interface",
                index=name,
                fields={
                    "operstate": link.get("operstate"),
                    "address": link.get("address"),
                    "mtu": link.get("mtu"),
                    "rx_bytes": rx.get("bytes"),
                    "tx_bytes": tx.get("bytes"),
                    "rx_packets": rx.get("packets"),
                    "tx_packets": tx.get("packets"),
                },
            )
        )
    return obs
