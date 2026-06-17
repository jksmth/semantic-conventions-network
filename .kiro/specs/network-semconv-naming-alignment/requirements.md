# Requirements Document

## Introduction

This feature applies the naming and refactor decisions documented in `docs/naming-review.md` as a
single coordinated sweep across the `model/network/` tree. The goal is to bring every telemetry name
(metrics, events, attributes, entities) into compliance with the OpenTelemetry naming rules (R1–R5)
and the project's own sub-namespacing conventions (`docs/conventions.md`).

All affected signals are at `development` stability, so no deprecation cycle is required. However the
change is a breaking rename sweep for anything already emitting, so it MUST land as one coordinated
change: every reference site in the model (`metrics.yaml`, `events.yaml`, `registry.yaml`,
`entities.yaml`), every example (`examples/*/README.md`), and the docs (`conventions.md`,
`naming-review.md`) update in lockstep so that no name dangles and the registry remains valid under
the semconv/Weaver tooling.

The requirements below are grouped by the decisions in the review document (D1–D9, plus §2 and D6),
followed by the cross-cutting requirements that apply to the sweep as a whole. Each renamed signal is
treated as a discrete, verifiable target so that completeness can be checked against the decision
document.

## Glossary

- **Network_Semconv_Registry**: The set of semantic-convention model files under `model/network/`
  (`metrics.yaml`, `events.yaml`, `registry.yaml`, `entities.yaml` across all sub-namespaces) that
  define the network telemetry conventions.
- **Semconv_Tooling**: The Weaver / semantic-conventions validation tooling that resolves attribute
  references, checks registry well-formedness, and reports broken references.
- **Reference_Site**: Any location where a metric, event, attribute, or entity name is defined or
  referenced — including model YAML files, example READMEs (`examples/*/README.md`), and docs
  (`docs/conventions.md`, `docs/naming-review.md`).
- **Occupancy_UpDownCounter**: A non-monotonic UpDownCounter that reports the current size of a table
  or population (e.g. number of routes, MAC entries, sessions) as an absolute polled value.
- **Monotonic_Counter**: A monotonically increasing Counter that records discrete countable events
  (e.g. packets, message setups, discards).
- **FDB**: Forwarding Database — the L2 MAC forwarding table (BRIDGE-MIB `dot1qTpFdbTable`,
  OpenConfig `fdb` container).
- **ARPND**: The merged IPv4-ARP + IPv6-ND L3 resolution cache, observed by a collector as one table
  discriminated by address family (`network.type`).
- **Admin_Oper_Axis**: The administrative-intent (`admin`) and operational-capability (`oper`) state
  axes, each carrying a descriptive enum (`.state`) and a status metric (`.status`).
- **Interface_Identity_Key**: The attribute that uniquely identifies an interface within a device.
- **Foreign_Key (FK)**: A flat attribute on one entity whose value references the identity attribute
  of another entity (e.g. `network.link.local.interface.id`).
- **R1**: OTel rule — UpDownCounter names MUST NOT be pluralized; a count of an entity is
  `{namespace}.{object}.count`.
- **R2**: OTel rule — monotonic Counters SHOULD be pluralized when recording discrete countable
  instances with a `{thing}` annotation unit.
- **R4**: OTel rule — use `{object}.{property}` with a dot; avoid `{object}_{property}` underscore
  when the object could have other properties.
- **R5**: OTel rule — be precise, avoid ambiguous or cross-convention names; reuse before defining.

## Requirements

### Requirement 1: De-pluralize occupancy UpDownCounters (D1)

**User Story:** As a semantic-conventions maintainer, I want every occupancy UpDownCounter renamed to
`{object}.count`, so that the model complies with OTel rule R1 and matches the existing
`network.session.count` template.

#### Acceptance Criteria

