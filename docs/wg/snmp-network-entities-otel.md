# Modeling SNMP-discovered network infrastructure as OTel entities: a candidate model

> Candidate definitions offered to the OpenTelemetry Network Semconv WG ([#3769](https://github.com/open-telemetry/semantic-conventions/issues/3769)). Names below are working vocabulary; the model is the proposal, the final names belong to the group. Maturity: implementing now, first real-device validation upcoming; a candidate model, not field-proven.

## Scope and non-goals

This describes how SNMP-discovered network infrastructure can be modeled as
**OTel entities with relationships**, aligned with the merged
[entity-events spec](https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/entities/entity-events.md).
It is the *shape* layer: entity types, identity keys, relationship types.

**Non-goal:** normalizing the thousands of MIB-derived descriptive attributes
and metrics; that is the (much larger) normalization effort discussed in the
WG. The two compose: normalized MIB attributes become the descriptive
attributes of these entities; identity + relationships give them a stable
shape over time.

## Design principles (what survived our own iterations)

1. **Exact, immutable, observer-independent identity.** Never a mutable value
   (PID, DHCP-leased IP) in identity; those are descriptive attributes. Two
   producers observing the same device MUST derive the same id from the data
   itself, so multiple observers converge on one graph node with no fuzzy
   matching and no consumer-side merge heuristics.
2. **Relationships are embedded in the source entity's state event**
   (`entity.relationships`, per the merged spec): bare descriptors naming
   only the target; an edge the source stops listing is retired by absence.
   No separate edge records, no edge lifecycle.
3. **No attributes on edges.** A fact that must persist (a route's metric, a
   port's speed) belongs on an *entity*. This rule is what pushed routes and
   addresses from "relationship with attributes" to first-class entities;
   see the next section.

## Candidate entities

| Entity | Identity | Derived from | Descriptive attributes (examples) |
|---|---|---|---|
| `network.device` | single key, subtype-prefixed:<br>`serial:` > `engine:` > `mac:` > `name:` > `mgmt:` | `entPhysicalSerialNum` (ENTITY-MIB), `snmpEngineID` (SNMP-FRAMEWORK-MIB), chassis MAC / LLDP chassis-id, `sysName`, management IP, in that precedence (not every device populates the stronger keys) | `sysDescr`, vendor, capabilities |
| `network.interface` | `{device id, interface.name}` (`ifName`, IF-MIB) | IF-MIB | `oper.state` (ifOperStatus), `speed` (ifHighSpeed) |
| `network.address` | `{ip}`, a **shared** node | IP-MIB `ipAddrTable`, host interface IPs, ARP | (none) |
| `network.route` | `{owner id, route.destination}` (CIDR) | ipCidrRouteTable / host routing table | `next_hop.ip` (scalar), `metric` |

Notes on the choices the group may want to debate:

- **Subtype-prefixed device id** (`mac:00:11:22:33:44:55`, `name:core-sw-1`,
  `mgmt:10.0.0.1`; canonicalized as lowercase hex-colon MACs, trimmed names,
  normalized IPs): avoids cross-subtype collisions, stays human-readable, and
  degrades gracefully on devices that don't populate ENTITY-MIB serials. The
  subtype is carried *in* the id, not as a second identity key.
- **Interface identity uses `ifName`, not `ifIndex`.** `ifIndex` is not
  guaranteed stable across re-initialization (RFC 2863 only requires
  stability between re-inits), so it fails the "immutable identity" bar;
  `ifName` is the operator-facing stable handle. `ifIndex` remains a
  descriptive attribute for joining raw table rows.
- **`network.address` as a first-class shared node** is the piece that makes
  two discovery planes converge without heuristics: a host's default-gateway
  route and a polled device's interface IP both reference the **same**
  `{ip}` node, so host-side and SNMP-side topology join by exact identity.
- **Routes as entities, not edges.** A route has identity, a lifecycle, and
  attributes (next hop, metric); modeling it as a relationship forced
  attributes onto edges and broke the discipline above. Same reasoning
  applies generally: when a "relationship" needs attributes, it is usually an
  entity in disguise. We believe this is a useful heuristic for the
  attributes-vs-entities line the group will keep hitting.

## Candidate relationships

| Type | Direction | Meaning |
|---|---|---|
| `has_interface` | device → interface | ownership |
| `has_route` | device/host → route | ownership |
| `bound_to` | address → interface | an IP sits on a port |
| `connected_to` | interface → interface | port-to-port link (LLDP adjacency) |

We initially had device-level relation types (`adjacent_to`, `routes_via`,
`forwards_to` for LLDP/route/FDB respectively) and **retired all three**: they
each needed edge attributes (local/remote port, destination, metric), the
"entity in disguise" smell. Port-to-port `connected_to` + route/address
entities carry the same information with attribute-free edges and survived
implementation review; the device-level forms did not.

**Independent convergence.** ElastiFlow's pre-OTel internal model
([shared on the WG thread](https://github.com/open-telemetry/semantic-conventions/issues/3769#issuecomment-4668587512))
arrived at near-identical types: their `connected to`, `binds to`,
`contained by` map one-to-one onto `connected_to`, `bound_to`, and ownership
(`has_interface`/`has_route`); their `runs on` matches a `runs_on` from our
broader host/service entity vocabulary, which sits outside this doc's network
scope, so the overlap spans more than topology alone. Their flow-level types
(`communicates with/through`,
`tunneled within`) cover a layer this model deliberately leaves out (traffic
rather than topology) and would compose with it the same way metrics do,
by entity identity. Two independent implementations converging on the same
relationship vocabulary is a useful signal that these types are
standardization-ready.

## Worked example

A polled switch, one port, its IP, and the LLDP adjacency, as an
`entity_state` event stream (shapes per the merged entity-events spec;
attribute maps flat, scalar leaves):

```text
LogRecord  EventName: entity.state
  entity.type: network.device
  entity.id:   { network.device.id: "serial:FDO2331A0BC" }
  entity.description: { sysname: "core-sw-1", vendor: "..." }
  entity.relationships:
    - { relationship.type: has_interface,
        entity.type: network.interface,
        entity.id: { network.device.id: "serial:FDO2331A0BC",
                     interface.name: "Gi1/0/1" } }

LogRecord  EventName: entity.state
  entity.type: network.interface
  entity.id:   { network.device.id: "serial:FDO2331A0BC",
                 interface.name: "Gi1/0/1" }
  entity.description: { oper.state: "up", speed: 1000 }
  entity.relationships:
    - { relationship.type: connected_to,
        entity.type: network.interface,
        entity.id: { network.device.id: "mac:00:11:22:33:44:55",
                     interface.name: "eth0" } }

LogRecord  EventName: entity.state
  entity.type: network.address
  entity.id:   { network.address: "10.0.0.1" }
  entity.relationships:
    - { relationship.type: bound_to,
        entity.type: network.interface,
        entity.id: { network.device.id: "serial:FDO2331A0BC",
                     interface.name: "Vlan10" } }
```

## How metrics join the topology

The entity rail and the metric rail are correlated **by shared identity**: an
interface-traffic metric carries the same `network.device.id` +
`interface.name` attributes as its `network.interface` entity, so a backend
joins traffic to topology with no inference. This is where the WG's
MIB-attribute/metric normalization plugs in: normalized metrics and
descriptive attributes attach to these entities by identity.

## A candidate heuristic for `system.network.*` vs `network.*`

The WG needs a documented line between the two namespaces (thread, point 1).
The entity lens suggests one that we found ourselves applying without having
named it:

- **`system.network.*`: a host observing itself.** Telemetry about the
  observer's own network stack (its interfaces, its counters, its sockets),
  attached to the `host` entity. Owner: the System WG.
- **`network.*`: infrastructure being discovered/observed from outside.**
  Telemetry and entities describing *other* boxes (`network.device`,
  `network.interface`, `network.route`), regardless of how they are reached
  (SNMP, streaming telemetry, flow records). Owner: this WG.

The same physical NIC can legitimately appear on both sides (a host sees its
own `eth0`; a switch's LLDP table sees it as a neighbour port): they stay
distinct records with distinct owners, and converge in a consumer through the
shared `network.address` node rather than by forcing one namespace to absorb
the other.

## Open questions we bring (not settled by our implementation)

1. **Cross-source identity reconciliation.** The same physical box can be
   seen via LLDP (chassis-id), ARP/FDB (MAC only), direct polling (serial),
   and as a `host` (machine-id). Our current position: no consumer-side
   merge, convergence by exact id only, `ifPhysAddress` bridges name/mgmt
   ids to `mac:`, and `host` ↔ `network.device` stay distinct entity types.
   That is conservative; the group may want a defined merge/alias mechanism.
2. **Degraded identity.** Devices that populate neither serial nor engine-id
   end up keyed on `name:`/`mgmt:`, which is weaker, and `mgmt:` collides
   under NAT. Is precedence-with-degradation acceptable for a convention, or
   should identity require a minimum subtype?
3. **Where exactly the attributes-vs-entities line sits.** Our heuristic
   ("a relationship that needs attributes is an entity in disguise") covered
   routes and addresses; the group will hit harder cases (VLANs, LAGs,
   VRFs: each has identity and lifecycle, all are entity candidates by the
   same test).

---
*Derived from a producer + consumer pair we are building (an infrastructure
agent emitting entity events over OTLP; a temporal-graph consumer ingesting
them). Happy to share the conformance fixtures the examples are drawn from.*