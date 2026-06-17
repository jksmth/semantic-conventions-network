"""The generic mapper: IR + crosswalk -> Weaver sample stream.

This file is the test of the architecture: it contains NO source-specific and
NO entity-specific logic. It iterates IR records, looks up the crosswalk block
for each record's `kind`, and emits a Weaver `resource` sample (the entity) plus
`metric` samples. Adding a source or an entity type touches data
(crosswalk/*.yaml) + an adapter, never this code.
"""
from __future__ import annotations

from typing import Any

import transforms
from ir import Observation


def _resolve(spec: dict, *, device_id: str, index, fields: dict) -> Any:
    if "const" in spec:
        return spec["const"]
    if "from" in spec:
        src = spec["from"]
        if src == "__device_id__":
            return device_id
        if src == "__index__":
            return index
        val = fields.get(src)
    elif "field" in spec:
        val = fields.get(spec["field"])
    else:
        raise ValueError(f"bad field-spec: {spec}")
    if val is None:
        return None
    if "transform" in spec:
        val = transforms.apply(spec["transform"], val)
    return val


def _otel_type(v):
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "double"
    return "string"


def _attrs(mapping: dict, *, device_id, index, fields) -> list[dict]:
    out = []
    for name, spec in mapping.items():
        v = _resolve(spec, device_id=device_id, index=index, fields=fields)
        if v is None:
            if spec.get("optional"):
                continue
            raise ValueError(f"required attribute {name} resolved to None")
        out.append({"name": name, "value": v, "type": _otel_type(v)})
    return out


def _metric_sample(mdef: dict, *, device_id, index, fields) -> dict | None:
    points = []
    for p in mdef["points"]:
        val = _resolve(p["value"], device_id=device_id, index=index, fields=fields)
        if val is None:
            continue
        if mdef.get("skip_if_value_zero") and val == 0:
            continue
        pattrs = _attrs(p.get("attributes", {}), device_id=device_id, index=index, fields=fields)
        points.append({"attributes": pattrs, "value": val})
    if not points:
        return None
    return {
        "metric": {
            "name": mdef["name"],
            "instrument": mdef["instrument"],
            "unit": mdef["unit"],
            "data_points": points,
        }
    }


def build_samples(observations: list[Observation], crosswalk: dict) -> list[dict]:
    blocks = crosswalk["records"]
    samples: list[dict] = []
    for obs in observations:
        for rec in obs.records:
            block = blocks.get(rec.kind)
            if block is None:
                continue
            ctx = dict(device_id=obs.device_id, index=rec.index, fields=rec.fields)
            attrs = _attrs(block["identity"], **ctx)
            attrs += _attrs(block.get("description", {}), **ctx)
            samples.append({"resource": {"attributes": attrs}})
            for mdef in block.get("metrics", []):
                s = _metric_sample(mdef, **ctx)
                if s:
                    samples.append(s)
    return samples


def identities(observations: list[Observation], crosswalk: dict) -> dict:
    """Extract the entity identities a source resolves to — for reconciliation.

    Returns {"devices": {id, ...}, "interfaces": {(device_id, name), ...}}.
    """
    blocks = crosswalk["records"]
    devices, interfaces = set(), set()
    for obs in observations:
        for rec in obs.records:
            block = blocks.get(rec.kind)
            if not block:
                continue
            ent = block["identity"]
            ctx = dict(device_id=obs.device_id, index=rec.index, fields=rec.fields)
            if block["entity"] == "network.device":
                devices.add(_resolve(ent["network.device.id"], **ctx))
            elif block["entity"] == "network.interface":
                interfaces.add(
                    (
                        _resolve(ent["network.device.id"], **ctx),
                        _resolve(ent["network.interface.name"], **ctx),
                    )
                )
    return {"devices": devices, "interfaces": interfaces}
