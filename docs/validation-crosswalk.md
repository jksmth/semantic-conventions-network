# Validation via a collector crosswalk (follow-up brief)

A plan for the highest-value next step the [roadmap](roadmap.md#the-central-risk-validation)
names: produce **real `network.*` telemetry from a real (virtual) device** and
machine-check it against this registry. This turns the model from a documented
paper exercise into something with at least one demonstrated producer, and closes
the gap between the prose mapping tables in [`examples/`](../examples/) and an
executable artifact.

This is a design brief. The first slice of it is now **built** and passing — a
two-router FRR lab, a declarative crosswalk, and a green `weaver registry
live-check` — under [`../validation/`](../validation/). The reasoning below is kept
so the remaining increments (a second source for reconciliation, events, flows) are
not re-litigated.

> **Status: MVP built.** `device + interface + an Established BGP neighbour`, mapped
> from real `vtysh json` and machine-checked: every emitted attribute and metric is
> registry-defined (zero non-registry names), only development-stability notes
> remain. See [`../validation/README.md`](../validation/README.md).

## Why this is the priority

Three review findings collapse into one fix:

- **No executable validation.** Today the only gate (`weaver_check.sh`) runs
  `weaver registry check` / `resolve` — it proves the registry is *well-formed and
  refs resolve*, nothing about whether real data maps cleanly. Every example is a
  prose README; there is no emitted telemetry anywhere in the repo.
- **Identity/reconciliation is asserted, not shown.** The model says an SNMP poller
  and a gNMI stream converge on one `network.device.id`; it has never been
  demonstrated.
- **The "paper exercise" critique.** Breadth was built ahead of instrumentation
  (by construction — OTel's own gate forbids stabilizing before instrumentation
  exists), so a single worked producer disproportionately raises credibility.

## The keystone tool: `weaver registry live-check`

Weaver can check **sample telemetry** against a registry, not just the registry
itself:

```
weaver registry live-check --registry model \
  --input-source file --input-format json  path/to/emitted.otlp.json
```

It ingests OTLP (file / stdin / live OTLP receiver) and reports attributes that are
missing, misspelled, wrong-typed, or off-convention. This is the gate the current
harness lacks. It upgrades CI from "the registry is well-formed" to "real telemetry
conforms to the registry."

> **Caveats.** (1) `live-check` is newer than the pinned `otel/weaver:v0.23.0`;
> bump and confirm flags before relying on it. (2) It checks **conformance, not
> semantic correctness** — it confirms an attribute exists and is well-typed, not
> that `ifOperStatus` was mapped to the *right* `oper.state` value. Pair the output
> against the example README mapping tables to cover that.

## Principle: decouple collection from mapping

Two stages, different lifetimes and tools. Do **not** fuse them.

```
containerlab (SR Linux / FRR / SONiC-VS)     # versioned topology + configs
        │  spin-up script
        ▼
snmpbulkwalk / gnmic get                     # capture once → committed fixtures
        │
        ▼
crosswalk/*.yaml  +  transforms/*            # declarative map + named transforms ← the IP
        │  engine
        ▼
*.otlp.json                                  # emitted telemetry, committed
        │
        ▼
weaver registry live-check                   # machine-checks output vs model     ← the gate
```

- **Collection** produces raw, structured, *replayable* captures. Solved by existing
  tools; keep it dumb and deterministic.
- **Mapping** turns a capture into `network.*` OTLP. This is the unsolved part, the
  real IP, and where the model gets validated.

Fusing them (e.g. leaning on Telegraf to both poll and shape) inherits that tool's
metrics-only worldview and fights the model's entity/event surface.

## Collection-layer reality

Nothing off-the-shelf emits this model in any of its three signals:

- OTel Collector **SNMP receiver** exists but is **alpha and metrics-only** — generic
  metrics from OID config, no entities/events/semconv.
- There is **no official OTel gNMI receiver**; gNMI is `gnmic` and Telegraf
  `inputs.gnmi`.

So the semconv mapping is custom regardless of poller. Capture choices:

- **SNMP** — `snmpbulkwalk` to a text dump; deterministic; `snmpsim` can replay a
  recorded walk for a live-ish CI target without the NOS.
- **gNMI** — `gnmic get`/`subscribe` to JSON (de-facto OpenConfig tool).
- **Telegraf** — fine *only* for the metric third; adds an impedance layer; not the
  backbone.

Output of this stage is committed fixtures (`srl-ams-01.snmpwalk.txt`,
`srl-ams-01.gnmi.json`) versioned next to the lab that produced them. CI never needs
the live device.

## The mapping is data, not bespoke code

Express the crosswalk as a **declarative mapping table** with a thin engine, plus a
small library of **named transforms** for the parts that need real logic.

Why declarative:

- The model is declarative YAML; the example README tables (OID → `network.*`,
  OpenConfig path → `network.*`) are *already* declarative — just prose. Promoting
  them to machine-readable data makes the docs the executable artifact, retiring the
  "prose rules nobody can lint" and "no executable validation" findings at once.
- A table is reviewable, diff-able, and language-portable: the engine can be Python
  now and Go later without touching the mapping.
- Mirrors how Weaver works (declarative registry + thin engine), idiomatic to where
  this project wants to live.

Sketch:

```yaml
# crosswalk/if-mib.yaml
- source: { type: snmp, oid: "1.3.6.1.2.1.2.2.1.7", table: ifEntry, index: ifIndex }
  target: { entity: network.interface, attr: network.interface.admin.state }
  transform: ifAdminStatus_to_admin_state
- source: { type: snmp, oid: "1.3.6.1.2.1.31.1.1.1.6" }   # ifHCInOctets
  target: { metric: network.interface.io, direction: receive }
```

### Where code is unavoidable (the named transforms)

These are the parts that prove the model works, so they deserve to be code, tested,
and clear:

- **Enum normalization** — `ifOperStatus` int → `up/down/...`; the normalized+native
  pairing (BGP `Established` → `up` + verbatim `native_state`).
- **Identity derivation** — the `network.device.id` source-precedence ladder;
  sub-entity identity `(device.id, interface.name)`.
- **Relationship synthesis** — foreign keys (`interface → device`,
  `neighbor → instance`) and `network.relationship.type` edges.

The table handles the boring ~80%; named transforms handle the meaningful ~20%.

## Language

Splits by what the artifact should become:

- **Validation harness now → Python.** `pysnmp`, JSON for gNMI, trivial OTLP-JSON
  emission, no perf concern, readable for reviewers. The no-brainer for the proof.
- **On-ramp to something OTel would ship → Go.** Every Collector
  receiver/processor/connector and OTTL is Go; a real "emit `network.*` semconv"
  component will be Go. (Rust only if extending **Weaver** itself.)
- The declarative-data approach dissolves the tension: mapping as data, engine in
  Python now, swap the engine to Go later — the IP (the crosswalk) carries over.

## Does the crosswalk generalize across source protocols?

Yes for one *family*; the others need an extra layer. The dividing line is the data
*shape*, not the protocol name.

**Family A — addressable polled state (the table works directly).** Fundamentally
"(path/key → typed value) with an optional multi-instance index." The `target` side
is identical; only addressing differs.

- **SNMP** — key = OID, index = table index (`ifIndex`).
- **gNMI / OpenConfig** — key = path with list keys
  (`/interfaces/interface[name=xe-0/0/0]/state/oper-status`).
- **TR-069 / TR-181 and TR-369/USP** — key = parameter path with instance numbers
  (`Device.Ethernet.Interface.{i}.Stats.BytesReceived`); a near-twin of gNMI.
- **NETCONF** — same YANG tree as gNMI, different encoding.

**Family B — records and events (needs an extractor first).** Not "poll a path" but
"parse a message/record and pull fields":

- **syslog / SNMP traps** → events (`network.state.changed`, `network.alarm`);
  source = trap OID + varbinds, or regex over text.
- **NetFlow / IPFIX / sFlow** → `network.flow` records; source = IPFIX IE id per
  field; the unit is a record, not a scalar.
- **CLI scraping** → needs TextFSM/regex to structure text before any mapping;
  hardest, lowest value.

Same philosophy (declarative descriptor + named transforms), but the descriptor must
reference an **extractor**, not just a key.

### Architectural consequence

Split so the model-facing half never changes:

```
source adapters (per protocol)        crosswalk (protocol-agnostic)
─────────────────────────────         ─────────────────────────────
SNMP walk      ─┐
gNMI get       ─┤
TR-069 params  ─┼──▶ normalized IR ──▶ target: network.* attr/metric/entity
NETCONF        ─┘    (key, value,        transform: named fn
                      index, type)
syslog/trap    ─┐
IPFIX record   ─┼──▶ extractor ────▶ (same target side)
CLI text       ─┘
```

- **Target side + transform library** = protocol-agnostic, reusable, the
  model-validation IP. Write once.
- **Source side** = small per-protocol adapters normalizing into a common
  intermediate representation (IR). Family A adapters trivial; Family B adapters
  carry an extractor.

### The docs already use the right layout

The example tables are **target-keyed rows with multiple source columns**:

```
| network.* | SNMP (MIB object) | OpenConfig path |
```

That *is* the generalized crosswalk shape — TR-069 is just another column.
Per-cell subtlety it already implies: the same target needs a **different transform
per source** (SNMP `ifOperStatus`=int `1`; OpenConfig oper-status=`"UP"`; TR-181
Status=`"Up"`), so the transform belongs to the (source, target) cell, not the
target. Author target-keyed (matches docs, shows model coverage); have the engine
build a source-keyed index at load (matches how a collector processes an incoming
walk).

## What to map first, and what else to mock

**First slice: `device` + `interface` + one BGP `neighbor`, off IF-MIB + a slice of
OpenConfig.** IF-MIB is the most universally agreed MIB (lowest mapping ambiguity,
highest payoff) and exercises the load-bearing parts at once: the `network.device.id`
identity contract, sub-entity scoping, admin/oper state planes, counters as metrics
(the cardinality firewall), and the `*.info` projection. One BGP neighbor adds the
normalized+native state table and the control-plane protocol key.

**Highest-value single move:** run the crosswalk **twice on the same device — SNMP
and gNMI — and show both land on the same `network.device.id` and
`(device.id, interface.name)`.** That *demonstrates* reconciliation (the
multi-observer rule) instead of asserting it, for roughly one extra mapping file.

**What else to mock — pick for model-surface coverage, not protocol count:**

| Add | Validates | Why unique |
|-----|-----------|------------|
| **syslog + SNMP traps** | the **events** third (`state.changed`, `alarm`) | nothing in SNMP/gNMI *polling* exercises the event envelopes |
| **IPFIX / NetFlow** | the **traffic-observation** domain + `observer`≠subject | the part resting on the unshipped OTel primitive — highest risk if left unproven |
| **TR-069 / TR-181** | the **CPE/access** examples (wifi-cpe, cpe-router) | proves the model isn't carrier-router-only and that Family A's "another column" claim holds |

SNMP + gNMI prove expressibility + reconciliation; traps prove events; IPFIX proves
flow/observer. Those cover all three signal types and both observer perspectives —
a stronger story than mapping five polling protocols.

## Proposed repo shape

```
validation/
  labs/                              # containerlab topologies + versioned configs
    srl-ams-01.clab.yml
  fixtures/                          # real captures, committed
    srl-ams-01.snmpwalk.txt
    srl-ams-01.gnmi.json
  crosswalk/                         # declarative mappings (the IP)
    if-mib.yaml
    bgp4-mib.yaml
  transforms/                        # named transforms (enum norm, identity, relations)
  engine/                            # thin applier (python now)
  expected/
    srl-ams-01.otlp.json             # emitted output, committed
  run.sh                             # capture → transform → weaver live-check
```

## Open decisions before building

1. **Commit to crosswalk-as-data**, not bespoke scripts — the difference between a
   one-off demo and an artifact the Networking WG could adopt.
2. **SNMP + gNMI on the same device** so the proof includes reconciliation, not just
   expressibility.
3. **Pin a Weaver version that ships `live-check`** and confirm the flags.
4. **Engine language**: Python for the proof; decide whether to skip straight to Go
   if the intent is a real Collector component.
5. **Free NOS choice**: SR Linux or FRR (fully open) to keep it frictionless; cEOS
   needs a free Arista account.

## Honest boundaries

- Family A (SNMP/gNMI/TR-069/NETCONF): one table, clean — the docs already prove the
  shape.
- Family B (syslog/traps, IPFIX): same philosophy, each needs an extractor; the
  flow/observer one is also where the *model* is least finished, so expect the model
  to push back, not just the tooling.
- CLI: possible, high-effort, low-validation-value — skip unless an example demands
  it.
- `live-check` proves conformance, not mapping correctness — the example tables
  remain the semantic check.

## See also

- [roadmap.md](roadmap.md#the-central-risk-validation) — the validation gate this
  serves.
- [prior-art.md](prior-art.md) — the crosswalk-as-adoption-lever framing.
- [examples/](../examples/) — the prose mapping tables this would make executable.
