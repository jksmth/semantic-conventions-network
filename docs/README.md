# Documentation

OpenTelemetry semantic conventions for network infrastructure — devices,
interfaces, links, protocols, optics, flows, and active measurements.

This is a federated [Weaver](https://github.com/open-telemetry/weaver) extension
registry that depends on the upstream
[OpenTelemetry Semantic Conventions](https://github.com/open-telemetry/semantic-conventions)
and adds a structured `network.*` domain on top of them. It is modelled after
[semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai):
the canonical definitions live outside the core repo and are composed by
`schema_url`.

**Status:** Development · **Schema domain:** `schemas.seconv.network`

## Read in this order

1. **[architecture.md](architecture.md)** — why this exists, the namespace
   layering (`system.*` / `hw.*` / `network.*`), the two modelling axes, and the
   domain view. Start here.
2. **[entity-model.md](entity-model.md)** — the entity catalogue, identity rules,
   relationships, reconciliation, and the classification ladder (role / vendor /
   label).
3. **[conventions.md](conventions.md)** — the cross-cutting modelling patterns:
   state modelling, signal choice, the cardinality firewall, and naming rules.
4. **[examples/](../examples/)** — end-to-end, consumer-facing worked examples:
   "here is device X with config Y, here is how it maps to `network.*`, and here
   is the line-by-line mapping back to SNMP MIBs and OpenConfig paths."

## Repository layout

| Path | Contents |
|------|----------|
| `model/` | The authored conventions, one package per sub-namespace (`device`, `interface`, `neighbor`, `routing`, …). Composed by `model/manifest.yaml`. |
| `docs/` | This documentation set (architecture, entity model, conventions). |
| `examples/` | Worked, consumer-facing device walkthroughs with diagrams and protocol mappings. |

## Scope

The model separates three things that naive network schemas collapse into one
attribute bag:

- **Inventory** — what exists (devices, cards, optics, peers). Low cardinality →
  entities / resources.
- **State** — how it is doing right now (link up/down, BGP established, route
  counts, optical BER). Medium cardinality → metrics + transition events.
- **Traffic** — what is flowing (flows, sampled packets). Very high cardinality →
  records + bounded aggregate metrics.

It also makes the *observer* explicit: device self-telemetry, a passive flow
observer, and an active synthetic tester are three different perspectives, not one.
See [architecture.md](architecture.md) for the full treatment.
