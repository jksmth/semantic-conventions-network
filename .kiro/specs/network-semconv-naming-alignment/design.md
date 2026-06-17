# Design Document

## Overview

This feature is a **coordinated naming-and-refactor sweep** across the `model/network/` semantic-convention
registry, applying the decisions documented in `docs/naming-review.md` (D1–D9, plus §2 and D6) as a single
landing. It is not application code — the "implementation" is a set of edits to declarative Weaver / OpenTelemetry
semantic-convention model files (YAML), plus the example READMEs and docs that reference the affected names.

The work has three shapes:

1. **Pure renames** — change an identifier (and every reference to it) while preserving every other property of
   the definition: instrument type, unit, value type, brief, note (except where the note text itself names the old
   identifier), attribute set, entity associations, requirement levels, and stability. This covers D1 (occupancy
   UpDownCounters), most of D2 (FDB), D3 (the single EIGRP `queue_depth` dot), D4 (`adjacency` → `arpnd`), the
   D5 axis-dotting, and the D7 foreign-key leaf renames.

2. **Structural changes** — fold or restructure definitions, not just rename them. This covers D5's folding of the
   interface admin/oper state into a single shared attribute with an open superset enum, and D7's dropping of the
   minted `network.interface.id` in favour of the Stable upstream `network.interface.name` as the identity key.

3. **Additive changes** — new attributes that do not rename anything: D8 (`network.interface.higher_layer.id`,
   `network.interface.last_change`) and D9 (`network.interface.ip.mtu`, plus a re-pinned definition of
   `network.interface.mtu`).

Every affected signal is at **`development` stability**, so there is no deprecation cycle: the breaking renames are
applied directly, with no aliases, no `deprecated` markers, and no backward-compatible duplicate definitions
(Requirement 13.2). Because a half-applied sweep would leave the registry with dangling references, the entire
change set MUST land together — every definition site, every `ref:` site, every example README, and the two docs
(`docs/conventions.md`, `docs/naming-review.md`) update in lockstep so the registry resolves cleanly under the
Weaver / semconv tooling (Requirements 11, 12, 13).

This design grounds each decision in the actual files that hold the affected names, surveyed from the current
`model/network/` tree.

### Scope summary (by decision)

| Decision | Shape | Primary files touched |
|----------|-------|-----------------------|
| D1 — de-pluralize occupancy UpDownCounters | rename | `routing/`, `multicast/`, `evpn/`, `sr/`, `nat/`, `access/`, `wifi/` metrics + every ref-site |
| D2 — FDB container `fdb`, entry `mac` | rename + dotting | `l2/`, `vlan/`, `instance/` |
| D3 — confirm underscore leaves; dot EIGRP queue | rename (1 leaf) | `neighbor/metrics.yaml` |
| D4 — `adjacency` → `arpnd` | rename (namespace) | `l3/` |
| D5 — dot admin/oper axes; fold interface state | rename + structural | `common/`, `device/`, `interface/` |
| §2 / D-§2 — keep two QoS depth gauges | no change (guard) | `qos/metrics.yaml` |
| D6 — confirm `network.neighbor` + anti-explosion rule | no change (doc) | `docs/conventions.md`, `neighbor/` |
| D7 — interface identity = upstream `name`; rename FKs | structural + rename | `interface/`, `link/`, `path/`, `l2/`, `lag/` |
| D8 — interface completeness additions | additive | `interface/registry.yaml` |
| D9 — MTU layering | additive + re-pin | `interface/registry.yaml`, `interface/metrics.yaml` |

## Architecture

The architecture under change is the **declarative semantic-convention registry** itself — there is no service or
runtime. This section describes the registry's structure and the def/ref resolution model the sweep must respect.

### Layout

The registry is organised as one directory per sub-namespace under `model/network/`, each containing up to four
file kinds:

- **`registry.yaml`** — `attributes:` definitions (the attribute vocabulary). This is where an attribute is
  *defined* (with `- key: ...`).
- **`metrics.yaml`** — `metrics:` definitions (instrument, unit, attribute `ref:`s, entity associations).
- **`events.yaml`** — `events:` / `event_refinements:` definitions.
- **`entities.yaml`** — `entities:` definitions with `identity:` and `description:` attribute `ref:`s.

The sub-namespaces present today:

```
access  common  device  events  evpn  instance  interface  l2  l3  lag  link
lldp  multicast  nat  neighbor  observer  optical  packet  path  pon  qos
redundancy  routing  session  sr  stp  test  tunnel  vlan  wifi
```

### How attributes are defined vs referenced (the resolution model)

An attribute is **defined once** in some `registry.yaml` with `- key: network.x.y` and a full body (`type`,
`stability`, `brief`, `note`, members/examples). Everywhere it is *used* — on a metric, an event, or an entity's
`identity`/`description` — it appears as a **reference**: `- ref: network.x.y` with a local `requirement_level`
(and sometimes a local `brief`/`note` override). Weaver resolves each `ref:` against the global set of defined
keys at validation time; an unresolved `ref:` is a **broken reference** and a hard error.

This def/ref split is the central fact for the sweep:

- Renaming a **defined attribute** (`- key:`) means the rename must also be applied to **every `- ref:`** of it,
  or the registry breaks. Example: `network.admin_state` is defined in `common/registry.yaml` and ref'd in
  `device/entities.yaml` (four grains) and `device/metrics.yaml` (two status metrics).
- Renaming a **metric or event** (`- name:` / `- id:`) is more localised — metrics are not ref'd by other
  metrics — but the name still appears in prose `note:` fields and in the example READMEs and docs, all of which
  must be swept (these are not resolved by Weaver but are Reference_Sites under Requirement 11).
- An attribute used as a **dimension** appears as a `ref:` on the metric; a **foreign-key attribute** (e.g.
  `network.link.local.interface.id`) is itself a defined attribute in a `registry.yaml`, so its rename is an
  attribute rename plus a ref-site sweep.

## Data Models

