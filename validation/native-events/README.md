# Events — a real port flap, validated as a `network.state.changed` event

The first time the **events half of the model** is executable. Until now every
path validated metrics; this one validates an **event**: a real port flap on
SR Linux becomes a registry-conformant `network.state.changed`, machine-checked by
Weaver.

```
SR Linux (flap ethernet-1/1)
   |  sr_chassis_mgr logs:  chassis|...|EV|portDown|W: Interface ethernet-1/1 is now down ...
   |  remote syslog (RFC5424, udp/514)
   v
otelcol-contrib
   syslogreceiver      — receive the syslog line
   filter              — keep only portUp/portDown lines
   transform / OTTL    — parse -> network.state.changed event + attributes
   otlpexporter        — OTLP logs
   v
weaver registry live-check   — validates the EVENT against the registry
```

## Run it

```bash
./run-events.sh          # deploy SR Linux (if needed), flap, validate the event
./run-events.sh --down   # destroy the SR Linux lab afterwards
```

Verified result:

```
samples: 36  {resource: 4, log: 4, attribute: 28}
registry events:    {network.state.changed: 4}
advisories: 40  by-level={improvement: 32, information: 8}
non-registry names: none
PASS: the port flap was validated as a registry-defined network.state.changed event.
```

## What it proves

- **Events, not just metrics.** An OTel event is a log record with `event_name`
  set; Weaver validates it against the registry's event definitions
  (`seen_registry_events: {network.state.changed: 4}`). This exercises
  `model/network/events` and the `network.interface.state.changed` refinement for
  the first time.
- **The model's name rule, honoured.** Per `model/network/interface/events.yaml`
  the interface refinement does **not** mint a new name — the wire `event.name`
  stays `network.state.changed`, with the entity carried by `network.interface.name`
  + `network.device.id`. The OTTL emits exactly that.
- **The "gauge + transition event" pairing.** This event is the point-in-time
  transition the `network.interface.oper.status` gauge (in `../native-srl`) cannot
  reconstruct after a restart — the two-signal pattern the model is built around,
  now both sides validated.
- **Off-the-shelf path.** `syslogreceiver` is upstream; the only custom part is the
  OTTL that maps the vendor log line to the event — the same crosswalk-as-data shape
  used everywhere else, just on logs instead of metrics.

## How the OTTL maps it

SR Linux logs `...EV|portDown|W: Interface ethernet-1/1 is now down for reason: ...`.
The transform turns that into:

| field | value |
|---|---|
| `event_name` (LogRecord) | `network.state.changed` |
| `network.event.state.current` (required) | `down` / `up` |
| `network.event.state.previous` | `up` / `down` (inferred from the transition) |
| `network.event.state.dimension` | `operational` |
| `network.interface.name` | `ethernet-1/1` (regex-extracted) |
| `network.event.message` | the verbatim log line |
| resource `network.device.id` | `srl1` |

Raw syslog attributes (`message`, `appname`, `facility_text`, …) are deleted so the
event carries only registry-defined names — verified by `non-registry names: none`.

## Honest boundaries

- **`previous` is inferred, not observed.** A single chassis log line carries only
  the new state; `network.event.state.previous` is derived from the transition
  direction. A stateful processor (or correlating with the oper-status gauge) would
  make it authoritative.
- **`dimension=operational` is a simplification.** The flap here is admin-driven
  (`port-admin-disabled` in the log), so a stricter mapping might emit
  `administrative`. The reason string is preserved in `network.event.message`; a
  refinement could parse it to set the dimension precisely.
- **Poll/push fidelity.** This is the syslog lane (Lane A in
  `../docs/realism-roadmap.md`) — reliable and fully upstream, but syslog is
  best-effort UDP. Lane B (gNMI `on-change` → OTLP logs) is the higher-fidelity
  push path; Lane C (SNMP traps) has no upstream OTel receiver yet.
- Same SR Linux resource/credential caveats as `../native-srl`.
