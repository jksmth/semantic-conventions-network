#!/usr/bin/env bash
# Off-box SNMP validation path:
#   FRR router (r1) + net-snmp agent  <--udp/161--  otelcol [snmpreceiver + OTTL]
#       --OTLP-->  weaver registry live-check  ->  verdict
#
#   ./run-snmp.sh           boot lab (if needed), poll, map, live-check
#   ./run-snmp.sh --down    tear lab + stack down afterwards
#
# Requires: docker.
set -euo pipefail
cd "$(dirname "$0")"

LAB="../labs/frr"
DOWN=0
POLL_SECONDS="${POLL_SECONDS:-18}"
for a in "$@"; do case "$a" in --down) DOWN=1 ;; esac; done

cleanup() {
  docker compose down >/dev/null 2>&1 || true
  if [[ "$DOWN" == 1 ]]; then
    ( cd "$LAB" && docker compose down >/dev/null 2>&1 ) || true
    echo "lab + snmp stack torn down"
  fi
}
trap cleanup EXIT

mkdir -p out; rm -f out/* 2>/dev/null || true

# 1. lab up (creates external `netlab`, gives us a real router at 172.20.0.11)
( cd "$LAB" && docker compose up -d >/dev/null )
echo "waiting for r1..."
for _ in $(seq 1 15); do docker exec netlab-r1 true >/dev/null 2>&1 && break; sleep 1; done

# 2. snmp agent + collector + weaver
docker compose up -d --build >/dev/null
echo "polling SNMP + mapping for ${POLL_SECONDS}s (snmpreceiver -> OTTL -> OTLP -> weaver)..."
sleep "$POLL_SECONDS"

# 3. stop the listener, read its exit code (non-zero == a violation was seen)
docker kill -s HUP netlab-weaver >/dev/null 2>&1 || true
rc="$(docker wait netlab-weaver 2>/dev/null || echo 1)"

# 4. report + verdict
echo "========================================================"
echo "  network.* live-check verdict (off-box SNMP: snmpreceiver + OTTL)"
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
  echo "  (no report; check: docker logs netlab-otelcol ; docker logs netlab-snmpd-r1)"
fi
echo "--------------------------------------------------------"
if [[ "${samples_seen:-0}" == "0" ]]; then
  echo "  FAIL: no samples reached weaver — SNMP poll or export did not work."
  echo "        try: docker logs netlab-snmpd-r1 ; docker logs netlab-otelcol"
  rc=1
elif [[ "$rc" == "0" ]]; then
  echo "  PASS: off-box SNMP telemetry is fully registry-conformant."
else
  echo "  FAIL: weaver exited $rc — a violation was found (see report above)."
fi
echo "========================================================"
exit "${rc:-1}"
