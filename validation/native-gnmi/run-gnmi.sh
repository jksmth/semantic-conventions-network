#!/usr/bin/env bash
# Real-NOS gNMI validation path:
#   SR Linux --gNMI subscribe--> gnmic --OTLP--> otelcol [OTTL] --OTLP--> weaver
#
#   ./run-gnmi.sh           deploy SR Linux (if needed), subscribe, map, live-check
#   ./run-gnmi.sh --down    destroy the SR Linux lab afterwards too
#
# Requires: docker (containerlab + gnmic + collector all run as containers).
set -euo pipefail
cd "$(dirname "$0")"

LAB_DIR="$(cd ../labs/srl && pwd)"
CLAB_IMAGE="${CLAB_IMAGE:-ghcr.io/srl-labs/clab:latest}"
GNMIC_IMAGE="${GNMIC_IMAGE:-ghcr.io/openconfig/gnmic:latest}"
TARGET="172.22.22.11"
DOWN=0
STREAM_SECONDS="${STREAM_SECONDS:-20}"
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

# 1. deploy SR Linux if not already running
if ! docker ps --format '{{.Names}}' | grep -q clab-srl-srl1; then
  echo "deploying SR Linux with containerlab (first boot ~1-2 min)..."
  clab deploy -t srl.clab.yml >/dev/null
fi

# 2. wait for the gNMI server to answer
echo "waiting for SR Linux gNMI on ${TARGET}:57400..."
ok=0
for _ in $(seq 1 30); do
  if docker run --rm --network srlmgmt "$GNMIC_IMAGE" \
       -a "${TARGET}:57400" -u admin -p 'NokiaSrl1!' --skip-verify -e json_ietf \
       get --path "/system/name/host-name" >/dev/null 2>&1; then ok=1; echo "  gNMI up"; break; fi
  sleep 4
done
[[ "$ok" == 1 ]] || echo "  (warning: gNMI not answering yet — continuing anyway)"

# 3. gnmic + collector + weaver
docker compose up -d >/dev/null
echo "gNMI subscribe + map for ${STREAM_SECONDS}s..."
sleep "$STREAM_SECONDS"

# 4. stop listener, read exit code
docker kill -s HUP gnmi-weaver >/dev/null 2>&1 || true
rc="$(docker wait gnmi-weaver 2>/dev/null || echo 1)"

# 5. report + verdict
echo "========================================================"
echo "  network.* live-check verdict (real NOS: SR Linux gNMI via gnmic)"
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
  echo "  (no report; check: docker logs gnmi-otelcol ; docker logs gnmic)"
fi
echo "--------------------------------------------------------"
if [[ "${samples_seen:-0}" == "0" ]]; then
  echo "  FAIL: no samples reached weaver (gNMI subscribe or export failed)."
  rc=1
elif [[ "$rc" == "0" ]]; then
  echo "  PASS: real-NOS gNMI telemetry is fully registry-conformant."
else
  echo "  FAIL: weaver exited $rc — a violation was found (see report above)."
fi
echo "========================================================"
echo "(SR Linux left running; use --down to destroy)"
exit "${rc:-1}"
