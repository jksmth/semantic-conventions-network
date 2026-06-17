# Conventions

Cross-cutting modelling patterns that apply across every package: how state is
represented, which signal carries which kind of telemetry, the cardinality
firewall, and naming rules.

## State modelling

State appears in three coordinated forms — do not pick only one.

1. **Current-state UpDownCounter** — e.g. the hardware-entity `network.oper.state`
   (shared by `network.device` / `network.chassis` / `network.module` /
   `network.component`) and its interface-plane sibling
   `network.interface.oper.state`, surfaced as
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

### Admin, oper, and health are three orthogonal axes

A managed hardware entity has **three independent state axes** (the X.731 /
ENTITY-STATE-MIB / RFC 8348 split) — never collapse them into one "status":

| Axis | Where | Question | Values |
|------|-------|----------|--------|
| **Administrative** | `network.admin.state` (`common`) | Did an operator take it out of service? | `unlocked` / `locked` / `shutting_down` |
| **Operational** | `network.oper.state` (`common`) | Can it carry traffic right now? | `enabled` / `disabled` / `testing` |
| **Health** | `hw.state` (upstream `hw.status`) | Is the hardware healthy? | `ok` / `degraded` / `failed` / … |

They are orthogonal because their combinations are all meaningful: a device can be
`hw.state=ok` + `admin.state=locked` + `oper.state=disabled` (healthy hardware an
operator shut down), or `hw.state=failed` + `admin.state=unlocked` +
`oper.state=disabled` (a fault, not an operator action). Comparing the axes is what
separates "operator shut it" from "it broke" — collapsing them loses that signal.
`hw.state` is **health only**; it is *not* an oper-state and must not be used as one.

There are **two distinct state planes**, because the two source standards use
different vocabularies and no consumer aggregates admin/oper state across
interfaces *and* chassis/modules in a single query:

- **Hardware-entity plane** — `network.admin.state` / `network.oper.state`
  (`common`), the ENTITY-STATE-MIB / X.731 vocabulary
  (`unlocked`/`locked`/`shutting_down`, `enabled`/`disabled`/`testing`). These
  four grains (`network.device` / `network.chassis` / `network.module` /
  `network.component`) are all RFC 8348 `/hardware/component` objects and
  genuinely share one vocabulary, so the attribute is defined once and surfaced
  as the `network.admin.status` / `network.oper.status` status metrics.
- **Interface plane** — `network.interface.admin.state` /
  `network.interface.oper.state` (the `interface` package), the RFC 2863 IF-MIB
  (RFC 8343) vocabulary (`up`/`down`/`testing` plus the diagnostic oper values
  `dormant`/`lower_layer_down`/`not_present`), surfaced as the
  `network.interface.admin.status` / `network.interface.oper.status` metrics.

They are kept as **separate attributes, not one shared superset enum**. Merging
them put synonyms (`up` ≡ `enabled`, `down` ≡ `disabled`) on the same axis, which
double-buckets the `sum by (state)` the status metrics depend on; splitting keeps
each enum to one value per concept while preserving the diagnostically valuable
interface states (`lower_layer_down`, `dormant`, `not_present`) rather than
collapsing them to a coarse `down`. The verbatim vendor term rides on the shared
`network.native_state` on either plane.

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

## Entity info metrics and `entity.state`

Each entity has a metric-pipeline projection — a `<entity>.info` gauge fixed at
1 (the Prometheus `target_info` / kube-state-metrics `*_info` pattern, e.g.
`network.device.info`, `network.interface.info`) — and an event-pipeline
projection — the `entity.state` event (model/events). **They are twins: the
same attribute set, carried in two signals.** The info metric serves
metric-only backends (Prometheus joins: `op_series * on(<identity>)
group_left(<descriptors>) <entity>.info`); the `entity.state` event serves
topology/lifecycle consumers and additionally carries relationships. Both
re-emit the full current attribute set on change (a new label set for the
metric; a fresh event for the event).

The rule for what goes on the info metric:

1. **Identity is REQUIRED and carried ON the metric** — it is the join key, so
   it cannot merely ride the Resource. For a sub-entity this is the
   device-scoped pair (e.g. `network.device.id` + `network.interface.name`).
