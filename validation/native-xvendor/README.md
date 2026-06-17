# Cross-vendor identity reconciliation — Nokia + Cisco, one rule

`../native-recon` proved the **same device** resolves to one identity across two
transports (SNMP vs gNMI). This proves the cross-**vendor** claim: applying the
**same vendor-agnostic identity rule** (sysName → `network.device.id`, ifName →
`network.interface.name`, over identical SNMP OIDs) to a **Nokia SR Linux** box and
a **Cisco IOS-XE** box yields valid, distinct, collision-free, device-scoped
identities — with no per-vendor special-casing.

## Run it

```bash
./run-xvendor.sh          # deploy single-node SR Linux + Cisco IOL, reconcile
./run-xvendor.sh --down   # destroy both labs afterwards
```

Single-node labs (`labs/srl/srl-solo.clab.yml`, `labs/cisco/cisco-solo.clab.yml`)
keep both vendors within the colima VM's RAM. Requires Rosetta for the Cisco node.

Verified result:

```
[nokia-srlinux]  network.device.id = 'srl1'      60 ifaces (ethernet-1/1 ..)
[cisco-iosxe]    network.device.id = 'cr1.lab'    5 ifaces (Et0/0 ..)
same rule produced an id + interfaces on every vendor: True
device.ids distinct (no cross-vendor clash):           True  ['srl1', 'cr1.lab']
interface NAMES that overlap across vendors:           none
device-scoped identities (device.id, ifname):          65 of 65, all unique = True
PASS: one vendor-agnostic rule yields valid, distinct, collision-free
      device-scoped identities across Nokia and Cisco.
```

## What it proves (and a real finding)

- **The identity rule is vendor-agnostic.** The same `sysName`/`ifName` OIDs derive a
  `network.device.id` and interface set on both vendors — no Cisco-vs-Nokia branching.
- **Device-scoping prevents collisions.** Interface identity is the pair
  `(network.device.id, network.interface.name)`. Even though name *forms* differ
  wildly (`ethernet-1/1` vs `Et0/0`), the device-scoped pair is globally unique. This
  is exactly why the model scopes interface identity by device — name alone would be
  fragile across a multi-vendor estate.
- **Vendors differ in the raw identity string** — Cisco's `sysName` is `cr1.lab`
  (carries the domain) while Nokia's is bare `srl1`. The model's open-string
  `network.device.id` tolerates both; a deployment wanting uniformity would normalize
  (strip domain) in the crosswalk. A concrete example of the "normalize-at-the-edge,
  model stays open" stance.

## Boundaries / next

- This is **identity distinctness + uniformity** across vendors (the complement of
  `../native-recon`'s same-device convergence). It is **name-based**; richer keys
  (chassis serial via ENTITY-MIB, `ifIndex`, LLDP chassis-id) are the next level.
- The strongest remaining cross-vendor test is **topology correlation**: wire srl1 to
  cr1, enable LLDP on both, and reconcile each side's view of the *same link*
  (`network.link` / neighbor) — two devices observing one adjacency. That needs
  LLDP-MIB polling and is the natural follow-on.
- Add **Arista cEOS** (arm64-native) as a third vendor to extend the rule to
  OpenConfig gNMI identity, not just SNMP.
