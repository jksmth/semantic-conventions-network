#!/usr/bin/env python3
"""NETCONF collection lane — the YANG-pull middle ground between SNMP and gNMI.

There is no upstream OTel NETCONF receiver, so this is the custom adapter the
brief predicted for sources without one: it does a NETCONF <get> against SR Linux
(YANG/XML over SSH/830), maps interface state to network.*, and emits the Weaver
sample stream consumed by `weaver registry live-check --input-source stdin`.

Same network.* targets as the SNMP/gNMI lanes — a 4th transport, one model.
"""
from __future__ import annotations

import json
import sys
from xml.etree import ElementTree as ET

from ncclient import manager

HOST = "172.22.22.11"
PORT = 830
USER = "admin"
PASS = "NokiaSrl1!"
DEVICE_ID = "srl1"
NS = "urn:nokia.com:srlinux:chassis:interfaces"


def _otel_type(v):
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "double"
    return "string"


def attr(name, value):
    return {"name": name, "value": value, "type": _otel_type(value)}


def norm_oper(s: str) -> str:
    # SR Linux oper-state -> network.interface.oper.state (open enum, lowercase)
    return (s or "unknown").strip().lower().replace("-", "_")


def collect():
    m = manager.connect(host=HOST, port=PORT, username=USER, password=PASS,
                        hostkey_verify=False, allow_agent=False, look_for_keys=False,
                        device_params={"name": "default"})
    filt = (f'<interface xmlns="{NS}"><name/><oper-state/>'
            f'<statistics><in-octets/><out-octets/></statistics></interface>')
    reply = m.get(filter=("subtree", filt))
    m.close_session()
    return ET.fromstring(reply.xml)


def text(el, tag):
    c = el.find(f"{{{NS}}}{tag}")
    return c.text if c is not None else None


def main():
    root = collect()
    samples = []
    for iface in root.iter(f"{{{NS}}}interface"):
        name = text(iface, "name")
        oper = text(iface, "oper-state")
        if not name:
            continue

        # entity: one resource per interface
        samples.append({"resource": {"attributes": [
            attr("network.device.id", DEVICE_ID),
            attr("network.device.type", "router"),
            attr("network.device.vendor.name", "nokia"),
            attr("network.interface.name", name),
        ]}})

        # oper status (updowncounter, value 1, state on the attribute)
        if oper:
            samples.append({"metric": {
                "name": "network.interface.oper.status",
                "instrument": "updowncounter",
                "unit": "1",
                "data_points": [{
                    "attributes": [attr("network.interface.oper.state", norm_oper(oper))],
                    "value": 1,
                }],
            }})

        # io counters (only present on up interfaces)
        stats = iface.find(f"{{{NS}}}statistics")
        if stats is not None:
            ino = stats.find(f"{{{NS}}}in-octets")
            outo = stats.find(f"{{{NS}}}out-octets")
            points = []
            if ino is not None and ino.text:
                points.append({"attributes": [attr("network.io.direction", "receive")],
                               "value": int(ino.text)})
            if outo is not None and outo.text:
                points.append({"attributes": [attr("network.io.direction", "transmit")],
                               "value": int(outo.text)})
            if points:
                samples.append({"metric": {
                    "name": "network.interface.io",
                    "instrument": "counter",
                    "unit": "By",
                    "data_points": points,
                }})

    json.dump(samples, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
