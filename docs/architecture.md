# Architecture

How the `network.*` domain is structured, where it sits relative to the existing
OpenTelemetry namespaces, and the two axes that organise every entity and signal
in the model.

## Why this exists

The current OTel `network.*` namespace is connection-centric: a flat set of
IP / port / transport attributes describing a single host's view of a single
connection. It defines **no entities, no metrics, and no events** — it is a
vocabulary consumed by other signals (HTTP / RPC / DB spans, plus `system.*` /
`hw.*` / `k8s.*` metrics).

Real network infrastructure — from a home CPE to carrier optical transport —
needs a structured domain model that separates inventory, state, and observed
traffic, and that distinguishes *who is reporting* the telemetry. Flattening
everything into one attribute bag fails the moment you have a modular chassis, a
flow exporter, an optical line system, or a synthetic probe.

This project grows `network.*` from a shared attribute vocabulary into a full
signal-bearing domain — **additively**. Existing `network.*` attributes keep their
meaning and are *referenced*, never redefined; all new surface lives under clearly
infrastructural sub-namespaces (`network.device.*`, `network.interface.*`,
`network.neighbor.*`, …).

## Namespace layering

Network telemetry touches three existing namespaces. Keeping the boundaries sharp
is the single most important structural decision.

```
host.*            resource identity of a host (when the device is a host)
 │
 ├─ system.network.*   host OS network stack (on-box, host perspective)
 │
 ├─ hw.network.*       physical NIC/port as a hardware FRU (inventory/health)
 │                     identity: hw.id (within monitored host)
 │
 └─ network.*          ── shared connection attributes (UPSTREAM, reused) ──
                          network.transport / type / local.* / peer.* / protocol.*(app)
                       ── networking DOMAIN (THIS PROJECT, additive) ───────
                          network.device / interface / link / instance / lag / tunnel
                          network.optical / flow / packet / observer
                          network.protocol(control-plane) / neighbor / routing / test
```

Each layer answers a different question:

- **`system.network.*`** — "how is *this host's own* network stack doing, measured
  on the host?" Host-exclusive and on-box-collection-only by spec.
- **`hw.network.*`** — "is this *physical port* healthy, as a piece of hardware?"
  Owns the physical NIC/port as a hardware component (up/down, bandwidth,
  byte/error counters, MAC), keyed by `hw.id`.
- **`network.*`** (this project) — "what *is* this network element, how is it
  forwarding, what is it peering with, and what traffic is being observed —
  regardless of who collected it or how?"

### Why not extend `system.*`?

`system.*` is host-exclusive and on-box-collection-only by its own normative spec.
A core router, an OLT, or a ROADM is not a "host" in the OTel sense, and the
dominant collection methods — SNMP, gNMI, NETCONF, streaming telemetry,
IPFIX/NetFlow/sFlow — are *external* observation of the element. The spec already
sets the precedent we follow: technology-specific telemetry collected via
well-defined APIs gets its own namespace (`k8s.*`, `container.*`). Network elements
are the same situation, so they get a dedicated `network.*` domain.

### The one legitimate overlap: a device that *is* a host

A Linux / SONiC whitebox switch or a virtual router genuinely runs a host OS. When
such a box reports its **own OS stack** via an on-box agent, that telemetry
correctly uses `system.*` and `host.*`. The same hardware can also emit
`network.interface.*` (the forwarding/topology view: VRF, role, admin/oper state,
sub-interfaces). These are different perspectives of one device — related by shared
host/device identity, **not** merged. Do not duplicate generic OS/host metrics
under `network.*`.

### Interface boundary: `network.interface.*` vs `hw.network.*` vs `system.network.*`

| Aspect | `system.network.*` | `hw.network.*` | `network.interface.*` (this project) |
|--------|-------------------|----------------|--------------------------------------|
| **Models** | A host OS network stack | A physical NIC/port as a hardware FRU | A network-element interface as a forwarding/topology entity |
| **Identity** | host + interface name | `hw.id` (within monitored host) | (`network.device.id`, `network.interface.id`) |
| **Logical / sub / LAG / tunnel / VLAN interfaces?** | partial | No (physical only) | **Yes** |
| **VRF / role / admin+oper state / subinterface tree?** | No | No | **Yes** |
| **Collection** | on-box agent | hardware monitoring | SNMP, gNMI, NETCONF, streaming telemetry |

