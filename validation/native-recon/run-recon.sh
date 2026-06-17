#!/usr/bin/env bash
# Cross-transport reconciliation on a real NOS:
#   does SR Linux resolve to ONE identity when observed over SNMP vs gNMI?
#
#   ./run-recon.sh           deploy SR Linux (if needed), reconcile, verdict
#   ./run-recon.sh --down    destroy the SR Linux lab afterwards too
#
# Requires: docker, python3.
set -euo pipefail
cd "$(dirname "$0")"

LAB_DIR="$(cd ../labs/srl && pwd)"
CLAB_IMAGE="${CLAB_IMAGE:-ghcr.io/srl-labs/clab:latest}"
GNMI_IMG="${GNMI_IMG:-ghcr.io/openconfig/gnmic:latest}"
SNMP_IMG="srlrecon-snmptools"
TARGET="172.22.22.11"
DOWN=0
for a in "$@"; do case "$a" in --down) DOWN=1 ;; esac; done

clab() {
  docker run --rm --privileged --network host --pid host \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$LAB_DIR":"$LAB_DIR" -w "$LAB_DIR" \
    "$CLAB_IMAGE" clab "$@"
}

cleanup() {
  if [[ "$DOWN" == 1 ]]; then
    clab destroy -t srl.clab.yml --cleanup >/dev/null 2>&1 || true
    echo "SR Linux lab destroyed"
  fi
}
trap cleanup EXIT

# 0. build the SNMP tools image (once)
docker build -t "$SNMP_IMG" tools >/dev/null

# 1. deploy SR Linux if not up
if ! docker ps --format '{{.Names}}' | grep -q clab-srl-srl1; then
  echo "deploying SR Linux with containerlab (first boot ~1-2 min)..."
  clab deploy -t srl.clab.yml >/dev/null
fi

# 2. wait for BOTH transports to answer (the whole point is two observers)
echo "waiting for SNMP + gNMI to respond..."
for _ in $(seq 1 30); do
  snmp_ok=0; gnmi_ok=0
  docker run --rm --network srlmgmt "$SNMP_IMG" \
    snmpget -v2c -c public -t 2 -r 0 "$TARGET" 1.3.6.1.2.1.1.5.0 >/dev/null 2>&1 && snmp_ok=1
  docker run --rm --network srlmgmt "$GNMI_IMG" \
    -a "${TARGET}:57400" -u admin -p 'NokiaSrl1!' --skip-verify -e json_ietf \
    get --path /system/name/host-name >/dev/null 2>&1 && gnmi_ok=1
  [[ "$snmp_ok" == 1 && "$gnmi_ok" == 1 ]] && { echo "  both up"; break; }
  sleep 4
done

# 3. reconcile
TARGET="$TARGET" NET=srlmgmt SNMP_IMG="$SNMP_IMG" GNMI_IMG="$GNMI_IMG" \
  python3 reconcile.py
rc=$?

echo "(SR Linux left running; use --down to destroy)"
exit $rc