2. **Mirror the entity's `description` set 1:1** as opt_in labels. Do not
   hand-pick a subset — divergence from the entity (and from the future
   automatic projection) is the failure mode. This **includes state enums**
   (`network.admin.state`, `network.oper.state`, `network.interface.duplex`,
   `network.interface.poe.state`, …): they appear BOTH as info labels AND as
   their own status metrics (`network.interface.oper.status` etc.). That dual
   is deliberate and matches kube-state (`kube_pod_status_phase` the series +
   identity on `kube_pod_info`) — do not "tidy it away".
3. **Exclude only measurements** — counters, continuous-value gauges, and
   timestamps. A measurement belongs on its own series, never as a label. A
   timestamp (e.g. `network.interface.last_change`) is the clearest case: an
   unbounded value space that would churn the info series on every change, so
   it is modelled as a gauge, not an entity-description attribute.

The litmus test for an entity attribute is therefore descriptor-vs-measurement,
**not** stable-vs-mutable: an occasionally-churning descriptor (an admin-state
flip) is still a label; a never-churning measurement (a one-off count) is still
a series.

## Flow and packet modelling

### Signal choice

| Form | Signal | When |
|------|--------|------|
| **Raw flow record** | **Log-based Event** (`event.name = network.flow`) | Default. A flow is a time-bounded observation with start/end/duration and measures — semantically a structured event, not a causal span. |
| **Aggregated flow** | **Metric** | Rates/totals over low-cardinality dimensions. |
| **Flow as span** | **Trace** | Pragmatic alternative for connection-oriented L4/L7 flows where duration + correlation drive tooling. Flows are not causal spans and won't form valid trace trees. |

The `network.flow.*` / `network.observer.*` attribute set is identical regardless of
which signal carries it.

### The `network.packet.*` namespace

`network.packet.*` describes a packet, or a **class** of packets aggregated by a
shared property (a dimension on a packet counter). It is the packet-property
partner to `network.flow.*` (the observed conversation), and it is an
**attribute-only namespace** — two authored leaves, both dimensions, no packet
record of its own:

- `network.packet.type` (`unicast`/`multicast`/`broadcast`) — the IF-MIB
  `ifHC*{Ucast,Multicast,Broadcast}Pkts` / OpenConfig
  `{in,out}-{unicast,multicast,broadcast}-pkts` cast split, reused verbatim from
  the OTel `ciscoosreceiver`. A low-cardinality opt-in dimension on the interface
  packet counters (`network.interface.packets` / `.discards`).
- `network.packet.drop.reason` — why an **intentional** discard happened
  (`no_route`/`acl_deny`/`policy`/…). The discards twin of how `error.type`
  classifies `network.interface.errors`: corrupt/unintended frames
  (`checksum_error`, `malformed`, CRC) stay on `network.interface.errors`, never
  here. Carried as an opt-in dimension on `network.interface.discards` and on a
  `network.flow` record where `network.flow.action = drop`.

Both follow the "class/cause is a dimension, not a name segment" idiom, as
`network.io.direction` is for direction. Three things that are **not** here: a
**sampled packet** is a `network.flow` observation (`packets = 1` +
`network.flow.sampling.rate`), not a packet record; **full payload capture**
(pcap) is **out of scope** — OTel does not carry captured packets; a per-drop
event (`network.packet.dropped`, eBPF/`drop_monitor` style) is named but
deferred.

### The cardinality firewall

**The general rule: high cardinality belongs on records, never on metric time
series.** Cardinality is a cost on *metric time series*, not on telemetry in the
abstract. A metric data point's attribute-set defines a series the backend holds
resident, indexes, and bills for the life of the series, so each unique combination
accumulates — N unique label-sets is N permanent series. A log/event record (or a
span) is a discrete, timestamped occurrence: its attributes describe that one
occurrence and then age out by retention, never accumulating into a resident index
keyed by attribute combination. A million distinct flow records is a million rows
(a throughput/retention concern); a million distinct values on a metric label is a
million series (a series-explosion concern). So high cardinality is not "bad" — it
is *misplaced* when it lands on a metric dimension. The flow table below is the
worked instance of this rule.

High-cardinality flow identity belongs on **records**, never on metric time series.

