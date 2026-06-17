# Validation realism roadmap — toward real NOS, gNMI, and events

Where the validation can go now that we've proven, end-to-end and runnable:

- collector + OTTL + OTLP → `weaver live-check` (`../native/`, Linux/hostmetrics)
- **off-box SNMP poll** → OTTL → live-check (`../native-snmp/`, with `ifOperStatus`
  enum normalization and per-interface entities)

Both retire the "is this real / does it stay clean" questions for the steady-state
poll. The two open frontiers are **a real network OS** and **events** (port flap →
trap / syslog / gNMI state-change).

## The collection-method matrix (what to run as the "device")

| Device | Spin-up | Mgmt plane | arm64 / Apple Silicon | OTel path | Notes |
|---|---|---|---|---|---|
| **net-snmp + FRR** (today) | docker | SNMP (IF-MIB) | yes | `snmpreceiver` + OTTL | proven here; not a full NOS |
| **Nokia SR Linux** | containerlab | **gNMI**, JSON-RPC, gNMI-subscribe; SNMP (limited) | **yes** (arm64 image) | gnmic → OTLP, or `snmpreceiver` | freely pullable `ghcr.io/nokia/srlinux`; best gNMI story |
| **VyOS** | docker/containerlab | SNMP (net-snmp), syslog | yes (build) | `snmpreceiver` + `syslogreceiver` | real router (FRR inside), full IF/BGP MIBs |
| **Arista cEOS** | containerlab | SNMP, eAPI, gNMI | amd64 (emulate) | `snmpreceiver` / gnmic | needs Arista login to pull |
| **Cisco XRd / 8000v** | docker/containerlab | SNMP, gNMI, NETCONF | amd64, heavy | `snmpreceiver` / gnmic | CCO login, big footprint |

Recommendation: **adopt containerlab** as the lab orchestrator (it's the industry
standard for exactly this and replaces the hand-rolled compose), and add **Nokia
SR Linux** as the first real NOS — it's freely pullable, arm64-native, and gNMI-first.

## gNMI path (the modern, "real telemetry" route)

gnmic has a **native OTLP output**, so there's no glue code — the same shape as the
SNMP path, different receiver:

```
SR Linux  --gNMI subscribe-->  gnmic (otlp output)  --OTLP-->  otelcol (OTTL)  -->  weaver
```

This is implemented and passing in `../native-gnmi/`; the snippets below are the
conceptual shape:

`labs/srl/topo.clab.yml`
```yaml
name: srl-net
topology:
  nodes:
    r1: { kind: nokia_srlinux, image: ghcr.io/nokia/srlinux:latest }
    r2: { kind: nokia_srlinux, image: ghcr.io/nokia/srlinux:latest }
  links:
    - endpoints: ["r1:e1-1", "r2:e1-1"]
```

`labs/srl/gnmic.yaml`
```yaml
targets:
  r1:6030: { username: admin, password: NokiaSrl1! }
  r2:6030: { username: admin, password: NokiaSrl1! }
skip-verify: true
subscriptions:
  if-state:
    paths:
      - /interface/statistics/in-octets
      - /interface/statistics/out-octets
      - /interface/oper-state
    stream-mode: sample
    sample-interval: 5s
outputs:
  otlp:                       # gnmic's native OpenTelemetry output
    type: opentelemetry
    url: weaver-livecheck:4317
    insecure: true
```

The OTTL crosswalk then renames the gNMI/OpenConfig paths to `network.*` exactly as
`../native-snmp/otelcol-snmp.yaml` does for SNMP (e.g. `oper-state` `up`/`down` →
`network.interface.oper.state`; in/out-octets → `network.interface.io`).

The value of the gNMI path: it exercises the same crosswalk-stays-clean thesis
against a **third, structurally different source** (OpenConfig YANG paths, not OIDs
or netlink), and SR Linux is a genuine NOS.

## Events — port flap → state-change, the concrete plan

So far everything is **metrics**. The model also defines **events** (currently 0%
exercised): `network.state.changed` and its refinement `network.interface.state.changed`
(`model/network/interface/events.yaml`). A port flap should produce one of these.
Weaver `live-check` validates OTLP **logs/events** against those event definitions
exactly as it does metrics, so the gate already exists — we just need to feed events
into it. Three source lanes, in order of how off-the-shelf they are today:

**Lane A — syslog (`syslogreceiver`, fully upstream).** Point SR Linux's syslog at
the collector's `syslogreceiver`; an interface up/down line arrives as a log record,
and OTTL parses it into a `network.interface.state.changed` event (set the event
name, `network.interface.name`, `network.interface.oper.state`,
`network.event.state.*`). Highest readiness — every component is upstream. Best
first lane to make pass.

