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

This documentation is written to help you **understand and extend** the model — not as a
design log. Each page explains a concept and the reasoning behind it so a contributor can
add a package, a vendor extension, or a crosswalk and stay consistent with the rest. If
you find something that reads as a private decision record rather than guidance for the
next reader, it is a bug in the docs.

## Read in this order

1. **[architecture.md](architecture.md)** — why this exists, the namespace
   layering (`system.*` / `hw.*` / `network.*`), the two modelling axes, the
   domain view, and governance. Start here.
2. **[entity-model.md](entity-model.md)** — the entity catalogue, identity rules,
   relationships and the relationship vocabulary, reconciliation, the
   attributes-vs-entities test, and the classification ladder (role / vendor / label).
3. **[conventions.md](conventions.md)** — the cross-cutting modelling patterns:
   state modelling, signal choice, the cardinality firewall, naming and instrument
   rules.

Then, depending on what you are doing:

4. **[prior-art.md](prior-art.md)** — how the model maps to SNMP MIBs, OpenConfig, TR-181,
   and IETF/BBF YANG, with entity/attribute **crosswalks**. Read this if you are
   translating existing telemetry into `network.*`.
5. **[vendor-extensions.md](vendor-extensions.md)** — how to add vendor-specific
   (`<vendor>.*`) attributes without polluting the neutral core. Read this if you are
   extending the model for one vendor.
6. **[roadmap.md](roadmap.md)** — what is in scope, what is deliberately out, what is
   planned, and the known open questions and limitations.
7. **[validation-crosswalk.md](validation-crosswalk.md)** — a follow-up brief on the
   top validation priority: producing real `network.*` telemetry from a (virtual)
   device via a declarative crosswalk and machine-checking it with
   `weaver registry live-check`. Read this if you are building the first worked
   producer.
8. **[examples/](../examples/)** — end-to-end, consumer-facing worked examples:
   "here is device X with config Y, here is how it maps to `network.*`, and here
   is the line-by-line mapping back to SNMP MIBs and OpenConfig paths."

## Repository layout

| Path | Contents |
|------|----------|
| `model/` | The authored conventions, one package per sub-namespace (`device`, `interface`, `neighbor`, `routing`, …). Composed by `model/manifest.yaml`. |
| `docs/` | This documentation set: architecture, entity model, conventions, prior-art/crosswalks, vendor extensions, and roadmap. |
| `examples/` | Worked, consumer-facing device walkthroughs with diagrams and protocol mappings. |

## Scope

The model separates three things that naive network schemas collapse into one
attribute bag:

- **Inventory** — what exists (devices, cards, optics, peers). Low cardinality →
  entities / resources.
- **State** — how it is doing right now (link up/down, BGP established, route
  counts, optical BER). Medium cardinality → metrics + transition events.
- **Traffic** — what is flowing (flows and the classified/dropped packets within
  them). Very high cardinality → records + bounded aggregate metrics.

It also makes the *observer* explicit: device self-telemetry, a passive flow
observer, and an active synthetic tester are three different perspectives, not one.
See [architecture.md](architecture.md) for the full treatment.
