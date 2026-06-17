# NETCONF — YANG-pull over SSH, validated against `network.*`

The **4th collection method** after SNMP, gNMI, and syslog: NETCONF (`<get>` of
YANG-modelled state over SSH/830). It's the structured-pull middle ground in the
progression **SNMP → NETCONF/RESTCONF → gNMI (streaming)**.

```
SR Linux (NETCONF server, ssh/830)
   |  <get> interface name / oper-state / statistics  (YANG/XML)
   v
netconf_collect.py  (ncclient -> parse XML -> network.* samples)   <- custom adapter,
   |  JSON sample stream                                              no OTel NETCONF receiver
   v
weaver registry live-check --input-source stdin   ->  engine/report.py verdict
```

## Run it

```bash
./run-netconf.sh          # deploy SR Linux (if needed), NETCONF collect, validate
./run-netconf.sh --down   # destroy the SR Linux lab afterwards
```

Verified result:

```
samples: 477  {resource: 59, metric: 60, data_point: 61, attribute: 297}
advisories: 357  by-level={improvement: 357}  (development-stability only)
PASS: every attribute & metric is registry-defined.
```

## Why NETCONF, and why on SR Linux (not Cisco)

Cisco IOS-XE *as an OS* supports NETCONF, RESTCONF, gNMI, and Model-Driven
Telemetry — but the **CML IOL lab binary does not**. Verified empirically on our
IOL: `netconf-yang` / `restconf` / `gnmi-yang` are silently rejected, and a port
scan shows only **SSH/22 + SNMP/161** open. IOL = SNMP + syslog + CLI, full stop.

SR Linux, by contrast, runs a **NETCONF server by default** (`netconf-server mgmt`,
port 830), is arm64-native, and runs here — so it's the NETCONF testbed. The lane
pulls `srl_nokia-interfaces` state (name, oper-state, in/out-octets), normalizes
`oper-state` to `network.interface.oper.state`, and maps the counters to
`network.interface.io` — the same `network.*` targets as the SNMP and gNMI lanes,
reached over a fourth, structurally different transport (XML/YANG over SSH).

## The collection-method landscape (for reference)

| Method | Transport | Model | Style | IOL | SR Linux |
|---|---|---|---|---|---|
| SNMP | UDP/161 | OID/MIB | poll | yes | yes |
| Syslog | UDP/514 | text | event push | yes | yes |
| **NETCONF** | SSH/830 | YANG (XML) | pull + RFC 8639 subscribe | no | **yes** |
| RESTCONF | HTTPS/443 | YANG (JSON) | pull | no | (JSON-RPC instead) |
| gNMI | gRPC/9339 | YANG (OpenConfig) | Get/Set/Subscribe (stream) | no | yes |
| MDT gRPC dial-out | gRPC | YANG | device pushes | no | — |

"Model-Driven Telemetry" = streaming YANG, either **dial-in** (collector subscribes
via gNMI or NETCONF RFC 8639) or **dial-out** (device initiates gRPC and pushes).

## What this adds to the suite

`network.interface.io` / `network.interface.oper.status` are now reached from
**four transports** — SNMP (OID poll), gNMI (gRPC subscribe), NETCONF (YANG/XML
pull), plus syslog for events — each via a small source-specific mapping, all
landing on the same `network.*` registry. The NETCONF mapping is a custom adapter
(no upstream OTel NETCONF receiver exists), which it shares with the original
`engine/` design and validates through the same `weaver live-check` stdin path.

## Honest boundaries

- **Custom adapter, not a collector receiver.** No upstream OTel NETCONF receiver
  exists; `netconf_collect.py` (ncclient) is the adapter. It emits the Weaver stdin
  sample stream (reusing `engine/report.py` for the verdict) rather than OTLP.
- **NETCONF subscribe (RFC 8639) not exercised** — this lane is the `<get>` pull.
  The streaming/subscribe side overlaps with the gNMI lane already covered.
- **RESTCONF** isn't shown: SR Linux offers JSON-RPC/gNMI rather than RESTCONF, and
  IOL lacks it. A RESTCONF lane would need cEOS or full IOS-XE.