The "data models" of this feature are the registry's definitions themselves — the metrics, events, attributes,
and entities that hold the affected names. This section enumerates where each affected name lives, per decision.

### Where the affected names live (per decision)

**D1 — occupancy UpDownCounters** (defined as `- name:` in `metrics.yaml`):

| Current metric | File |
|----------------|------|
| `network.routing.routes` | `model/network/routing/metrics.yaml` |
| `network.routing.ecmp.routes` | `model/network/routing/metrics.yaml` |
| `network.multicast.routes` | `model/network/multicast/metrics.yaml` |
| `network.multicast.groups` | `model/network/multicast/metrics.yaml` |
| `network.evpn.routes` | `model/network/evpn/metrics.yaml` |
| `network.sr.sids` | `model/network/sr/metrics.yaml` |
| `network.nat.translations` | `model/network/nat/metrics.yaml` |
| `network.nat.ports` | `model/network/nat/metrics.yaml` |
| `network.nat.port_blocks` | `model/network/nat/metrics.yaml` |
| `network.nat.pool.addresses` | `model/network/nat/metrics.yaml` |
| `network.access.sessions` | `model/network/access/metrics.yaml` |
| `network.access.pool.addresses` | `model/network/access/metrics.yaml` |
| `network.wifi.bss.stations` | `model/network/wifi/metrics.yaml` |

`network.session.count` (in `model/network/session/metrics.yaml`) is the already-correct template and is left
unchanged (Requirement 1.14). The `network.routing.routes` name is also referenced in prose in
`model/network/neighbor/metrics.yaml` (the EIGRP comment block) and `model/network/routing/metrics.yaml`
(the ECMP note) — both are ref-sites that must be swept.

**D2 — FDB** lives in `l2/`, `vlan/`, `instance/`:

| Current | Kind | File |
|---------|------|------|
| `network.l2.mac.entries` | metric | `model/network/l2/metrics.yaml` |
| `network.l2.mac.entry.type` | attribute | `model/network/l2/registry.yaml` |
| `network.l2.mac.learn_discards` | metric | `model/network/l2/metrics.yaml` |
| `network.l2.mac_limit.exceeded` | event | `model/network/l2/events.yaml` |
| `network.vlan.mac_limit` | attribute | `model/network/vlan/registry.yaml` |
| `network.instance.mac_limit` | attribute | `model/network/instance/registry.yaml` |
| `network.instance.mac_learning` | attribute | `model/network/instance/registry.yaml` |

The `mac.entry.type` attribute is ref'd by `network.l2.mac.entries` in `l2/metrics.yaml`; `vlan.mac_limit` /
`instance.mac_limit` and the `mac.entries`/`mac_limit.exceeded` names are cross-referenced in the prose notes of
`l2/metrics.yaml` and `l2/events.yaml`. The **keep** items — `network.l2.mac.status`, `network.l2.mac.state`,
`network.l2.mac.moved`, `network.l2.mac.address`, `network.l2.mac.previous_interface.*` — stay under `mac`
(Requirement 2.8/2.9), with the single exception of the FK leaf `previous_interface.id` → `.name` from D7.

**D4 — ARP/ND** lives entirely in `l3/`:

| Current | Kind | File |
|---------|------|------|
| `network.l3.adjacency.entries` | metric | `model/network/l3/metrics.yaml` |
| `network.l3.adjacency.entry.type` | attribute | `model/network/l3/registry.yaml` |
| `network.l3.adjacency.state` | attribute | `model/network/l3/registry.yaml` |

All `network.l3.adjacency.*` names move to `network.l3.arpnd.*`; the `network.type` (ipv4/ipv6) discriminator on
the count metric is preserved (Requirement 4.4).

**D5 — admin/oper state** spans three packages:

| Current | Kind | File |
|---------|------|------|
| `network.admin_state` | attribute (def) | `model/network/common/registry.yaml` |
| `network.oper_state` | attribute (def) | `model/network/common/registry.yaml` |
| `network.admin_status` | metric | `model/network/device/metrics.yaml` |
| `network.oper_status` | metric | `model/network/device/metrics.yaml` |
| `network.interface.admin_state` | attribute (def) | `model/network/interface/registry.yaml` |
| `network.interface.oper_state` | attribute (def) | `model/network/interface/registry.yaml` |

Ref-sites for the shared `network.admin_state`/`network.oper_state`: `device/entities.yaml` references them on
**four** grains (`network.device`, `network.chassis`, `network.module`, `network.component`), and
`device/metrics.yaml` references them on the two status metrics. The interface pair is ref'd in
`interface/entities.yaml` and used as the gauge dimension described in `interface/metrics.yaml` and
`interface/events.yaml`. After D5 the interface becomes the **fifth grain** referencing the shared attribute.

**D7 — interface identity + FKs**:

| Current | Kind | File |
|---------|------|------|
| `network.interface.id` | attribute (def — to drop) | `model/network/interface/registry.yaml` |
| `network.interface.parent.id` | attribute (def — FK) | `model/network/interface/registry.yaml` |
| `network.interface.lower_layer.id` | attribute (def — FK) | `model/network/interface/registry.yaml` |
| `network.link.local.interface.id` | attribute (def — FK) | `model/network/link/registry.yaml` |
| `network.link.remote.interface.id` | attribute (def — FK) | `model/network/link/registry.yaml` |
| `network.path.local.interface.id` | attribute (def — FK) | `model/network/path/registry.yaml` |
| `network.l2.mac.previous_interface.id` | attribute (def — FK) | `model/network/l2/registry.yaml` |
| `network.lag.members` | attribute (def — note only) | `model/network/lag/registry.yaml` |

`network.interface.id` is also ref'd as a dimension on `network.l2.mac.entries`/`.learn_discards`/`.status` in
`l2/metrics.yaml`, and named in many prose notes (e.g. `link/registry.yaml`, `path/registry.yaml`,
`device/registry.yaml`). Per D7 the dimension `ref: network.interface.id` on the FDB/MAC metrics becomes
`ref: network.interface.name` (the Stable upstream attribute), and the FK *definitions* rename their leaf
`.id` → `.name`.

