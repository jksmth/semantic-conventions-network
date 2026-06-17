# Events Lane B (push) — gNMI on-change flap → `network.state.changed`

The push counterpart to `../native-events` (syslog). A port flap on SR Linux is
captured as a **gNMI `on-change` subscription** the instant it happens, and
validated as the same registry event — but sub-second, not best-effort syslog.

```
SR Linux (flap ethernet-1/1)
   |  gNMI on-change push: /interface[name=*]/oper-state -> "down"/"up"
   v
gnmic  (file output, split-events: one JSON object per line)   <- gnmic OTLP is metrics-only,
   |   /shared/events.jsonl                                       so events ride the file path
   v
otelcol-contrib
   filelogreceiver   — tail the file, json_parser
   transform / OTTL  — -> network.state.changed event + attributes
   otlpexporter      — OTLP logs
   v
weaver registry live-check   — validates the EVENT against the registry
```

## Run it

```bash
./run-events-gnmi.sh          # deploy SR Linux (if needed), flap, validate the event
./run-events-gnmi.sh --down   # destroy the SR Linux lab afterwards
```

Verified result:

```
samples: 32  {resource: 4, attribute: 24, log: 4}
registry events:    {network.state.changed: 4}
advisories: 40  by-level={information: 12, improvement: 28}
non-registry names: none
PASS: the gNMI on-change flap was validated as a registry-defined
      network.state.changed event — a sub-second push, not a poll.
```

## Why this lane (vs the syslog lane)

- **Push, sub-second, structured.** `on-change` emits the transition the moment
  `oper-state` flips — no polling interval, no log-line regex. The value arrives
  typed (`"down"`/`"up"`) from the YANG tree, not parsed out of free text.
- **Same event, different source.** It produces the identical
  `network.state.changed` event as `../native-events`, so the model's event shape is
  now validated from **two independent event transports** (syslog and gNMI) — the
  events-side echo of the metrics-side three-transport convergence.

## The bridge: why a file, and why it's still "no glue code"

gnmic's OTLP output is **metrics-only**, so a state transition (an event) can't go
straight out as an OTLP log. The bridge is two upstream features, no custom code:

- gnmic `file` output with **`split-events: true`** writes one JSON object per line
  (not a batched array), and `updates-only: true` suppresses the initial full dump.
- the collector's **`filelogreceiver`** tails that file; OTTL maps each line to the
  event — the same crosswalk-as-data shape used in every other lane.

So the only "new" idea here is a shared file as the hand-off between two
off-the-shelf tools. The semantic mapping stays declarative in OTTL.

## How the OTTL maps it

gnmic line: `{"tags":{"interface_name":"ethernet-1/1",...},"values":{"/srl_nokia-interfaces:interface/oper-state":"down"}}`

| field | value |
|---|---|
| `event_name` (LogRecord) | `network.state.changed` |
| `network.event.state.current` (required) | the `oper-state` value (`down`/`up`) |
| `network.event.state.previous` | inferred opposite |
| `network.event.state.dimension` | `operational` |
| `network.interface.name` | `tags.interface_name` |
| resource `network.device.id` | `srl1` |

Raw gnmic fields (`tags`, `values`, `name`, `timestamp`, …) are deleted so the event
carries only registry names — `non-registry names: none`.

## Honest boundaries

- **The file hand-off adds a hop.** gnmic→file→filelog is reliable but not the
  zero-copy ideal. A native gNMI receiver in the collector (none exists upstream)
  or a gnmic OTLP-logs output (it only does metrics) would remove the file. Worth
  raising upstream — it's the same class of gap as the missing SNMP-trap receiver.
- **`previous` is inferred** (on-change carries only the new value), and
  **`dimension=operational`** is a simplification for an admin-driven flap — same
  caveats as the syslog lane.
- Same SR Linux resource/credential caveats as `../native-srl`.
