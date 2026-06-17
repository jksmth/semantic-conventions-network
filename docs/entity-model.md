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
| `network.interface` | `interface.name` (+ device.id) | The most-instrumented object; own state + counters |
| `network.link` | `link.id` | Cross-device relationship; discovered topology |
| `network.path` | `path.id` | Cross-device ingress→transit→egress traversal (MPLS LSP, SR policy, lightpath); hops join by reference |
| `network.instance` | `instance.name` (+ device.id) | Forwarding/routing context — VRF (L3), bridge-domain/VSI (L2), or pseudowire |
| `network.vlan` | `vlan.id` (+ device.id) | L2 broadcast domain (802.1Q tag) |
| `network.lag` | `lag.id` (+ device.id) | Aggregation group with member set |
| `network.tunnel` | `tunnel.id` (+ device.id) | Overlay/encapsulation endpoint |
| `network.optical.channel` | `channel.id` (+ device.id) | Lambda/carrier with signal telemetry |
| `network.observer` | `observer.id` | The producing probe/collector/agent |
| `network.neighbor` | `neighbor.id` (+ protocol, device.id) | Peer/adjacency/session with own state |

**Not entities** (carry as attributes/metrics): queues, TCAM entries as data, route
prefixes, individual flows-as-things (a flow is a record, not a durable entity).

**The test for "is this an entity?":** *a relationship that needs attributes is an
entity in disguise.* A route has a next-hop and a metric, an interface has state and
counters, a VLAN/LAG/VRF each has identity and a lifecycle — all carry attributes, so all
are entities (a route's *count* is a metric, but a route as a thing is data, not a durable
entity). The corollary keeps edges clean: **no attributes on an edge.** A fact that must
persist belongs on an entity, not on a relationship — which is exactly why `network.link`
is a first-class entity (it carries `type`/`topology`/`state`) rather than a bare edge.

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