**Lane B — gNMI on-change (push; DONE, see `../native-events-gnmi/`).** The
`on-change` subscription pushes `oper-state` transitions the moment they happen. The
gap (gnmic's OTLP output is metrics-only) is bridged with two upstream features and
no custom code: gnmic `file` output with `split-events: true` (one JSON object per
line) → the collector's `filelogreceiver` → OTTL → the same `network.state.changed`
event. Sub-second push, validated by `live-check`. A native gNMI receiver in the
collector (none exists) or a gnmic OTLP-logs output would remove the file hop.

**Lane C — SNMP trap (the real gap).** A `linkDown`/`linkUp` trap is the classic
event, but there is **no upstream SNMP-trap receiver** in collector-contrib (only the
`snmpreceiver` poller). Options: run `snmptrapd` with an exec handler that emits OTLP,
or derive the transition from a short-interval `ifOperStatus` poll (a delta, not a
true trap). Worth raising upstream as a missing component — and a finding the project
can contribute back.

**Concrete first milestone (DONE — see `../native-events/`):** Lane A end-to-end —
SR Linux syslog → `syslogreceiver` → OTTL → `network.state.changed` OTLP event →
`live-check`, flapping `ethernet-1/1` to generate it. PASS: Weaver validated the
flap as a registry event (`seen_registry_events: {network.state.changed: 4}`), zero
violations. The events half of the model is now executable, paired with the
`network.interface.oper.status` gauge from `../native-srl`. Lane B (gNMI on-change
push) and the Lane C SNMP-trap gap remain.

## Suggested phasing

1. **Done.** collector+OTTL+OTLP→live-check; off-box SNMP poll with enum norm.
2. **Done.** containerlab + **Nokia SR Linux** (arm64) over its native SNMP server,
   validated with the *same* `snmpreceiver` + OTTL crosswalk — see `../native-srl/`.
   Port-flap (`admin-state disable`) verified observable as `oper-state` up→down.
3. **Done.** **gNMI via gnmic→OTLP** on SR Linux (`../native-gnmi/`): third
   transport, same `network.interface.io` target via OTTL, PASS. Port-flap shown as
   a true gNMI `on-change` push event (`up→down→up`).
4. **Done.** **Cross-transport reconciliation** (`../native-recon/`): SNMP-derived
   vs gNMI-derived identity for the same SR Linux device converge on one
   `network.device.id` + physical interface set; the `mgmt0.0` subinterface
   divergence is correctly classified, not failed on. The strong (non-tautological)
   version of `engine/reconcile.py`.
5. **Events — Lanes A + B DONE.** Lane A (`../native-events/`): SR Linux syslog →
   `syslogreceiver` → OTTL → `network.state.changed` event → `live-check`. Lane B
   (`../native-events-gnmi/`): gNMI `on-change` push → gnmic `file` (split-events) →
   `filelogreceiver` → OTTL → the same event, sub-second. A real `ethernet-1/1` flap
   validated as a registry event from two independent event transports, zero
   violations. Remaining: Lane C SNMP traps (no upstream OTel receiver — flag/contribute upstream).
6. **Multi-vendor — Cisco + cross-vendor reconcile DONE.** Cisco IOS-XE (IOL)
   validated over SNMP with the byte-identical Nokia crosswalk (`../native-cisco/`),
   and **cross-vendor identity reconciliation** (`../native-xvendor/`): one rule on
   Nokia `srl1` + Cisco `cr1.lab` → distinct, collision-free, device-scoped
   identities, no per-vendor special-casing (PASS). Unlock: colima + Rosetta for the
   amd64 IOL. Vendor finding: Cisco `sysName` carries a domain (`cr1.lab`) vs Nokia
   `srl1` — model tolerates both.
7. **Topology correlation DONE (`../native-xtopo/`):** SR Linux wired to Cisco IOL,
   LLDP on both; each vendor's view of the adjacency reconciles to one undirected
   `network.link` `(cr1,ethernet0/1) <-> (srl1,ethernet-1/1)` (PASS). Two vendors,
   two access methods, one link — after normalizing the domain suffix and Cisco's
   `Et0/1`→`Ethernet0/1` abbreviation (evidence for device-scoped link identity + an
   edge normalization layer).
8. **NETCONF lane DONE (`../native-netconf/`):** added a 4th collection method —
   NETCONF `<get>` of SR Linux YANG state over SSH/830, mapped to `network.*` via a
   custom ncclient adapter (no upstream OTel NETCONF receiver), validated PASS via
   the `weaver live-check` stdin path. Finding: **Cisco IOL exposes only SNMP + SSH
   + syslog** (NETCONF/RESTCONF/gNMI/MDT silently rejected; only 22 + 161 open) — so
   YANG-management lanes run on SR Linux/cEOS, not IOL. `network.interface.io` /
   `oper.status` are now reached from SNMP, gNMI, and NETCONF + syslog events.
9. **Next frontiers:** **Arista cEOS** (arm64-native) for OpenConfig gNMI + RESTCONF
   as a third vendor; sturdier join keys (chassis-id/MAC, ENTITY-MIB serial); the
   SNMP-trap-receiver gap upstream; Cisco MDT gRPC dial-out (needs full IOS-XE on a
   KVM host). VM-based NOSes still need KVM.
```
