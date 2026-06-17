# Prior art and crosswalks

Where this model aligns with the established vendor-neutral network data models, where
it deliberately diverges, and how to map existing telemetry into it. If you are
translating an existing NOS/CPE model (SNMP, OpenConfig over gNMI, or TR-181 over
TR-069/USP) into `network.*`, start here.

The two mature vendor-neutral domain models compared against are the Broadband Forum's
**TR-181 "Device:2"** (carried by TR-069/CWMP and TR-369/USP; strong on CPE/access —
DSL, GPON, WiFi, VoIP, hosts) and **OpenConfig** (operator-driven YANG via gNMI; strong
on routing/MPLS/optical/platform). Both descend from **SNMP MIBs** and run in parallel
with **IETF/BBF YANG**.

## The one difference that explains all the others

| | TR-181 / TR-069 / TR-369 | OpenConfig | This model (`network.*`) |
|---|---|---|---|
| **Purpose** | Remote management + telemetry of CPE/access | Config + streaming telemetry of SP/DC elements | **Observability only** |
| **Operation** | Read **and write**, RPCs, diagnostics | Read/write config, subscribe to state | Emit signals; never configure |
| **Authority** | One authoritative **per-device tree** | One authoritative **per-device tree** | **Multi-source, multi-perspective**; telemetry may be partial, externally observed, or aggregated |
| **Identity** | Object **path** + instance index | Component/interface **name** in the device tree | **Stable producer-assigned id** + relationship refs; must reconcile across collectors |

TR-181 and OpenConfig are management/configuration models with a single authoritative
device tree. This model is an **observability vocabulary** that must work when (a) nobody
owns a complete tree, (b) the emitter is a probe that is *not* the device, and (c) data
is aggregated across a fleet. Almost every alignment and divergence below follows from
that.

## The lineage: SNMP MIBs and standards-track YANG

TR-181 and OpenConfig did not appear from nowhere. Both descend from SNMP MIBs (the
original network telemetry data model) and run in parallel with IETF/BBF YANG. Aligning
to these roots gives decades of battle-tested structure and normative sources to cite.

### SNMP MIBs — the root, and the strongest validation of the entity model

| MIB (RFC) | Models | Maps to |
|---|---|---|
| **IF-MIB** (RFC 2863) | `ifTable`/`ifXTable`, `ifStackTable` (higher/lower sub-layer) | `network.interface.*`, state enums, counters, `lower_layer.name`/`higher_layer.name` |
| **ENTITY-MIB** (RFC 6933) | `entPhysicalTable`, `entPhysicalContainedIn` (parent pointer) | `network.device`/`chassis`/`module`/`component` + `hw.*` |
| **ENTITY-STATE-MIB** (RFC 4268) | admin/oper/usage/alarm state of physical entities | `network.admin.state` / `network.oper.state` + events |
| **BGP4-MIB** (RFC 4273) | `bgpPeerTable` | `network.neighbor` |
| **LLDP-MIB** (IEEE 802.1AB) | `lldpRemTable`; `lldpStats*` | `network.link`/`network.neighbor` (lldp) + `network.lldp.*` |
| **BRIDGE-MIB / Q-BRIDGE-MIB** | FDB (MAC table), VLANs | `network.instance` (l2vsi), `network.vlan`, `network.l2.fdb.*` |
| **IP-FORWARD-MIB** (RFC 4292) | `inetCidrRouteTable` | `network.routing` route counts per `network.instance` |
| **DISMAN-PING/TRACEROUTE-MIB** | active ping/traceroute | `network.test.*` |

The key insight: ENTITY-MIB's `entPhysicalContainedIn` — a flat table of components,
each pointing to its parent — is the **same flat-entities-with-parent-reference pattern**
this model uses and that OpenConfig `components` later adopted. It dates to the late
1990s. That is deep validation that the approach is correct, not novel.

