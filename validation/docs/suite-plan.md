# Validation suite — restructure plan (the "production-ready" harness)

Status: **proposed / not yet started.** This is the design we converged on for
turning the current pile of bespoke `native-*` lanes into a config-driven,
CI-able test suite. It supersedes the ad-hoc structure described in
[`realism-roadmap.md`](realism-roadmap.md) (which remains the record of *what has
been proven*; this plan is *how we package and grow it*).

## Why

The suite has proven its thesis — *`network.*` is collection-method- and
vendor-agnostic* — thoroughly, but on a narrow slice (interface IO + oper status
+ a state-change event, ~2% of the registry) across 11 lanes. The thesis axis is
near-saturated; the cost of every new lane is not.

Concretely, `run-srl.sh` and `run-cisco.sh` are ~95% byte-identical (they differ
only in lab dir, target IP, container prefix, network name, and banner text), and
the verdict-parsing Python is copy-pasted into each lane. The `oper.status` enum
ladder and the `resource:` device-identity block are duplicated across every
`otelcol-*.yaml`. That duplication is a tax on **all** future work — more vendors,
more model scope (BGP/ISIS/EVPN), more transports. Paying it down is the
multiplier that makes everything else cheap.

The bar: this restructure must itself *prove something*, not just DRY for its own
sake. Each move below demonstrates a model claim.

## The core idea — three layers

Every mapping today tangles three different kinds of thing. Separating them is the
whole design:

| Layer | What it is | Varies by | Who authors it | Where it lives |
|---|---|---|---|---|
| **1 — model-side** | target names, units, instrument shapes, **enum value sets** | the registry only | generated from `model/` | `contracts/` |
| **2 — source-side** | which OID / YANG path / syslog regex carries the value | transport (+ vendor) | human / vendor | `crosswalks/` |
| **3 — device/topology** | `network.device.id`, vendor, os, target address, lab file | the deployment | a per-test manifest | `scenarios/` |

The "config explosion" fear is really layers 1 and 3 being **duplicated per lane**
while only layer 2 legitimately varies per transport. The fix: author each once,
compose them per scenario.

- Layer 1 is **derivable from the registry** — the `oper.state` enum ladder in
  `native-srl/otelcol-srl.yaml` is literally the registry enum, hand-copied. That
  is the C seam (see below).
- Layer 2 is the only irreducibly source-specific knowledge.
- Layer 3 is pure data — it belongs in a manifest, not in YAML processor blocks.

## Decisions locked

### Mapping surface: collector config (OTTL) is primary; code is the fallback

