# Real NOS — Nokia SR Linux over its native SNMP, validated against `network.*`

The first validation against a **genuine network operating system**, not a routing
daemon on Linux. Nokia SR Linux (v26.3.2, arm64) is deployed by **containerlab**,
and its **own SNMP server** is polled off-box and machine-checked against the
`network.*` registry.

```
containerlab: srl1 ▪┄┄▪ srl2   (real NOS, gNMI/SNMP/NETCONF, real interfaces)
   |  SR Linux SNMP server (IF-MIB)   <- the NOS, not net-snmp
   |  udp/161 off-box poll
   v
otelcol-contrib  [ snmpreceiver + OTTL ]   <- byte-for-byte the ../native-snmp crosswalk
   |  OTLP
   v
weaver registry live-check   -> verdict
```

## Run it

No host install of containerlab is needed — it runs as a container against the
Docker socket.

```bash
./run-srl.sh           # deploy SR Linux (if needed), poll, map, live-check
./run-srl.sh --down    # destroy the SR Linux lab afterwards (it's heavy: ~2 GB/node)
```

Verified result:

```
samples: 4200  {resource: 300, metric: 600, data_point: 900, attribute: 2400}
metrics matched: {network.interface.io: 300, network.interface.oper.status: 300}
advisories: 3000  by-level={improvement: 3000}
non-registry names: none
PASS: real-NOS SNMP telemetry is fully registry-conformant.
```

SR Linux exposes ~50 interfaces (`ethernet-1/1..`, `mgmt0`, `system0`, `lo0`, …),
each becoming a `network.interface` resource with conformant `network.interface.io`
and `network.interface.oper.status` series. Zero non-registry names, zero
violations — only development-stability advice.

## Why this matters

- **It's a real NOS.** `ethernet-1/1`, `ifOperStatus`, 64-bit `ifHCInOctets` come
  from SR Linux's own management plane, served by the NOS SNMP agent — the same
  data an operator's poller would retrieve from a production box.
- **The crosswalk did not change.** `otelcol-srl.yaml` is the same IF-MIB OID map
  and the same `ifOperStatus`→`network.interface.oper.state` OTTL as
  `../native-snmp/otelcol-snmp.yaml` (only the target host and port differ). A real
  NOS is "just another SNMP source" to the source-agnostic mapping — exactly the
  thesis the whole validation set out to test, now proven on a third source.
- **containerlab on Apple Silicon works.** SR Linux's arm64 image boots under Docker
  Desktop via containerlab-in-Docker; no x86 emulation.

## Port flap — the event scenario, demonstrated

Disabling a port on the NOS changes the oper-state observably through the same path:

```bash
docker exec -i clab-srl-srl1 sr_cli <<'EOF'
enter candidate
set / interface ethernet-1/1 admin-state disable
commit now
EOF
# IF-MIB::ifOperStatus.32768:  up(1)  ->  down(2)
```

Verified: `ethernet-1/1` went `up(1)` → `down(2)`, which the OTTL rule normalizes to
`network.interface.oper.state="down"`. That's the steady-state-poll view of a flap.
The push-based version (a true event the instant it happens) is the gNMI-subscribe
step in `../docs/realism-roadmap.md` — SR Linux streams the `oper-state` transition
over gNMI, and `gnmic`'s OTLP output carries it straight to `live-check`.

## Honest boundaries

- **SNMP is on by default** in containerlab's SR Linux (access-group
  `SNMPv2-RO-Community`, community `public`, mgmt instance enabled) — no
  startup-config needed for the poll. A locked-down box would require enabling it.
- **Resource cost is real**: ~2 GB RAM per SR Linux node. containerlab warns when
  Docker's VM is under-provisioned; it still booted here, but give the Docker
  Desktop VM ≥ 6 GB for headroom.
- **Coverage is still ~2%** (interface IO + oper-state). BGP/EVPN/LLDP MIBs, the
  entity-association layer, and events are the next OID rows / the gNMI path.
- **Poll, not push.** This proves the off-box poll against a real NOS. True event
  push (gNMI subscribe / SNMP trap) is roadmap — and SNMP traps have no upstream
  OTel receiver (a gap worth raising upstream).
