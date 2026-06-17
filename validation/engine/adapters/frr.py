"""FRR adapter: `vtysh -c "show ... json"` -> IR.

DOCS declares each source document twice — how to fetch it live (a command run
in the device container) and where a cached copy lives (a fixture filename) —
so the same parser serves both modes. device_id is the configured hostname (the
managed-router source in the network.device.id precedence table).
"""
from __future__ import annotations

import json

from ir import Observation, Record

SOURCE = "frr-vtysh"

DOCS = {
    "hostname": {
        "live": ["sh", "-c", "vtysh -c 'show running-config' | awk '/^hostname /{print $2; exit}'"],
        "fixture": "{tag}.hostname.txt",
    },
    "interfaces": {
        "live": ["vtysh", "-c", "show interface json"],
        "fixture": "{tag}.frr.interfaces.json",
    },
    "bgp_neighbors": {
        "live": ["vtysh", "-c", "show bgp neighbors json"],
        "fixture": "{tag}.frr.bgp-neighbors.json",
    },
}


def container(tag: str) -> str:
    return f"netlab-{tag}"


def parse(docs: dict[str, str], meta: dict) -> Observation:
    device_id = docs["hostname"].strip()
    obs = Observation(source=SOURCE, device_id=device_id)
    obs.records.append(Record(kind="device", index=None, fields=dict(meta)))

    for name, obj in json.loads(docs["interfaces"]).items():
        obs.records.append(Record(kind="interface", index=name, fields=obj))

    for addr, obj in json.loads(docs["bgp_neighbors"]).items():
        obs.records.append(Record(kind="neighbor", index=addr, fields=obj))

    return obs
