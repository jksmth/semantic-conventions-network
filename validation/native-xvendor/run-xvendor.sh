#!/usr/bin/env bash
# Cross-vendor identity reconciliation: Nokia SR Linux + Cisco IOS-XE, one rule.
#
#   ./run-xvendor.sh           deploy both single-node labs, reconcile, verdict
#   ./run-xvendor.sh --down     destroy both labs afterwards
#
# Requires: docker, python3, colima + Rosetta (for the Cisco IOL node).
set -euo pipefail
cd "$(dirname "$0")"

SRL_DIR="$(cd ../labs/srl && pwd)"
CISCO_DIR="$(cd ../labs/cisco && pwd)"
CLAB_IMAGE="${CLAB_IMAGE:-ghcr.io/srl-labs/clab:latest}"
TOOLS_IMG="xvendor-snmptools"
DOWN=0
for a in "$@"; do case "$a" in --down) DOWN=1 ;; esac; done

clab() { # clab <lab-dir> <args...>
  local dir="$1"; shift
  docker run --rm --privileged --network host --pid host \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$dir":"$dir" -w "$dir" "$CLAB_IMAGE" clab "$@"
}

cleanup() {
  if [[ "$DOWN" == 1 ]]; then
    clab "$SRL_DIR"   destroy -t srl-solo.clab.yml   --cleanup >/dev/null 2>&1 || true
    clab "$CISCO_DIR" destroy -t cisco-solo.clab.yml --cleanup >/dev/null 2>&1 || true
    echo "both labs destroyed"
  fi
}
trap cleanup EXIT

# 0. snmp tools image
docker build -t "$TOOLS_IMG" ../native-recon/tools >/dev/null

# 1. deploy both single-node labs
docker ps --format '{{.Names}}' | grep -q clab-srl-solo-srl1   || { echo "deploying SR Linux..."; clab "$SRL_DIR"   deploy -t srl-solo.clab.yml >/dev/null; }
docker ps --format '{{.Names}}' | grep -q clab-cisco-solo-cr1  || { echo "deploying Cisco IOL (Rosetta)..."; clab "$CISCO_DIR" deploy -t cisco-solo.clab.yml >/dev/null; }

# 2. wait for SNMP on both
echo "waiting for SNMP on both vendors..."
for _ in $(seq 1 40); do
  n=0; c=0
  docker run --rm --network srlmgmt   "$TOOLS_IMG" snmpget -v2c -c public -t2 -r0 172.22.22.11 1.3.6.1.2.1.1.5.0 >/dev/null 2>&1 && n=1
  docker run --rm --network ciscomgmt "$TOOLS_IMG" snmpget -v2c -c public -t2 -r0 172.30.30.11 1.3.6.1.2.1.1.5.0 >/dev/null 2>&1 && c=1
  [[ "$n" == 1 && "$c" == 1 ]] && { echo "  both up"; break; }
  sleep 5
done

# 3. reconcile
TOOLS_IMG="$TOOLS_IMG" python3 reconcile-vendors.py
rc=$?

echo "(labs left running; use --down to destroy)"
exit $rc