Two telemetry lessons SNMP teaches (and this model honours):
- **Index instability.** `ifIndex`/`entPhysicalIndex` are not guaranteed stable across
  reboots — which is exactly why `network.interface.index` is *descriptive*, not
  identifying (see [entity-model.md](entity-model.md#sub-entity-identity-is-scoped-by-its-parent)).
- **Counter width & polling.** SNMP needed 32→64-bit "HC" counters and is poll-based;
  OTel monotonic counters with reset detection subsume both, so byte/packet counts are
  modelled as OTel `Counter`s with no 32-bit variants.

### IETF & BBF YANG — standards-track precedent

| YANG model (RFC) | Models | Maps to |
|---|---|---|
| **ietf-interfaces** (RFC 8343) | interface[name], type, admin/oper-status, `higher-layer-if`/`lower-layer-if` | `network.interface.*` + layering |
| **ietf-hardware** (RFC 8348) | component/parent/class/sensor (YANG successor to ENTITY-MIB) | `network.device`/`chassis`/`module`/`component` + `hw.*` |
| **ietf-network-instance** (RFC 8529) | network instances (VRF/VSI) | `network.instance` (direct precedent) |
| **ietf-network / -topology** (RFC 8345) | abstract networks/nodes/termination-points/links | `network.link` + topology |
| **BBF YANG** (TR-383/385/355) | DSL/PON/access, subscriber, QoS | `network.access`, `network.wifi`, `network.qos` |

`network.instance` is independently confirmed by three bodies (BBF, OpenConfig, IETF all
converged on a unified "network instance"); `network.link` should align to RFC 8345's
node/termination-point/link concepts rather than inventing a shape.

## Where this model aligns (and should)

- **Hardware/component hierarchy.** OpenConfig `openconfig-platform` models inventory as a
  flat `components` list with a `parent` leaf and a `type`
  (`CHASSIS/LINECARD/CONTROLLER_CARD/FABRIC/INTEGRATED_CIRCUIT(ASIC-NPU)/…`) — essentially
  this model's flat-entities-plus-relationships design. Align `network.module.type` /
  `network.component.type` enums to OpenConfig where they overlap; keep the `hw.*`
  boundary (FAN/POWER_SUPPLY/SENSOR map to `hw.*`, not `network.component.*`).
- **Interface state & counters.** OpenConfig `oper-status`/`admin-status` and TR-181
  status both derive from IF-MIB `ifOperStatus`/`ifAdminStatus`; counters mirror
  `in/out-octets/pkts/errors/discards`. RFC 2863 + IANA `ifType` (a curated subset) are
  the normative sources for the interface state/type enums.
- **Optical.** OpenConfig `terminal-device`/`transport-types` channels (frequency, output
  power, OSNR, pre/post-FEC BER, dispersion) map onto `network.optical.channel`. Keep the
  UCUM units canonical (`dB[mW]`, `dB`, `1`, `ps/nm`).
- **Active test/diagnostics.** TR-181 `Device.IP.Diagnostics.{IPPing,TraceRoute,Download,Upload}`
  independently validates treating synthetic tests as a distinct mode (`network.test.*`).
- **Topology/LLDP.** OpenConfig `openconfig-lldp` and TR-181 LLDP expose neighbour
  chassis-id/port-id — discovery inputs for `network.link` + `network.neighbor`
  (`protocol=lldp`).

## Where this model deliberately diverges (and should)

- **Observer / flow / packet telemetry exists in neither model** — they are device-self
  models. `network.observer.*` / `network.flow.*` / `network.packet.*` come from the
  IPFIX/sFlow/ECS lineage and must not be aligned to OpenConfig/TR-181.
- **Flow has three blessed carriers, and the prior art picked all three.** A flow is the
  same attribute set whether it rides a record, a metric, or a span — and real
  implementers each chose a different carrier: **ElastiFlow → span**, **OpenTelemetry eBPF
  (OBI) → metric counter**, **IPFIX/NetFlow exporters → event record**. The model blesses
  all three rather than declaring one canonical (record is the default floor; metric is
  bounded aggregates; span is the connection-oriented L4/L7 view). Cross-observer
  correlation uses `network.community_id` (the bidirectional 5-tuple hash from the
  [community-id spec](https://github.com/corelight/community-id-spec) / ECS), distinct
  from the per-exporter `network.flow.id`.
- **Telemetry-only:** no config containers, no RPCs, no writable params. The only "intent"
  kept is the administrative state alongside operational state — which both models also
  distinguish.
- **Identity:** do **not** adopt path-as-identity or the single-device tree. The reality
  is N collectors describing one fleet, so identity is a stable producer-assigned id plus
  reconciliation (see [entity-model.md](entity-model.md#identity-relationships-and-reconciliation)).
- **Curated dimensions, not full leaf fidelity.** A rich NOS tree maps *into* the curated
  set; this is not a lossless MIB/YANG re-encoding.

## Crosswalks: the adoption lever

A NOS already emitting OpenConfig over gNMI, or a CPE speaking USP/TR-181, is a
ready-made data source. Publishing mapping tables lets a Collector receiver translate
existing telemetry into `network.*` with no device-side change — the fastest route to
validation data.

### Entity crosswalk

| `network.*` entity | OpenConfig | TR-181 (`Device.`) |
|---|---|---|
| `network.device` | `/components` root + `openconfig-system` | `DeviceInfo` (OUI, serial, model, versions) |
| `network.chassis` | component `type=CHASSIS` | (implicit; fixed-form CPE) |
| `network.module` | `LINECARD`/`CONTROLLER_CARD`/`FABRIC` | (modular CPE rare) |
| `network.component` | `INTEGRATED_CIRCUIT` (ASIC/NPU), `CPU`, `FPGA` | — |
| `network.interface` | `/interfaces/interface[name]` (+ subinterfaces) | `Ethernet.Interface`, `IP.Interface`, `PPP.`, `DSL.`, `Optical.` |
| interface **layering** | subinterfaces / stacking | `InterfaceStack` + `LowerLayers` |
| `network.instance` | `network-instance` (`DEFAULT`/`L3VRF`/`L2VSI`/`L2P2P`/`L2L3`) | `Routing.` (L3) / Annex A bridging (L2) |
| `network.vlan` | `vlans` / subinterface vlan | `Bridging.` VLAN |
| `network.lag` | `aggregate` interface + members | `Ethernet.Link` aggregation |
| `network.tunnel` | tunnel interfaces / `network-instance` | Annex B Tunneling (GRE/IPsec) |
| `network.optical.channel` | `terminal-device` logical channels | `Optical.Interface` / XPON |
| `network.neighbor` | `bgp/neighbors`, `ospf`, `isis`, `lldp` | `Routing.`, LLDP |
| `network.observer` / `network.flow` | **none** — IPFIX/sFlow/ECS lineage | **none** — IPFIX/sFlow/ECS lineage |
| `network.test` | gNOI ping/traceroute | `IP.Diagnostics.*` |

### Attribute crosswalk (interface example)

| `network.*` | OpenConfig | TR-181 | Source of truth |
|---|---|---|---|
| `network.interface.oper.state` | `oper-status` | `Status` | RFC 2863 `ifOperStatus` |
| `network.interface.admin.state` | `admin-status` | `Enable`/`Status` | RFC 2863 `ifAdminStatus` |
| `network.interface.type` | `type` (iana-if-type) | object type | IANA `ifType` (curated subset) |
| `network.interface.io` (`By`, dir) | `counters/in-octets`,`out-octets` | `Stats.Bytes{Received,Sent}` | IF-MIB |
| `network.interface.packets` | `in-unicast-pkts`… | `Stats.Packets{Received,Sent}` | IF-MIB |
| `network.interface.errors` | `in-errors`/`out-errors` | `Stats.Errors{Received,Sent}` | IF-MIB |
| `network.interface.discards` | `in-discards`/`out-discards` | `Stats.DiscardPackets{Received,Sent}` | IF-MIB |
| `network.interface.speed` | `port-speed` / `speed` | `MaxBitRate`/`CurrentBitRate` | — |

## An independent normalization: SuzieQ

The models above are config/management trees. [SuzieQ](https://github.com/netenglabs/suzieq)
is a different kind of prior art — an open-source network *observability* application that
polls multi-vendor devices and normalizes their state into its own vendor-neutral schema
(Parquet-backed tables: `device`, `interfaces`, `bgp`, `ospfNbr`, `lldp`, `routes`,
`macs`, `arpnd`, `vlan`, `evpnVni`, `mlag`, …). Because it solved the same normalization
problem independently and pragmatically, a field-level comparison of its table schemas
against this model is a useful sanity check, and a worked one was done.

It corroborates the model. SuzieQ's tables land on the same entity boundaries
(`device`/`interface`/`neighbor`/`link`/`vlan`/`instance` + counts for MAC/ARP/route),
and several non-obvious calls match exactly: interfaces keyed on **name** with `ifindex`
as a non-key column (our identifying-name / descriptive-index split); the
state-change *timestamp* kept as a value, not a descriptor (`network.interface.last_change`);
a separate **VLAN vs bridge-domain** column pair (`network.vlan` vs `network.instance`);
a RIB-vs-FIB "hardware programmed" flag (`network.routing.route.state` `active` vs `fib`);
EVPN-learned ARP/MAC marked as control-plane (`entry.type=control_plane`, the Type-2
dual-population); and an MLAG table that maps almost one-to-one onto `network.redundancy.*`
plus a peer-link `network.link` and an anycast-VTEP `network.address.role=anycast`.

The two places it diverges are explained by *what SuzieQ is*, not by a modelling
disagreement, which is itself validating: it is a **single observer**, so it keys
everything on `(namespace, hostname)` and never needs our opaque stable `network.device.id`
or the multi-observer reconciliation discipline; and it is a **retained columnar store,
not a metrics pipeline**, so it stores per-route / per-MAC / per-ARP *rows* freely where
this model applies the [cardinality firewall](conventions.md#the-cardinality-firewall)
(counts + records, never per-object metric series). SuzieQ also mixes BGP *configuration*
into its state tables, which this model deliberately excludes (telemetry-only). Its
per-protocol tables (`bgp`, `ospfNbr`, `ospfIf`) versus our generic `network.neighbor`
validate both halves of our design: the common fields are exactly the generic core, and
the protocol-specific columns (OSPF `area`/`nbrPrio`, BGP max-prefix) are exactly what the
`network.neighbor.<protocol>.*` refinement hatch is for.

The comparison surfaced one omission worth fixing — an interface **state-change counter**
(SuzieQ `numChanges`), the interface twin of the existing `network.neighbor.state_changes`,
whose "a count survives a collector restart, an event stream does not" rationale applies
equally to interface flaps. The other candidate gaps (a per-route record, BGP
max-prefix telemetry, VLAN/instance oper-state, an interface IP-address list) are either
deliberately deferred breadth or in tension with the addresses-are-not-entities stance,
and are left as conscious non-goals.

## Net assessment

Independent convergence with OpenConfig (flat components + parent refs; RFC 2863 state
lineage) and with the IETF YANG models (network-instance, topology), and with an independent observability normalization (SuzieQ,
above) is strong evidence
the entity/identity approach is right for telemetry. The lines to **hold** are the
deliberate divergences: observer/flow/packet, telemetry-only, stable-id-not-path
identity, and curated-dimensions-not-full-leaf-fidelity. The biggest adoption leverage is
publishing the crosswalks so existing gNMI/USP telemetry can be translated by a Collector.
