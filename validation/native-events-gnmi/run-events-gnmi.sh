#!/usr/bin/env bash
# Events Lane B (push): a real port flap on SR Linux, captured as a gNMI on-change
# push and validated as a network.state.changed event.
#
#   SR Linux (flap) --gNMI on-change--> gnmic(file) --> otelcol(filelog+OTTL)
#       --OTLP event--> weaver registry live-check  ->  verdict
#
#   ./run-events-gnmi.sh           deploy SR Linux (if needed), flap, validate
#   ./run-events-gnmi.sh --down    destroy the SR Linux lab afterwards too
#
# Requires: docker, python3.
set -euo pipefail
cd "$(dirname "$0")"

LAB_DIR="$(cd ../labs/srl && pwd)"
CLAB_IMAGE="${CLAB_IMAGE:-ghcr.io/srl-labs/clab:latest}"
DOWN=0
for a in "$@"; do case "$a" in --down) DOWN=1 ;; esac; done

clab() {
  docker run --rm --privileged --network host --pid host \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$LAB_DIR":"$LAB_DIR" -w "$LAB_DIR" \
    "$CLAB_IMAGE" clab "$@"
}

cleanup() {
  docker compose down >/dev/null 2>&1 || true
  if [[ "$DOWN" == 1 ]]; then
    clab destroy -t srl.clab.yml --cleanup >/dev/null 2>&1 || true
    echo "SR Linux lab destroyed"
  fi
}
trap cleanup EXIT

mkdir -p out shared; rm -f out/* 2>/dev/null || true
: > shared/events.jsonl   # fresh event file

# 1. deploy SR Linux if not up
if ! docker ps --format '{{.Names}}' | grep -q clab-srl-srl1; then
  echo "deploying SR Linux with containerlab (first boot ~1-2 min)..."
  clab deploy -t srl.clab.yml >/dev/null
  for _ in $(seq 1 20); do docker exec clab-srl-srl1 sr_cli -c "info from state system information version" >/dev/null 2>&1 && break; sleep 4; done
fi

# 2. weaver + gnmic(on-change subscribe) + collector(filelog)
docker compose up -d >/dev/null
echo "establishing gNMI on-change subscription..."
sleep 8

# 3. flap ethernet-1/1 a few times -> on-change pushes each transition
echo "flapping ethernet-1/1 (gNMI on-change push)..."
for state in disable enable disable enable; do
  docker exec -i clab-srl-srl1 sr_cli >/dev/null 2>&1 <<EOF
enter candidate
set / interface ethernet-1/1 admin-state ${state}
commit now
EOF
  sleep 3
done
sleep 3

# 4. stop listener, read exit code
docker kill -s HUP evg-weaver >/dev/null 2>&1 || true
rc="$(docker wait evg-weaver 2>/dev/null || echo 1)"

# 5. report + verdict
echo "========================================================"
echo "  network.* live-check verdict (events push: gNMI on-change flap)"
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
  echo "  (no report; check: docker logs evg-otelcol ; docker logs evg-gnmic ; cat shared/events.jsonl)"
fi
echo "--------------------------------------------------------"
if [[ "${events_seen:-0}" == "0" ]]; then
  echo "  FAIL: no registry events reached weaver (gNMI/file/parse/export issue)."
  rc=1
elif [[ "$rc" == "0" ]]; then
  echo "  PASS: the gNMI on-change flap was validated as a registry-defined"
  echo "        network.state.changed event — a sub-second push, not a poll."
else
  echo "  FAIL: weaver exited $rc — a violation was found (see report above)."
fi
echo "========================================================"
echo "(SR Linux left running; use --down to destroy)"
exit "${rc:-1}"
