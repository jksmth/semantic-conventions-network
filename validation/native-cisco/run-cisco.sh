#!/usr/bin/env bash
# Cross-vendor SNMP validation: Cisco IOS-XE (IOL) -> network.* -> weaver, using
# the SAME crosswalk as Nokia SR Linux (../native-srl).
#
#   ./run-cisco.sh           deploy cisco lab (if needed), poll, map, live-check
#   ./run-cisco.sh --down    destroy the cisco lab afterwards too
#
# Requires: docker, python3, colima with Rosetta (vz + --vz-rosetta) so the amd64
# IOL binary's iouyap networking works on Apple Silicon.
set -euo pipefail
cd "$(dirname "$0")"

LAB_DIR="$(cd ../labs/cisco && pwd)"
CLAB_IMAGE="${CLAB_IMAGE:-ghcr.io/srl-labs/clab:latest}"
TARGET="172.30.30.11"
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
    clab destroy -t cisco.clab.yml --cleanup >/dev/null 2>&1 || true
    echo "cisco lab destroyed"
  fi
}
trap cleanup EXIT

mkdir -p out; rm -f out/* 2>/dev/null || true

# 1. deploy cisco lab if not up
if ! docker ps --format '{{.Names}}' | grep -q clab-cisco-cr1; then
  echo "deploying Cisco IOL lab with containerlab (IOS boots under Rosetta ~2 min)..."
  clab deploy -t cisco.clab.yml >/dev/null
fi

# 2. wait for IOS + SNMP
echo "waiting for Cisco SNMP on ${TARGET}:161..."
ok=0
for _ in $(seq 1 40); do
  if docker run --rm --network ciscomgmt alpine:3.20 sh -c \
       "apk add --no-cache net-snmp-tools >/dev/null 2>&1 && snmpget -v2c -c public -t 2 -r 0 ${TARGET} 1.3.6.1.2.1.1.5.0" \
       >/dev/null 2>&1; then ok=1; echo "  SNMP up"; break; fi
  sleep 5
done
[[ "$ok" == 1 ]] || echo "  (warning: SNMP not answering yet — continuing anyway)"

# 3. collector + weaver
docker compose up -d >/dev/null
echo "polling Cisco SNMP + mapping for ${POLL_SECONDS}s..."
sleep "$POLL_SECONDS"

# 4. stop listener, read exit code
docker kill -s HUP cisco-weaver >/dev/null 2>&1 || true
rc="$(docker wait cisco-weaver 2>/dev/null || echo 1)"

# 5. report + verdict
echo "========================================================"
echo "  network.* live-check verdict (cross-vendor: Cisco IOS-XE SNMP)"
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
print(f"  non-registry names:{nonreg if nonreg else ' none'}")
PY
  samples_seen="$(python3 -c "import json;print((json.load(open('$report')).get('statistics') or {}).get('total_entities',0))" 2>/dev/null || echo 0)"
else
  echo "  (no report; check: docker logs cisco-otelcol)"
fi
echo "--------------------------------------------------------"
if [[ "${samples_seen:-0}" == "0" ]]; then
  echo "  FAIL: no samples reached weaver (SNMP poll or export failed)."
  rc=1
elif [[ "$rc" == "0" ]]; then
  echo "  PASS: Cisco IOS-XE SNMP is registry-conformant via the SAME crosswalk as Nokia."
else
  echo "  FAIL: weaver exited $rc — a violation was found (see report above)."
fi
echo "========================================================"
echo "(cisco lab left running; use --down to destroy)"
exit "${rc:-1}"
