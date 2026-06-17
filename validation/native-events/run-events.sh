#!/usr/bin/env bash
# Events lane: a real port flap on SR Linux, validated as a network.state.changed
# event against the registry.
#
#   SR Linux (flap ethernet-1/1) --syslog--> otelcol [syslogreceiver + OTTL]
#       --OTLP event--> weaver registry live-check  ->  verdict
#
#   ./run-events.sh           deploy SR Linux (if needed), flap, validate event
#   ./run-events.sh --down    destroy the SR Linux lab afterwards too
#
# Requires: docker, python3.
set -euo pipefail
cd "$(dirname "$0")"

LAB_DIR="$(cd ../labs/srl && pwd)"
CLAB_IMAGE="${CLAB_IMAGE:-ghcr.io/srl-labs/clab:latest}"
COLLECTOR_IP="172.22.22.100"
DOWN=0
for a in "$@"; do case "$a" in --down) DOWN=1 ;; esac; done

clab() {
  docker run --rm --privileged --network host --pid host \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$LAB_DIR":"$LAB_DIR" -w "$LAB_DIR" \
    "$CLAB_IMAGE" clab "$@"
}

srl() { docker exec -i clab-srl-srl1 sr_cli >/dev/null 2>&1; }

cleanup() {
  docker compose down >/dev/null 2>&1 || true
  if [[ "$DOWN" == 1 ]]; then
    clab destroy -t srl.clab.yml --cleanup >/dev/null 2>&1 || true
    echo "SR Linux lab destroyed"
  fi
}
trap cleanup EXIT

mkdir -p out; rm -f out/* 2>/dev/null || true

# 1. deploy SR Linux if not up
if ! docker ps --format '{{.Names}}' | grep -q clab-srl-srl1; then
  echo "deploying SR Linux with containerlab (first boot ~1-2 min)..."
  clab deploy -t srl.clab.yml >/dev/null
  echo "waiting for management plane..."
  for _ in $(seq 1 20); do docker exec clab-srl-srl1 sr_cli -c "info from state system information version" >/dev/null 2>&1 && break; sleep 4; done
fi

# 2. collector (at COLLECTOR_IP) + weaver
docker compose up -d >/dev/null
sleep 4

# 3. point SR Linux's syslog at the collector (chassis subsystem = port events)
echo "configuring SR Linux remote syslog -> ${COLLECTOR_IP}..."
docker exec -i clab-srl-srl1 sr_cli >/dev/null 2>&1 <<EOF
enter candidate
set / system logging remote-server ${COLLECTOR_IP} network-instance mgmt remote-port 514 transport udp
set / system logging remote-server ${COLLECTOR_IP} subsystem chassis priority match-above informational
commit now
EOF

# 4. flap ethernet-1/1 a few times to generate portUp/portDown events
echo "flapping ethernet-1/1 (generating state-change events)..."
for state in disable enable disable enable disable; do
  docker exec -i clab-srl-srl1 sr_cli >/dev/null 2>&1 <<EOF
enter candidate
set / interface ethernet-1/1 admin-state ${state}
commit now
EOF
  sleep 2
done
sleep 3

# 5. stop listener, read exit code
docker kill -s HUP ev-weaver >/dev/null 2>&1 || true
rc="$(docker wait ev-weaver 2>/dev/null || echo 1)"

# 6. report + verdict
echo "========================================================"
echo "  network.* live-check verdict (events: port flap -> network.state.changed)"
echo "========================================================"
report="$(ls -1 out/* 2>/dev/null | head -n1 || true)"
events_seen=0
if [[ -n "$report" ]]; then
  python3 - "$report" <<'PY' || true
import json, sys
try: data = json.load(open(sys.argv[1]))
except Exception as e: print(f"  (could not parse report: {e})"); sys.exit(0)
stats = (data.get("statistics") if isinstance(data, dict) else None) or {}
ev = {k: v for k, v in stats.get("seen_registry_events", {}).items() if v}
nonreg = {k: stats.get(k) for k in
          ("seen_non_registry_events","seen_non_registry_attributes") if stats.get(k)}
print(f"  samples:            {stats.get('total_entities')}  {stats.get('total_entities_by_type', {})}")
print(f"  registry events:    {ev if ev else ' none'}")
print(f"  advisories:         {stats.get('total_advisories')}  by-level={stats.get('advice_level_counts', {})}")
print(f"  non-registry names: {nonreg if nonreg else ' none'}")
PY
  events_seen="$(python3 -c "import json;print(sum((json.load(open('$report')).get('statistics') or {}).get('seen_registry_events',{}).values()))" 2>/dev/null || echo 0)"
else
  echo "  (no report; check: docker logs ev-otelcol)"
fi
echo "--------------------------------------------------------"
if [[ "${events_seen:-0}" == "0" ]]; then
  echo "  FAIL: no registry events reached weaver (syslog/parse/export issue)."
  echo "        try: docker logs ev-otelcol"
  rc=1
elif [[ "$rc" == "0" ]]; then
  echo "  PASS: the port flap was validated as a registry-defined"
  echo "        network.state.changed event. Events half of the model is executable."
else
  echo "  FAIL: weaver exited $rc — a violation was found (see report above)."
fi
echo "========================================================"
echo "(SR Linux left running; use --down to destroy)"
exit "${rc:-1}"
