# Validation — `network.*` proven against real devices

This directory is the **executable proof** that the `network.*` semantic conventions
are more than prose. Real network operating systems — booted from real config — are
observed over real management protocols, their telemetry is mapped to `network.*`,
and machine-checked against the registry with `weaver registry live-check`. Where it
matters, independent observers are shown to **reconcile** onto one identity, one link.

It runs on an Apple-Silicon laptop (colima + Rosetta), no cloud, no licensed images
beyond a one-time free Cisco/Arista download.

## The thesis being tested

> The `network.*` model is **collection-method- and vendor-agnostic**: the
> source-specific part is just *data* (a crosswalk), and many different
> devices/protocols converge on the same registry-defined targets.

Every lane below is a falsifiable test of that claim — and the gate has teeth
(typo'd names, gauge-where-counter, non-registry attributes all fail `live-check`,
demonstrated repeatedly).

## The shape every lane shares

```
real device (NOS, real config)
   │   collect over a real protocol (SNMP / gNMI / NETCONF / netlink / syslog)
   ▼
mapping to network.*  ──  OTTL crosswalk (collector)  or  a small adapter
   │                      (the "source-specific = data" layer)
   ▼
OTLP  or  Weaver sample stream
   ▼
weaver registry live-check  ──►  PASS/FAIL verdict against the registry
```

The mapping is the only source-specific piece. Adding a transport or a vendor
changes the crosswalk/adapter, never the model.

## What's been validated

**Devices / vendors** (all run on this Mac):

| Device | Kind | Arch | Notes |
|---|---|---|---|
| Linux host | `hostmetrics` | arm64 | server-NIC slice (the cheapest first proof) |
| net-snmp agent | SNMP agent | arm64 | a real off-box SNMP poll target |
| FRR | routing daemon | arm64 | the original engine lab |
| **Nokia SR Linux** | real NOS | arm64-native | SNMP + gNMI + NETCONF |
| **Cisco IOS-XE (IOL)** | real NOS | amd64 via **Rosetta** | SNMP + syslog + CLI only |

**Transports** reaching the same `network.*` targets: **SNMP**, **gNMI**,
**NETCONF**, netlink, and **syslog** (events).

**Signals**: metrics (`network.interface.io`, `network.interface.oper.status`),
events (`network.state.changed`), and identity/topology reconciliation.

## The lanes (each is runnable: `./run-*.sh`)

| Lane | What it proves | Result |
|---|---|---|
| `native/` | collector + OTTL + OTLP → live-check, **zero engine code** (Linux/netlink) | PASS |
| `native-snmp/` | off-box **SNMP** poll → `network.*`, with `ifOperStatus` enum-normalization | PASS |
| `native-srl/` | **real NOS** (SR Linux) over its native SNMP, same crosswalk | PASS (4200 samples) |
| `native-gnmi/` | **gNMI** (gnmic→OTLP) → `network.interface.io`, gauge→counter via OTTL | PASS |
| `native-netconf/` | **NETCONF** `<get>` (YANG/XML over SSH) via a custom ncclient adapter | PASS (477 samples) |
| `native-events/` | **syslog** port-flap → `network.state.changed` event | PASS (events) |
| `native-events-gnmi/` | **gNMI on-change** push → same event, sub-second | PASS (events) |
| `native-recon/` | **same device, 2 transports** (SNMP vs gNMI) converge on one identity | PASS |
| `native-cisco/` | **Cisco IOS-XE** over SNMP via the *byte-identical* Nokia crosswalk | PASS (350 samples) |
| `native-xvendor/` | **cross-vendor identity**: one rule on Nokia + Cisco → distinct, collision-free | PASS |
| `native-xtopo/` | **cross-vendor topology**: LLDP, both ends reconcile to one `network.link` | PASS |
| `engine/` + `run.sh` | the original MVP: FRR/Linux → IR → crosswalk → stdin live-check + reconcile | PASS |

**Labs** (`labs/`): `frr` (2× FRR), `srl` (SR Linux, + `srl-solo`), `cisco`
(IOL L3+L2, + `cisco-solo`), `xvendor` (SR Linux ↔ Cisco wired).

**Image builder** (`images/build-cisco-iol.sh`): turns a Cisco CML-Free refplat ISO
into runnable `cisco_iol` L3 + L2 images.

## Headline findings (the things only real devices surface)

- **One crosswalk, many sources.** `network.interface.io` / `oper.status` are reached
  from netlink, SNMP, gNMI, and NETCONF — the SNMP and Cisco lanes use a
  *byte-identical* OTTL crosswalk to the Nokia one. Source-specific = data, proven.
- **Identity is device-scoped, and that's necessary.** Cross-vendor, interface names
  differ wildly (`ethernet-1/1` vs `Et0/0`); only the `(network.device.id,
  network.interface.name)` pair stays collision-free. Topology reconciliation needs
  two normalizations — strip Cisco's domain-suffixed sysName (`cr1.lab`→`cr1`), expand
  `Et0/1`→`Ethernet0/1` — which argues for *normalize-at-the-edge, keep the registry
  open*.
- **The gate has teeth.** `live-check` fails on non-registry names, type mismatches,
  and gauge-where-updowncounter — each hit and fixed during the build.
- **Environment truths.** VM-based NOSes need `/dev/kvm` (not on macOS Docker).
  Container-native NOSes (SR Linux arm64; Cisco IOL as an x86 *binary*) run here — but
  IOL's `iouyap` needs **Rosetta** (qemu-user can't emulate its `AF_PACKET` syscalls).
  Cisco **IOL exposes only SNMP + syslog + CLI** (no NETCONF/RESTCONF/gNMI/MDT).

## How to run

Prereqs: Docker via **colima with Rosetta** (`colima start --vz-rosetta`), `python3`.
Vendor images are sourced once (free accounts) and built locally — never committed.

```bash
cd native-srl   && ./run-srl.sh --down       # real-NOS SNMP
cd native-gnmi  && ./run-gnmi.sh --down       # gNMI
cd native-netconf && ./run-netconf.sh --down  # NETCONF
cd native-xtopo && ./run-xtopo.sh --down      # cross-vendor LLDP link
# ... each lane has its own run script + README
```

Each `run-*.sh` deploys its lab (containerlab), collects, validates, prints a
verdict, and tears down with `--down`. Every lane has a README with its exact
result and honest boundaries.

## Honest boundaries (suite-wide)

- **Coverage is ~2%** of the registry — interface IO + oper-state + a state-change
  event + identity/topology. Relationships, the full entity-association layer, flows,
  alarms, and exotic device classes (optical/PON/WiFi/carrier-NAT) are not yet
  exercised against real hardware.
- **`live-check` proves conformance, not semantic correctness** — that `Established`
  or `up` maps to the *right* state still rides on the crosswalk + review.
- **Some methods have no OTel receiver** (NETCONF, SNMP traps) — those use small
  custom adapters, an honest reflection of the ecosystem.
- **Mapping ≠ deployment.** These are reproducible proofs, not a production pipeline.

## Where next

See [`docs/realism-roadmap.md`](docs/realism-roadmap.md) — phases 1–8 are done
(collector+OTTL, SNMP/gNMI/NETCONF transports, syslog + gNMI events, same-device /
cross-vendor / topology reconciliation, Cisco as a second vendor). Open frontiers:
Arista cEOS (OpenConfig gNMI + RESTCONF), sturdier identity join keys
(chassis-id/serial), the upstream SNMP-trap-receiver gap, and Cisco MDT gRPC dial-out
(needs full IOS-XE on a KVM host).
