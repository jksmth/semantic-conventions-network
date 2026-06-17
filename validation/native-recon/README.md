# Cross-transport reconciliation — the multi-observer rule on a real NOS

Does the same device resolve to **one identity** when observed over two genuinely
different management protocols? This checks SR Linux's `network.device.id` and
`network.interface.name` set, derived independently over **SNMP** and **gNMI**, and
verifies they converge.

This is the strong version of `../engine/reconcile.py`. There, both "observers"
read the same Linux hostname string, so convergence was near-tautological (a point
raised in the original review). Here the observers are different wire protocols with
different data models, so agreement is a real result — and the *disagreements* are
the interesting part.

```
            SNMP (IF-MIB)                         gNMI (OpenConfig/YANG)
  device.id  sysName.0                            /system/name/host-name
  interfaces ifName (1.3.6.1.2.1.31.1.1.1.1)      /interface[name=*]/name
                         \                        /
                          ->  converge on one identity?
```

## Run it

```bash
./run-recon.sh          # deploy SR Linux (if needed), reconcile, verdict
./run-recon.sh --down   # destroy the SR Linux lab afterwards
```

Verified result:

```
[snmp]  device.id = 'srl1'   interfaces = 60
[gnmi]  device.id = 'srl1'   interfaces = 59
device.id converged:    True  -> 'srl1'
base interfaces agree:  True  (59 shared)
subinterface-level diff: ['mgmt0.0']  (SNMP flattens subinterfaces into ifTable)
PASS: both protocols resolve the SAME device.id and the SAME set of physical
      interface identities. The entity does not fork across collection methods.
```

## Why this is a real test, not a tautology

- The two protocols derive identity from **different places**: SNMP from `sysName`
  and the IF-MIB `ifName` column; gNMI from the `/system` and `/interface` YANG
  trees. They could easily disagree (different name forms, index-based identity,
  truncation) — the model's claim is that they *don't*, and that's what's verified.
- **The one divergence is meaningful and correctly handled.** SNMP's IF-MIB
  flattens subinterfaces into `ifTable`, so it reports `mgmt0.0`; gNMI models that
  under `/interface[name=mgmt0]/subinterface[index=0]`, so its interface list
  doesn't. The check splits base interfaces from subinterfaces, requires the base
  set to match exactly, and reports the subinterface difference as an **expected
  structural divergence** rather than an identity fork. A naive set-equality check
  would have failed here and been wrong to.

This is exactly the "multi-observer rule, demonstrated not asserted" the model is
built around — now shown across transports on a real NOS, where it has teeth.

## How identity is derived (no engine, just the two clients)

`reconcile.py` shells out to the two standard clients and compares:

- **SNMP**: `snmpget sysName.0`, `snmpwalk ifName` (net-snmp tools).
- **gNMI**: `gnmic get /system/name/host-name` and `/interface[name=*]/name`.

No bespoke collection stack — the same off-the-shelf clients used in
`../native-srl` and `../native-gnmi`.

## Honest boundaries

- **Identity == name here.** It checks `device.id` + `interface.name` convergence.
  It does not yet reconcile richer keys (chassis serial, `ifIndex` ↔ gNMI ifindex,
  LLDP chassis-id) — those are the next level of identity robustness.
- **Same vendor, two transports.** Cross-*vendor* identity reconciliation (does a
  Nokia box and an Arista box expose comparable identity?) is the harder, more
  valuable follow-on — see `../docs/realism-roadmap.md`.
- It's a point-in-time check, not a continuous one; a device rename mid-run isn't
  exercised.