1. THE Network_Semconv_Registry SHALL rename `network.routing.routes` to `network.routing.route.count`.
2. THE Network_Semconv_Registry SHALL rename `network.routing.ecmp.routes` to `network.routing.ecmp.route.count`.
3. THE Network_Semconv_Registry SHALL rename `network.multicast.routes` to `network.multicast.route.count`.
4. THE Network_Semconv_Registry SHALL rename `network.multicast.groups` to `network.multicast.group.count`.
5. THE Network_Semconv_Registry SHALL rename `network.evpn.routes` to `network.evpn.route.count`.
6. THE Network_Semconv_Registry SHALL rename `network.sr.sids` to `network.sr.sid.count`.
7. THE Network_Semconv_Registry SHALL rename `network.nat.translations` to `network.nat.translation.count`.
8. THE Network_Semconv_Registry SHALL rename `network.nat.ports` to `network.nat.port.count`.
9. THE Network_Semconv_Registry SHALL rename `network.nat.port_blocks` to `network.nat.port_block.count`.
10. THE Network_Semconv_Registry SHALL rename `network.nat.pool.addresses` to `network.nat.pool.address.count`.
11. THE Network_Semconv_Registry SHALL rename `network.access.sessions` to `network.access.session.count`.
12. THE Network_Semconv_Registry SHALL rename `network.access.pool.addresses` to `network.access.pool.address.count`.
13. THE Network_Semconv_Registry SHALL rename `network.wifi.bss.stations` to `network.wifi.bss.station.count`.
14. THE Network_Semconv_Registry SHALL preserve `network.session.count` unchanged, as it already complies with R1.
15. WHERE a signal is a Monotonic_Counter (e.g. `network.interface.packets`, `network.path.packets`,
    `network.qos.queue.packets`, `network.protocol.messages`, `network.protocol.errors`,
    `network.neighbor.state_changes`, `network.stp.topology_changes`, `network.routing.updates`,
    `network.access.session.setups`/`teardowns`, `network.session.setups`/`teardowns`,
    `network.access.aaa.requests`, `network.access.coa.requests`, `network.path.label.operations`,
    `network.path.protection.switches`, `network.multicast.rpf_failures`, `network.pon.fec.corrected`),
    THE Network_Semconv_Registry SHALL preserve its plural name unchanged.
16. THE Network_Semconv_Registry SHALL, for each of the 13 renamed occupancy counters, preserve its
    UpDownCounter instrument type, unit, brief text, and attribute set, modifying the metric name only.
17. THE Network_Semconv_Registry SHALL treat exactly the 13 metrics named in criteria 1 through 13 as
    the complete set of occupancy UpDownCounters subject to renaming, and SHALL leave every metric not
    named in criteria 1 through 13 unchanged.
18. IF a target `{object}.count` name produced by a rename already exists in the registry as a distinct
    metric definition, THEN THE Network_Semconv_Registry SHALL reject that rename, report an error
    indicating the name collision and the conflicting metric, and leave all metric definitions unchanged.
19. WHEN all 13 renames in criteria 1 through 13 have been applied, THE Network_Semconv_Registry SHALL
    pass registry validation with zero R1 naming-rule violations across the 13 renamed counters.

### Requirement 2: FDB rename — container `fdb`, entry `mac` (D2)

**User Story:** As a semantic-conventions maintainer, I want the L2 forwarding-table signals to use
`fdb` for the table container and `mac` for the MAC-object, so that the model matches the
standards-aligned local rule (FDB container + `mac` entry) and R4 (dotted `fdb.limit`).

#### Acceptance Criteria

