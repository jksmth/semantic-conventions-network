# gNMI — SR Linux streamed telemetry, validated against `network.*`

The **third transport**, after netlink (`../native`) and SNMP (`../native-snmp`,
`../native-srl`): Nokia SR Linux streamed over **gNMI**, collected by **gnmic**,
exported as OTLP, mapped to `network.*` with OTTL, and machine-checked by Weaver.
Same registry targets, a structurally different source (OpenConfig/YANG paths).

```
SR Linux  --gNMI subscribe-->  gnmic (OTLP output)  --OTLP-->  otelcol [OTTL]  --OTLP-->  weaver
```

## Run it

```bash
./run-gnmi.sh          # deploy SR Linux (if needed), subscribe, map, live-check
./run-gnmi.sh --down   # destroy the SR Linux lab afterwards
```

Verified result:

```
samples: 84  {resource: 4, metric: 16, data_point: 16, attribute: 48}
metrics matched: {network.interface.io: 16}
non-registry names: none
PASS: real-NOS gNMI telemetry is fully registry-conformant.
```

## Port flap as a true push event (the gNMI advantage)

gNMI `on-change` subscriptions push state transitions the instant they happen — no
polling interval, no delta reconstruction. Verified live by flapping a port:

```bash
gnmic ... subscribe --path "/interface[name=ethernet-1/1]/oper-state" --stream-mode on_change
# while running:  set / interface ethernet-1/1 admin-state disable / enable
```

The stream emitted, in real time:

```
/srl_nokia-interfaces:interface/oper-state: "up"
/srl_nokia-interfaces:interface/oper-state: "down"    <- pushed the instant the port went down
/srl_nokia-interfaces:interface/oper-state: "up"
```

This is the push-based counterpart to the SNMP `ifOperStatus` poll in
`../native-srl`: the same state change, observed as an event instead of inferred
between polls. It's the natural feed for the model's `network.*.state.changed` events.

## What the OTTL crosswalk does (gNMI edition)

gnmic emits raw OpenConfig-derived names; the collector maps them to `network.*`:

| gnmic output | → | network.* |
|---|---|---|
| metric `gnmic__srl_nokia_interfaces:interface_statistics_in_octets` (Gauge) | → | `network.interface.io`, `network.io.direction=receive`, unit `By`, **gauge→counter** |
| metric `..._out_octets` | → | `network.interface.io`, `network.io.direction=transmit` |
| data-point attr `interface_name` | → | `network.interface.name` |
| resource tag `source` | → | dropped; `network.device.id=srl1` set instead |

Two findings worth recording:

- **gnmic returns SR Linux Counter64 as JSON strings**, which its OTLP output drops
  by default. A gnmic `event-convert` processor casts them to int (see `gnmic.yaml`).
- **gnmic exports them as Gauges** even with `counter-patterns` set, so the OTTL
  `convert_gauge_to_sum("cumulative", true)` fixes the instrument type — otherwise
  `live-check` flags a gauge-where-counter `violation` (the gate has teeth on shape).

## Honest boundaries

- **Counters only in the gate.** `oper-state` is a string; gnmic's
  `strings-as-attributes` would emit it as a gauge-with-value-1, which collides with
  the model's updowncounter shape for `network.interface.oper.status`. It's shown
  here as the flap *event* (above) rather than forced into the conformance metric.
  A clean oper-state metric would need a small connector or a downstream type fix.
- **gNMI path naming is verbose and vendor-flavoured** (`srl_nokia-interfaces:...`).
  The OTTL matches on a path suffix (`.*octets`); a cross-vendor crosswalk would key
  on OpenConfig paths where the device exposes them.
- Same ~2% coverage and on-box/credentials caveats as `../native-srl`.

## The three transports, one registry

`network.interface.io` is now reached from **netlink counters**, **SNMP
ifHCInOctets**, and **gNMI in/out-octets** — three different collection methods,
three different field encodings, the same `network.*` target, each via a small OTTL
crosswalk and each PASSing Weaver. That convergence is the strongest evidence the
model is collection-method-agnostic. The natural next step is to run
`engine/reconcile.py`'s idea across SNMP-derived vs gNMI-derived identity for the
*same* SR Linux device (see `../docs/realism-roadmap.md`).