**D8 / D9 — interface additions** are all in `model/network/interface/registry.yaml` (and `interface/metrics.yaml`
for the `ip.mtu` dimension wiring).

### Example READMEs

Eleven example narratives reference these names and must be swept (Requirement 11.2):

```
examples/README.md
examples/bng/README.md          examples/core-router/README.md
examples/cpe-router/README.md   examples/dc-fabric/README.md
examples/l2-switch/README.md    examples/l3-switch/README.md
examples/olt-ont/README.md      examples/sd-wan-edge/README.md
examples/ucpe/README.md         examples/wifi-ap/README.md
examples/wifi-cpe/README.md
```

The actual subset each README touches is discovered by the lockstep scan (below), not assumed — the sweep is
driven by "find every occurrence of each old token," so an example that never mentions a renamed name is simply
left untouched.

## Components and Interfaces

The "interfaces" of a semantic-convention registry are the telemetry names themselves — each name is a contract a
producer emits against and a consumer queries on. The rename mapping table below is the complete contract change;
the structural-approach subsection that follows specifies the non-trivial changes that are more than string
substitutions.

### Rename Mapping Table

Consolidated from the requirements, grouped by decision. `kind` is one of metric / event / attribute / namespace.
"Ref-sites" names the files beyond the definition site that hold the token (model `ref:`s and/or prose); the
authoritative list is produced by the lockstep scan.

### D1 — Occupancy UpDownCounters → `{object}.count` (Requirement 1)

| Old name (metric) | New name | Definition file |
|-------------------|----------|-----------------|
| `network.routing.routes` | `network.routing.route.count` | `routing/metrics.yaml` |
| `network.routing.ecmp.routes` | `network.routing.ecmp.route.count` | `routing/metrics.yaml` |
| `network.multicast.routes` | `network.multicast.route.count` | `multicast/metrics.yaml` |
| `network.multicast.groups` | `network.multicast.group.count` | `multicast/metrics.yaml` |
| `network.evpn.routes` | `network.evpn.route.count` | `evpn/metrics.yaml` |
| `network.sr.sids` | `network.sr.sid.count` | `sr/metrics.yaml` |
| `network.nat.translations` | `network.nat.translation.count` | `nat/metrics.yaml` |
| `network.nat.ports` | `network.nat.port.count` | `nat/metrics.yaml` |
| `network.nat.port_blocks` | `network.nat.port_block.count` | `nat/metrics.yaml` |
| `network.nat.pool.addresses` | `network.nat.pool.address.count` | `nat/metrics.yaml` |
| `network.access.sessions` | `network.access.session.count` | `access/metrics.yaml` |
| `network.access.pool.addresses` | `network.access.pool.address.count` | `access/metrics.yaml` |
| `network.wifi.bss.stations` | `network.wifi.bss.station.count` | `wifi/metrics.yaml` |

Name-only change: instrument (`updowncounter`), unit, brief, attribute set all preserved (Requirement 1.16).
Monotonic counters keep their plurals (Requirement 1.15) — see the keep inventory.

### D2 — FDB: container `fdb`, entry `mac` (Requirement 2)

| Old name | New name | Kind | Definition file |
|----------|----------|------|-----------------|
| `network.l2.mac.entries` | `network.l2.fdb.entry.count` | metric | `l2/metrics.yaml` |
| `network.l2.mac.entry.type` | `network.l2.fdb.entry.type` | attribute | `l2/registry.yaml` |
| `network.l2.mac.learn_discards` | `network.l2.fdb.entry.discards` | metric | `l2/metrics.yaml` |
| `network.l2.mac_limit.exceeded` | `network.l2.fdb.limit_exceeded` | event | `l2/events.yaml` |
| `network.vlan.mac_limit` | `network.vlan.fdb.limit` | attribute | `vlan/registry.yaml` |
| `network.instance.mac_limit` | `network.instance.fdb.limit` | attribute | `instance/registry.yaml` |
| `network.instance.mac_learning` | `network.instance.fdb.mac_learning` | attribute | `instance/registry.yaml` |

`network.l2.mac.entries` participates in **both** D1 and D2 — its new name `network.l2.fdb.entry.count` already
embeds `.count`, so the two decisions are applied as one edit (see Ordering). The `mac.entries` → `fdb.entry.count`
rename also drops a dimension reference site: `mac.entry.type` is ref'd on `mac.entries`, so the metric's `ref:`
updates to `network.l2.fdb.entry.type` at the same time.

### D3 — EIGRP queue dot (Requirement 3)

| Old name | New name | Kind | Definition file |
|----------|----------|------|-----------------|
| `network.neighbor.eigrp.queue_depth` | `network.neighbor.eigrp.queue.depth` | metric | `neighbor/metrics.yaml` |

All other underscore leaves are confirmed unchanged (keep inventory, Requirement 3.2/3.4).

### D4 — `adjacency` → `arpnd` (Requirement 4)

| Old name | New name | Kind | Definition file |
|----------|----------|------|-----------------|
| `network.l3.adjacency.entries` | `network.l3.arpnd.entry.count` | metric | `l3/metrics.yaml` |
| `network.l3.adjacency.entry.type` | `network.l3.arpnd.entry.type` | attribute | `l3/registry.yaml` |
| `network.l3.adjacency.state` | `network.l3.arpnd.state` | attribute | `l3/registry.yaml` |

The count metric also carries the D1 transformation (`entries` → `entry.count`). The `network.type` (ipv4/ipv6)
discriminator and both attribute dimensions are preserved, renamed only on the `adjacency` → `arpnd` segment.

### D5 — admin/oper axes dotted + interface fold (Requirement 5)