1. THE Network_Semconv_Registry SHALL rename the metric `network.l2.mac.entries` to `network.l2.fdb.entry.count`, retaining the original definition's instrument type, unit, value type, brief, and stability level with only the identifier changed.
2. THE Network_Semconv_Registry SHALL rename the attribute `network.l2.mac.entry.type` to `network.l2.fdb.entry.type`, retaining the original definition's value type, enumeration members (if any), brief, and stability level with only the identifier changed.
3. THE Network_Semconv_Registry SHALL rename the metric `network.l2.mac.learn_discards` to `network.l2.fdb.entry.discards`, retaining the original definition's instrument type, unit, value type, brief, and stability level with only the identifier changed.
4. THE Network_Semconv_Registry SHALL rename the event `network.l2.mac_limit.exceeded` to `network.l2.fdb.limit_exceeded`, retaining the original definition's attribute set, brief, and stability level with only the identifier changed.
5. THE Network_Semconv_Registry SHALL rename the attribute `network.vlan.mac_limit` to `network.vlan.fdb.limit`, retaining the original definition's value type, brief, and stability level with only the identifier changed.
6. THE Network_Semconv_Registry SHALL rename the attribute `network.instance.mac_limit` to `network.instance.fdb.limit`, retaining the original definition's value type, brief, and stability level with only the identifier changed.
7. THE Network_Semconv_Registry SHALL place the MAC-learning attribute under the `fdb` container while retaining the `mac_learning` leaf word, producing the exact identifier `network.instance.fdb.mac_learning`, and retaining the original definition's value type, brief, and stability level.
8. THE Network_Semconv_Registry SHALL retain the identifiers `network.l2.mac.status`, `network.l2.mac.state`, `network.l2.mac.moved`, and `network.l2.mac.address` exactly as written, with their value type, brief, and stability level unchanged.
9. THE Network_Semconv_Registry SHALL retain the MAC move-record field identifier prefix `network.l2.mac.previous_interface.*` exactly as written, except for the foreign-key leaf rename mandated by Requirement 7, with all other attributes of each affected definition unchanged.
10. WHEN the renames in criteria 1 through 7 are applied, THE Network_Semconv_Registry SHALL contain zero occurrences of the pre-rename identifiers `network.l2.mac.entries`, `network.l2.mac.entry.type`, `network.l2.mac.learn_discards`, `network.l2.mac_limit.exceeded`, `network.vlan.mac_limit`, and `network.instance.mac_limit` across all definitions and references.
11. WHEN the renames in this requirement are applied, THE Network_Semconv_Registry SHALL pass registry validation with zero errors and zero unresolved references.

### Requirement 3: Confirm acceptable underscore leaves; dot the EIGRP queue (D3)

**User Story:** As a semantic-conventions maintainer, I want the remaining snake_case underscore leaves
confirmed as acceptable and the one genuine `{object}.{property}` violation dotted, so that R4 is
applied precisely without over-reaching into legitimate multi-word leaves.

#### Acceptance Criteria

1. THE Network_Semconv_Registry SHALL rename `network.neighbor.eigrp.queue_depth` to
   `network.neighbor.eigrp.queue.depth`, changing only the affected leaf segment and preserving the
   definition's instrument type, unit, and semantics.
2. THE Network_Semconv_Registry SHALL preserve unchanged the acceptable snake_case multi-word terminal
   leaf segments comprising exactly the following set, wherever they appear:
   `min_links`, `system_id`, `route_type`, `df_role`, `address_family`, `route_distinguisher`,
   `route_target`, `transport_class`, `path_cost`, `is_root`, `prefix_sid`, `adjacency_sid`,
   `binding_sid`, `segment_list`, `in_segment`, `out_segment`, `filter_mode`, `noise_floor`,
   `tx_power`, `service_name`, `ac_name`, `address_scope`, `state_changes`, `topology_changes`,
   `rpf_failures`, `native_state`, and the `previous_*` leaves.
3. THE Network_Semconv_Registry SHALL preserve the already-dotted limit attributes
   `network.optical.power.limit`, `network.optical.bias_current.limit`, and
   `network.device.memory.limit` unchanged in both name and instrument type.
4. THE Network_Semconv_Registry SHALL NOT dot or otherwise rename any snake_case multi-word leaf under
   D3 other than `network.neighbor.eigrp.queue_depth`.

### Requirement 4: ARP/ND merged namespace rename to `arpnd` (D4)