**Coexistence rule:** do not re-emit physical-port health that `hw.network.*`
already provides. A physical port can be both a `network.interface` (the logical /
forwarding object) and a `hw.network` component (the physical FRU); express that as
a relationship (`network.interface` ↔ `hw.id`) rather than duplicating counters.

## The two modelling axes

Most failed network telemetry schemas collapse two independent questions into one.
Keep them separate.

### Axis 1 — what is being described

| Concern | Examples | Cardinality | Primary OTel signal |
|---------|----------|-------------|---------------------|
| **Inventory** | device, chassis, line card, optic, BGP peer identity | Low | Entity / Resource |
| **State** | interface up/down, BGP established, route counts, optical BER | Medium | Metrics (current) + Events (transitions) |
| **Traffic** | flows/conversations, classified + dropped packets | Very high | Logs/Events (records) + Metrics (aggregates) |

### Axis 2 — who is observing

| Perspective | Identifier namespace | Endpoint identity | Example |
|-------------|---------------------|-------------------|---------|
| **Device self-telemetry** | `network.device.*` | the device's own interfaces / peers | router reports its own BGP session, interface counters |
| **Passive observer** | `network.observer.*` | `source.*` / `destination.*` (observer is neither) | NetFlow exporter, tap, eBPF agent, packet broker |
| **Active tester** | `network.observer.*` (type `agent`) + `network.test.*` | `source.*` (agent) / `destination.*` (target) | synthetic latency/loss/jitter probe, BGP reachability |

A router reporting its own BGP neighbour is **not** the same telemetry as a probe
observing a TCP flow between two hosts, which is **not** the same as an agent
actively measuring loss to a target. The model makes the perspective explicit
instead of forcing all three into one object.

## Domain view

The model is organised into four domains. The tree below shows **logical**
containment — see [entity-model.md](entity-model.md#logical-containment-is-not-otel-nesting)
for how that is actually transmitted (it is *not* nested resources).

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          NETWORK RESOURCE DOMAIN                                 │
│                                                                                 │
│  ┌──────────────────┐                                                           │
│  │  network.device   │──── router, switch, firewall, CPE, OLT, optical node     │
│  └────────┬─────────┘     (may also be a host.* — see entity-model.md)          │
│           │ device.id (referenced on child entities)                            │
│           ├────────────────────┐                                                │
│  ┌────────▼─────────┐  ┌──────▼────────────┐                                   │
│  │ network.chassis   │  │ network.instance   │  network.vlan · network.lag      │
│  └────────┬─────────┘  │ (VRF / bridge-dom) │  network.tunnel                  │
│           │ chassis.id  └───────────────────-┘                                  │
│  ┌────────▼─────────┐                                                           │
│  │  network.module   │──── line_card, route_processor, fabric_card             │
│  └────────┬─────────┘     module.parent.id → module.id (recursive)             │
│           │ module.id                                                           │
│           ├──────────────────┬────────────────────┐                             │
│  ┌────────▼─────────┐ ┌─────▼──────────┐ ┌───────▼─────────────┐               │
│  │network.component  │ │network.interface│ │network.optical      │               │
│  │(ASIC, NPU, TCAM)  │ │  device.id +    │ │      .channel       │               │
│  │                   │ │  interface.id   │ │                     │               │
│  └───────────────────┘ └───────┬────────┘ └─────────────────────┘               │
│                                │ (interface.id, device.id)                      │
│                       ┌────────▼─────────┐                                      │
│                       │  network.link     │ local/remote (device.id, iface.id)  │
│                       └──────────────────-┘                                      │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                       TRAFFIC OBSERVATION DOMAIN                                 │
│  ┌───────────────────┐          ┌────────────────────────┐                      │
│  │ network.observer   │─────────▶│  network.flow (record)  │  source.* /         │
│  │ (probe, collector, │ observer │  unidir/bidir, 5-tuple, │  destination.*      │
│  │  tap, agent, fw)   │  .id     │  bytes, pkts, action    │  network.transport  │
│  └───────────────────┘          └────────────────────────┘  network.type        │
│                                  ┌────────────────────────┐                      │
│                                  │ network.packet          │  drop.reason on a    │
│                                  │ (class / drop dims)     │  dropped flow;       │
│                                  └────────────────────────┘  pcap = out of scope  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│            CONTROL-PLANE DOMAIN              │        ACTIVE TEST DOMAIN          │
│  ┌───────────────────────┐                  │  ┌──────────────────────────┐      │
│  │ network.protocol       │─▶ network.neighbor│  │ network.test (synthetic) │      │
│  │ (BGP, OSPF, IS-IS,    │   (peer/adjacency/ │  │ latency, loss, jitter,   │      │
│  │  LACP, BFD, LLDP ...) │    session)        │  │ reachability, path)      │      │
│  └───────────────────────┘                  │  └──────────────────────────┘      │
│  network.routing  (RIB/FIB, route counts)    │  observer.type = agent             │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Design principles