The collector config **is the production artifact**. A passing OTTL lane validates
*the thing an operator would actually deploy*, not a paraphrase in a bespoke DSL.
So OTTL/collector config is the primary mapping surface. The custom-code path
(`collectors/`, today's `engine/` + the NETCONF adapter) is reserved for
transports with **no upstream OTel receiver** (NETCONF now; SNMP traps later). We
do **not** grow a parallel code DSL to cover what OTTL already covers — that would
be two sources of truth for one claim.

### Two-plane validation gate (lean on Rego — both planes)

Weaver has two distinct policy planes. We use only (a sliver of) one today. The
suite gate becomes both, in order:

1. **Model plane** — `weaver registry check -r ./model --policy policies/registry`
   (Rego package `after_resolution`, input = the resolved registry). Validates
   *"the right thing is **defined** in the model"*: naming, stability, required
   fields, no orphan attributes. **This repo has never policy-checked `model/`.**
   New capability.
2. **Telemetry plane** — `weaver registry live-check --advice-policies policies/live`
   (package `live_check_advice`, input = each sample). Validates *"the right thing
   **ends up in** the telemetry"*: cross-field invariants the built-ins can't
   express, e.g. an `oper.status` datapoint of `1` must carry an
   `oper.state` from the registry enum; every `network.interface` must carry a
   `network.device.id`; `io.direction ∈ {receive, transmit}`. This closes the
   README's own caveat — *"live-check proves conformance, not semantic
   correctness."* We have one rule (`network_only.rego`) today; grow this.

Policies are themselves tested (`policies_test/`, fixture inputs + expected
findings), mirroring upstream `open-telemetry/semantic-conventions`.

### Offline — two fidelities, made first-class

"Offline" is what makes this a CI gate rather than a lab demo (containerlab needs
privilege/Rosetta/vendor images and is flaky — the run scripts literally retry and
warn). It is **not one thing**:

```
device → [receiver] → [OTTL crosswalk] → OTLP(network.*) → weaver live-check
         └ capture P0: raw source ┘       └ capture P1: transformed samples ┘
```

| Mode | What it replays | What it proves | Cost |
|---|---|---|---|
| **live** | nothing — real NOS | realism (OIDs/paths exist & carry what we claim); also the **source of captures** | privilege, Rosetta, vendor images; flaky |
| **replay P0** | raw source → the *same collector config* via a trivial feeder/sim | crosswalk **and** model, deterministically, no NOS | OTLP-in free; SNMP via snmpsim; gNMI a small sim |
| **replay P1** | committed `network.*` golden samples → `live-check` stdin | registry/model conformance (not the crosswalk) | free, universal, instant (already done in `engine/`) |

Plan: every scenario declares the modes it supports. Implement **P1 first**
(free, universal CI coverage) → **P0 per-transport** (start with OTLP-in lanes
that need no simulator) → keep **live** as the realism proof and capture source.

Payoff for "plug in real hardware": point at a physical switch once, `--capture`
its raw source, and that device's telemetry becomes a permanent CI regression
fixture that re-runs forever **without the device**.

### Real hardware "plug it in" — separate acquisition from collection

The harness splits *target acquisition* from *collection*. A scenario's `target`
is either:

```yaml
target: { lab: srl.clab.yml, address: 172.22.22.11, credentials: ... }  # boot a container
target: { external: true, address: 10.0.0.5:161, credentials: ... }     # a real switch already on the net
```

A physical switch is then just a manifest with **no deploy step and a routable
address** — layers 1 and 2 (collector config + crosswalk) are identical. If
plugging in real hardware needs zero change to the mapping, vendor/transport
agnosticism is demonstrated more convincingly than any container lab can.

### Weaver templating (phase "C") — deferred, but the structure is shaped for it

C generates layer-1 `contracts/` (and the layer-1 `policies/live` enum-membership
rules) **from the registry**, so they cannot drift from `model/`. We defer
*building* C but make it a content-swap, not a refactor:

- `contracts/` is a separate dir, organized **per registry group/signal** (one
  file per metric/event group) so a template maps 1:1, with a
  "generated — do not edit" header.
- An **assemble step** in `harness/` joins `contracts/` + `crosswalks/` into the
  final collector config (today via otelcol multi-`--config` merge — supported, no
  custom code). When C lands, only the *producer* of `contracts/` changes.
- **Trigger:** the first model domain with a registry-defined enum — **BGP
  neighbor state** is the natural first consumer. Build the template against that
  real domain, not speculatively. C is expected to follow this restructure
  closely.
- C and the policy plane are the **same machinery**: weaver templating emits both
  the mapping scaffolding and the assertion rules. "Generate-and-diff in CI"
  (commit generated artifacts; CI fails on drift) keeps them honest.

## Naming

From two vocabularies that actually fit: testing (case, harness, fixture) and the
domain (model, crosswalk, device).

| Concept | Name | Rationale |
|---|---|---|
| one runnable validation (layer-3 manifest) | `scenarios/` | a whole observed situation; "lane" was project history |
| shared lifecycle / two-plane gate | `harness/` | standard test term; "engine" was overloaded |
| authored source→`network.*` bindings (layer 2) | `crosswalks/` | term of art, already in `docs/` |
| registry-derived invariants (layer 1) | `contracts/` | "what the data must satisfy, from the model"; the C seam |
| model-plane Rego (validates `model/`) | `policies/registry/` | matches upstream semconv convention |
| telemetry-plane Rego (validates samples) | `policies/live/` | the teeth beyond name/type |
| policy unit tests | `policies_test/` | mirrors upstream |
| custom collection (no OTel receiver) | `collectors/` | says what it is |
| captured data for replay | `captures/` | provenance: raw P0 snapshots + golden P1 samples |
| containerlab topologies | `labs/` | keep — standard, accurate |
| pinned tool versions | `versions.env` | pin Weaver (we use `:latest` today) |
| retired bespoke lanes (transitional) | `_archive/` | kept visible during migration, then deleted |

## Target structure

```
validation/
  scenarios/            # thin per-test manifests: device/topology + transport + signal + modes + expected verdict
  harness/              # gate: (1) registry check+policies on model/, (2) per-scenario collect → live-check+policies → verdict
  crosswalks/           # authored source→network.* bindings (layer 2)
    snmp/if-mib.yaml
    gnmi/openconfig-interfaces.yaml
  contracts/            # registry-derived invariants (layer 1) — hand-written now, weaver-generated at C
    metrics/network.interface.io.yaml
    metrics/network.interface.oper.status.yaml
  policies/
    registry/           # after_resolution — validates model/ itself (NEW for this repo)
    live/               # live_check_advice — semantic invariants on telemetry (grow this)
  policies_test/        # fixture inputs + expected findings
  collectors/           # custom collection for no-receiver transports (NETCONF, future traps)
  captures/             # raw-source snapshots (P0) + golden samples (P1)
  labs/   images/   docs/
  versions.env          # pinned WEAVER_VERSION (+ other tool pins)
  _archive/             # the old native-* lanes, kept for reference during migration
```

The `scenario` manifest carries layer-3 facts (device id/vendor/os), the `target`
block (`lab:` vs `external:`), the transport, which `contracts`/`crosswalks` to
assemble, and `modes: [live, replay]`.

## Tricks borrowed from upstream OTel repos

Evidenced in [`semantic-conventions-genai`](https://github.com/open-telemetry/semantic-conventions-genai)
and [`semantic-conventions`](https://github.com/open-telemetry/semantic-conventions):

- **Pin Weaver** in `versions.env`, run as the `otel/weaver:$(VERSION)` container
  (we use `:latest` — unpinned gate can move under us).
- **`policies/` + `policies_test/`** — write *and test* policies (fixture inputs,
  expected findings).
- **`schema-snapshot`** — `weaver registry generate ... yaml ./schema-snapshot`, a
  committed render of the resolved registry so **PR diffs show model changes**.
- **`registry check` as the first gate** — model well-formed → then `live-check`.
- **`--baseline-registry`** breaking-change detection as `network.*` grows.
- **Generate-and-diff in CI** — commit generated artifacts; CI fails on drift
  (the mechanism that makes C safe).

Tangent (future axis, parked): [`opentelemetry-ebpf-instrumentation`](https://github.com/open-telemetry/opentelemetry-ebpf-instrumentation)
is a telemetry *producer* — eBPF is a possible host-level "real source" lane with
no NOS at all.

## Phasing

**Phase 0 — freeze & scaffold (first slice).**
- `git tag validation-v1` (history reference).
- Create `_archive/`, move the bespoke `native-*` lanes + old top-level
  `run.sh`/MVP into it; keep `labs/`, `images/`, `docs/` at top level.
- Add `versions.env` and pin `WEAVER_VERSION`.
- Scaffold `harness/` (acquire → collect → assemble → gate → verdict) and the
  `scenario` manifest schema.

**Phase 1 — reference port.**
- Port **`srl-snmp`** onto the harness: one scenario manifest + the SNMP crosswalk
  fragment + interface contracts.
- Prove **live** and **P1-replay** both reproduce the existing PASS, and a first
  `weaver registry check` of `model/` goes green.

**Phase 2 — consolidate SNMP, prove "source = data" structurally.**
- Migrate `native-snmp` and `native-cisco` onto the **same** shared SNMP crosswalk
  + thin manifests. The byte-identical-crosswalk claim becomes structurally
  enforced instead of asserted in a comment. Retire those `_archive/` lanes.

**Phase 3 — remaining transports & signals.**
- Port gNMI, NETCONF (via `collectors/`), syslog + gNMI events, and the
  reconciliation/topology checks onto the harness. Add P0 replay where a cheap
  feeder/sim exists (OTLP-in first). Empty and delete `_archive/`.

**Phase 4 — grow the policy plane.**
- Add `policies/registry` model-hygiene rules and `policies/live` semantic
  invariants, with `policies_test/`. Add `schema-snapshot` + breaking-change
  baseline.

**Phase C — weaver-generate layer 1 (next, triggered by BGP).**
- When adding the first registry-enum domain (BGP neighbor state), build the
  weaver template that generates `contracts/` and the enum-membership
  `policies/live` rules from `model/`; wire generate-and-diff into CI.

## Acceptance test for the restructure

Each lane migration is "done" only when the new harness makes the same device
produce the **same verdict the old lane produced** (live and P1-replay). The
suite validating itself is the safety net for its own refactor.