**User Story:** As a semantic-conventions maintainer, I want the merged L3 resolution-cache signals
renamed from `adjacency` to the vendor-neutral `arpnd`, so that the namespace is not tied to the
Cisco-specific "adjacency" term while keeping ARP and ND merged under one address-family-discriminated
namespace.

#### Acceptance Criteria

1. THE Network_Semconv_Registry SHALL keep ARP and ND merged under one namespace discriminated by `network.type` (well-known values ipv4/ipv6) and SHALL NOT split them into separate `network.l3.arp.*` and `network.l3.nd.*` namespaces.
2. THE Network_Semconv_Registry SHALL rename the `network.l3.adjacency.*` namespace to `network.l3.arpnd.*`.
3. THE Network_Semconv_Registry SHALL rename the metric `network.l3.adjacency.entries` to `network.l3.arpnd.entry.count`, preserving the original UpDownCounter instrument type, unit, and brief.
4. THE Network_Semconv_Registry SHALL preserve the `network.type` (ipv4/ipv6) discriminator association on the renamed `network.l3.arpnd.entry.count` metric.
5. WHERE any other leaf or attribute exists under `network.l3.adjacency.*`, THE Network_Semconv_Registry SHALL move it to the corresponding `network.l3.arpnd.*` name by changing only the `adjacency` segment to `arpnd`, leaving the remainder of the name, instrument type, attribute set, and stability unchanged.
6. IF any reference to a `network.l3.adjacency.*` name remains after the rename, THEN THE Network_Semconv_Registry SHALL treat the rename as incomplete and resolve the remaining reference.

### Requirement 5: Admin/oper state — dot the axes and fold interface state (D5)

**User Story:** As a semantic-conventions maintainer, I want the admin/oper state axes dotted and the
interface admin/oper state folded into the shared axis, so that the model follows R4 and the
`hw.state`/`hw.status` precedent, and so that hardware and interface state share one normalized axis as
the neighbor-state precedent (Principle 10) and RFC 8343/8348 reuse both indicate.

#### Acceptance Criteria

1. THE Network_Semconv_Registry SHALL define the attribute `network.admin.state` and SHALL NOT define any attribute named `network.admin_state`.
2. THE Network_Semconv_Registry SHALL define the attribute `network.oper.state` and SHALL NOT define any attribute named `network.oper_state`.
3. THE Network_Semconv_Registry SHALL define the administrative status metric with the exact name `network.admin.status`.
4. THE Network_Semconv_Registry SHALL define the operational status metric with the exact name `network.oper.status`.
5. THE Network_Semconv_Registry SHALL define `network.admin.state` as a single shared attribute referenced at the interface grain, and SHALL NOT define any separate attribute named `network.interface.admin_state`.
6. THE Network_Semconv_Registry SHALL define `network.oper.state` as a single shared attribute referenced at the interface grain, and SHALL NOT define any separate attribute named `network.interface.oper_state`.
7. THE Network_Semconv_Registry SHALL support exactly five reference grains for the shared `network.admin.state` and `network.oper.state` attributes, with interface as the fifth grain.
8. THE Network_Semconv_Registry SHALL define each shared state attribute as an open enum whose well-known member set is exactly the union of the prior hardware and interface value sets, containing the members `enabled`, `up`, `disabled`, `down`, `degraded`, `testing`, `dormant`, `lower_layer_down`, `not_present`, and `unknown`, and SHALL accept additional caller-supplied values without registry validation failure.
9. THE Network_Semconv_Registry SHALL specify, at each reference site of the shared state attribute, an explicit requirement level drawn from the set {`required`, `recommended`, `opt_in`} and an explicit entity association, such that the interface reference site MAY be `recommended` and the chassis reference site MAY be `opt_in`.
10. THE Network_Semconv_Registry SHALL define the attributes `network.stp.port.state`, `network.pon.onu.state`, `network.wifi.ap.state`, and `network.multicast.querier` with identical names, value sets, and requirement levels to their definitions prior to this change.
11. THE Network_Semconv_Registry SHALL define a `native_state` companion attribute that carries the verbatim, untransformed vendor-supplied state value as a string, matching the `native_state` definition used by the `network.neighbor` attribute group.

