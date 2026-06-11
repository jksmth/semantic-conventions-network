# Examples

Consumer-facing, end-to-end worked examples. Each one takes a **real device with a
concrete configuration** and shows:

1. **The device** — what it is, how it is configured, and what an operator wants to
   monitor.
2. **The structure** — a diagram of how that device maps onto `network.*` entities
   and their relationships.
3. **The telemetry** — the metrics and events it emits.
4. **The mapping** — a concise, line-by-line table from each `network.*` attribute
   or metric back to the **SNMP MIB object** and **OpenConfig path** an
   implementer reads it from.

These are written for someone who already operates the device and wants to know
"how do I express *this* in `network.*`, and where does each value come from on the
box?" For the model itself, see [`../docs/`](../docs/).

## Available examples

| Example | Device | Exercises |
|---------|--------|-----------|
| [cpe-router](cpe-router/) | Fixed-form branch CPE router | The clean baseline: device identity, interfaces & counters, sub-interface + VLAN trunk, BGP peer, PPPoE on a dialer, optical DOM, the `hw.*` boundary, and events. |
| [l2-switch](l2-switch/) | Managed L2 access switch | The layer-2 control plane: switchport VLAN membership, QinQ/dot1q-tunnel, the MAC forwarding database, spanning tree (MSTP), the LACP uplink LAG, PoE on the access ports (`network.interface.poe.*` as PSE + the budget split to `hw.*`), and the ASIC `network.component`. |
| [core-router](core-router/) | Modular backbone PE router | The full forwarding plane: modular chassis/module/component, IS-IS + multi-AF BGP + BFD, L3VPN instances, MPLS/SR-MPLS/SRv6 paths (`network.path`), the SID plane, table-fill utilization, and 400G coherent optics. |
| [l3-switch](l3-switch/) | Enterprise L3 distribution switch | The campus L2/L3 hybrid: the SVI as the L2/L3 hinge, the ARP/ND resolution table (`network.l3.adjacency.*`) between the MAC FDB and the RIB, OSPF + EIGRP + static/connected/aggregate route provenance, HSRP/VRRP shared-identity first-hop redundancy (`network.redundancy.*`), and the PIM-SM + IGMP/MLD multicast plane (`network.multicast.*`). |
| [olt-ont](olt-ont/) | PON access node (OLT + ONTs) | The access southbound: the 1:N point-to-multipoint PON tree (`network.link`), per-ONT burst-mode RSSI + BIP/FEC, the ONT activation/ranging state machine, DBA upstream bandwidth, the dying-gasp alarm, and the OLT-as-`network.observer` (producer ≠ subject) mechanism over OMCI. |
| [bng](bng/) | Broadband Network Gateway | The subscriber edge at scale: the cardinality firewall in action — aggregate session counts (state/type) + setup/teardown rates instead of per-subscriber entities, client-side AAA/RADIUS + CoA, and the address-pool entity with its utilisation alert. |
| [dc-fabric](dc-fabric/) | EVPN-VXLAN fabric leaf | The many-to-many fabric by reference: the VXLAN VTEP as a source (not N tunnels), BGP-EVPN route types and the Type-2 L2/L3 fusion, anycast gateway + MLAG shared identity, the ESI-LAG bond across two leaves, and BUM/multicast replication. |
| [wifi-ap](wifi-ap/) | Controller-managed WiFi AP | The RF layer + producer ≠ subject: radios and airtime/noise/tx-power telemetry, the BSS and its point-to-multipoint RF cell, the transient MAC-randomised station as count + record, the AP-join state machine, and the WLC-as-`network.observer` over CAPWAP. |
| [wifi-cpe](wifi-cpe/) | All-in-one wireless gateway | The composite/delta over CPE ∪ WiFi-AP: self-reported RF (observer absent), the device-as-station Wi-Fi-WAN uplink (`radio.mode=sta` + self-measured RSSI/SNR), wireless backhaul + mesh via `network.link` + `network.path`, the integrated-modem self-report, and TR-069/USP management. |

More device walkthroughs (firewall) follow the same template.

## How to read a mapping table

Each example's mapping tables use these source columns:

- **`network.*`** — the attribute or metric this registry defines.
- **SNMP** — the MIB object (and RFC/MIB module) an SNMP poller reads it from.
- **OpenConfig** — the gNMI/YANG path a streaming-telemetry collector subscribes to.

Where a value lives in `hw.*` rather than `network.*` (fans, PSUs, voltages, generic
temperatures), it is marked `hw.*` — see
[the namespace layering](../docs/architecture.md#namespace-layering).