| Old name | New name | Kind | Definition file |
|----------|----------|------|-----------------|
| `network.admin_state` | `network.admin.state` | attribute | `common/registry.yaml` |
| `network.oper_state` | `network.oper.state` | attribute | `common/registry.yaml` |
| `network.admin_status` | `network.admin.status` | metric | `device/metrics.yaml` |
| `network.oper_status` | `network.oper.status` | metric | `device/metrics.yaml` |
| `network.interface.admin_state` | *(folded into `network.admin.state`)* | attribute | removed from `interface/registry.yaml` |
| `network.interface.oper_state` | *(folded into `network.oper.state`)* | attribute | removed from `interface/registry.yaml` |
| *(new)* | `network.native_state` | attribute | `common/registry.yaml` |

### D7 — interface identity + FK leaf renames (Requirement 7)

| Old name | New name | Kind | Definition file |
|----------|----------|------|-----------------|
| `network.interface.id` | *(dropped; identity = upstream `network.interface.name`)* | attribute | removed from `interface/registry.yaml` |
| `network.interface.parent.id` | `network.interface.parent.name` | attribute | `interface/registry.yaml` |
| `network.interface.lower_layer.id` | `network.interface.lower_layer.name` | attribute | `interface/registry.yaml` |
| `network.link.local.interface.id` | `network.link.local.interface.name` | attribute | `link/registry.yaml` |
| `network.link.remote.interface.id` | `network.link.remote.interface.name` | attribute | `link/registry.yaml` |
| `network.path.local.interface.id` | `network.path.local.interface.name` | attribute | `path/registry.yaml` |
| `network.l2.mac.previous_interface.id` | `network.l2.mac.previous_interface.name` | attribute | `l2/registry.yaml` |
| *(new)* | `network.interface.index` (`opt_in`) | attribute | `interface/registry.yaml` |

Plus the dimension `ref: network.interface.id` on `network.l2.mac.*` metrics retargets to
`ref: network.interface.name`, and `network.lag.members`' note is restated (key unchanged).

### D8 / D9 — additions (Requirements 8, 9)

| New name | Kind | Definition file |
|----------|------|-----------------|
| `network.interface.higher_layer.id` (`opt_in`, array; value = interface names) | attribute | `interface/registry.yaml` |
| `network.interface.last_change` (timestamp) | attribute | `interface/registry.yaml` |
| `network.interface.ip.mtu` (int bytes, keyed by `network.type`) | attribute | `interface/registry.yaml` |
| `network.interface.mtu` (re-pinned to L2 frame MTU; key unchanged) | attribute | `interface/registry.yaml` |

### Design Approach for Structural Changes

The pure renames are mechanical (rename definition + sweep refs). The four non-trivial structural changes need
explicit design.

### D5 — Folding interface state into a shared `network.admin.state` / `network.oper.state`

**Before.** Two parallel vocabularies exist:

- `network.admin_state` / `network.oper_state` (defined in `common/registry.yaml`), the ENTITY-STATE-MIB /
  X.731 hardware-entity enums (`locked`/`unlocked`/`shutting_down`; `enabled`/`disabled`/`testing`), ref'd on
  four hardware grains in `device/entities.yaml`.
- `network.interface.admin_state` / `network.interface.oper_state` (defined in `interface/registry.yaml`), the
  RFC 2863 IF-MIB interface enums (`up`/`down`/`testing`; `up`/`down`/`dormant`/`lower_layer_down`/`not_present`/
  `testing`/`unknown`), ref'd in `interface/entities.yaml`.

**After.** A single shared pair `network.admin.state` / `network.oper.state` defined once in
`common/registry.yaml`, referenced at **five** grains: `network.device`, `network.chassis`, `network.module`,
`network.component`, and `network.interface` (Requirement 5.7). The interface-specific definitions are removed
(Requirement 5.5/5.6).

**The enum becomes an open superset.** The single hard problem with folding is the interface-only values that are
diagnostically valuable (`lower_layer_down`, `dormant`, `not_present`) and must not collapse to a coarse `down`.
The shared `network.oper.state` (and `network.admin.state`) is defined as an **open enum whose well-known member
set is exactly the union** of the prior hardware and interface value sets (Requirement 5.8):

```
enabled, up, disabled, down, degraded, testing, dormant, lower_layer_down, not_present, unknown
```

Open means each plane emits the subset relevant to it (a chassis uses `enabled`/`disabled`/`testing`; an interface
uses `up`/`down`/`dormant`/`lower_layer_down`/`not_present`) and a caller MAY supply an additional value without a
validation failure. This is the RFC 8343/8348 "one leaf, value set valid for the node class" model, and it keeps
the high-value interface values as first-class members rather than demoting them to a string.

**Per-ref-site control is preserved.** Requirement level and entity association are set at the **ref site**, not on
the shared definition, so folding costs no per-grain control: the interface ref site MAY be `recommended` and the
chassis ref site MAY be `opt_in` with no conflict (Requirement 5.9). Each of the five `- ref: network.oper.state`
sites carries its own explicit `requirement_level` and the entity association is the entity it sits on.

**The `native_state` companion.** A `network.native_state` attribute is added to `common/registry.yaml`, defined
exactly as the existing `network.neighbor.native_state` is (a verbatim, untransformed vendor string), so genuine
vendor terms that the normalized enum discards are still carried (Requirement 5.11).

**The status metrics** `network.admin.status` / `network.oper.status` (renamed from `*_status` in
`device/metrics.yaml`) reference the renamed `network.admin.state` / `network.oper.state` as their
value-always-1 dimension (the K8s `status.phase` pattern), unchanged except for the dotted names.

**Out of scope of the fold** (Requirement 5.10): `network.stp.port.state`, `network.pon.onu.state`,
`network.wifi.ap.state`, `network.multicast.querier` are genuine per-domain current-state gauges, not the
admin/oper axis, and keep their names, value sets, and requirement levels.

### D7 — Interface identity = upstream `network.interface.name`

**Drop the minted key.** `network.interface.id` (defined in `interface/registry.yaml`) is removed entirely
(Requirement 7.1). No defining site declares it after the sweep. The identity key becomes the **Stable upstream**
`network.interface.name` (IF-MIB `ifName`), referenced from upstream and preserving its `stable` stability and
string type (Requirement 7.2). This is reuse-before-defining (R5) and keeps identity minimal for the Prometheus
hash projection.

