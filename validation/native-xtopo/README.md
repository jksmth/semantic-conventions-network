# Cross-vendor topology reconciliation — two vendors, one link

The strongest multi-observer test in the suite. A Nokia SR Linux and a Cisco
IOS-XE box are **wired together** and run **LLDP**. Each independently reports its
view of the adjacency over a *different* access method, and the two directed views
are reconciled into **one undirected `network.link`**.

```
   srl1:ethernet-1/1  ●────────────●  cr1:Ethernet0/1     (clab data link)
        │   LLDP                          │   LLDP
        ▼ (SR Linux CLI/state)            ▼ (Cisco SSH CLI)
   sees cr1.lab / Et0/1             sees srl1 / ethernet-1/1
                       \           /
                        reconcile → one link
```

## Run it

```bash
./run-xtopo.sh          # deploy the wired lab, ensure LLDP, reconcile
./run-xtopo.sh --down   # destroy the lab afterwards
```

Lab: `labs/xvendor/xvendor.clab.yml` (srl1 + cr1 on one mgmt net + a data link).
Requires colima + Rosetta for the Cisco IOL node.

Verified result:

```
[cisco-iosxe]    local ('cr1','ethernet0/1')   --LLDP-->  remote ('srl1','ethernet-1/1')
[nokia-srlinux]  local ('srl1','ethernet-1/1') --LLDP-->  remote ('cr1','ethernet0/1')
same undirected link: True
proper mirror (each side's remote == other's local): True
PASS: reconciles to one network.link: ('cr1','ethernet0/1') <--> ('srl1','ethernet-1/1')
```

## Why this is the strongest test

- **Two devices observing one adjacency** (not one device, and not two unrelated
  devices). This is the genuine multi-observer rule applied to a *link*: each end
  independently discovers the other via LLDP, and the two halves must compose into
  one undirected edge whose endpoints are device-scoped `(network.device.id,
  network.interface.name)` pairs.
- **Two vendors, two protocols.** Cisco's view comes from its SSH CLI
  (`show lldp neighbors`), SR Linux's from its own state — genuinely heterogeneous
  observers, agreeing on one link.
- **The normalization is the real finding.** They reconcile only after two
  cross-vendor fix-ups, both surfaced earlier in the suite:
  - **domain suffix** — Cisco advertises its sysName as `cr1.lab`; SR Linux as bare
    `srl1`. Strip the domain to get one `network.device.id`.
  - **interface-name abbreviation** — Cisco's LLDP port-id is `Et0/1`; its full name
    is `Ethernet0/1`. Expand `Et`→`Ethernet` to match. (LLDP port-id subtype is
    `INTERFACE_NAME` on both, which is what makes name-based reconciliation possible
    at all — a MAC-or-ifindex port-id subtype would need a different join key.)

  This is concrete evidence for *why* `network.link`/neighbor identity must be the
  device-scoped interface pair, and why a small normalization layer (not model
  changes) absorbs vendor differences.

## Honest boundaries

- **Cisco data-port `no shutdown` is enforced post-boot** by the run script: the
  clab `cisco_iol` partial-config `no shutdown` did not stick on first boot, so the
  script SSHes in to bring `Ethernet0/1` up and `write memory`. (IOL also discovers
  the neighbor over the shared mgmt segment as `Et0/0`; the test uses the wired data
  link `Et0/1` ↔ `ethernet-1/1`.)
- **Name-based reconciliation.** It joins on `INTERFACE_NAME` port-ids + sysName.
  Chassis-id (MAC) is also exchanged and could be a sturdier join key; using it
  (and ENTITY-MIB serials) is the next level of robustness.
- Two NOS nodes (one native arm64, one emulated IOL) run together; fine on the
  6 GB colima VM.
