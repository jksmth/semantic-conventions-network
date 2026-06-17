"""Named transforms — the ~20% that needs real logic.

The crosswalk table handles the boring field->target plumbing; these are the
parts that *prove* the model works: enum normalization (the normalized+native
pattern) and unit conversion. Each is a pure function registered by name and
referenced from crosswalk/frr.yaml.
"""
from __future__ import annotations


def identity(v):
    return v


def lower(v):
    return str(v).lower()


def iface_type(v):
    """FRR interface `type` -> network.interface.type (open string)."""
    return {"Ethernet": "ethernet", "Loopback": "loopback"}.get(v, str(v).lower())


def mac_ieee(v):
    """`e6:cb:f9:28:35:28` -> IEEE RA hex form `E6-CB-F9-28-35-28`.

    network.interface.mac follows the host.mac convention: hyphen-separated,
    uppercase octets.
    """
    if not v:
        return None
    return str(v).replace(":", "-").upper()


def mbps_to_bps(v):
    """FRR reports link speed in Mbit/s; network.interface.speed is bit/s."""
    return int(v) * 1_000_000


# --- The normalized+native pattern (the headline mapping) ----------------
# BGP FSM state -> network.neighbor.state (coarse, cross-protocol). The
# verbatim term is preserved separately in network.neighbor.native_state.
_BGP_STATE = {
    "Established": "up",
    "Idle": "down",
    "Clearing": "down",
    "Deleted": "down",
    "Connect": "connecting",
    "Active": "connecting",
    "OpenSent": "connecting",
    "OpenConfirm": "connecting",
}


def bgp_state(v):
    return _BGP_STATE.get(v, "unknown")


# Linux iproute2 RFC 2863 operational states (different source, same target as
# FRR's administrativeStatus/operationalStatus) -> network.interface.oper.state.
# Note it exercises the diagnostic values the interface enum keeps distinct.
_LINUX_OPERSTATE = {
    "UP": "up",
    "DOWN": "down",
    "TESTING": "testing",
    "DORMANT": "dormant",
    "LOWERLAYERDOWN": "lower_layer_down",
    "NOTPRESENT": "not_present",
    "UNKNOWN": "unknown",
}


def linux_operstate(v):
    return _LINUX_OPERSTATE.get(str(v).upper(), "unknown")


REGISTRY = {
    "identity": identity,
    "lower": lower,
    "iface_type": iface_type,
    "mac_ieee": mac_ieee,
    "mbps_to_bps": mbps_to_bps,
    "bgp_state": bgp_state,
    "linux_operstate": linux_operstate,
}


def apply(name, value):
    try:
        fn = REGISTRY[name]
    except KeyError as e:
        raise KeyError(f"unknown transform '{name}' (have: {sorted(REGISTRY)})") from e
    return fn(value)
