#!/usr/bin/env bash
# Real-NOS validation path: Nokia SR Linux (containerlab) over its native SNMP.
#
#   SR Linux SNMP server  <--udp/161--  otelcol [snmpreceiver + OTTL]
#       --OTLP-->  weaver registry live-check  ->  verdict
#
#   ./run-srl.sh           deploy SR Linux (if needed), poll, map, live-check
#   ./run-srl.sh --down    destroy the SR Linux lab afterwards too
#
# Requires: docker (containerlab runs as a container, no host install needed).
set -euo pipefail
cd "$(dirname "$0")"

LAB_DIR="$(cd ../labs/srl && pwd)"
CLAB_IMAGE="${CLAB_IMAGE:-ghcr.io/srl-labs/clab:latest}"
TARGET="172.22.22.11"
DOWN=0
POLL_SECONDS="${POLL_SECONDS:-20}"
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

mkdir -p out; rm -f out/* 2>/dev/null || true

# 1. deploy SR Linux via containerlab (idempotent: re-deploy is a no-op if up)
if ! docker ps --format '{{.Names}}' | grep -q clab-srl-srl1; then
  echo "deploying SR Linux with containerlab (first boot pulls/initialises ~1-2 min)..."
  clab deploy -t srl.clab.yml >/dev/null
fi

# 2. wait for SR Linux's SNMP server to answer (it's enabled by default,
#    community 'public', on the mgmt network-instance).
echo "waiting for SR Linux SNMP to respond on ${TARGET}:161..."
ok=0
for _ in $(seq 1 30); do
  if docker run --rm --network srlmgmt alpine:3.20 sh -c \
       "apk add --no-cache net-snmp-tools >/dev/null 2>&1 && snmpget -v2c -c public -t 2 -r 1 ${TARGET} 1.3.6.1.2.1.1.5.0" \
       >/dev/null 2>&1; then ok=1; echo "  SNMP up"; break; fi
  sleep 4
done
[[ "$ok" == 1 ]] || echo "  (warning: SNMP not answering yet — continuing anyway)"

# 3. collector + weaver
docker compose up -d >/dev/null
echo "polling SR Linux SNMP + mapping for ${POLL_SECONDS}s..."
sleep "$POLL_SECONDS"

# 4. stop listener, read exit code
docker kill -s HUP srl-weaver >/dev/null 2>&1 || true
rc="$(docker wait srl-weaver 2>/dev/null || echo 1)"

# 5. report + verdict
echo "========================================================"
echo "  network.* live-check verdict (real NOS: SR Linux SNMP)"
echo "========================================================"
report="$(ls -1 out/* 2>/dev/null | head -n1 || true)"
samples_seen=0
if [[ -n "$report" ]]; then
  python3 - "$report" <<'PY' || true
import json, sys
try: data = json.load(open(sys.argv[1]))
except Exception as e: print(f"  (could not parse report: {e})"); sys.exit(0)
stats = (data.get("statistics") if isinstance(data, dict) else None) or {}
seen = {k: v for k, v in stats.get("seen_registry_metrics", {}).items() if v}
nonreg = {k: stats.get(k) for k in ("seen_non_registry_metrics","seen_non_registry_attributes") if stats.get(k)}
print(f"  samples:           {stats.get('total_entities')}  {stats.get('total_entities_by_type', {})}")
print(f"  metrics matched:   {seen if seen else ' none'}")
print(f"  advisories:        {stats.get('total_advisories')}  by-level={stats.get('advice_level_counts', {})}")
print(f"  registry coverage: {stats.get('registry_coverage', 0)*100:.1f}%")
print(f"  non-registry names:{nonreg if nonreg else ' none'}")
PY
  samples_seen="$(python3 -c "import json;print((json.load(open('$report')).get('statistics') or {}).get('total_entities',0))" 2>/dev/null || echo 0)"
else
  echo "  (no report; check: docker logs srl-otelcol)"
fi
echo "--------------------------------------------------------"
if [[ "${samples_seen:-0}" == "0" ]]; then
  echo "  FAIL: no samples reached weaver (SNMP poll or export failed)."
  rc=1
elif [[ "$rc" == "0" ]]; then
  echo "  PASS: real-NOS SNMP telemetry is fully registry-conformant."
else
  echo "  FAIL: weaver exited $rc — a violation was found (see report above)."
fi
echo "========================================================"
echo "(SR Linux left running; use --down to destroy, or: $0 --down)"
exit "${rc:-1}"