### Requirement 6: QoS queue depth gauges — keep as two metrics (§2 / D-§2)

**User Story:** As a semantic-conventions maintainer, I want the two QoS queue-depth gauges kept as
separate metrics, so that an instantaneous depth and a hardware high-water-mark are not folded into a
single `stat` dimension that would invite meaningless cross-aggregation.

#### Acceptance Criteria

1. THE Network_Semconv_Registry SHALL define `network.qos.queue.depth` as a gauge metric registered under its own metric name, distinct from `network.qos.queue.depth.max`.
2. THE Network_Semconv_Registry SHALL define `network.qos.queue.depth.max` as a gauge metric registered under its own metric name, distinct from `network.qos.queue.depth`.
3. THE Network_Semconv_Registry SHALL NOT define a single metric that combines the instantaneous queue depth and the high-water-mark queue depth, including any combination achieved through a `stat` (current/max) attribute or any other attribute that distinguishes a current value from a maximum value.
4. THE Network_Semconv_Registry SHALL NOT declare on either `network.qos.queue.depth` or `network.qos.queue.depth.max` any attribute whose value selects between instantaneous and high-water-mark semantics.

### Requirement 7: Interface identity — use upstream name, rename FKs (D7)

**User Story:** As a semantic-conventions maintainer, I want the interface identity keyed on the Stable
upstream `network.interface.name` instead of a minted `network.interface.id`, with interface foreign
keys renamed to match, so that the model reuses the Stable upstream attribute (R5 reuse-before-defining),
keeps identity minimal for the Prometheus hash projection, and aligns with WG #3769.

#### Acceptance Criteria

1. THE Network_Semconv_Registry SHALL ensure that no defining site declares the attribute `network.interface.id`.
2. THE Network_Semconv_Registry SHALL use the Stable upstream `network.interface.name` as the Interface_Identity_Key, referencing the upstream definition and preserving its `stable` stability and value type.
3. THE Network_Semconv_Registry SHALL add `network.interface.index` as an `opt_in` disambiguator and SHALL NOT name it `if_index`.
4. THE Network_Semconv_Registry SHALL pin `network.interface.description` to SNMP ifAlias and SHALL update its note to remove the conflated "/ interface description" phrasing.
5. THE Network_Semconv_Registry SHALL rename the foreign keys `network.link.local.interface.id` and `network.link.remote.interface.id` to `network.link.local.interface.name` and `network.link.remote.interface.name`.
6. THE Network_Semconv_Registry SHALL rename the foreign key `network.path.local.interface.id` to `network.path.local.interface.name`.
7. THE Network_Semconv_Registry SHALL rename the foreign key `network.l2.mac.previous_interface.id` to `network.l2.mac.previous_interface.name`.
8. THE Network_Semconv_Registry SHALL rename the foreign keys `network.interface.parent.id` and `network.interface.lower_layer.id` to `network.interface.parent.name` and `network.interface.lower_layer.name`.
9. THE Network_Semconv_Registry SHALL restate the note on `network.lag.members` to clarify that its value is a list of interface names, while keeping the attribute key unchanged.
10. WHERE a sub-entity keys on its own minted `.id` (module, lag, pool), THE Network_Semconv_Registry SHALL preserve that `.id` identity key unchanged.
11. THE Network_Semconv_Registry SHALL NOT model a third interface string (ifDescr is not modeled and is covered by `hw.*`).
12. THE Network_Semconv_Registry SHALL apply the foreign-key renames in criteria 5 through 8 as leaf-name-only changes, preserving each affected attribute's value type, requirement level, entity association, and `development` stability.

### Requirement 8: Interface completeness additions (D8)

**User Story:** As a semantic-conventions maintainer, I want the symmetric upward layering attribute and
the last-flap timestamp added, so that the interface surface matches IF-MIB / RFC 8343 / OpenConfig
expectations.