| Attribute | On flow **records** (logs/events) | On flow **metrics** |
|-----------|:---:|:---:|
| `source.address`, `destination.address`, ports | ✅ | ❌ |
| `network.tunnel.id`, `source.mac` / `destination.mac` pairs | ✅ | ❌ |
| `network.flow.id`, `tcp.flags`, `community_id` | ✅ | ❌ |
| `network.observer.id`, `observer.type` | ✅ | ✅ |
| `network.flow.direction`, `network.flow.action` | ✅ | ✅ |
| `network.protocol.name`, `network.transport`, `network.type` | ✅ | ✅ |
| `network.interface.name` (observation interface), `network.instance.name` | ✅ | ✅ (bounded) |
| `source.zone` / `destination.zone`, `destination.vlan.id` / `.name` | ✅ | ✅ (bounded) |
| `network.flow.sampling.rate` | ✅ | ✅ |

The ordered MPLS **label stack** (beyond the single `network.tunnel.id`) and
distinct ingress+egress interfaces (IPFIX IE 10/14) are deferred to the IPFIX IE
long tail, not shipped here.

The same discipline applies to operator `label`s: because their key space is
unbounded, labels are entity/resource metadata only and MUST NOT be attached to
metric or flow data points.

### Two direction axes, distinct by design

Two direction attributes coexist and are not interchangeable:

- `network.io.direction` = `transmit` | `receive` — for interface/device **counters**
  (the reused upstream attribute).
- `network.flow.direction` = `ingress` | `egress` — the **observation-point**
  perspective on a flow (the closed IPFIX `flowDirection` pair, IE 61:
  0=ingress/1=egress). The broader perimeter axis (`internal`/`external`) and the
  initiator/responder (request-vs-response) axis are deferred, not minted here.

A flow record may carry both: which way the bytes moved on the wire
(`network.io.direction`), and which way the flow crossed the observation point
(`network.flow.direction`).

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

### The OpenTelemetry naming rules this model follows

