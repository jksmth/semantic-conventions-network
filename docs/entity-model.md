# Entity model

The catalogue of entities, how their identity works, how they relate, and how to
classify them. Entities follow the
[K8s `entities.yaml`](https://github.com/open-telemetry/semantic-conventions/blob/main/model/k8s/entities.yaml)
schema: each has `identifying` and `descriptive` attributes.

## Entity catalogue

| Entity | Identity (scoped by) | Make it an entity because… |
|--------|----------------------|----------------------------|
| `network.device` | `device.id` | Independent identity + lifecycle + telemetry |
| `network.chassis` | `chassis.id` (+ device.id) | Physical enclosure with serial/position |
| `network.module` | `module.id` (+ device.id) | FRU with own state, serial, lifecycle (insert/remove) |
| `network.component` | `component.id` (+ device.id) | **Only** when telemetry attaches to it (ASIC/NPU temp, TCAM util). Resist proliferation. |
| `network.interface` | `interface.id` (+ device.id) | The most-instrumented object; own state + counters |
| `network.link` | `link.id` | Cross-device relationship; discovered topology |
| `network.instance` | `instance.name` (+ device.id) | Forwarding/routing context — VRF (L3), bridge-domain/VSI (L2), or pseudowire |
| `network.vlan` | `vlan.id` (+ device.id) | L2 broadcast domain (802.1Q tag) |
| `network.lag` | `lag.id` (+ device.id) | Aggregation group with member set |
| `network.tunnel` | `tunnel.id` (+ device.id) | Overlay/encapsulation endpoint |
| `network.optical.channel` | `channel.id` (+ device.id) | Lambda/carrier with signal telemetry |
| `network.observer` | `observer.id` | The producing probe/collector/agent |
| `network.neighbor` | `neighbor.id` (+ protocol, device.id) | Peer/adjacency/session with own state |

**Not entities** (carry as attributes/metrics): queues, TCAM entries as data, route
prefixes, individual flows-as-things (a flow is a record, not a durable entity).

### The fixed-form profile

`chassis` / `module` / `component` are **optional**. On a fixed-form device (a CPE,
a pizza-box switch, a VM), the `network.device` **is** the inventory unit — do not
emit empty sub-entity shells. Only model a chassis/module when it is independently
identifiable (own serial, position, or virtual-chassis/stack membership) or
independently instrumented (own state, lifecycle events like insert/remove).

`network.component` exists **only** for forwarding-specific utilization
(`network.component.utilization` with `resource=mac_table/tcam/fib/…`). All physical
health — temperature, voltage, fan speed, PSU status, including CPU/ASIC
temperature — is `hw.*`, keyed by `hw.id`. There is one rule: if `hw.*` has a
concept for it, use `hw.*`.

## Identity, relationships, and reconciliation

This is the hard part of network telemetry. Get it wrong and you get duplicate or
merged entities across collection methods.

### Identifier strategy (mirrors K8s `uid` vs `name`)

| Role | Attribute | Properties |
|------|-----------|------------|
| **identifying** | `network.device.id` | Producer-assigned, **stable**, opaque, unique within the deployment. Survives hostname/IP/config change. |
| descriptive | `network.device.name`, `vendor.name`, `hw.model`, `hw.serial_number`, `os.version` | Human-readable, mutable, **not** used for identity matching. |

`serial_number` is a tempting natural key but breaks on RMA/replacement and is
absent on virtual/cloud devices. Treat it as descriptive. Where no stable producer
id exists, recommend deriving one (a UUID persisted on the device, a
controller-assigned system-ip, or a deterministic hash of `chassis.serial_number` +
slot for fixed-form units) — and document the chosen scheme.

### Sub-entity identity is scoped by its parent

`network.interface.id` (e.g. `xe-0/0/0`) is unique **only within a device**. The
full identity of an interface is the pair (`network.device.id`,
`network.interface.id`). The same is true for `module`, `component`, `instance`,
`vlan`. Always emit the parent `device.id` alongside a sub-entity. `ifIndex`
(`network.interface.index`) is **not** reliably stable across reboots unless
ifIndex-persistence is enabled — keep it descriptive, not identifying.

### The reconciliation problem

The same router is observed by an SNMP poller, a gNMI stream, and a NetFlow
exporter. For these to resolve to **one** `network.device`, the chosen
`network.device.id` must be derivable consistently by every producer, or a
downstream entity-resolution step must alias them. This convention's job is to
(a) name the identifying attribute and (b) require its stability; it cannot force
three independent agents to agree. Implementations SHOULD document how each
collection method populates `network.device.id`.

**Never reconcile on a deliberately-shared address.** Some addresses are replicated
across many devices *on purpose* — an anycast gateway (the same SVI IP and anycast
MAC on every leaf), an anycast or MLAG VTEP source IP, an FHRP virtual IP/MAC
(VRRP/HSRP), an Anycast-RP loopback. An address marked `network.address.role` =
`anycast` or `virtual` **MUST NOT** be used as an identity or reconciliation key.
The set of cooperating devices is related by `network.redundancy.group.id`
(membership-by-reference), not by collapsing them onto the shared address.

### A network device may also be a host

A SONiC/Linux whitebox switch or a virtual router genuinely **is** both a `host.*`
and a `network.device.*`. Emit both resource/entity sets and relate them (shared
host identity); do not overload `host.*` to carry network-element semantics, and do
not duplicate generic OS/host metrics under `network.*`.

## Logical containment is not OTel nesting

The domain tree in [architecture.md](architecture.md#domain-view) shows **logical**
containment. OTel does **not** transmit it as nested resources or scopes. It is
expressed through:

1. **Relationship attributes** — child entities carry the parent's identifying key
   as a foreign-key-style reference: `network.interface` carries `network.device.id`
   (and `network.module.id` when applicable); `network.module` carries
   `network.module.parent.id`.
2. **`entity_associations` on metrics** — a metric like `network.interface.io`
   associates with the `network.interface` entity (which in turn references its
   device), exactly as `k8s.pod.network.io` associates with `k8s.pod`.
3. **The emerging OTel entity relationship model** — when it stabilizes, "interface
   BELONGS_TO device" becomes a typed relationship. Until then, relationship
   attributes are the portable mechanism.

Do not put module/interface identity in `InstrumentationScope`. Scope identifies the
*producing instrumentation*, not the network sub-object.

## `network.instance` vs `network.vlan`

These answer different questions and both exist deliberately.

- `network.vlan` is the 802.1Q **broadcast domain** (a tag/segment).
- `network.instance` is a **forwarding/routing context** — `type` ∈ `default` ·
  `l3vrf` · `l2vsi` · `l2p2p` · `l2l3`. It maps 1:1 to OpenConfig
  `network-instance`.

For simple enterprise switching the VLAN **is** effectively the bridge domain, and
no explicit `l2vsi` instance is needed — per-VLAN L2 telemetry (e.g.
`network.l2.mac.entries`) associates with `network.vlan` directly. A
`network.instance` of type `l2vsi`/`l2p2p` is used when a distinct bridging context
exists (VPLS, EVPN MAC-VRF, cross-site bridge domains); `l3vrf` is the classic VRF;
`l2l3` is an integrated L2+L3 instance (EVPN IRB). Routes, protocol neighbours, and
interface bindings attach to a `network.instance`, never to a VLAN directly.

## Classification: the tagging ladder

Operators always want to tag things. There are three tiers; choosing the right one
keeps the model both governed and flexible.

1. **Defined attribute (closed enum or typed value)** — when the classification has
   known, shared, enumerable meaning. Examples: `network.instance.type`,
   `network.interface.role` (uplink/peer/customer/fabric…), `network.device.type`.
   Typed, documented, validated.
2. **`<vendor>.*`** (top-level, e.g. `cisco.*`) — proprietary, vendor-defined
   semantics that are still standardized within that vendor's registry (OTel
   system-specific naming; the namespace root equals `network.device.vendor.name`).
3. **`network.<entity>.label.<key>`** (`template[string]`) — open-ended,
   operator-defined metadata with no shared schema, mirroring `k8s.*.label`.
   Examples: `network.device.label.tenant`, `network.interface.label.site_tier`.

`role` is the curated closed enum; `label` is its open complement. Because label
keys are unbounded, labels are **entity/resource metadata only** — they MUST NOT be
attached to high-cardinality metric or flow data points (the same discipline as the
[cardinality firewall](conventions.md#the-cardinality-firewall)).

### `type` vs `role`

For devices and interfaces, `type` and `role` are **orthogonal** and both exist:

- **`type`** is what the object intrinsically *is* — its dominant capability class,
  intrinsic to the hardware/function. The test: the label is still true if the box
  is redeployed elsewhere (a router is still a router).
- **`role`** is *where it sits* / *what it serves* in this operator's design —
  positional and redeployment-dependent (`pe`, `spine`, `leaf`, `cpe`,
  `aggregation`).

A CPE is `type=router` (or `switch`/`ont`) **+ `role=cpe`** — there is no
`type=cpe`, because a CPE *is* a router/switch/ONT positioned at the customer
premises. Likewise `bng`/`bras` are roles, not types. `olt`/`ont`/`access_point`
**are** types because they name an intrinsic PON/radio device class, not a position.