`network.device.id` is the [`host.id`](https://opentelemetry.io/docs/specs/semconv/resource/host/)
pattern applied to a network element: **one opaque key, sources documented by
context, value never source-prefixed.** Just as `host.id` is the cloud
`instance_id` for a cloud VM and the OS `machine-id` for bare metal — one key, a
documented source table, an opaque value — `network.device.id` takes its value from
the most stable identifier available for that class of device, and the *value stays
opaque* (no `serial:` / `name:` prefix). This follows the OTel
[Entity Data Model](https://opentelemetry.io/docs/specs/otel/entities/data-model/):
identity is a typed attribute map, so cross-type collisions are handled by the *key*
name and any genuine insufficiency is handled by adding a second identifying
attribute (Minimally Sufficient Identity) — never by encoding structure into one
value.

#### Source precedence by device class

Like the `host.id` OS-source table, the recommended source for `network.device.id`
depends on what the device class reliably exposes. Pick the strongest available and
**document the choice per collection method**:

| Device class | Recommended source (strongest available) | Rationale |
|--------------|-------------------------------------------|-----------|
| Managed router / switch / firewall / OLT | Operator/controller-**assigned** id (provisioned UUID, controller system-ip), else the configured hostname | These are deliberately provisioned and named; allocation gives a clean, stable, collision-free key. |
| Sealed access unit — ONT/ONU, CPE, Wi-Fi AP, transceiver | Hardware **serial number** | No operator hostname exists at fleet scale; the serial is burned-in, immutable, and is how the upstream system already addresses the unit (e.g. an OLT addressing an ONT over OMCI). |
| Modular / fixed-form sub-chassis without its own assigned id | Deterministic hash of chassis serial + slot | A repeatable derived key when nothing stronger is assigned. |
| Last resort only | Management IP | Mutable and collision-prone under NAT/re-addressing; acceptable only when no stabler key exists, and never a deliberately-shared address (see below). |

`snmpEngineID` (SNMP-FRAMEWORK-MIB) is a reasonable SNMP-collection-specific source
between hostname and MAC where a poller has it. Whatever the source, the value is
recorded opaquely and **does not change for the entity's lifetime** — a stronger key
appearing later is descriptive (`hw.serial_number`), not a reason to re-key.

### Sub-entity identity is scoped by its parent

`network.interface.name` (e.g. `xe-0/0/0`, the IF-MIB `ifName`) is unique **only within
a device**. The full identity of an interface is the pair (`network.device.id`,
`network.interface.name`). The same scoping is true for `module`, `component`,
`instance`, `vlan`. Always emit the parent `device.id` alongside a sub-entity.

Interface identity reuses the **Stable upstream `network.interface.name`** attribute
rather than minting a parallel `network.interface.id`: reuse-before-defining, plus
minimal identity (non-SDK producers synthesize the Prometheus `instance` label by hashing
the identifying attributes, so a redundant same-valued key only bloats the hash), plus
alignment with the Networking WG direction of keying interfaces on the standard IF-MIB
identifiers. `ifIndex` (`network.interface.index`) is **not** reliably stable across
reboots unless ifIndex-persistence is enabled — it is an opt-in disambiguator, **not**
identifying. The other sub-entities keep a minted `.id` because no Stable upstream
attribute exists to reuse for them; interface is special precisely because upstream
already owns the name attribute. Foreign keys are named for the identity they join on
(`network.link.local.interface.name`, `network.interface.lower_layer.name`).

### The reconciliation problem

The same router is observed by an SNMP poller, a gNMI stream, and a NetFlow
exporter. For these to resolve to **one** `network.device`, the OTel
[Entity Data Model](https://opentelemetry.io/docs/specs/otel/entities/data-model/)
gives two normative rules we adopt (rather than treating convergence as purely a
backend concern):

- **Repeatable Identity.** Identifying values SHOULD be repeatably obtainable by any
  observer of the entity — the device itself, a Collector beside it, or another
  system — so independent observers that pick the same documented source converge by
  construction.
- **Multi-observer rule.** Two observers reporting the same device MUST be able to
  supply identical identifying values. An observer that **cannot** reliably obtain
  the stable id MUST NOT emit a `network.device` on a guessed or weak key. Instead it
  SHOULD either (a) delegate to the observer that can — treating that observer as the
  source of truth — or (b) emit a **different entity type** whose identity it *can*
  populate reliably (a NetFlow exporter that sees only addresses emits flow records
  and, where modelled, address/neighbour entities — not a half-identified device).

This is a stronger discipline than degrading down a precedence ladder to a weak rung:
a producer that only has a MAC or a management IP does not mint a fragile
`network.device` that will later collide or fork — it stays in its lane. The
convention still cannot force three independently-configured agents to agree on a
value; what it now does is name the source precedence (above), require stability, and
forbid emitting the entity type when the identity cannot be met. Implementations
SHOULD document how each collection method populates `network.device.id`.

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

The relationship *types* are a small vocabulary, `network.relationship.type`, carried in
the merged entity-events `entity.state` payload (and supplying values for the generic
upstream `relationship.type`): `contains` (parent → part), `layered_over` (an interface
or tunnel over its lower layer), `member_of` (a member → its aggregate),
`connected_to` (an L1/L2 adjacency), `adjacent_to` / `peers_with` (a control-plane
adjacency / session), and `next_hop`. The core set (`connected_to`, `member_of`,
`contains`) has independently converged across multiple implementations, which is a
standardization-readiness signal.

**Membership-by-reference, not n-ary edges.** A 1:N or group relationship is expressed by
the members each carrying the owner's id as a descriptive attribute, with the set
reconstructed by a query over that id — never an edge entity. This is how `network.lag`
members, `network.link` point-to-multipoint members (a PON ODN tree, a WiFi BSS, a PtMP
sector — `network.link.topology` ∈ `point_to_point`/`point_to_multipoint`/`broadcast`/`nbma`),
`network.path` hops, and `network.redundancy.group` members are all modelled. The
head/owner entity emits its own state; members reference it. This keeps the model
expressible today without waiting for a first-class edge primitive.

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