| # | Principle | Rationale |
|---|-----------|-----------|
| 1 | **Entities first, related — not nested** | Model like [K8s semconv](https://github.com/open-telemetry/semantic-conventions/tree/main/model/k8s): many flat entities with identifying + descriptive attributes, linked by relationship attributes and `entity_associations`. OTel has no native deep entity containment — do not rely on it. |
| 2 | **Separate device identity from observed-endpoint identity** | `network.device.*` for the managed element; `network.observer.*` for the probe/sensor; `source.*`/`destination.*` for observed traffic; `client.*`/`server.*` only when roles are known. |
| 3 | **Vendor-neutral first** | Standardize the domain concept; carry vendor names/models as descriptive attributes. Never `cisco.fpc.*` or `juniper.pic.*` as structure. |
| 4 | **Physical ≠ logical ≠ traffic** | Independent entity types for hardware (`module`, `component`), logical constructs (`instance`, `vlan`, `lag`, `tunnel`), and observations (`flow`, `packet`). |
| 5 | **Reuse `hw.*` for generic hardware** | Fans, PSUs, voltage, generic temp sensors stay in [`hw.*`](https://opentelemetry.io/docs/specs/semconv/attributes-registry/hw/). Use `network.*` only when the object carries forwarding/topology semantics. |
| 6 | **Raw flows are records; only aggregates are metrics** | 5-tuple / label-stack / MAC pairs appear only on flow log/event records, never on metric time series. See the [cardinality firewall](conventions.md#the-cardinality-firewall). |
| 7 | **Control plane ≠ data plane** | A BGP neighbour state is device telemetry; a TCP 5-tuple seen by a probe is flow telemetry; an MPLS LSP on the router is control-plane state; an MPLS label seen in traffic is a flow attribute. |
| 8 | **Reuse existing OTel attributes** | `network.transport`, `network.type`, `network.io.direction`, `source.*`, `destination.*`, `error.type`, `server.*`/`client.*` are referenced via Weaver, not redefined. |
| 9 | **Align with ECS where converging** | [ECS](https://www.elastic.co/docs/reference/ecs/ecs-field-reference) `observer.*`, `interface.*`, `network.*`, `source/destination.*` are being absorbed into OTel; align early. |
| 10 | **Normalized state + native state** | Cross-protocol/cross-vendor enums carry a coarse normalized value plus a verbatim native string. No single enum can represent BGP, OSPF, IS-IS, and BFD states. See [state modelling](conventions.md#state-modelling). |

## Governance

This is a separate Weaver extension registry with its own maintainers that
*depends on* upstream semconv via `model/manifest.yaml`. The core semconv
maintainers are not asked to own network-element conventions: they continue to own
the shared `network.*` connection attributes, and this registry references them and
adds the infrastructure sub-namespaces. The attribute names are designed to be
upstream-compatible (development stability, OTel naming rules, reuse of existing
attributes) so a path to upstream remains open but is not required.

The OpenTelemetry **Networking Working Group**
([#3769](https://github.com/open-telemetry/semantic-conventions/issues/3769)) has been
chartered to take the `network.*` namespace from "nebulous ownership" and to improve and
extend it — the same scope expansion this registry prototypes. The intent is for this
work to serve as reference input, and a possible adoption candidate, for that group;
contributing a worked `network.*` model to the body chartered to own `network.*` is the
sanctioned path, not a land grab. WG membership does not by itself confer adoption — and
the stabilization gate still applies: conventions cannot graduate past `development` until
instrumentation uses them (see [roadmap.md](roadmap.md#the-central-risk-validation)). The
WG roadmap of SNMP / NetFlow / eBPF Collector receivers is the credible path to the
validating instrumentation that gate requires.
