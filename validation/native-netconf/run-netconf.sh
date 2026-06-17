#!/usr/bin/env bash
# NETCONF collection lane: SR Linux YANG state over NETCONF -> network.* -> weaver.
#
#   NETCONF <get> (ncclient, ssh/830)  ->  netconf_collect.py maps to network.*
#       ->  weaver registry live-check (stdin)  ->  engine/report.py verdict
#
#   ./run-netconf.sh           deploy SR Linux (if needed), collect, validate
#   ./run-netconf.sh --down    destroy the SR Linux lab afterwards
#
# Requires: docker, python3.
set -euo pipefail
cd "$(dirname "$0")"

REPO_ROOT="$(cd ../.. && pwd)"
WEAVER_IMAGE="${WEAVER_IMAGE:-otel/weaver:latest}"
SRL_DIR="$(cd ../labs/srl && pwd)"
CLAB_IMAGE="${CLAB_IMAGE:-ghcr.io/srl-labs/clab:latest}"
DOWN=0
for a in "$@"; do case "$a" in --down) DOWN=1 ;; esac; done

clab() {
  docker run --rm --privileged --network host --pid host \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$SRL_DIR":"$SRL_DIR" -w "$SRL_DIR" "$CLAB_IMAGE" clab "$@"
}
cleanup() { [[ "$DOWN" == 1 ]] && { clab destroy -t srl-solo.clab.yml --cleanup >/dev/null 2>&1 || true; echo "lab destroyed"; }; }
trap cleanup EXIT

docker build -t netconf-tools tools >/dev/null

# 1. ensure SR Linux is up (NETCONF server is on by default)
if ! docker ps --format '{{.Names}}' | grep -q clab-srl-solo-srl1; then
  echo "deploying SR Linux..."; clab deploy -t srl-solo.clab.yml >/dev/null; sleep 35
fi
echo "waiting for NETCONF (830)..."
for _ in $(seq 1 20); do
  docker run --rm --network srlmgmt netconf-tools python3 -c "import socket;socket.create_connection(('172.22.22.11',830),3)" >/dev/null 2>&1 && { echo "  up"; break; }
  sleep 3
done

# 2. NETCONF collect -> map -> weaver live-check (stdin) -> report
REPORT="$(mktemp)"
set +e
docker run --rm --network srlmgmt -v "$(pwd)":/w -w /w netconf-tools python3 netconf_collect.py \
  | docker run --rm -i -v "$REPO_ROOT":/work -w /work "$WEAVER_IMAGE" \
      --quiet registry live-check -r model --input-source stdin --input-format json --format json \
  > "$REPORT" 2>/dev/null
set -e

# 3. verdict (reuse the original engine's report parser)
echo "========================================================"
echo "  network.* live-check verdict (NETCONF: SR Linux YANG over SSH)"
echo "========================================================"
python3 ../engine/report.py "$REPORT"
rc=$?
rm -f "$REPORT"

echo "(lab left running; use --down to destroy)"
exit $rc