When adding a metric or attribute, check it against the upstream
[naming spec](https://opentelemetry.io/docs/specs/semconv/general/naming/). The rules
that come up most often here:

- **An UpDownCounter name MUST NOT be pluralized.** The count of a thing is
  `{namespace}.{object}.count`, not `{namespace}.{objects}` — e.g.
  `network.routing.route.count`, `network.l2.fdb.entry.count`, not
  `network.routing.routes`. (Spec precedent: `system.process.count`.) This keys off the
  *semantics* ("a count of a thing"), not the instrument type.
- **Monotonic Counters SHOULD be pluralized** when they record discrete countable
  instances with a `{thing}` unit — `network.interface.packets`,
  `network.protocol.messages`, `network.neighbor.state_changes`,
  `network.session.setups`/`teardowns`. So the occupancy gauges are `.count` (singular)
  and the monotonic event counters are plural — that asymmetry is intentional.
- **`limit` / `usage` / `utilization` are a defined vocabulary.** `limit` = the known
  total, `usage` = the amount used, `utilization` = the fraction (`1`). Use them as
  upstream `system.memory.*` does.
- **`{object}.{property}` with a dot, not an underscore,** when the object could have
  other properties. `network.vlan.fdb.limit` (the FDB object has entries/learning/limit),
  not `fdb_limit`. Reserve the underscore for a single multi-word concept where the dot
  would change the meaning (`min_links`, `route_target`, `system_id`, `native_state`).
- **Be precise; avoid cross-convention collisions.** Abbreviations are fine when
  domain-qualified.
- **Local table rule (OpenConfig-aligned).** For a table, the *container* takes the
  standard table name and the *entry/object* keeps its object name — `network.l2.fdb`
  (the filtering database) with `network.l2.fdb.entry.*` and `network.l2.mac.*`
  leaves, mirroring the BRIDGE-MIB / OpenConfig `fdb` container + `mac-*` entries.

### Names shared across signals are allowed

A metric and an attribute MAY share the same name — the uniqueness rule applies only
*within* a category (two attributes, or two metrics, must not collide; an attribute and a
metric may). This is the sanctioned bridge for the entity/signal duality:
`network.interface.speed` exists both as a **descriptive entity attribute**
(configured/negotiated speed, "at rest") and as a **gauge** (current operational speed,
"in motion"). Comparing the two surfaces a speed-mismatch fault. Do not rename one to
avoid an imagined collision.

### Naming-collision watch

A few names sit close to existing upstream attributes and need a deliberate, distinct
key rather than an overload:

- `network.protocol.name` (upstream, app-layer: http, amqp) vs control-plane protocols
  → use `network.neighbor.protocol` / `network.routing.protocol`. **The most important
  one.**
- `network.connection.type` (upstream: wifi/wired/cell) vs `network.interface.type`
  (ethernet/lag/tunnel) — different keys, different meaning.
- `network.carrier.*` (upstream, mobile/RUM, device-side) vs `network.access.technology`
  (operator-side access medium) — keep separate.

## Choosing an instrument

For a "how many right now" value (route count, MAC/FDB entries, sessions, pool
addresses), the instrument is an **(asynchronous) UpDownCounter**, not a Gauge. The
deciding property is **additivity**: summing the value across a dimension is meaningful
(`sum(network.routing.route.count)` across devices = "total routes in the fleet"), and the
value is non-monotonic (entries come and go). Additive + non-monotonic + an absolute
polled table size = UpDownCounter. A Gauge is for *non-additive* levels — a temperature,
a ratio, an optical power reading.

**Status/state metrics are also UpDownCounters.** A current-state metric uses the
enum-as-attribute pattern (one series per possible state value, `1` for the active state
and `0` otherwise) so a `sum by (state)` counts how many entities sit in each state — per
the OTel [status-metrics guide](https://opentelemetry.io/docs/specs/semconv/how-to-write-conventions/status-metrics/),
a deliberate UpDownCounter, not a Gauge. This model keeps the domain word **state** for
both the metric and its enum attribute (`network.interface.oper.state`,
`network.stp.port.state`) because networking has a well-known "state" vocabulary (IEEE
802.1D, RFC 2863); the spec permits keeping a well-known term over the generic
`status`/`state` split.

**Peak/high-water-mark values stay their own metric, not a `stat` dimension.** Where a
device hands you a reset-on-read watermark (e.g. `network.qos.queue.depth.max` alongside
the instantaneous `network.qos.queue.depth`), keep them as separate metrics: a watermark
cannot be reconstructed from a histogram, and a shared `stat=current|max` dimension would
invite meaningless aggregation across two different measurement semantics.

**UCUM unit gotchas** (OTel requires UCUM): optical power is `dB[mW]` (decibel-milliwatts),
**not** the literal `dBm`; ratios such as OSNR are `dB`; BER, utilization, and loss ratio
are the dimensionless `1` (0–1), not a percentage; link speed is `bit/s` everywhere, never
`By/s`. Reuse `network.io.direction` rather than minting `rx`/`tx` names **for a
bidirectional counter of one quantity** — the rule does not apply to a single-valued
quantity whose name happens to contain a direction word (see below).

### Naming signal power and strength

Three packages measure optical/RF power, and the naming follows the established term for
each — which is deliberately *not* uniform, because the industry terms are not uniform:

- **Symmetric power measured at both ends of one link → one metric + `network.io.direction`.**
  Optical Tx and Rx power are the *same quantity* (optical power, `dB[mW]`) measured at
  each fibre end, so they fold into `network.optical.power` + direction (the OTel-idiomatic
  form of OpenConfig's `output-power`/`input-power`).
- **Transmit power with no same-quantity receive twin → `transmit_power`.** A radio's
  output power (`network.wifi.radio.transmit_power`, `dB[mW]`) is a single value; there is
  no `rx_power`. The name matches OpenConfig `transmit-power` and TR-181 `TransmitPower`.
  Do **not** spell it `tx_power` — that reads as the folded-direction counter pattern it is
  not.
- **Received signal strength → `rssi`.** The strength of an incoming signal at the
  receiver is RSSI everywhere in RF and PON: `network.wifi.radio.rssi` (the radio's own
  uplink in sta/mesh mode), `network.wifi.station.rssi` (a client at the AP), and
  `network.pon.onu.rssi` (the OLT's per-ONU upstream burst). All `dB[mW]`. RSSI is the
  receiver-side measurement regardless of *who* the receiver is — the observer model
  records who measured it, not the metric name.

So `transmit_power` (output) paired with `rssi` (received) is the correct asymmetric RF
naming, not an inconsistency to "fix" by forcing a symmetric `rx_power`/`tx_power` pair.

## Protocol counter scoping

Per-protocol message/error counters look alike across protocols, but they do not
all live in the same place. The rule that decides where a protocol's counters go is
**whether the counted unit has an identifiable peer**:

- **Peered protocol → the generic neighbour counters.** When a protocol forms an
  identifiable adjacency/session — BGP, OSPF, IS-IS, LDP, RSVP, BFD, PIM, **LACP** —
  its message and error counters attach to `network.protocol.messages` /
  `network.protocol.errors` on the `network.neighbor`, keyed by
  `network.neighbor.protocol`, with a PDU kind on `network.protocol.message.type`
  and an error class on `error.type`. No per-protocol metric namespace is minted.
  LACP is the worked case: it runs per member port against exactly one partner
  (already a `network.neighbor` `protocol=lacp`), so its LACPDU/marker counters are
  `network.protocol.messages` (`message.type=lacpdu`/`marker`/`marker_response`) and
  its unknown/illegal receive errors are `network.protocol.errors`
  (`error.type=unknown`/`illegal`) — zero new metric names.

- **Peerless protocol → its own per-domain namespace.** When the counted unit has
  **no** identifiable peer — multicast/broadcast discovery where a frame is processed
  before any peer is known (**LLDP**), or a per-agent table churn — the generic
  neighbour counters are structurally the wrong home (there is no neighbour to key
  on). These get a per-domain `network.<protocol>.*` namespace instead
  (`network.lldp.frames`/`.errors`/`.remote_changes`), scoped to the entity that
  genuinely owns them (`network.interface` for per-port stats, `network.device` for
  per-agent tables).

- **Per-protocol facets with no generic equivalent → a protocol-qualified
  refinement.** A peered protocol may expose facets the generic counters cannot carry
  — a protocol-specific timer, an oper-state flag octet, a convergence counter. These
  refine the core signal under `network.neighbor.<protocol>.*`, gated on
  `network.neighbor.protocol`. Examples: `network.neighbor.eigrp.srtt`/`.rto`/
  `.queue.depth`; `network.neighbor.lacp.state` (the IEEE 802.1AX actor/partner
  oper-state octet as a per-flag StateSet) and `network.neighbor.lacp.churn`. This is
  for *standardized* protocols (EIGRP is RFC 7868; LACP is IEEE 802.1AX); genuinely
  proprietary internals with no neutral equivalent instead use a top-level vendor
  namespace keyed by `network.device.vendor.name` (`cisco.cdp.*`), never a
  `network.<vendor>.*` infix.

The litmus test is the same one the [state-modelling](#state-modelling) and
[cardinality](#the-cardinality-firewall) rules use: model the signal on the entity
that genuinely owns it. A counter with one identifiable peer is owned by the
adjacency; a discovery frame with no peer is owned by the port or the device.

### `network.neighbor` is the adjacency namespace, and the anti-explosion rule

`network.neighbor` is the confirmed term for the control-plane adjacency/peer
namespace. It is deliberately **not** `network.peer`: the Stable upstream
`network.peer.*` is the peer of a single network *connection* (a socket-scoped
descriptor that fits only TCP/UDP neighbours), whereas a `network.neighbor` is
protocol-agnostic — OSPF runs over IP multicast, IS-IS/LLDP/LACP over L2 with no IP
socket. `network.peer` therefore never substitutes for `network.neighbor`.

The namespace exists to **gate per-protocol sub-namespace explosion**. Three rules
decide where a protocol's counters live:

1. **One identifiable peer → reuse the generic neighbour counters.** A counter whose
   counted unit has exactly one identifiable peer reuses `network.protocol.messages` /
   `network.protocol.errors` on the `network.neighbor`, keyed by
   `network.neighbor.protocol`. No new metric namespace is minted.
2. **Peerless signal → its own per-domain namespace.** A signal with no identifiable
   peer (a discovery frame processed before any peer is known, a per-agent table
   churn) gets its own `network.<x>.*` namespace, scoped to the entity that genuinely
   owns it — never the neighbour counters, because there is no neighbour to key on.
3. **Protocol-unique facet → a qualified refinement, only when justified.** A
   `network.neighbor.<protocol>.*` refinement is justified **only** when a facet is
   protocol-unique and has no vendor-neutral generic equivalent (a protocol-specific
   timer, an oper-state flag octet, a convergence counter). When a facet is
   expressible by the generic counters, the refinement is not justified and MUST NOT
   be minted.
