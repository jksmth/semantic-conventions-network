# Off-box SNMP — a real management-plane poll, validated against `network.*`

This is the proof the brief actually asked for and the earlier work deferred: an
**off-box SNMP poll** of a device, mapped to `network.*`, machine-checked by
Weaver. It retires the "SNMP didn't work" caveat in the top-level validation README.

```
net-snmp agent (IF-MIB)            <- a standard SNMP agent, real interface data
   |  udp/1161  (off-box poll, over the wire — nothing on the device but the agent)
   v
otelcol-contrib
   snmpreceiver   — walk ifName / ifHCInOctets / ifHCOutOctets / ifOperStatus
   transform/OTTL — ifOperStatus integer -> network.interface.oper.state enum
   otlpexporter   — real OTLP
   v
weaver registry live-check  — conformance + non-zero-on-violation verdict
```

## Run it

```bash
./run-snmp.sh          # boot lab, poll SNMP, map, live-check, verdict
./run-snmp.sh --down   # also tear everything down
```

Verified result (zero engine code, real SNMP on the wire):

```
samples: 120  {metric: 20, resource: 10, attribute: 60, data_point: 30}
metrics matched: {network.interface.io: 10, network.interface.oper.status: 10}
advisories: 80  by-level={improvement: 80}
non-registry names: none
PASS: off-box SNMP telemetry is fully registry-conformant.
```

## What this demonstrates that the other paths did not

- **Off-box, over-the-wire collection.** The collector reaches the device on
  udp/1161; the device runs only a standard SNMP agent. This is the real operator
  ingestion model, not an on-box reader.
- **The headline enum normalization, in OTTL.** SNMP `ifOperStatus` is an integer
  (1=up, 2=down, 3=testing, …). The `transform` processor maps it to the model's
  open string enum `network.interface.oper.state` and pins the status value to 1 —
  the SNMP analogue of `crosswalk/transforms.py:bgp_state`/`linux_operstate`.
- **Per-interface entity modelling.** `snmpreceiver` builds one Resource per ifName
  (`network.interface.name`), which is closer to a faithful `network.interface`
  entity than the single-Resource hostmetrics path.
- **`snmpreceiver` is the SNMP adapter you'd otherwise own.** The brief predicted a
  custom SNMP walk parser; this replaces it with config. The mapping is OTTL.

## Honest boundaries

- **The agent is net-snmp serving IF-MIB, not a full NOS.** It exposes real
  interface counters and oper-state, but it is not BGP4-MIB / ENTITY-MIB off a
  Cisco/Nokia box. It proves the pipeline shape; richer MIBs are more OID rows.
- **Two LinuxKit workarounds** (Docker Desktop on macOS), both environment limits,
  not model/engine ones:
  - Port **1161**, not 161 — the privileged bind is refused.
  - Listen address on the **snmpd command line**, not `agentAddress` in the conf —
    net-snmp fails to open the endpoint from the config file under this kernel.
  - The `/proc/net/snmp` header-length warnings are harmless (they only affect the
    IP/TCP/UDP scalar MIBs we don't poll).
- **Instrument types must match.** `live-check` flags a gauge where the registry
  says updowncounter as a `violation`; `network.interface.oper.status` is therefore
  emitted as a non-monotonic cumulative sum. Good signal that the gate has teeth on
  metric shape, not just names.
- **Polling, not events.** This is the steady-state poll. Port-flap traps / syslog
  / gNMI state-change are the next step — see `../docs/realism-roadmap.md`.
