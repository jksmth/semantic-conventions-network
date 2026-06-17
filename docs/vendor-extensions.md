# Extending the model: vendor-specific attributes

How to model vendor-specific (non-portable) network telemetry **without polluting
the vendor-neutral core**. If you are adding telemetry for one vendor's hardware or
NOS and it has no neutral equivalent, this is the page for you.

The pattern mirrors how OpenTelemetry's GenAI conventions handle provider-specific
detail (`openai.*`, `aws.bedrock.*`) on top of a generic `gen_ai.*` model, which is
itself the modern form of a long-standing SNMP discipline: model against the
standard MIB (IF-MIB, ENTITY-MIB) wherever possible, and hang proprietary objects
off the vendor's enterprise OID only when no standard object fits.

## The principle

> **Standard first; vendor only for the genuinely proprietary.** Anything that can be
> generalized belongs in core `network.*`. The vendor space exists only for concepts
> truly specific to one vendor's hardware/OS that cannot be expressed neutrally.

This is one rung of the [tagging ladder](entity-model.md#classification-the-tagging-ladder).
Pick the highest tier that fits:

1. **Defined core attribute** (closed enum / typed value) — known, shared, enumerable
   meaning, e.g. `network.interface.role`, `network.instance.type`. **Strongly preferred.**
2. **`<vendor>.*`** (top-level, e.g. `cisco.*`; product-qualified `cisco.cdp.*`) —
   proprietary, vendor-defined semantics, still statically authored and validated in the
   vendor's registry. **This page.**
3. **`network.<entity>.label.<key>`** (`template[string]`) — open-ended, operator-defined
   metadata with no shared schema, mirroring `k8s.*.label`.

The critical distinction between tiers 2 and 3: tier 2 is a **static namespace** —
`<vendor>` is fixed per registry and every attribute is fully defined, typed, and
documented. Tier 3 is a `template[string]` — the `<key>` is dynamic at runtime and
values are opaque passthrough. Do not use a label where a vendor attribute belongs (you
lose typing/validation), and do not mint vendor attributes for unbounded operator
metadata (you pollute the schema).

## The three building blocks

The GenAI conventions do three things this model copies:

1. **A discriminator attribute on the core signals.** GenAI uses `gen_ai.provider.name`.
   This model uses **`network.device.vendor.name`** (`cisco`, `juniper`, `nokia`,
   `arista`, …), normalized lowercase, paired with **`network.device.vendor.id`** = the
   vendor's **IANA Private Enterprise Number** (the PEN in `sysObjectID`) as a stable,
   unambiguous machine key.

2. **A vendor-namespaced attribute space.** GenAI uses top-level `openai.*`. This model
   uses the same top-level form, keyed by the discriminator: **`<vendor>.*`**,
   product-qualified where the vendor spans multiple domains (`cisco.cdp.*`,
   `cisco.iosxr.*`).

3. **Refinement of core signals, gated on the discriminator.** GenAI does not mint a
   parallel `openai.client.token.usage`; it reuses the generic
   `gen_ai.client.token.usage` and adds provider-gated attributes. This model does the
   same: attach a vendor attribute onto a core entity (a `ref` in the entity's
   description list) or as a vendor dimension on a core metric, present only when
   `network.device.vendor.name` matches.

## Why top-level `<vendor>.*` and not `network.vendor.<x>.*`

OpenTelemetry's **system-specific naming** rule (Stable) requires the namespace root to
**equal the discriminator value**: `db.system.name=cassandra` ↔ `cassandra.*`,
`gen_ai.provider.name=openai` ↔ `openai.*`. The discriminator here is
`network.device.vendor.name`, so the root is the vendor itself — `cisco.*`. An infix
form like `network.vendor.cisco.*` has root `network`, which violates the rule, so it is
not used.

This also dissolves the "multi-domain company" objection: OTel already namespaces
multi-domain vendors with a product-qualified token under the top-level root
(`aws.s3.*`, `aws.lambda.*`, `azure.cosmosdb.*`). A proprietary network protocol gets the
same treatment regardless of company breadth: `cisco.cdp.*`, `cisco.iosxr.*`.

## The contract a vendor package must follow

1. **Map to core first.** If a concept maps to a core `network.*` attribute or entity,
   use the core one. Do not redefine `network.interface.oper.state` as `cisco.if_state`.
2. **Namespace** all proprietary attributes under top-level **`<vendor>.*`**,
   product-qualified where needed, with the root equal to `network.device.vendor.name`.
3. **Attach, don't fork.** Add a vendor descriptive attribute to a core entity by
   re-opening it with an `entity_refinements` block and `ref`-ing the attribute into its
   description list (`requirement_level: opt_in`); add vendor dimensions to a core
   metric — rather than defining parallel entities. The core entity's identifying
   attributes MUST NOT change. (Use `ref`, not `extends`: in semconv, entities compose by
   `ref`; `extends` is for a signal group inheriting a base attribute group, a different
   job.)
4. **Gate on the discriminator.** Vendor attributes are expected only when
   `network.device.vendor.name` (and/or `network.device.vendor.id`) identifies that vendor.
5. **Stability `development`** until proven; promote only with real data.
6. **Generalize upward.** If two vendors model the same concept, propose it into core and
   deprecate the vendor-specific forms (the SNMP "standardize the enterprise object" path).

## Where vendor packages live (federation)

- A vendor (or the community) publishes a **separate Weaver registry** — e.g.
  `semantic-conventions-network-cisco` — that declares this core as a dependency by
  `schema_url`, exactly as this repo depends on upstream OTel. The core maintainers do
  not own or review vendor conventions.
- For reference/community mappings, an in-repo area at `model/<vendor>/` (e.g.
  `model/cisco/`) holds **non-normative**, illustrative definitions until a vendor adopts
  them.

## Worked example — CDP (Cisco Discovery Protocol)

CDP is Cisco's proprietary sibling of LLDP. Almost everything it carries has a
vendor-neutral home, so it is the model case for "map to core first, vendor-namespace
only the residue":

| CDP field (CISCO-CDP-MIB) | Where it lands |
|---|---|
| Device-ID | `network.neighbor.id` (core) |
| Port-ID | core remote port-id on `network.link` |
| Capabilities | core neighbour capability |
| Software version / Platform | core device system-description / model |
| Management address | `network.neighbor.address` (core) |
| Native VLAN | core interface native-VLAN |
| Power draw | `network.interface.poe.*` (core) |
| **VTP management domain** | **`cisco.cdp.vtp_domain`** (proprietary residue) |

Only the VTP management domain has no neutral equivalent, so it is the single attribute
that stays vendor-namespaced. The protocol value itself is normalized:
`network.neighbor.protocol=cdp` and `network.link.discovery.protocol=cdp` are
closed-enum **core** values (CDP is one discovery protocol among LLDP/CDP), not vendor
attributes.

The vendor attribute is defined in the vendor registry and attached to the core
`network.neighbor` entity through an `entity_refinements` block, so the vendor-neutral
core still resolves standalone:

```yaml
# model/cisco/registry.yaml
attributes:
- key: cisco.cdp.vtp_domain
  type: string
  stability: development
  brief: >
    The VTP (VLAN Trunking Protocol) management domain advertised by a CDP neighbour.
    Proprietary to Cisco; no vendor-neutral equivalent.

# Re-open the vendor-neutral core entity to attach the lone proprietary facet.
entity_refinements:
- id: cisco.network.neighbor
  ref: network.neighbor
  description:
  - ref: cisco.cdp.vtp_domain
    requirement_level: opt_in
```

The neighbour entity is still `network.neighbor` (identity unchanged); a Cisco device
reporting a CDP neighbour simply carries one extra opt-in descriptive attribute.

## Counter-example — EIGRP is *not* a vendor attribute

EIGRP looks proprietary but is **IETF RFC 7868** (with a second independent
implementation in FRRouting), so by the "standardize the enterprise object" rule it is
**core**, not vendor. Its internals are modelled as a core refinement gated on the
existing `network.neighbor.protocol=eigrp` discriminator, with no vendor namespace:

- per-neighbour timers/queue as core gauges `network.neighbor.eigrp.srtt` / `.rto` /
  `.queue.depth`;
- Stuck-In-Active as `network.protocol.errors` with `error.type=stuck_in_active`;
- EIGRP PDU types as values of `network.protocol.message.type`.

Recognizing EIGRP as a standard keeps it in core and reserves `cisco.*` for genuine
residue like `cisco.cdp.vtp_domain`. The rule that decides where a protocol's signals
live — generic neighbour counters vs a per-domain namespace vs a protocol-qualified
refinement — is in [conventions.md](conventions.md#protocol-counter-scoping).