#### Acceptance Criteria

1. THE Network_Semconv_Registry SHALL add `network.interface.higher_layer.id` as an `opt_in`, multi-valued attribute (array of interface identifiers) that lists the interfaces running directly on top of this one, as the inverse of `network.interface.lower_layer.id`.
2. WHERE the interface identity is keyed on `network.interface.name` (Requirement 7), THE Network_Semconv_Registry SHALL express the value of `network.interface.higher_layer` as interface names consistent with the FK convention.
3. THE Network_Semconv_Registry SHALL add `network.interface.last_change` as the timestamp of the instant the interface entered its current operational state (the most recent oper-state transition, IF-MIB `ifLastChange`).
4. THE Network_Semconv_Registry SHALL define `network.interface.higher_layer` and `network.interface.lower_layer` as an exact bidirectional inverse pair, such that interface B appears in A's `higher_layer` set if and only if A appears in B's `lower_layer` set.
5. WHERE an interface is at the top of the interface stack, THE Network_Semconv_Registry SHALL permit `network.interface.higher_layer.id` to be omitted, mirroring the omission of `lower_layer` at the bottom of the stack.
6. WHERE no operational-state transition has occurred since the interface was re-initialized, THE Network_Semconv_Registry SHALL permit `network.interface.last_change` to be omitted (IF-MIB `ifLastChange` boundary).

### Requirement 9: MTU layering (D9)

**User Story:** As a semantic-conventions maintainer, I want MTU modeled as an L2 frame value plus a
per-address-family L3 value, so that a dual-stack interface with differing IPv4/IPv6 MTUs and the
L2-vs-L3 mismatch fault can both be represented.

#### Acceptance Criteria

1. THE Network_Semconv_Registry SHALL define `network.interface.mtu` to mean the L2 frame MTU (OpenConfig `config/mtu` sense), expressed as an integer number of bytes in the range 64 to 65535 inclusive.
2. THE Network_Semconv_Registry SHALL define `network.interface.ip.mtu` to carry the L3 per-address-family MTU as an integer number of bytes in the range 64 to 65535 inclusive, dimensioned by the `network.type` attribute.
3. THE Network_Semconv_Registry SHALL constrain the `network.type` values that dimension `network.interface.ip.mtu` to the closed set `ipv4` and `ipv6`.
4. WHERE an interface is dual-stack, THE Network_Semconv_Registry SHALL permit `network.interface.ip.mtu` to be reported once per `network.type` value (`ipv4` and `ipv6`) with independent values alongside a single `network.interface.mtu` value.
5. THE Network_Semconv_Registry SHALL retain the existing `network.interface.mtu` attribute key without renaming it, so that the addition of `network.interface.ip.mtu` is additive.

### Requirement 10: Confirm `network.neighbor` term and anti-explosion rule (D6)

**User Story:** As a semantic-conventions maintainer, I want `network.neighbor` confirmed as the correct
term and the "one identifiable peer" scoping rule stated as the explicit guard, so that the control-plane
adjacency namespace is documented as the gate against per-protocol sub-namespace explosion.

#### Acceptance Criteria

1. THE Network_Semconv_Registry SHALL retain `network.neighbor` as the control-plane adjacency/peer namespace, and the identifier `network.peer` SHALL NOT appear in the registry as a replacement for it.
2. THE Reference_Site `docs/conventions.md` SHALL state that a counter with exactly one identifiable peer reuses the generic `network.neighbor` counters (`network.protocol.messages` / `network.protocol.errors` keyed by `network.neighbor.protocol`), while a peerless signal gets its own `network.<x>.*` namespace.
3. WHEN a protocol facet is protocol-unique and has no vendor-neutral generic equivalent, THE Reference_Site `docs/conventions.md` SHALL state that a `network.neighbor.<protocol>.*` refinement is justified; WHEN a facet is expressible by the generic counters, the refinement is not justified.
4. THE Network_Semconv_Registry SHALL keep the attribute keys, metric names, and namespace identifiers under `network.neighbor` identical before and after this change (documentation/confirmation only).
5. IF a change would rename or restructure the `network.neighbor` namespace as part of this decision, THEN THE Network_Semconv_Registry SHALL reject it and retain the namespace unchanged.

