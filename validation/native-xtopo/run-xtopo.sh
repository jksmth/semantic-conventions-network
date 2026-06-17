#!/usr/bin/env bash
# Cross-vendor topology reconciliation: SR Linux <-> Cisco IOL over LLDP.
#
#   ./run-xtopo.sh           deploy the wired lab, ensure LLDP, reconcile the link
#   ./run-xtopo.sh --down    destroy the lab afterwards
#
# Requires: docker, python3, colima + Rosetta (for the Cisco IOL node).
set -euo pipefail
cd "$(dirname "$0")"

LAB_DIR="$(cd ../labs/xvendor && pwd)"
CLAB_IMAGE="${CLAB_IMAGE:-ghcr.io/srl-labs/clab:latest}"
SSH_IMG="xtopo-ssh"
CR1="172.40.40.12"
DOWN=0
for a in "$@"; do case "$a" in --down) DOWN=1 ;; esac; done

clab() {
  docker run --rm --privileged --network host --pid host \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$LAB_DIR":"$LAB_DIR" -w "$LAB_DIR" "$CLAB_IMAGE" clab "$@"
}
cisco_ssh() {
  docker run --rm --network xvmgmt "$SSH_IMG" sh -c \
    "sshpass -p admin ssh -tt -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=12 admin@$CR1"
}
cleanup() { [[ "$DOWN" == 1 ]] && { clab destroy -t xvendor.clab.yml --cleanup >/dev/null 2>&1 || true; echo "lab destroyed"; }; }
trap cleanup EXIT

docker build -t "$SSH_IMG" tools >/dev/null

# 1. deploy the wired cross-vendor lab
if ! docker ps --format '{{.Names}}' | grep -q clab-xvendor-srl1; then
  echo "deploying SR Linux <-> Cisco IOL (IOL boots under Rosetta ~2 min)..."
  clab deploy -t xvendor.clab.yml >/dev/null
  echo "waiting for nodes to settle..."; sleep 120
fi

# 2. ensure the Cisco data port is up (the partial-config no-shutdown is
#    unreliable on first boot, so enforce it here) and LLDP is running.
echo "ensuring Cisco Ethernet0/1 is up + LLDP running..."
printf 'conf t\nlldp run\ninterface Ethernet0/1\nno shutdown\nend\nwrite memory\n' | cisco_ssh >/dev/null 2>&1 || true

# 3. let LLDP converge on the data link
echo "waiting for LLDP to converge..."; sleep 45

# 4. reconcile
NET=xvmgmt CR1="$CR1" SSH_IMG="$SSH_IMG" python3 reconcile-topology.py
rc=$?

echo "(lab left running; use --down to destroy)"
exit $rc
