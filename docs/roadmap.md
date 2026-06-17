# Scope, roadmap, and open questions

What this model covers, what it deliberately does **not**, what is built versus planned,
and the questions still open. If you are deciding whether a piece of network telemetry
belongs here — or wondering why something is missing — start here.

## Scope philosophy

The model follows a few rules that decide what gets built and what gets referenced or
declined:

- **Reuse before you mint.** `network.transport`, `source.*`/`destination.*`, `hw.*`,
  `network.io.direction`, `error.type` already exist upstream — reference them, never
  redefine them.
- **Don't transcribe MIBs/YANG.** Take the *concept* and render it OTel-idiomatically
  (the way `hw.*` took the ENTITY-MIB parent-pointer concept without copying the table).
- **Stay in your domain.** Security, synthetic/RUM, and application-layer telemetry have
  (or will have) their own conventions. Align and reference; do not re-implement.
- **Cardinality discipline.** High-cardinality objects are counts + records, never metric
  dimensions and rarely entities (see [the cardinality firewall](conventions.md#the-cardinality-firewall)).
- **Breadth that matters.** A signal every device emits beats one three specialist
  devices emit. Stabilize the common core; gate the long tail behind optional packages.

## In scope

The core every network element shares, stabilized first:

- **Inventory** — `network.device` (+ optional `chassis`/`module`/`component`),
  `network.interface`, `network.link`, `network.observer`.
- **State** — admin/oper/health axes, normalized+native protocol state, interface
  counters, table-occupancy counts, transition events and alarms.
- **Traffic observation** — `network.flow` records and bounded aggregates,
  `network.packet`, the observer/source/destination split.
- **Control plane** — `network.neighbor` (the generic adjacency/peer), `network.routing`.
- **Active measurement** — `network.test` (latency/loss/jitter, path, reachability).

Extended packages (real `network.*` concepts, narrower device classes) build on the core:
L2/STP, ARP/ND, VLAN/LAG/instance/tunnel, EVPN, MPLS/segment-routing, multicast, optical
endpoint channels, PON/access and subscriber edge, WiFi, NAT, QoS, redundancy, session.

## Out of scope (reference or decline)

These serve a small device population at large modelling cost, or belong to another
standards body. They are deliberately excluded from the core so they stop generating
pressure on it:

- **Full optical line system / photonic transport** — the *endpoint coherent channel* is
  in scope; the line system between endpoints (EDFA gain/tilt, ROADM degrees + WSS
  spectrum, OMS/OTS layering, flexgrid, multi-ROADM lightpath) is an enormous specialist
  domain (OpenROADM / `openconfig-optical-amplifier` / G.872). If demand materializes it
  is a separate optional package, not part of the stable core.
- **Full packet capture / payload (pcap)** — OTel does not carry captured packets:
  not the packet bytes, and not a capture-artifact pointer. pcap/pcapng already has
  its format and tooling; re-encoding captures as OTLP inflates size and loses every
  tool. A *sampled* packet is a `network.flow` observation (`packets = 1` +
  `network.flow.sampling.rate`), not a capture; packet *drop classification* is
  `network.packet.drop.reason`. Payload capture itself is declined.
- **5G / mobile packet core + RAN** — UPF/AMF/gNB is a 3GPP domain. Mobile is kept as an
  access-technology attribute only; the packet core/RAN is declined.
- **Application-layer test detail** — HTTP/DNS/page-load waterfalls reuse the upstream
  HTTP / DNS / synthetic-monitoring conventions; `network.test.*` owns only the L3/L4 +
  path + transport-voice layer, joined by `network.test.id`.
- **Security analytics** — app-ID, URL filtering, IPS/threat, TLS-decryption analytics
  align with ECS / a future OTel security convention. The model owns the
  network-structural anchor (zones, the stateful session/connection table as occupancy
  metrics, NAT/address pools, the policy rulebase as hit-counted aggregates), not the
  threat layer.
- **Configuration and control** — no config containers, no RPCs, no writable parameters;
  this is a telemetry vocabulary.

## Recurring structural patterns

Several packages are instances of the same primitive. Recognizing this keeps the model
small and is the strongest signal that a shape is right (it recurs across unrelated
technologies):

- **Membership-by-reference, not n-ary edges.** A 1:N or group relationship is modelled
  as a head/owner entity plus members that each carry the owner's id as a descriptive
  attribute. The set is reconstructed by a query over that id. This is how `network.lag`
  members, `network.link` point-to-multipoint members (PON tree, WiFi BSS, PtMP sector),
  `network.path` hops, and redundancy-group members all work — no edge entity required.
- **The source-endpoint / edge / path trio.** `network.tunnel` (a device-scoped overlay
  *source* endpoint anchoring a discovered peer mesh — VXLAN VTEP, SD-WAN TLOC),
  `network.link` (a cross-device *edge*), and `network.path` (a cross-device
  ingress→transit→egress *traversal* — MPLS LSP, SR policy, lightpath) are three faces of
  one primitive. Discovered peer meshes are metric dimensions, not entities.
- **Counts + records, not entities.** Routes, MAC/ARP entries, sessions, subscribers,
  and stations are high-cardinality and transient: modelled as aggregate counts (low-card
  metrics) plus per-object records, never as per-object entities or per-object metric
  series.

## Known limitations and open questions

These are unresolved or depend on evolving OpenTelemetry work. They are recorded so they
are not re-litigated and so contributors know where the soft spots are.

### Depends on the evolving OTel entity/relationship model

- **Telemetry about a subject the producer is not.** A flow exporter, tap, or SNMP poller
  produces telemetry *about* devices it is not. OTel's Resource = *the producing entity*,
  and `entity_associations` assume the associated entity is part of the producing
  resource. Attaching the subject entity to externally-observed telemetry is not yet fully
  expressible; `network.observer.id` is carried as a Resource attribute as the interim
  answer.
- **Relationships as first-class edges.** Topology relationships (a link or adjacency
  spanning two separately-observed devices, where only one side reports) are modelled with
  foreign-key attributes plus the `network.relationship.type` vocabulary carried in the
  merged entity-events `entity.state` payload. A static `relationships:` authoring field,
  n-ary/two-ended edges, and formal "is-a" relationships (a NOS switch *is-a* host) await
  upstream.
- **Entity composition for a device that is a host.** Upstream composes a host Resource
  from co-located `host` ⊕ `os` entities rather than flattening. This model currently
  flattens `os.*`/`hw.*` onto `network.device`; modelling the NOS as a co-located `os`
  entity (so a NOS upgrade is an `os` change, not device-identity churn) is a staged
  direction.

### Identity and reconciliation

- **Cross-method id derivation.** The model names `network.device.id`, requires its
  stability, and gives a source-precedence table by device class, but cannot force an SNMP
  poller, a gNMI stream, and a flow exporter to independently derive the *same* value. The
  multi-observer rule ("if you cannot reliably obtain the stable id, do not emit the
  entity type") bounds the damage; full reconciliation is a backend concern. See
  [entity-model.md](entity-model.md#the-reconciliation-problem).
- **Address-as-join-node (under evaluation).** A shared `network.address` node would let
  host-side and SNMP-side topology join by exact identity with no heuristic. It is
  attractive but collides with the anycast/virtual hazard; a bounded form gated by
  `network.address.role` is the candidate, not yet built.

### Governance

- **Federated versioning** — if vendor/domain registries pin this `schema_url`, how core
  breaking changes propagate needs a defined schema-transformation discipline.
- **Community `schema_url` domain** — `schemas.seconv.network` is a community domain, not
  `opentelemetry.io`, unless/until officially adopted.
- **Long-term home** — federated registry versus upstreaming, to be decided with the OTel
  Semantic Conventions group and the Networking Working Group (see
  [architecture.md](architecture.md#governance)).

## The central risk: validation

The model's breadth was built ahead of instrumentation, and OpenTelemetry's own gate
forbids declaring conventions stable until instrumentation uses them. Everything here is
`development` by construction. The highest-value next step is not more breadth — it is
driving one or two core packages (device, interface, neighbor, flow) to a validating
implementation, with an OpenConfig→`network.*` or SNMP→`network.*` Collector crosswalk
([prior-art.md](prior-art.md#crosswalks-the-adoption-lever)) as the first real data
source. The Networking Working Group's roadmap of SNMP / NetFlow / eBPF Collector
receivers is the credible path to that validation.