### Requirement 11: Update all reference sites in lockstep

**User Story:** As a semantic-conventions maintainer, I want every reference site updated together, so
that no renamed name dangles anywhere in the model, examples, or docs.

#### Acceptance Criteria

1. WHEN a metric, event, attribute, or entity is renamed, THE Network_Semconv_Registry SHALL replace the old name with the new name at its definition site and at every site that references it across `metrics.yaml`, `events.yaml`, `registry.yaml`, and `entities.yaml` under `model/network/`, matching only complete name tokens and not substrings of unrelated names.
2. WHEN a signal (a metric, event, attribute, or entity) is renamed, THE feature SHALL replace every occurrence of the old name with the new name in all `examples/*/README.md` files.
3. WHEN a signal is renamed, THE feature SHALL replace every occurrence of the old name with the new name in `docs/conventions.md`.
4. WHEN a signal is renamed, THE feature SHALL update `docs/naming-review.md` so that each reference to the old name is replaced with the new name and the recorded status of that rename is set to applied.
5. WHEN the sweep completes, THE feature SHALL scan all defining and referencing sites covered by criteria 1 through 4 for any remaining occurrence of a renamed old name and report the count of remaining occurrences.
6. IF the post-sweep scan reports one or more remaining occurrences of an old name in any defining or referencing site within `model/network/`, `examples/*/README.md`, `docs/conventions.md`, or `docs/naming-review.md`, THEN THE feature SHALL treat the sweep as incomplete and replace each remaining old-name occurrence with the new name, leaving the original content otherwise unchanged.

### Requirement 12: Registry validity after the sweep

**User Story:** As a semantic-conventions maintainer, I want the registry to remain valid after the
sweep, so that downstream consumers and the build pipeline are not broken.

#### Acceptance Criteria

1. WHEN the rename sweep is complete, THE Semconv_Tooling SHALL resolve every attribute reference and report zero broken (unresolved) references.
2. WHEN the rename sweep is complete, THE Semconv_Tooling SHALL complete the Weaver / semconv checks with zero validation errors (a passing, success-status result).
3. IF the Semconv_Tooling reports a broken reference or validation error after the sweep, THEN THE feature SHALL correct the affected Reference_Site(s) and SHALL NOT treat the change as complete while any broken reference or validation error remains.
4. WHEN a fix is applied under criterion 3, THE feature SHALL re-run the Semconv_Tooling and SHALL require a zero-error, zero-broken-reference result before the change is considered complete.

### Requirement 13: Coordinated single landing at `development` stability

**User Story:** As a semantic-conventions maintainer, I want the entire sweep to land as one coordinated
change, so that the breaking renames do not leave the model in a half-renamed state between changes.

#### Acceptance Criteria

1. THE feature SHALL apply all renames defined in Requirements 1–11 within a single coordinated change set such that either every rename is present or none is applied, with no partial application.
2. WHERE a rename would break existing `development` usage, THE feature SHALL apply the breaking rename directly without adding deprecation aliases, deprecated markers, or backward-compatible duplicate definitions for the pre-rename identifier.
3. THE feature SHALL set the stability of every signal affected by Requirements 1–11 to `development`.
4. THE feature SHALL include the example README updates and documentation updates that reference any renamed identifier within the same coordinated change set as the model changes.
5. IF any signal affected by Requirements 1–11 is declared with a stability other than `development` (for example `stable`), THEN THE feature SHALL fail registry validation with an error indicating the disallowed stability level and SHALL leave the model unchanged.
6. IF the change set retains any reference to a pre-rename identifier from Requirements 1–11 after the renames are applied, THEN THE feature SHALL fail registry validation with an error identifying each stale reference and SHALL leave the model unchanged.