**The reference sites split into two kinds:**

1. **Identity / dimension uses** (`network.interface.id` used to *point at* an interface) become
   `network.interface.name`. This covers `interface/entities.yaml`'s `identity:` and the FDB/MAC metric dimensions
   in `l2/metrics.yaml` (`ref: network.interface.id` → `ref: network.interface.name`).

2. **Foreign-key leaf definitions** (`*.interface.id`) are renamed to `*.interface.name`, because a flat FK should
   be named for the identity attribute it joins on (YANG leafref precedent). These are attribute *definitions* in
   their own packages:
   - `network.link.local.interface.id` / `network.link.remote.interface.id` → `.name` (`link/registry.yaml`)
   - `network.path.local.interface.id` → `.name` (`path/registry.yaml`)
   - `network.l2.mac.previous_interface.id` → `.name` (`l2/registry.yaml`; also ref'd in `l2/events.yaml` on the
     `network.l2.mac.moved` record)
   - `network.interface.parent.id` / `network.interface.lower_layer.id` → `.name` (`interface/registry.yaml`)

   Each is a **leaf-name-only change** preserving value type, requirement level, entity association, and
   `development` stability (Requirement 7.12).

**`network.interface.index`** is added as an `opt_in` disambiguator (IF-MIB `ifIndex`), named `index` not
`if_index` (the package's no-`if_`-prefix convention; Requirement 7.3).

**`network.interface.description`** is pinned to ifAlias and its note edited to drop the "/ interface description"
phrasing that conflated ifAlias and ifDescr (Requirement 7.4). No third interface string is modelled — ifDescr is
covered by `hw.*` (Requirement 7.11).

**`network.lag.members`** keeps its key but its note is restated to clarify the values are interface *names*
(Requirement 7.9).

**Sub-entities keep their minted `.id`.** `network.module.parent.id`, `network.lag.id`, and pool ids are unchanged —
there is no Stable upstream name attribute to reuse for them, so the `.id` identity convention holds for everything
except interface (Requirement 7.10).

### D8 — Symmetric upward layering + last-change

- **`network.interface.higher_layer.id`** — added as an `opt_in`, multi-valued (array) attribute listing the
  interfaces running directly on top of this one, the inverse of `network.interface.lower_layer` (Requirement 8.1).
  Although the attribute key segment is `.id` per the naming-review's stated target (`higher_layer.id[]`), its
  **value is interface names**, consistent with the FK convention after D7 (Requirement 8.2) — the note states this
  explicitly, mirroring how `network.lag.members` is handled. (The lower-layer FK leaf itself is renamed to
  `lower_layer.name` under D7; `higher_layer` is the new symmetric companion.)
- **`network.interface.last_change`** — added as the timestamp of the instant the interface entered its current
  operational state (the most recent oper-state transition, IF-MIB `ifLastChange`) (Requirement 8.3).
- **Bidirectional inverse invariant** — the two attributes form an exact inverse pair: B ∈ A.higher_layer ⇔
  A ∈ B.lower_layer (Requirement 8.4). Top-of-stack omits `higher_layer`; bottom-of-stack omits `lower_layer`
  (Requirement 8.5). `last_change` MAY be omitted when no transition has occurred since re-init (Requirement 8.6).

### D9 — MTU layering

- **`network.interface.mtu`** is re-pinned (note edit, key unchanged — Requirement 9.5) to mean the **L2 frame
  MTU** (OpenConfig `config/mtu` sense), an integer number of bytes in 64–65535 (Requirement 9.1).
- **`network.interface.ip.mtu`** is added to carry the **L3 per-address-family MTU**, an integer in 64–65535,
  dimensioned by `network.type` (Requirement 9.2). The `network.type` values that dimension it are constrained to
  the closed set `ipv4`/`ipv6` (Requirement 9.3); a dual-stack interface reports it once per value alongside a
  single `network.interface.mtu` (Requirement 9.4).

This is additive — a new attribute plus a re-pinned definition — so it carries no rename coordination, but it lands
in the same change set.

## Lockstep Update Strategy

The sweep must leave **nothing dangling** (Requirement 11) and the registry must resolve cleanly (Requirement 12).
The strategy:

### 1. Build the authoritative old→new token map

The mapping table above is the source of truth. Each entry is a complete identifier token (e.g.
`network.routing.routes` → `network.routing.route.count`), not a fragment.

### 2. Find every occurrence by complete-token match

For each old name, scan all Reference_Sites:

- model YAML under `model/network/**` (`registry.yaml`, `metrics.yaml`, `events.yaml`, `entities.yaml`) — both
  definition sites (`- key:` / `- name:` / `- id:`) and reference sites (`- ref:`) and prose `note:`/`brief:` text;
- every `examples/*/README.md` and `examples/README.md`;
- `docs/conventions.md` and `docs/naming-review.md`.

**Complete-token matching, not substring** (Requirement 11.1). This is critical because the names are prefixes of
each other:

- `network.nat.ports` must NOT match inside `network.nat.port_blocks`, `network.nat.port.utilization`, or
  `network.nat.pool.addresses`.
- `network.multicast.routes` must NOT match inside `network.multicast.route.state` (a dimension attribute).
- `network.admin_state` must NOT corrupt `network.interface.admin_state` (which is folded, not string-replaced) —
  the two are handled by distinct map entries, and the shared one is matched only at a token boundary.
- `network.l2.mac.entries` must NOT match `network.l2.mac.entry.type` (handled by its own D2 entry) nor the kept
  `network.l2.mac.address`/`.state`/`.status`/`.moved`.

Practically, matching is anchored on identifier boundaries: a match requires the character before the token to be a
non-identifier character (quote, whitespace, `` ` ``, `:`) and the character after to not be a `.` or identifier
character that would extend it into a longer name (e.g. `…ports` followed by `_` or `.` is a different name). The
`.weaver`/Weaver resolve in the validation step is the backstop that catches any miss as a broken reference.

### 3. Apply renames at definition and reference sites together

Because Weaver resolves `ref:` against `key:`, a definition rename and all its `ref:` renames are applied as one
unit. A metric/event rename additionally updates prose mentions but has no `ref:` dependents.

### 4. Ordering considerations

- **D1 + D2 overlap on `network.l2.mac.entries`.** Its correct final name is `network.l2.fdb.entry.count`, which is
  simultaneously the FDB container rename (D2) and the `.count` de-pluralization (D1). Apply it as the single target
  `network.l2.fdb.entry.count` — do not stage an intermediate `network.l2.mac.entry.count` that would itself need a
  second rename. The same applies to `network.l3.adjacency.entries`: target `network.l3.arpnd.entry.count` directly
  (D4 namespace + D1 count in one).
- **D5 fold before interface ref rewrite.** Define the shared `network.admin.state`/`network.oper.state` (renamed
  from `common`'s `admin_state`/`oper_state`) first, then repoint the interface entity's refs at the shared
  attribute and delete the interface-specific definitions — so the interface ref never points at a not-yet-existing
  key.
- **D7 drop-and-repoint atomicity.** Removing `network.interface.id` and repointing every identity/dimension/FK use
  to `network.interface.name` (or the renamed FK leaf) must happen together; a partial application leaves either a
  dangling `ref:` or an orphaned definition.
- The additive changes (D8, D9) have no ordering constraint among themselves; they land in the same set.

### 5. Single coordinated landing

All renames from Requirements 1–11 land in one change set — every rename present or none (Requirement 13.1), no
deprecation aliases (13.2), all affected signals at `development` (13.3), examples and docs included in the same
set (13.4). `docs/naming-review.md` additionally has each swept row's recorded status set to "applied"
(Requirement 11.4).

## Validation Strategy

The registry is validated with the OpenTelemetry **Weaver** semantic-convention tooling (the `Semconv_Tooling` of
the glossary). This repository carries a `.weaver/` directory (currently just `vdir_cache/`); there is no top-level
`Makefile` in this repo, so validation is run via Weaver directly against the `model/` registry (the
`weaver registry check` / `weaver registry resolve` commands, the same `otel/weaver` image the sibling
`otel-semantic-conventions` repos pin in their `.weaver.toml`/`Makefile`). The relevant invariants the tooling
enforces:

1. **Reference resolution** — every `- ref:` resolves to a defined `- key:`. This is the primary guard for the
   def/ref renames: a missed admin/oper, FDB, or interface-FK ref surfaces here as a broken reference
   (Requirement 12.1).
2. **Registry well-formedness** — no duplicate keys/metric names, valid enum members, valid stability values
   (Requirement 12.2). The D1 collision guard (Requirement 1.18) maps here: if a `{object}.count` target already
   existed as a distinct metric the resolve would report a duplicate; the design's answer is to reject that rename
   and leave definitions unchanged. (No such collision exists in the current registry — `network.session.count`
   is the only pre-existing `.count` and it is not a rename target.)

**The validation loop** (Requirement 12.3/12.4): after the sweep, run the Weaver resolve/check. If it reports any
broken reference or validation error, fix the affected reference site(s) and re-run; the change is not complete
until a zero-error, zero-broken-reference result is obtained.

**Stability guard** (Requirement 13.5): every affected signal must be `development`. Any signal found at a
different stability (e.g. `stable`) is a validation failure — the sweep does not silently change a stability level.

**Stale-reference guard** (Requirements 11.5/11.6, 13.6): after the renames, re-scan all defining and referencing
sites for any remaining occurrence of any old name and report the count. A non-zero count means the sweep is
incomplete: replace each remaining occurrence and re-scan. This scan covers the model YAML, the example READMEs,
and the two docs — broader than Weaver's own resolution (which only sees the model), because the examples and docs
are prose Reference_Sites Weaver does not parse.

The two guards compose: Weaver proves the *model* resolves; the token re-scan proves *no old name survives
anywhere* (model + examples + docs). Both must pass.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system —
essentially, a formal statement about what the system should do. Properties serve as the bridge between
human-readable specifications and machine-verifiable correctness guarantees.*

This feature is a deterministic rename/refactor of a declarative registry, not a program with a runtime. The
"system under test" is the post-sweep registry plus the sweep procedure. The properties below are invariants that
must hold over the **set of renames** and the **resulting registry**; each is checkable by a scan, a Weaver
resolve, or a structured diff of preserved fields, rather than by 100 randomized program executions. They are
expressed with universal quantification over the rename set so they read as property-style invariants, but the
practical check for several is a single exhaustive pass (the rename set is finite and fully enumerated).

After prework analysis and a redundancy reflection, the many per-decision "rename X to Y / preserve fields /
zero occurrences" criteria collapse into a small set of registry-wide invariants, plus a few decision-specific
ones (the D5 fold, the D8 inverse pair) that carry unique validation value.

### Property 1: No pre-rename identifier survives at any reference site

*For all* old names in the rename set and *for all* Reference_Sites (model YAML definition and `ref:` sites under
`model/network/**`, every `examples/*/README.md`, `docs/conventions.md`, and `docs/naming-review.md`), the count of
complete-token occurrences of that old name is zero after the sweep.

This is the master zero-occurrence invariant. It is checked by the lockstep token re-scan and is the property
behind the per-decision "zero occurrences" rows.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 2.10, 4.6, 7.1, 11.1, 11.2, 11.3, 11.5, 11.6, 13.6**

### Property 2: Renames are name-only / structure-preserving

*For all* renamed signals (metrics, events, attributes, namespace leaves) in the rename set, the post-sweep
definition differs from the pre-sweep definition in the identifier only — instrument type, unit, value type,
enumeration members, brief, attribute set / dimension `ref:`s, entity associations, requirement levels, and
stability are all preserved (note text changes only where it itself named the old identifier or is an explicitly
mandated re-pin).

This is the single highest-value invariant of the sweep and generalizes the per-decision "retaining the original
definition's … with only the identifier changed" clauses. Checked by a structured field-diff of each definition
pre/post.

**Validates: Requirements 1.16, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 4.2, 4.3, 4.5, 7.5, 7.6, 7.7, 7.8, 7.12**

### Property 3: Every name not in the rename set is unchanged (non-over-reach)

*For all* metric, event, attribute, and entity names that are NOT in the rename set, the definition is unchanged by
the sweep — no accidental rename, no field change.

This guards against substring corruption and over-reach (e.g. de-pluralizing a monotonic counter, dotting an
acceptable snake_case leaf, restructuring the kept `mac.*`/`neighbor.*`/sub-entity `.id` names).

**Validates: Requirements 1.15, 1.17, 2.8, 2.9, 3.2, 3.4, 7.10, 10.4, 10.5**

### Property 4: De-pluralized occupancy counters have the `{object}.count` shape

*For all* 13 renamed occupancy counters, the new name matches the `{namespace}.{object}.count` form, the instrument
remains an UpDownCounter, and no plural occupancy name remains — yielding zero R1 violations across the renamed
set.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.19**

### Property 5: The shared admin/oper state attribute has exactly five reference grains

*For all* reference sites of the shared `network.admin.state` and `network.oper.state` attributes, the set of
referencing entity grains is exactly {`network.device`, `network.chassis`, `network.module`, `network.component`,
`network.interface`} — interface being the fifth grain — and no separate `network.interface.admin_state` /
`network.interface.oper_state` attribute is defined.

**Validates: Requirements 5.5, 5.6, 5.7**

### Property 6: The shared state enum membership equals the exact union and is open

*For all* well-known members of `network.admin.state` / `network.oper.state`, the member set is exactly the union
{`enabled`, `up`, `disabled`, `down`, `degraded`, `testing`, `dormant`, `lower_layer_down`, `not_present`,
`unknown`}, and the enum is open such that any additional caller-supplied value is accepted without a registry
validation failure.

**Validates: Requirements 5.8**

### Property 7: Every shared-state reference site carries explicit control

*For all* five reference sites of the shared state attribute, the site declares an explicit `requirement_level`
drawn from {`required`, `recommended`, `opt_in`} and an explicit entity association — independently per site (so
the interface site MAY be `recommended` while the chassis site is `opt_in`).

**Validates: Requirements 5.9**

### Property 8: `higher_layer` and `lower_layer` are an exact bidirectional inverse pair

*For all* interfaces A and B in any interface topology, B appears in A's `network.interface.higher_layer` set if
and only if A appears in B's `network.interface.lower_layer` set.

This is the one genuinely data-instance-quantified invariant: over any generated set of interfaces with
lower-layer edges, the higher-layer relation must equal the inverse edge set. It is the natural property-based
test of the layering model.

**Validates: Requirements 8.1, 8.4**

### Property 9: No deprecation residue

*For all* old names in the rename set, the post-sweep registry contains no deprecation alias, no `deprecated`
marker, and no backward-compatible duplicate definition for the pre-rename identifier.

**Validates: Requirements 13.2**

### Property 10: All affected signals are at `development` stability

*For all* signals affected by Requirements 1–11, the declared stability is `development`; any other stability is a
validation failure.

**Validates: Requirements 13.3, 13.5**

### Property 11: The post-sweep registry resolves cleanly

*For all* attribute references in the post-sweep registry, the reference resolves to a defined key, and the Weaver /
semconv checks complete with zero validation errors. (Integration-style: verified by a Weaver resolve/check over
the whole registry, not by randomized inputs.)

**Validates: Requirements 2.11, 12.1, 12.2, 12.3, 12.4**

## Error Handling

Because the artifact is a declarative registry, "errors" are validation failures and incomplete-sweep states
rather than runtime exceptions. The handling strategy:

- **Broken reference after a rename** (a `ref:` whose `key:` was renamed but the ref was missed) — caught by the
  Weaver resolve (Property 11). Handling: locate the dangling `ref:`, apply the rename, re-run. The change is not
  complete while any broken reference remains (Requirement 12.3/12.4).
- **Surviving old identifier** (an old name left in a prose note, an example README, or a doc) — caught by the
  token re-scan (Property 1). Handling: replace the occurrence, re-scan to zero (Requirement 11.6, 13.6).
- **Name collision on a `{object}.count` target** (Requirement 1.18) — caught by Weaver's duplicate-name
  detection. Handling: reject that single rename, report the collision and the conflicting metric, and leave all
  metric definitions unchanged. No such collision exists in the current registry, so this is a guard, not an
  expected path.
- **Disallowed stability** (an affected signal at `stable` rather than `development`, Requirement 13.5) — caught by
  the stability scan / Weaver. Handling: fail validation with the offending signal named; do not silently downgrade
  or change the stability.
- **Substring over-reach** (a complete-token rule that accidentally edits a longer name) — guarded by
  complete-token matching (Property 3) and surfaced as either a broken ref (the longer name's definition now
  mismatches its refs) or a non-target diff in the field-diff check.
- **Partial application** (Requirement 13.1) — the sweep is treated as atomic: the landing either contains every
  rename or none. A half-applied state is itself the error condition the lockstep scan + resolve detect.

## Testing Strategy

This feature is a declarative-registry refactor, so the "tests" are validation passes over the model and a scan
harness, complemented by the example/integration checks the prework identified. There is no application runtime to
exercise with randomized inputs for most criteria — with the single exception of the layering inverse invariant
(Property 8), which is genuinely amenable to property-based testing if the layering relation is exercised as code.

### Validation-driven checks (primary)

1. **Weaver resolve / check** over `model/network/**` — the authoritative gate for Properties 2 (field
   preservation surfaces as resolvable, well-formed definitions), 6 (open-enum validity), 10 (stability), and 11
   (zero broken refs, zero errors). Run via the `otel/weaver` tooling against the registry (no repo `Makefile`
   exists; invoke Weaver directly, matching the sibling repos' pinned image).
2. **Token re-scan harness** — a complete-token search over model YAML + `examples/*/README.md` +
   `docs/conventions.md` + `docs/naming-review.md` for every old name, asserting a zero count (Property 1) and that
   no non-target name was altered (Property 3). This is the lockstep completeness check and the stale-reference
   guard (Requirements 11.5/11.6, 13.6).
3. **Structured field-diff** — for each renamed definition, diff the pre/post YAML node and assert the only
   difference is the identifier (Property 2, 4). Drives the name-only invariant across D1/D2/D3/D4/D7.

### Example-based checks

The keep items, single edits, and optionality boundaries from the prework are verified by direct assertion:

- keep inventory items unchanged (`network.session.count`, the three `.limit` attrs, the four per-domain `.state`
  leaves, `qos.queue.depth`/`.max` as two gauges, the `network.neighbor.*` namespace, sub-entity `.id` keys);
- single edits present and correct (`eigrp.queue.depth`, `interface.index` opt_in, `description` ifAlias pin,
  `last_change`, `ip.mtu` keyed by `network.type` over the closed `{ipv4,ipv6}` set, `lag.members` note);
- optionality boundaries (top-of-stack `higher_layer` omission, `last_change` pre-transition omission);
- documentation-content checks for the D6 rules in `docs/conventions.md` and the D2 QoS prohibition (no
  current-vs-max selecting attribute on the depth gauges).

### Property-based testing (where applicable)

Only **Property 8** (the `higher_layer`/`lower_layer` bidirectional inverse) is a true for-all over data instances.
If the layering relation is realized as code (a function deriving `higher_layer` from the fleet-wide set of
`lower_layer` edges, or validating consistency between the two), it SHOULD be covered by a property-based test:

- Generate a random DAG of interfaces with `lower_layer` edges (including LAG fan-out and multi-layer stacks).
- Assert: for all A, B — B ∈ A.higher_layer ⇔ A ∈ B.lower_layer.
- Use the target ecosystem's PBT library (do not hand-roll), minimum 100 iterations, tagged
  **Feature: network-semconv-naming-alignment, Property 8: higher_layer and lower_layer are an exact bidirectional
  inverse pair**.

The remaining properties (1–7, 9–11) are invariants over a finite, fully-enumerated rename set and the registry
files; they are exhaustively verified in one pass by the Weaver resolve, the token re-scan, and the field-diff
above, which is stronger than sampling and is the correct tool for declarative-config correctness. No
property-based test is written for them because there is no meaningful input space to randomize — the rename set is
fixed and the check is exhaustive by construction.

## Keep / Do-Not-Change Inventory

To prevent over-reach (Property 3; Requirements 1.15, 1.17, 2.8/2.9, 3.2/3.3/3.4, 5.10, 7.10, 10.4/10.5, and the
preserved items in 2 and 5), the following are explicitly **not** changed by this sweep:

**Metrics that stay (monotonic counters — correctly plural, R2):**
`network.interface.packets`, `network.path.packets`, `network.qos.queue.packets`, `network.protocol.messages`,
`network.protocol.errors`, `network.neighbor.state_changes`, `network.stp.topology_changes`,
`network.routing.updates`, `network.access.session.setups`/`teardowns`, `network.session.setups`/`teardowns`,
`network.access.aaa.requests`, `network.access.coa.requests`, `network.path.label.operations`,
`network.path.protection.switches`, `network.multicast.rpf_failures`, `network.pon.fec.corrected`.

**Already-correct count:** `network.session.count` (the template — unchanged).

**QoS depth gauges (§2 / D-§2):** `network.qos.queue.depth` and `network.qos.queue.depth.max` stay as **two
separate gauge metrics** — never folded into one metric, never given a `stat`/current-vs-max selecting attribute
(Requirement 6).

**FDB keep items (D2 / Requirement 2.8/2.9):** `network.l2.mac.status`, `network.l2.mac.state`,
`network.l2.mac.moved`, `network.l2.mac.address`, and `network.l2.mac.previous_interface.*` stay under `mac` — the
only change to the latter is the D7 FK leaf `previous_interface.id` → `.name`.

**Acceptable snake_case leaves (D3 / Requirement 3.2) — unchanged:**
`min_links`, `system_id`, `route_type`, `df_role`, `address_family`, `route_distinguisher`, `route_target`,
`transport_class`, `path_cost`, `is_root`, `prefix_sid`, `adjacency_sid`, `binding_sid`, `segment_list`,
`in_segment`, `out_segment`, `filter_mode`, `noise_floor`, `tx_power`, `service_name`, `ac_name`, `address_scope`,
`state_changes`, `topology_changes`, `rpf_failures`, `native_state`, and the `previous_*` leaves.

**Already-dotted limit attributes (D3 / Requirement 3.3) — unchanged:**
`network.optical.power.limit`, `network.optical.bias_current.limit`, `network.device.memory.limit`.

**Per-domain state leaves (D5 / Requirement 5.10) — NOT folded into the admin/oper axis:**
`network.stp.port.state`, `network.pon.onu.state`, `network.wifi.ap.state`, `network.multicast.querier`.

**`network.neighbor` namespace (D6 / Requirement 10.4/10.5) — documentation/confirmation only:** every attribute
key, metric name, and namespace identifier under `network.neighbor.*` is identical before and after; `network.peer`
does not appear as a replacement. D6 adds only the two rule statements to `docs/conventions.md`.

**Sub-entity minted `.id` keys (D7 / Requirement 7.10) — unchanged:** `network.module.id`,
`network.module.parent.id`, `network.lag.id`, NAT/access pool ids, and every other entity `.id` keep the `.id`
identity convention. Interface is the sole exception (it reuses the Stable upstream `network.interface.name`).

**`network.interface.mtu` key (D9 / Requirement 9.5)** — the key is retained (not renamed); only its note is
re-pinned to the L2 frame MTU sense, and `network.interface.ip.mtu` is added alongside.
