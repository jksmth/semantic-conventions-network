# Native path — the same proof, built from OTel parts instead of an engine

This is a side-by-side prototype of the validation gate built the **OTel-native**
way, to answer one question from the architecture review: *is the hand-rolled
Python engine (`../engine/`) the right way to do this, or is it re-implementing
things the OpenTelemetry ecosystem already ships?*

It validates the **same Linux source** as `../crosswalk/linux.yaml`, against the
same `network.*` registry, and reaches the same verdict — with **no engine code**.

```
FRR lab (r1)
   |
   |  otelcol-contrib  (network_mode: container:netlab-r1, sees r1's interfaces)
   |    hostmetricsreceiver   — collect  (replaces collectors.py + adapters/linux.py)
   |    transformprocessor/OTTL — crosswalk (replaces crosswalk/linux.yaml + transforms.py + mapper.py + ir.py)
   |    otlpexporter          — emit real OTLP  (replaces the bespoke sample JSON)
   v
weaver registry live-check --input-source otlp   — conformance + verdict (replaces report.py)
        exit code != 0  iff any `violation`        — the "teeth", built in
```

## Run it

```bash
./run-native.sh          # boot lab, collect, map, live-check, print verdict
./run-native.sh --down   # also tear everything down afterwards
```

Requires Docker. Pulls `otel/weaver` and `otel/opentelemetry-collector-contrib`.

## What maps to what

| Concern | Python engine (`../`) | Native (here) |
|---|---|---|
| Collect | `collectors.py` + `adapters/linux.py` | `hostmetricsreceiver` (core component) |
| IR | `ir.py` | OTLP pdata (built in) |
| Crosswalk (data) | `crosswalk/linux.yaml` | `transformprocessor` OTTL in `otelcol-linux.yaml` |
| Transforms | `transforms.py` | OTTL `set()` / `delete_key()` |
| Generic mapper | `mapper.py` (124 lines) | — (the collector pipeline *is* the mapper) |
| Sample format | bespoke JSON over stdin | OTLP gRPC |
| Verdict / teeth | `report.py` | Weaver's non-zero-on-`violation` exit code |
| Custom pass/fail rule | Python in `report.py` | `policies/network_only.rego` (optional) |

The entire engine collapses into one collector config file plus Weaver's built-in
OTLP ingest. The mapping that mattered — `system.network.io` → `network.interface.io`,
`device` → `network.interface.name`, `direction` → `network.io.direction`, unit
normalization — is four OTTL lines you can read against the YAML crosswalk.

## Why this is a stronger proof than the Python path

- **It produces real OTLP.** The bytes Weaver checks are the exact bytes a real
  operator's collector emits. The Python path checks a private JSON dialect that
  only this repo produces, so a pass says less about real deployments.
- **The mapping is in the real mapping language.** Proving an OTTL crosswalk stays
  clean transfers directly to production pipelines and to the upstream semconv
  discussion; proving *our own DSL* stays clean does not.
- **The teeth are built in.** `live-check` exits non-zero on any `violation` — no
  custom verdict parser to keep correct, and project-specific rules can be added
  as Rego (`policies/network_only.rego`) that Weaver evaluates itself.

## Honest boundaries (specific to this prototype)

- **This is the Linux source only.** It's the one with a pure off-the-shelf
  receiver (`hostmetricsreceiver`), so it best demonstrates "no engine code."
- **FRR has no Collector receiver.** The native FRR equivalent would still need a
  *custom receiver* (or a small sidecar that emits OTLP) to parse `vtysh ... json`.
  That's an honest finding, not a gap in this prototype: it reinforces that the
  collection adapter is the part you genuinely own, while IR + mapping + verdict
  are not.
- **`hostmetrics` runs on-box**, in r1's network namespace — same on-box limitation
  the Python Linux source has. It is not the off-box SNMP/gNMI poll the brief
  ultimately wants. For that, the native path would swap `hostmetricsreceiver` for
  `snmpreceiver` (which exists) with the OTTL crosswalk and Weaver unchanged.
- **Resource modelling is coarse.** hostmetrics emits one Resource with the
  interface name as a *data-point* attribute (`network.interface.name`), not one
  Resource per interface. Fine for name/type/enum conformance (what `live-check`
  checks); a faithful `entity_associations` test is future work — the same caveat
  the Python path carries.
- **Reconciliation is not covered here.** `../engine/reconcile.py` (multi-observer
  identity convergence) has no OTel-native equivalent and remains the genuinely
  novel, worth-keeping piece.
- **Weaver flag/version skew.** `--inactivity-timeout` and `--advice-policies` are
  documented on `weaver` main; the published image may differ. The script stops
  the listener with `SIGHUP` (a documented stop condition) to stay version-robust.
  Check `weaver registry live-check --help` if a flag is rejected.
