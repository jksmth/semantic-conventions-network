#!/usr/bin/env python3
"""Orchestrator: device (or snapshot) -> IR -> network.* Weaver sample stream.

Default is LIVE: collect straight from the running lab, map, print samples to
stdout for `weaver registry live-check`. Nothing is committed in the live path —
the running device is the source of truth.

  --mode live      collect from the lab containers (default)
  --mode offline   read a frozen snapshot from fixtures/ (CI without the lab)
  --capture        live-collect and WRITE the fixtures snapshot, then exit
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import adapters  # noqa: E402
import collectors  # noqa: E402
import mapper  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent


def device_tags(devices_meta: dict) -> list[str]:
    return list(devices_meta)


def acquire_docs(adapter, tag, mode, fixtures) -> dict[str, str]:
    docs = {}
    for key, spec in adapter.DOCS.items():
        if mode == "live":
            docs[key] = collectors.get_live(adapter.container(tag), spec["live"])
        else:
            docs[key] = collectors.get_cached(fixtures, spec["fixture"].format(tag=tag))
    return docs


def observations_for(source, mode, fixtures, devices_meta):
    adapter = adapters.SOURCES[source]["adapter"]
    obs = []
    for tag in device_tags(devices_meta):
        docs = acquire_docs(adapter, tag, mode, fixtures)
        obs.append(adapter.parse(docs, devices_meta.get(tag, {})))
    return obs


def load_crosswalk(source):
    return yaml.safe_load((ROOT / adapters.SOURCES[source]["crosswalk"]).read_text())


def load_devices(path):
    return (yaml.safe_load(pathlib.Path(path).read_text()) or {}).get("devices", {})


def do_capture(fixtures, devices_meta):
    fixtures.mkdir(parents=True, exist_ok=True)
    for source in adapters.SOURCES:
        adapter = adapters.SOURCES[source]["adapter"]
        for tag in device_tags(devices_meta):
            for key, spec in adapter.DOCS.items():
                text = collectors.get_live(adapter.container(tag), spec["live"])
                (fixtures / spec["fixture"].format(tag=tag)).write_text(text)
    print(f"captured snapshot to {fixtures}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["live", "offline"], default="live")
    ap.add_argument("--capture", action="store_true", help="live-collect, write fixtures, exit")
    ap.add_argument("--fixtures", default=str(ROOT / "fixtures"))
    ap.add_argument("--devices", default=str(ROOT / "labs" / "frr" / "devices.yaml"))
    args = ap.parse_args()

    devices_meta = load_devices(args.devices)
    fixtures = pathlib.Path(args.fixtures)

    if args.capture:
        do_capture(fixtures, devices_meta)
        return

    merged = []
    for source in adapters.SOURCES:
        obs = observations_for(source, args.mode, fixtures, devices_meta)
        merged += mapper.build_samples(obs, load_crosswalk(source))

    # samples to stdout — piped straight into live-check, nothing committed
    json.dump(merged, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
