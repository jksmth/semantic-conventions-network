"""The typed intermediate representation (IR).

Every source adapter normalises into this shape; the mapper and the crosswalk
only ever see the IR, never a source's native format. This is the seam that
decides whether the system stays clean as sources are added: a new collection
method is a new adapter that produces `Observation`s, plus a crosswalk file —
the mapper does not change.

    Observation  = one device, observed by one method
      .source      e.g. "frr-vtysh", "linux-iproute2", "snmp-ifmib"
      .device_id   the identity the adapter derived (the id contract in action)
      .records     the observed objects

    Record       = one observed object of a logical `kind`
      .kind        "device" | "interface" | "neighbor" | ... (extensible)
      .index       instance key within the device (ifname, peer address); None for device
      .fields      raw source fields (source-native names) — the crosswalk maps these
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Record:
    kind: str
    index: Optional[str]
    fields: dict[str, Any]


@dataclass
class Observation:
    source: str
    device_id: str
    records: list[Record] = field(default_factory=list)
