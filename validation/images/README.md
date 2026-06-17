# Vendor image builders

Turns vendor downloads (which can't be committed or pulled anonymously) into
containerlab-ready images. Sourced images live here but are gitignored.

## Cisco IOL (L3 router + L2 switch) — `build-cisco-iol.sh`

One script from a Cisco **CML‑Free refplat ISO** to two runnable images.

### Get the ISO (one-time, free Cisco account)

cisco.com → **Cisco Modeling Labs Free** → download the **reference platform ISO**
(it bundles IOL, IOL‑L2, and ASAv). Drop it in this directory, e.g.
`images/refplat-YYYYMMDD-free-iso/refplat-YYYYMMDD-free.iso`.

### Build

```bash
./build-cisco-iol.sh                       # auto-detects refplat-*/*.iso
./build-cisco-iol.sh /path/to/refplat.iso  # or pass it explicitly
```

Produces:

| Image | Shape | containerlab |
|---|---|---|
| `vrnetlab/cisco_iol:<ver>` | IOS‑XE L3 router | `kind: cisco_iol` |
| `vrnetlab/cisco_iol:L2-<ver>` | IOS‑XE L2 switch | `kind: cisco_iol` + `type: l2` |

Verified on Apple Silicon: builds and **boots IOS‑XE 17.18 under amd64 emulation**
(IOL is an x86 binary running as a process — no KVM needed, unlike VM-based NOSes).

> **arm64 networking requires Rosetta (not qemu-user).** IOL's network glue
> (`iouyap`) uses `AF_PACKET` socket options that **qemu‑user cannot emulate** — it
> fails with `setsockopt (PACKET_ADD_MEMBERSHIP): Protocol not available`, leaving
> the node with no network. **Rosetta fixes this**: it translates x86 instructions
> but lets syscalls hit the real arm64 kernel (which supports `AF_PACKET`). On
> colima: `colima start --vz-rosetta` (vmType `vz` + Rosetta). Verified: with
> Rosetta, IOL builds, boots, **and networks** (SNMP works) on Apple Silicon — see
> `../native-cisco`. Without Rosetta (plain qemu-user) IOL is boot-only; a native
> x86_64 Linux host also works.

### What it does (and why it's not just "docker load")

Newer CML refplats ship IOL as an **OCI image** wrapped in CML's own `/iol-runner`
(not the raw `.iol` binary, and not compatible with containerlab's `cisco_iol`
kind). So the script:

1. mounts the ISO (`hdiutil` on macOS, `mount` on Linux),
2. `docker load`s the `iol-xe` / `ioll2-xe` OCI tarballs,
3. `docker cp`s the real IOL binary (`x86_64_crb_linux*-adventerprisek9-ms.iol`)
   out of each image,
4. feeds them to **srl-labs/vrnetlab**'s `cisco_iol` builder (the launcher that
   gives clab networking, serial, startup-config, health),
5. builds as `linux/amd64` so the x86 binary runs under emulation here.

The IOL binary is self-licensed in recent IOS‑XE (the bundled `.iourc` is not
needed by the vrnetlab build).

### Use it

```yaml
# example.clab.yml
name: cisco
topology:
  nodes:
    r1:  { kind: cisco_iol, image: vrnetlab/cisco_iol:17.18.02 }
    sw1: { kind: cisco_iol, image: vrnetlab/cisco_iol:L2-17.18.02, type: l2 }
  links:
    - endpoints: ["r1:Ethernet0/1", "sw1:Ethernet0/1"]
```

Default credentials: `admin` / `admin`. IOS boot under emulation takes ~1–2 min.

## Other vendors (planned, same pattern)

- **Arista cEOS** (arm64 native, single `docker import`) — `build-ceos.sh`
- **Juniper cRPD** (arm64 native, `docker load`) — `build-crpd.sh`

VM-based NOSes (Cisco XRd/XRv9k/cat9kv, Juniper vMX/vJunos) need `/dev/kvm`, which
Docker Desktop on macOS doesn't provide — they require a Linux/KVM host.
