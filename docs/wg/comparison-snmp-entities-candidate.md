# Comparison: SNMP-entities candidate model vs this model

> **Status:** Draft for review · **Created:** 2026-06-12 · **Scope:** a side-by-side
> read of a fellow WG member's candidate design against this registry.
> **Purpose:** record where the two independently-built models converge, where they
> genuinely diverge (and why), and what each one is missing — so the convergence is
> citable in the WG thread and the divergences feed our own action list.
> **Subject doc:** [`snmp-network-entities-otel.md`](snmp-network-entities-otel.md)
> (Matthieu Noirbusson's candidate, offered to
> [#3769](https://github.com/open-telemetry/semantic-conventions/issues/3769)).

Nothing here changes the model. Follow-up actions are listed in
[§6](#6-action-list); each is a separate piece of work.

---

## 1. The two docs are at different scopes

The single most important framing point, without which most "gaps" read as
oversights when they are deliberate scope choices.

| | Subject candidate | This model |
|---|---|---|
| **Layer** | The *shape* layer only: entity types, identity keys, relationship types | Full signal-bearing domain: entities **+** metrics **+** events **+** state modelling **+** observer axis **+** cardinality rules |
| **Source framing** | SNMP-discovered infrastructure (ENTITY-MIB / IF-MIB / IP-MIB / route table), first real-device validation upcoming | Collection-method-agnostic (SNMP, gNMI, NETCONF, streaming telemetry, IPFIX), 30+ packages authored |
| **Explicit non-goal** | Normalizing MIB-derived attributes/metrics ("the much larger effort") | — (that *is* the bulk of this model) |
| **Carrier** | Merged [entity-events spec](https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/entities/entity-events.md) `entity.state` events | Entities + `entity_associations` on metrics; entity-events as a forward-planning placeholder (DEC-139) |

The two compose rather than compete: his "normalized MIB attributes become the
descriptive attributes of these entities" is precisely the surface this model
authors. The interesting signal is the **overlap** — identity and relationships —
because that is where independent convergence (or divergence) carries weight for the
group.

---

## 2. Where the two models converge

These are worth surfacing in the thread: two (in places three) independently-built
implementations reaching the same conclusion is a standardization-readiness signal.

| Topic | Convergence | Our anchor |
|---|---|---|
| **Interface identity = `ifName`, not `ifIndex`** | His core argument (RFC 2863 only guarantees `ifIndex` stability *between re-inits*, so it fails the immutable-identity bar; `ifName` is the operator-facing handle; `ifIndex` stays descriptive for joining raw rows) is identical to our reasoning. | entity-model.md interface identity ("`ifIndex` … not reliably stable across reboots … keep it descriptive") |
| **Collection-method-agnostic `network.*`** | "Infrastructure discovered/observed from outside, regardless of how reached (SNMP, streaming telemetry, flow records)." | architecture.md ("what *is* this element … regardless of who collected it or how") |
| **Core topology relationship vocabulary** | His `connected_to` / `bound_to` / `has_interface` (+ ElastiFlow's `connected to` / `binds to` / `contained by`) map onto our `connected_to` / `member_of` / `contains`. A **three-way** convergence. | `network.relationship.type` enum (entity_events/registry.yaml) |
| **Stable, immutable identity; never a mutable value** | Both bar PID / DHCP-leased IP / transport port from identity; those are descriptive. | entity-model.md identifier strategy ("Producer-assigned, **stable**, opaque … Survives hostname/IP/config change") |
| **`system.network.*` vs `network.*` is a host-self vs observed-other split** | His one-liner ("a host observing itself" vs "infrastructure observed from outside"). | architecture.md namespace layering (same boundary, more prose) |

The interface-identity convergence is the strongest single item: he reached our
*newest* position (D7, not yet applied) independently and from the same RFC 2863
reading. That promotes D7 from "defensible" to "cross-implementation-validated."

---

## 3. Where the two models genuinely diverge

These are real design forks, not scope artifacts. Each needs a stated position from
us (most already have one implicitly).

### 3.1 Identity derivation — and why upstream already settles it

The candidate raises a real question we had under-specified: *how* does a producer
derive `network.device.id`, and how do independent observers converge on one entity?
Its answer is a **deterministic, observer-independent** id derived from device data
via a precedence ladder (strongest available key wins: chassis serial → an
SNMP-agent engine id → chassis/LLDP MAC → hostname → management IP), with the chosen
key's **source encoded as a prefix in the value** (e.g. `serial:…`, `name:…`,
`mgmt:…`) so two observers cannot collide across sources. Our model, by contrast,
treats `network.device.id` as producer-assigned, stable, and **opaque**, and
explicitly puts derivation/reconciliation out of scope ("an operator/backend
concern").

Rather than pick between these, we checked what upstream already prescribes — and it
is decisive. The OTel
[Entity Data Model](https://opentelemetry.io/docs/specs/otel/entities/data-model/)
and the
[`host.id`](https://opentelemetry.io/docs/specs/semconv/resource/host/) convention
together answer every part of this, and **neither uses an in-value prefix.**

**What the Entity Data Model says (paraphrased; rephrased for licensing):**

1. **Identity is a `map<string,value>`, not a single string.** An entity ID "must
   contain at least one attribute" and MUST NOT change for the entity's lifetime.
   Multi-attribute identity is the *native* mechanism (their example: a process is
   `process.pid` + `process.start_time`).
2. **Minimally Sufficient Identity** — include the smallest attribute set that
   uniquely identifies; adding more is a stated violation.
3. **Repeatable Identity** — identifying values SHOULD be repeatably obtainable by
   *any* observer (the device itself, a Collector on the host, or another system).
4. **Multi-observer rule** — two observers reporting the same entity MUST supply
   identical identifying values; an observer that cannot reliably obtain an
   identifying attribute **MUST NOT emit that entity type** — it delegates to the
   observer that can (the source of truth), or emits a *different* entity type whose
   identity it can populate.
5. **Key-naming** — identifying attribute *keys* take the entity type as a prefix
   (`k8s.node.uid`) to avoid cross-type collision.

**What `host.id` does** — it is the direct analogue of `network.device.id` (a single
opaque identifier for an infrastructure node) and it resolves the derivation question
exactly the way we should: **one opaque key whose value carries no prefix, plus a
documented table of sources by context.** Cloud hosts use the provider-assigned
`instance_id` (allocation); bare-metal uses `machine-id` with an OS-specific
precedence (Linux `/etc/machine-id` → fallback `/var/lib/dbus/machine-id`; macOS
`IOPlatformUUID`; Windows `MachineGuid`). The published example value is a bare hash
(`fdbf79e8af94cb7f9e8df36789187052`), **not** `machineid:fdbf…`.

**This settles the prefix question.** The prefix exists to keep a single flat
string-space collision-free across sources — but OTel identity is *not* a single flat
string-space. Cross-**type** collision is handled by the key name
(`network.device.id` vs `network.interface.id`); "which source produced the value" is
handled by a **documented source precedence** in prose (the `host.id` table), leaving
the value opaque; and if one key is genuinely insufficient, the spec's answer is to
add a **second identifying attribute** (Minimally Sufficient Identity), never to
encode structure into one value. So the prefix is non-idiomatic on all three counts,
and `host.id` is the precedent that proves it.

**The precedence ladder, though, is worth keeping — as documentation.** A per-device-
class source precedence (serial for sealed ONT/CPE/AP units; assigned id or hostname
for managed router/switch/OLT; chassis MAC; management IP only as a last resort)
is *exactly* the `host.id` OS-table pattern and answers the operator's real question
("what do I populate this with?"). It belongs in prose with an opaque value, not in a
prefix.

> **The shared-address hazard still applies and gets sharper under the spec.** Our
> reconciliation rule already bars a deliberately-shared address (anycast GW,
> MLAG/anycast VTEP, VRRP/HSRP virtual IP/MAC, Anycast-RP loopback) from being an
> identity key. The multi-observer rule reinforces this: a MAC/IP-only observer that
> *cannot* obtain a stable per-device key MUST NOT emit a half-identified
> `network.device` at all — it defers to the SNMP/gNMI source of truth, or models
> what it actually sees (an address/neighbour) as its own entity type. That is a
> cleaner discipline than degrading down a ladder to a weak, collision-prone rung.

→ action **A2** (now: align to the `host.id` pattern + adopt the spec's identity
rules; reject the in-value prefix).

### 3.2 Routes and addresses as first-class entities

He promotes `network.route` and `network.address` to entities, driven by his "a
relationship that needs attributes is an entity in disguise" heuristic (a route has
a next-hop and a metric; those are entity facts, not edge facts).

- **Routes — we deliberately do the opposite.** routing/registry.yaml models routes
  as a **count** ("a full Internet table is ~1M routes"), bucketed by
  `network.routing.ecmp.width`, "NEVER … a per-prefix series." **But the precise
  objection is narrower than "cardinality," and getting it right matters because his
  `network.route` is an *entity* emitted via `entity.state` events, not a metric
  dimension.** Our cardinality firewall is a rule about *metric time series* (a
  per-prefix metric label = ~1M resident series per device); it does **not** bar
  high cardinality on the records/events rail, where his route-as-entity actually
  sits. So routes-as-entities does **not** breach the firewall, and we must not
  defend routes-as-count on cardinality grounds against an events-based proposal —
  that argument doesn't apply to records. The real objections are two others:
  (a) **entity vs observation** — our entity-model.md "Not entities" list already
  holds that route prefixes are *data, not durable entities* (a route is closer to a
  flow/observation than to a device with a lifecycle); and (b) **emission volume /
  consumer-graph cost** — 1M `entity.state` events per device, re-emitted on
  `report.interval` and on every BGP update, across thousands of devices, is a real
  throughput and temporal-graph-size problem. Both are stronger than, and distinct
  from, the cardinality firewall (which stays exactly as-is for the per-prefix
  *metric*, still forbidden). → action **A4**.
- **Address-as-shared-node — the more interesting idea, and a genuine gap for us.**
  His `network.address` `{ip}` node lets host-side and SNMP-side topology **join by
  exact identity** with no heuristic (a host's default-gateway route and a polled
  device's interface IP reference the *same* node). We have **no equivalent**. It
  collides with our anycast/virtual hazard (which his doc never addresses — a real
  flaw in his shared-node idea), but a **bounded** join-node gated by
  `network.address.role` could capture the benefit safely. → action **A5**.

### 3.3 Edge attributes — "no attributes on edges" vs `network.link` as an attributed edge entity

He **bans** attributes on edges and retired three device-level relation types
(`adjacent_to`, `routes_via`, `forwards_to`) because each needed edge attributes
(local/remote port, destination, metric) — folding them into port-to-port
`connected_to` plus route/address entities.

We keep `network.link` as a **first-class edge entity** carrying `type` /
`topology` / `state` / `discovery.protocol`. **We actually agree with his
heuristic** — `network.link` *is* "an edge promoted to an entity because it has
attributes and a lifecycle." But our `network.relationship.type` enum still carries
`connected_to` **and** `adjacent_to` **and** `peers_with`, where he collapsed to
`connected_to` + a neighbour entity. His retirement argument deserves an explicit
answer: are `adjacent_to` / `peers_with` carrying their weight, or should
control-plane adjacency be solely a `network.neighbor` entity reference with the
edge type folded? → action **A6**.

### 3.4 The `system.network.*` / `network.*` boundary statement

His one-liner is crisper than our prose, **but his split omits `hw.network.*`
entirely** — he has no physical-FRU-health layer. Our three-way split
(`system.network.*` host-stack / `hw.network.*` FRU health / `network.interface.*`
forwarding entity) is more complete. We should adopt his clean headline *over* our
nuance, not instead of it. Directly useful for thread point #1, which asks for this
boundary. → action **A3**.

---

## 4. What each model is missing

### 4.1 In his model (this model has)

- **The observer axis** — passive observer vs active tester, `source.*` /
  `destination.*` / `network.observer.*`. His model is single-perspective
  (a poller looking at devices).
- **`hw.network.*` physical-FRU health** — no hardware-health layer at all.
- **The point-to-multipoint / shared-medium primitive** — his `connected_to` is
  strictly two-ended port-to-port; PON ODN trees, WiFi BSS, PtMP sectors, DOCSIS MAC
  domains do not fit. Our `network.link.topology` (point_to_point /
  point_to_multipoint / broadcast / nbma, RFC 2328 / 6845) handles the 1:N case.
- **The anycast / virtual reconciliation hazard** (§3.1).
- **The three orthogonal state axes** — admin (intent) / oper (capability) / health
  (`hw.state`); his single `oper.state` collapses them.
- **All metric / event / state-transition / cardinality modelling.**

### 4.2 In this model (his model has, or states better)

- **A concrete recommended identity-derivation precedence** — we punt on derivation
  entirely; the candidate at least supplies an explicit precedence. The
  upstream-aligned form of this (a documented source table, opaque value, no prefix)
  is the genuinely useful import (§3.1).
- **The address-as-join-node** for cross-plane (host ↔ SNMP) convergence (§3.2).
- **An *explicitly stated* attributes-vs-entities design rule** — "a relationship
  that needs attributes is an entity in disguise." We *apply* it (network.link;
  routes-as-count; VLAN / LAG / VRF are all entities) but never write it down. He
  hands us the heuristic **and** the hard test cases (VLANs, LAGs, VRFs) — which our
  model already passes, so we should say so. → action **A4**.

---

## 5. Net assessment

The two models are complementary and largely aligned on the contested fundamentals
(interface identity, relationship vocabulary, observed-from-outside scope). His doc
is a focused, well-argued **shape layer** for the SNMP discovery plane; ours is the
**superset** that also carries metrics, events, the observer axis, and the
hardware-health and shared-medium nuance his single-perspective SNMP framing does
not reach. The genuinely new ideas we should harvest are a **documented identity
source-precedence** (in the upstream `host.id` style — opaque value, no prefix) and
the **address-as-join-node**; the genuine divergence we should defend is
**routes-as-count vs routes-as-entities** — but on the *right* grounds (route is
an observation, not a durable entity, plus the emission-volume cost of 1M
`entity.state` events per device), not on cardinality, since route-as-entity
rides the records/events rail the cardinality firewall does not govern. The "no
attributes on edges" discipline is a useful lens to re-audit our relationship enum
against, even though our `network.link`-as-entity choice already honours its spirit.

---

## 6. Action list

| ID | Action | Output | Priority |
|---|---|---|---|
| **A1** | This comparison note (WG-facing) | `docs/wg/comparison-snmp-entities-candidate.md` | done |
| **A2** | Align `network.device.id` to the upstream `host.id` pattern: keep the value **opaque/unprefixed**, add a documented **source-precedence table** by device class, and adopt the Entity Data Model identity rules (Minimally Sufficient, Repeatable, multi-observer "can't identify → don't emit that type"); reject the in-value prefix as non-idiomatic | edit `entity-model.md`, `model/network/device/registry.yaml` (note only) | High |
| **A3** | Add the crisp `system.network.*` vs `network.*` headline one-liner, keeping the `hw.network.*` detail underneath; cite thread point #1 | edit `architecture.md` | High |
| **A4** | State the attributes-vs-entities heuristic explicitly; name `network.link` and routes-as-count as worked cases; confirm VLAN/LAG/VRF pass; add the route-as-entity rebuttal to the routing banner **on entity-vs-observation + emission-volume grounds, not cardinality** | edit `conventions.md`, `model/network/routing/registry.yaml` | Medium |
| **A5** | Evaluate a **bounded** `network.address` join-node — cross-plane-convergence benefit vs cardinality firewall vs anycast hazard | decision scratch (no implementation yet) | Medium |
| **A6** | Re-audit `network.relationship.type` against his "no attributes on edges" / retirement argument — keep or fold `adjacent_to` / `peers_with` | edit entity-events design notes | Medium |

All targets are `development` stability — no deprecation cycle — but A2–A4 touch
reviewed docs, so they should land as deliberate, separately-reviewed edits.
