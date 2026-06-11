# Conventions

Cross-cutting modelling patterns that apply across every package: how state is
represented, which signal carries which kind of telemetry, the cardinality
firewall, and naming rules.

## State modelling

State appears in three coordinated forms — do not pick only one.

1. **Current-state UpDownCounter** — e.g. `network.interface.oper_state` as an
   UpDownCounter using the K8s `status.phase` enum-attribute pattern: one series per
   possible state, value `1` for the active state and `0` otherwise, so a simple
   `sum` counts how many entities sit in each state. Per the
   [OTel status-metrics guide](https://opentelemetry.io/docs/specs/semconv/how-to-write-conventions/status-metrics/)
   this is a deliberate UpDownCounter, not a Gauge. It is required because you cannot
   reconstruct "state right now" from a stream of transition events after a collector
   restart.
2. **Transition event** — e.g. `network.interface.state.changed` with
   `network.event.previous_state` / `network.event.new_state`. Point-in-time; never a
   gauge pretending to be history.
3. **Normalized + native value** — the coarse cross-protocol enum
   (`up`/`down`/`degraded`/`connecting`/`unknown`) plus a verbatim `*.native_state`
   string. BGP `Established`, OSPF `Full`, BFD `Up`, LACP `collecting_distributing`
   all normalize to `up` while preserving the native term. No single enum can
   represent BGP, OSPF, IS-IS, and BFD states, so both are carried.

The three legs are complementary: the gauge tells you the state right now, the
transition **count** (`state_changes`, `routing.updates`) survives restarts and
measures churn, and the transition **event** is the point-in-time signal the
SNMP/syslog trap feed is built on.

## Events

Two base events underpin the events package:

- **`network.state.changed`** — an X.731 state transition (interface up/down,
  neighbour up/down, device reboot). Carries previous/new normalized + native state.
- **`network.alarm`** — an RFC 8632 / X.733 condition (fan failure, threshold
  crossed, optical degrade). Carries a `cause` and, where relevant, threshold and
  observed values.

Per-domain events are **refinements** of these envelopes: each resolves to its own
`event.name` (e.g. `network.interface.state.changed`,
`network.optical.threshold_crossed`, `network.hardware.alarm`) while inheriting the
common envelope fields. A config change is modelled as an observation **record**
(what changed + commit-id), not a state transition — it is deliberately not forced
into `state.changed`.

## Flow and packet modelling

### Signal choice

| Form | Signal | When |
|------|--------|------|
| **Raw flow record** | **Log-based Event** (`event.name = network.flow`) | Default. A flow is a time-bounded observation with start/end/duration and measures — semantically a structured event, not a causal span. |
| **Aggregated flow** | **Metric** | Rates/totals over low-cardinality dimensions. |
| **Flow as span** | **Trace** | Pragmatic alternative for connection-oriented L4/L7 flows where duration + correlation drive tooling. Flows are not causal spans and won't form valid trace trees. |

The `network.flow.*` / `network.observer.*` attribute set is identical regardless of
which signal carries it.

### The cardinality firewall

High-cardinality flow identity belongs on **records**, never on metric time series.

| Attribute | On flow **records** (logs/events) | On flow **metrics** |
|-----------|:---:|:---:|
| `source.address`, `destination.address`, ports | ✅ | ❌ |
| `network.flow.mpls.label.stack`, `vlan.stack`, MAC pairs | ✅ | ❌ |
| `network.flow.id`, `tcp.flags`, `community_id` | ✅ | ❌ |
| `network.observer.id`, `observer.type` | ✅ | ✅ |
| `network.flow.direction`, `network.flow.action` | ✅ | ✅ |
| `network.protocol.name`, `network.transport`, `network.type` | ✅ | ✅ |
| `network.flow.ingress.interface.id` / `egress.interface.id`, `network.instance.name` | ✅ | ✅ (bounded) |
| `network.flow.sampling.rate` | ✅ | ✅ |

The same discipline applies to operator `label`s: because their key space is
unbounded, labels are entity/resource metadata only and MUST NOT be attached to
metric or flow data points.

## Naming rules

- **Additive only.** Never change the meaning of an existing upstream `network.*`
  attribute. Stable connection descriptors (`network.transport`, `network.type`,
  `network.local/peer.*`, `network.protocol.*`) are referenced via Weaver and reused
  verbatim.
- **Reuse before defining.** `network.io.direction`, `source.*`, `destination.*`,
  `error.type`, `hw.*`, `os.*` are referenced, not redefined.
- **Control-plane protocols use a distinct key.** Upstream `network.protocol.name`
  means the app-layer protocol (http, amqp). Control-plane protocols (bgp, ospf,
  isis) use `network.neighbor.protocol` / `network.routing.protocol` so the two never
  collide.
- **Normalize vendor names to lowercase.** `network.device.vendor.name` is the
  discriminator for vendor extension namespaces; under OTel system-specific naming
  the namespace root equals this value (`cisco.*`, product-qualified `cisco.cdp.*`).
- **Open enums by default.** Closed enums are reserved for genuinely bounded,
  shared vocabularies; most classification attributes accept custom values when no
  well-known value applies.
