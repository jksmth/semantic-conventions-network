"""Adapter registry. Each adapter module is one collection method (a "source")
and exposes: SOURCE, DOCS, container(tag), parse(docs, meta).
"""
from __future__ import annotations

from . import frr, linux

# source name -> (adapter module, crosswalk file relative to validation/)
SOURCES = {
    frr.SOURCE: {"adapter": frr, "crosswalk": "crosswalk/frr.yaml"},
    linux.SOURCE: {"adapter": linux, "crosswalk": "crosswalk/linux.yaml"},
}
