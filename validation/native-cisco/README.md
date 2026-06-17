# Cross-vendor — Cisco IOS-XE over SNMP, validated against `network.*`

The first **second-vendor** validation: Cisco IOS-XE (IOL, built from the CML-Free
refplat) polled over SNMP and machine-checked against `network.*` using the **exact
same crosswalk** as Nokia SR Linux (`../native-srl`).

```
Cisco IOL (cr1, IOS-XE 17.18)
   |  SNMP IF-MIB (ifName=Et0/0.., ifHCInOctets, ifOperStatus)
   |  udp/161 off-box poll
   v
otelcol-contrib [ snmpreceiver + OTTL ]   <- byte-identical to ../native-srl
   |  OTLP
   v
weaver registry live-check   ->  verdict
```

## Run it

```bash
./run-cisco.sh          # deploy cisco lab (if needed), poll, map, live-check
./run-cisco.sh --down   # destroy the cisco lab afterwards
```

Verified result:

```
samples: 350  {resource: 25, metric: 50, data_point: 75, attribute: 200}
metrics matched: {network.interface.io: 25, network.interface.oper.status: 25}
advisories: 250  by-level={improvement: 250}
non-registry names: none
PASS: Cisco IOS-XE SNMP is registry-conformant via the SAME crosswalk as Nokia.
```

## Why this matters

- **The crosswalk did not change.** `otelcol-cisco.yaml` is `../native-srl/otelcol-srl.yaml`
  with only the target host and device identity (`vendor=cisco`, `os=IOS-XE`) changed —
  same IF-MIB OIDs, same `ifOperStatus`→`network.interface.oper.state` OTTL. A Cisco
  box and a Nokia box reach the identical `network.*` targets through one unchanged
  crosswalk. That is the cross-*vendor* form of the thesis (previously proven only
  across *transports* on one vendor).
- **A real second vendor.** `Et0/0`, IOS-XE 17.18, real Cisco IF-MIB — not a Linux
  stand-in. The interface names differ from Nokia (`Et0/0` vs `ethernet-1/1`), which
  is exactly the cross-vendor identity variation the reconcile test wants next.
- **L2 + L3.** The lab also boots an IOL-L2 switch (`csw1`, 172.30.30.12) serving the
  same IF-MIB — switching telemetry is one more SNMP target away.

## The Apple-Silicon unlock: colima + Rosetta

IOL is an x86 binary. Under **qemu-user** emulation its network glue (`iouyap`)
fails — `setsockopt(PACKET_ADD_MEMBERSHIP): Protocol not available` — because
qemu-user can't translate that `AF_PACKET` syscall, so the node has no network.
Switching colima to **Rosetta** fixes it: Rosetta translates x86 *instructions* but
syscalls hit the real arm64 Linux kernel, which supports `AF_PACKET`.

```bash
colima stop
colima start --vz-rosetta     # vmType vz + Rosetta (was: rosetta=false -> qemu-user)
```

With Rosetta, IOL builds, boots, **and networks** on Apple Silicon — SNMP works.
(Apple's `container` runtime leans on the same Rosetta idea, but it has no
containerlab integration, so colima+Rosetta is the right lever here.)

## Honest boundaries

- **Needs colima/Lima with Rosetta** (`vz` + `--vz-rosetta`) on Apple Silicon, or a
  native x86_64 Linux host. Plain qemu-user emulation will not work (iouyap).
- **SNMP, not gNMI.** IOL's strength is SNMP + CLI; its gNMI/telemetry story is weak,
  so the Cisco lane leads with SNMP. gNMI cross-vendor stays with cEOS (OpenConfig).
- `sysName` is `cr1.lab`; `network.device.id` is set to `cr1` via the collector.
- Same ~2% coverage (interface IO + oper-state) as the other SNMP lanes.
