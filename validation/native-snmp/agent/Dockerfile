# A real off-box SNMP agent (net-snmp) for the lab routers. Runs in the router's
# network namespace (see docker-compose.yml) so its IF-MIB reflects the router's
# actual interfaces — the same eth0/lo the FRR daemon and `ip link` see.
FROM alpine:3.20
RUN apk add --no-cache net-snmp net-snmp-tools
COPY snmpd.conf /etc/snmp/snmpd.conf
# -f foreground, -Lo log to stdout. The listen address is passed on the command
# line (not via agentAddress in the conf): under Docker Desktop's LinuxKit kernel
# net-snmp fails to open the endpoint when it's set in the config file.
ENTRYPOINT ["snmpd", "-f", "-Lo", "-c", "/etc/snmp/snmpd.conf", "udp:0.0.0.0:1161"]
