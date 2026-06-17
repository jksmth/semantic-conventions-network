# Implementation Plan: Network Semconv Naming Alignment

## Overview

This plan lands the D1–D9 (plus §2 and D6) naming-and-refactor decisions as a single coordinated sweep
across `model/network/**`, `examples/*/README.md`, `docs/conventions.md`, and `docs/naming-review.md`. The
"implementation" is edits to declarative Weaver / OpenTelemetry semantic-convention YAML and the prose
Reference_Sites that mention the affected names — there is no application runtime.

Tasks are grouped by decision (per the design's Rename Mapping Table and Scope summary). Each rename task
covers **both the definition site and every ref-site** (model `ref:`s plus prose `note:`/`brief:` text) for
the names it owns, because Weaver resolves `ref:` against `key:` and a half-applied rename leaves a dangling
reference (design: "How attributes are defined vs referenced", "Lockstep Update Strategy").

The design's §4 ordering constraints are honored explicitly:

- **D1+D2 overlap** — `network.l2.mac.entries` lands directly as `network.l2.fdb.entry.count` (one edit, no
  intermediate `network.l2.mac.entry.count`); handled inside the D2 task (task 3).
- **D4+D1 overlap** — `network.l3.adjacency.entries` lands directly as `network.l3.arpnd.entry.count`;
  handled inside the D4 task (task 5).
- **D5 fold before interface ref rewrite** — the shared `network.admin.state`/`network.oper.state` are
  defined first (task 6.1) before the interface entity refs are repointed and the interface-specific defs
  removed (task 6.3).
- **D7 drop-and-repoint atomicity** — dropping `network.interface.id` and repointing every
  identity/dimension/FK use to `network.interface.name` (or the renamed FK leaf) happen together (tasks 7.1,
  7.2).

The keep / do-not-change inventory is enforced as **guard checks** (read-only assertions), never as edit tasks
(tasks 3.2, 4.2, 6.5, 7.3, 9.2, 10.1, 13.5).

## Tasks

- [x] 1. Establish the rename token map and validation harness
  - [x] 1.1 Build the authoritative old→new token map and the keep-inventory guard list
    - Enumerate every old→new identifier as a **complete token** from the design's Rename Mapping Table
      (D1: 13 occupancy counters; D2: FDB metrics/attrs/event; D3: `eigrp.queue_depth`; D4: `adjacency`→`arpnd`;
      D5: `admin_state`/`oper_state` + `*_status`; D7: `interface.id` drop + FK `.id`→`.name`).
    - Record the keep/do-not-change inventory verbatim from the design ("Keep / Do-Not-Change Inventory") so
      guard tasks can assert non-change: `network.session.count`; monotonic counters; `qos.queue.depth`/`.max`;
      `mac.status`/`.state`/`.moved`/`.address`; acceptable snake_case leaves; already-dotted `.limit` attrs;
      per-domain `.state` leaves; the `network.neighbor.*` namespace; sub-entity `.id` keys; `interface.mtu` key.
    - Encode complete-token (identifier-boundary) matching so prefixes do not cross-match (`network.nat.ports`
      ∉ `network.nat.port_blocks`; `network.admin_state` ∉ `network.interface.admin_state`).
    - _Requirements: 11.1, 13.1_
    - _Design: Lockstep Update Strategy (steps 1–2), Keep / Do-Not-Change Inventory_

  - [x] 1.2 Set up the Weaver resolve/check invocation and the complete-token scan harness
    - Wire the `otel/weaver` resolve/check over `model/network/**` (no repo `Makefile`; invoke Weaver directly,
      matching the sibling repos' pinned image) as the reference-resolution and well-formedness gate.
    - Wire a complete-token search over model YAML + `examples/*/README.md` + `docs/conventions.md` +
      `docs/naming-review.md` that reports per-old-name occurrence counts.
    - Wire a structured per-definition field-diff (pre/post YAML node) that asserts identifier-only difference.
    - _Requirements: 11.5, 12.1, 12.2_
    - _Design: Validation Strategy, Testing Strategy (validation-driven checks 1–3)_

- [x] 2. D1 — De-pluralize occupancy UpDownCounters
  - [x] 2.1 Rename the standalone occupancy counters at definition + every ref-site
    - Rename in `routing/`, `multicast/`, `evpn/`, `sr/`, `nat/`, `access/`, `wifi/` metrics.yaml:
      `routing.routes`→`routing.route.count`, `routing.ecmp.routes`→`routing.ecmp.route.count`,
      `multicast.routes`→`multicast.route.count`, `multicast.groups`→`multicast.group.count`,
      `evpn.routes`→`evpn.route.count`, `sr.sids`→`sr.sid.count`, `nat.translations`→`nat.translation.count`,
      `nat.ports`→`nat.port.count`, `nat.port_blocks`→`nat.port_block.count`,
      `nat.pool.addresses`→`nat.pool.address.count`, `access.sessions`→`access.session.count`,
      `access.pool.addresses`→`access.pool.address.count`, `wifi.bss.stations`→`wifi.bss.station.count`.
    - Sweep the prose ref-sites for `network.routing.routes`: the EIGRP comment block in `neighbor/metrics.yaml`
      and the ECMP note in `routing/metrics.yaml`.
    - Preserve instrument (`updowncounter`), unit, brief, and attribute set on each — name-only change.
    - `network.l2.mac.entries` and `network.l3.adjacency.entries` are the two D1 members that also carry a
      namespace change; they are landed in tasks 3 and 5 respectively (single combined target), NOT here.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.16, 11.1, 11.2, 11.3_
    - _Design: Rename Mapping D1, Lockstep Update Strategy (step 3)_

  - [x] 2.2 Field-diff verification for the D1 renames
    - **Property 2: Renames are name-only / structure-preserving**
    - **Property 4: De-pluralized occupancy counters have the `{object}.count` shape**
    - **Validates: Requirements 1.16, 1.19**

- [x] 3. D2 — FDB rename (container `fdb`, entry `mac`), incl. combined D1+D2 target
  - [x] 3.1 Rename the FDB metrics, attribute, and event at definition + ref-sites
    - In `l2/metrics.yaml`: rename `network.l2.mac.entries` directly to `network.l2.fdb.entry.count` (the single
      combined D1+D2 target — no intermediate name), and `network.l2.mac.learn_discards` to
      `network.l2.fdb.entry.discards`; update the metric's dimension `ref:` from `network.l2.mac.entry.type` to
      `network.l2.fdb.entry.type`.
    - In `l2/registry.yaml`: rename attribute `network.l2.mac.entry.type` to `network.l2.fdb.entry.type`.
    - In `l2/events.yaml`: rename event `network.l2.mac_limit.exceeded` to `network.l2.fdb.limit_exceeded`.
    - In `vlan/registry.yaml`: rename `network.vlan.mac_limit` to `network.vlan.fdb.limit`.
    - In `instance/registry.yaml`: rename `network.instance.mac_limit` to `network.instance.fdb.limit` and
      `network.instance.mac_learning` to `network.instance.fdb.mac_learning` (keep the `mac_learning` leaf word).
    - Sweep the cross-referencing prose notes in `l2/metrics.yaml` and `l2/events.yaml`.
    - Preserve instrument/unit/value type/brief/stability and enum members on each — name-only change.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.10, 11.1_
    - _Design: Rename Mapping D2, §4 ordering (D1+D2 overlap)_

  - [x] 3.2 Guard: FDB keep items unchanged
    - **Property 3: Every name not in the rename set is unchanged (non-over-reach)**
    - Assert `network.l2.mac.status`, `network.l2.mac.state`, `network.l2.mac.moved`, `network.l2.mac.address`
      and the `network.l2.mac.previous_interface.*` prefix (except the D7 FK leaf) are unchanged.
    - **Validates: Requirements 2.8, 2.9**

- [x] 4. D3 — Dot the EIGRP queue leaf
  - [x] 4.1 Rename `network.neighbor.eigrp.queue_depth` to `network.neighbor.eigrp.queue.depth`
    - Edit only the affected leaf segment in `neighbor/metrics.yaml`; preserve instrument, unit, semantics.
    - _Requirements: 3.1, 11.1_
    - _Design: Rename Mapping D3_

  - [x] 4.2 Guard: no other snake_case leaf dotted under D3
    - **Property 3: Every name not in the rename set is unchanged (non-over-reach)**
    - Assert the acceptable snake_case leaf set (`min_links`, `system_id`, … `native_state`, `previous_*`) and
      the already-dotted `.limit` attributes (`optical.power.limit`, `optical.bias_current.limit`,
      `device.memory.limit`) are unchanged.
    - **Validates: Requirements 3.2, 3.3, 3.4**

- [x] 5. D4 — Rename `adjacency` namespace to `arpnd`, incl. combined D4+D1 target
  - [x] 5.1 Rename every `network.l3.adjacency.*` name to `network.l3.arpnd.*` at definition + ref-sites
    - In `l3/metrics.yaml`: rename `network.l3.adjacency.entries` directly to `network.l3.arpnd.entry.count`
      (combined D4 namespace + D1 count, one edit), preserving the UpDownCounter instrument/unit/brief and the
      `network.type` (ipv4/ipv6) discriminator association.
    - In `l3/registry.yaml`: rename `network.l3.adjacency.entry.type` to `network.l3.arpnd.entry.type` and
      `network.l3.adjacency.state` to `network.l3.arpnd.state`, changing only the `adjacency`→`arpnd` segment.
    - Keep ARP and ND merged under one `network.type`-discriminated namespace (no `arp.*`/`nd.*` split).
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 11.1_
    - _Design: Rename Mapping D4, §4 ordering (D4+D1 overlap)_

  - [x] 5.2 Field-diff verification for the arpnd renames
    - **Property 2: Renames are name-only / structure-preserving**
    - **Property 1: No pre-rename identifier survives** (zero `network.l3.adjacency.*` occurrences)
    - **Validates: Requirements 4.5, 4.6**

- [x] 6. D5 — Dot the admin/oper axes and fold interface state (define shared first, then repoint)
  - [x] 6.1 Define the shared `network.admin.state` / `network.oper.state` in `common/registry.yaml`
    - Rename `network.admin_state`→`network.admin.state` and `network.oper_state`→`network.oper.state`.
    - Redefine each as an **open enum** whose well-known member set is exactly the union
      `{enabled, up, disabled, down, degraded, testing, dormant, lower_layer_down, not_present, unknown}`,
      accepting additional caller-supplied values without validation failure.
    - Add the `network.native_state` companion (verbatim untransformed vendor string), defined exactly as
      `network.neighbor.native_state`.
    - _Requirements: 5.1, 5.2, 5.8, 5.11, 11.1_
    - _Design: D5 Folding interface state, §4 ordering (D5 fold before interface ref rewrite)_

  - [x] 6.2 Rename the device status metrics and repoint the four hardware grains
    - In `device/metrics.yaml`: rename `network.admin_status`→`network.admin.status` and
      `network.oper_status`→`network.oper.status`, repointing their value-always-1 dimension `ref:`s to the
      renamed `network.admin.state`/`network.oper.state`.
    - In `device/entities.yaml`: repoint the `network.device`, `network.chassis`, `network.module`,
      `network.component` ref-sites to the renamed shared attributes, keeping each site's explicit
      `requirement_level` and entity association.
    - _Requirements: 5.3, 5.4, 5.9, 11.1_
    - _Design: D5 (status metrics; per-ref-site control preserved)_

  - [x] 6.3 Repoint the interface entity to the shared attributes and remove the interface-specific defs
    - In `interface/entities.yaml`: repoint the admin/oper refs to the shared `network.admin.state` /
      `network.oper.state` (interface becomes the **fifth grain**), with explicit `requirement_level`
      (MAY be `recommended`) and entity association.
    - In `interface/registry.yaml`: remove the `network.interface.admin_state` and
      `network.interface.oper_state` definitions (folded — not string-replaced).
    - _Requirements: 5.5, 5.6, 5.7, 5.9, 11.1_
    - _Design: D5 After (five grains), §4 ordering (fold before repoint)_

  - [x] 6.4 Verify the fold: grains, enum membership, per-site control
    - **Property 5: The shared admin/oper state attribute has exactly five reference grains**
    - **Property 6: The shared state enum membership equals the exact union and is open**
    - **Property 7: Every shared-state reference site carries explicit control**
    - **Validates: Requirements 5.5, 5.6, 5.7, 5.8, 5.9**

  - [x] 6.5 Guard: per-domain state leaves NOT folded
    - **Property 3: Every name not in the rename set is unchanged (non-over-reach)**
    - Assert `network.stp.port.state`, `network.pon.onu.state`, `network.wifi.ap.state`,
      `network.multicast.querier` keep their names, value sets, and requirement levels.
    - **Validates: Requirements 5.10**

- [x] 7. D7 — Interface identity = upstream `name`; rename FK leaves (drop-and-repoint atomically)
  - [x] 7.1 Drop `network.interface.id` and repoint identity/dimension uses to `network.interface.name`
    - In `interface/registry.yaml`: remove the `network.interface.id` definition; add `network.interface.index`
      as an `opt_in` disambiguator (named `index`, not `if_index`); pin `network.interface.description` to SNMP
      ifAlias and edit its note to drop the conflated "/ interface description" phrasing.
    - In `interface/entities.yaml`: change the `identity:` ref from `network.interface.id` to
      `network.interface.name` (Stable upstream, preserving its `stable` stability and string type).
    - In `l2/metrics.yaml`: retarget the dimension `ref: network.interface.id` on the FDB/MAC metrics to
      `ref: network.interface.name`.
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.11, 11.1_
    - _Design: D7 (drop minted key; identity/dimension uses), §4 ordering (drop-and-repoint atomicity)_

  - [x] 7.2 Rename the foreign-key leaf definitions `.id`→`.name` and restate `lag.members`
    - In `interface/registry.yaml`: `network.interface.parent.id`→`.parent.name`,
      `network.interface.lower_layer.id`→`.lower_layer.name`.
    - In `link/registry.yaml`: `network.link.local.interface.id`→`.name`,
      `network.link.remote.interface.id`→`.name`.
    - In `path/registry.yaml`: `network.path.local.interface.id`→`.name`.
    - In `l2/registry.yaml`: `network.l2.mac.previous_interface.id`→`.name` (also sweep its `ref:` on the
      `network.l2.mac.moved` record in `l2/events.yaml`).
    - In `lag/registry.yaml`: restate the `network.lag.members` note to clarify the values are interface
      **names** (key unchanged).
    - Each FK rename is leaf-name-only: preserve value type, requirement level, entity association, and
      `development` stability.
    - _Requirements: 7.5, 7.6, 7.7, 7.8, 7.9, 7.12, 11.1_
    - _Design: D7 (foreign-key leaf definitions)_

  - [x] 7.3 Verify FK leaf-name-only preservation and sub-entity `.id` keep
    - **Property 2: Renames are name-only / structure-preserving**
    - **Property 3: Every name not in the rename set is unchanged** (sub-entity `.id` keys: `network.module.id`,
      `network.module.parent.id`, `network.lag.id`, pool ids — unchanged)
    - **Validates: Requirements 7.10, 7.12**

- [x] 8. D8 — Interface completeness additions
  - [x] 8.1 Add `higher_layer.id` and `last_change` to `interface/registry.yaml`
    - Add `network.interface.higher_layer.id` as `opt_in`, multi-valued (array), the inverse of
      `network.interface.lower_layer.name`; note states the value is interface **names**.
    - Add `network.interface.last_change` as the timestamp of the most recent oper-state transition
      (IF-MIB `ifLastChange`); MAY be omitted when no transition has occurred since re-init.
    - Top-of-stack MAY omit `higher_layer` (mirrors bottom-of-stack omitting `lower_layer`).
    - _Requirements: 8.1, 8.2, 8.3, 8.5, 8.6_
    - _Design: D8 Symmetric upward layering + last-change_

  - [x] 8.2 Property test for the layering inverse pair
    - **Property 8: `higher_layer` and `lower_layer` are an exact bidirectional inverse pair**
    - Generate a random DAG of interfaces with `lower_layer` edges (including LAG fan-out and multi-layer
      stacks); assert for all A, B: B ∈ A.higher_layer ⇔ A ∈ B.lower_layer. Use the target ecosystem's PBT
      library, minimum 100 iterations, tagged "Feature: network-semconv-naming-alignment, Property 8".
    - **Validates: Requirements 8.1, 8.4**

- [x] 9. D9 — MTU layering
  - [x] 9.1 Re-pin `interface.mtu` and add `interface.ip.mtu`
    - In `interface/registry.yaml`: re-pin `network.interface.mtu`'s note to the L2 frame MTU (OpenConfig
      `config/mtu` sense), integer bytes 64–65535, **key unchanged**.
    - Add `network.interface.ip.mtu` as the L3 per-address-family MTU (integer bytes 64–65535), dimensioned by
      `network.type` constrained to the closed set `{ipv4, ipv6}`; a dual-stack interface reports it once per
      value alongside a single `network.interface.mtu`.
    - In `interface/metrics.yaml`: wire the `ip.mtu` `network.type` dimension where applicable.
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
    - _Design: D9 MTU layering_

  - [x] 9.2 Guard: `interface.mtu` key retained, addition is additive
    - **Property 3: Every name not in the rename set is unchanged (non-over-reach)**
    - **Validates: Requirements 9.5**

- [x] 10. D6 — Confirm `network.neighbor` term and state the anti-explosion rule (docs only)
  - [x] 10.1 Add the D6 rule statements to `docs/conventions.md` and guard the neighbor namespace
    - State that a counter with exactly one identifiable peer reuses the generic `network.neighbor` counters
      (`network.protocol.messages` / `network.protocol.errors` keyed by `network.neighbor.protocol`), while a
      peerless signal gets its own `network.<x>.*` namespace.
    - State that a `network.neighbor.<protocol>.*` refinement is justified only when a facet is protocol-unique
      with no vendor-neutral generic equivalent.
    - Guard (read-only): every `network.neighbor.*` key/metric/namespace is identical before and after, and
      `network.peer` does not appear as a replacement.
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
    - _Design: Scope summary (D6), Keep / Do-Not-Change Inventory (network.neighbor)_

- [x] 11. Lockstep cross-cutting Reference_Site updates
  - [x] 11.1 Sweep `examples/*/README.md` for every renamed identifier
    - Replace every complete-token occurrence of an old name with its new name across all example narratives
      (`examples/README.md` and the eleven device-example READMEs); leave examples that mention no renamed name
      untouched (driven by the token scan, not assumed).
    - _Requirements: 11.2, 13.4_
    - _Design: Example READMEs, Lockstep Update Strategy_

  - [x] 11.2 Sweep `docs/conventions.md` for every renamed identifier
    - Replace every complete-token occurrence of an old name with its new name (distinct from the D6 rule-text
      additions in task 10.1).
    - _Requirements: 11.3, 13.4_
    - _Design: Lockstep Update Strategy_

  - [x] 11.3 Update `docs/naming-review.md` names and statuses
    - Replace each old name with its new name and set each swept row's recorded status to "applied".
    - _Requirements: 11.4, 13.4_
    - _Design: §5 Single coordinated landing_

- [x] 12. Checkpoint — model edits complete
  - Ensure all model edits and lockstep sweeps are in place, ask the user if questions arise.

- [x] 13. Validation and completeness guards
  - [x] 13.1 Run Weaver resolve/check over `model/network/**`
    - **Property 11: The post-sweep registry resolves cleanly** (zero broken refs, zero validation errors).
    - On any broken reference or error, fix the affected Reference_Site(s) and re-run until zero/zero.
    - **Validates: Requirements 2.11, 12.1, 12.2, 12.3, 12.4**

  - [x] 13.2 Run the complete-token re-scan for surviving old names
    - **Property 1: No pre-rename identifier survives at any reference site**
    - Scan model YAML + `examples/*/README.md` + `docs/conventions.md` + `docs/naming-review.md`; assert a zero
      count for every old name. A non-zero count means incomplete — replace and re-scan to zero.
    - **Validates: Requirements 11.5, 11.6, 13.6**

  - [x] 13.3 Run the structured field-diff for name-only preservation
    - **Property 2: Renames are name-only / structure-preserving**
    - For each renamed definition, diff the pre/post YAML node and assert the only difference is the identifier
      (and mandated note re-pins).
    - **Validates: Requirements 1.16, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 4.2, 4.3, 4.5, 7.5, 7.6, 7.7, 7.8, 7.12**

  - [x] 13.4 Run the stability guard
    - **Property 10: All affected signals are at `development` stability**
    - Assert every signal affected by Requirements 1–11 is `development`; any other stability is a failure.
    - **Validates: Requirements 13.3, 13.5**

  - [x] 13.5 Run the non-over-reach / keep-inventory guard
    - **Property 3: Every name not in the rename set is unchanged (non-over-reach)**
    - Assert the full keep inventory unchanged: monotonic counters, `network.session.count`,
      `qos.queue.depth`/`.max` (two gauges, no current-vs-max selecting attribute — Requirement 6),
      `mac.*` keep items, acceptable snake_case leaves, already-dotted `.limit` attrs, per-domain `.state`
      leaves, `network.neighbor.*`, sub-entity `.id` keys, `interface.mtu` key.
    - Assert no deprecation residue exists for any old name (Property 9).
    - **Validates: Requirements 1.15, 1.17, 2.8, 2.9, 3.2, 6.1, 6.2, 6.3, 6.4, 7.10, 10.4, 10.5, 13.2**

- [x] 14. Final checkpoint — single coordinated landing
  - Ensure Weaver resolve/check, the token re-scan, the field-diff, the stability guard, and the keep-inventory
    guard all pass with zero errors; confirm every rename is present (no partial application). Ask the user if
    questions arise.

## Notes

- Tasks marked with `*` are optional verification/guard sub-tasks and can be skipped for a faster landing; the
  core edit tasks (unmarked) must all be applied for a valid registry.
- Every rename task edits the **definition site and all ref-sites together** (model `ref:`s + prose), because a
  half-applied rename leaves a dangling reference that Weaver rejects.
- The two combined targets (`network.l2.fdb.entry.count`, `network.l3.arpnd.entry.count`) are landed as single
  edits — no intermediate names — per the design's §4 ordering.
- The keep / do-not-change inventory is enforced only through read-only guard checks (tasks 3.2, 4.2, 6.5, 7.3,
  9.2, 10.1, 13.5); it is never an edit target.
- Property 8 is the one genuinely data-instance-quantified invariant and is the only property-based test; the
  remaining properties (1–7, 9–11) are exhaustive single-pass invariants over the finite rename set, verified by
  the Weaver resolve, the token re-scan, and the field-diff.
- This is a single coordinated landing at `development` stability with no deprecation aliases (Requirement 13).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "3.1", "5.1", "6.1", "6.2", "10.1", "11.1", "11.3"] },
    { "id": 2, "tasks": ["4.1", "6.3", "11.2"] },
    { "id": 3, "tasks": ["7.1"] },
    { "id": 4, "tasks": ["7.2"] },
    { "id": 5, "tasks": ["8.1"] },
    { "id": 6, "tasks": ["9.1"] },
    { "id": 7, "tasks": ["2.2", "3.2", "4.2", "5.2", "6.4", "6.5", "7.3", "8.2", "9.2"] },
    { "id": 8, "tasks": ["13.1", "13.2", "13.3", "13.4", "13.5"] }
  ]
}
```
