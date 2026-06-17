#!/usr/bin/env bash
# Native validation path — proves the same conformance claim as ../run.sh, but
# with ZERO engine code:
#
#   FRR lab (r1)  ->  otelcol-contrib [hostmetrics + OTTL crosswalk]
#                 ->  OTLP  ->  weaver registry live-check  ->  verdict
#
# Weaver's own exit code is the gate: non-zero iff any `violation` finding.
#
#   ./run-native.sh           boot lab (if needed), collect, map, live-check
#   ./run-native.sh --down    tear the lab + native stack down afterwards
#
# Requires: docker.
set -euo pipefail
cd "$(dirname "$0")"

LAB="../labs/frr"
DOWN=0
SCRAPE_SECONDS="${SCRAPE_SECONDS:-12}"
for a in "$@"; do
  case "$a" in --down) DOWN=1 ;; esac
done

cleanup() {
  docker compose down >/dev/null 2>&1 || true
  if [[ "$DOWN" == 1 ]]; then
    ( cd "$LAB" && docker compose down >/dev/null 2>&1 ) || true
    echo "lab + native stack torn down"
  fi
}
trap cleanup EXIT

mkdir -p out
rm -f out/* 2>/dev/null || true

# 1. lab up (creates the external `netlab` network the collector attaches to)
( cd "$LAB" && docker compose up -d >/dev/null )
echo "waiting for r1 to be up..."
for _ in $(seq 1 15); do
  docker exec netlab-r1 true >/dev/null 2>&1 && break
  sleep 1
done

# 2. start the native stack (weaver listener + collector sharing r1's netns)
docker compose up -d >/dev/null
echo "collecting + mapping for ${SCRAPE_SECONDS}s (hostmetrics -> OTTL -> OTLP -> weaver)..."
sleep "$SCRAPE_SECONDS"

# 3. stop the listener (SIGHUP is a documented stop condition) and read its
#    exit code: non-zero == a registry violation was seen.
docker kill -s HUP netlab-weaver >/dev/null 2>&1 || true
rc="$(docker wait netlab-weaver 2>/dev/null || echo 1)"

# 4. show the report Weaver wrote, then the verdict.
echo "========================================================"
echo "  network.* live-check verdict (native: collector + OTTL + OTLP)"
echo "========================================================"
report="$(ls -1 out/* 2>/dev/null | head -n1 || true)"
if [[ -n "$report" ]]; then
  python3 - "$report" <<'PY' || true
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"  (could not parse report: {e})"); sys.exit(0)
# Weaver writes {"samples": [...], "statistics": {...}}.
stats = data.get("statistics") if isinstance(data, dict) else None
if not stats:  # older/streamed shapes: a trailing stats-shaped object
    objs = data if isinstance(data, list) else [data]
    stats = next((o for o in reversed(objs)
                  if isinstance(o, dict) and "total_entities" in o), None)
if stats:
    lv = stats.get("advice_level_counts", {})
    nonreg = {k: stats.get(k) for k in
              ("seen_non_registry_metrics", "seen_non_registry_attributes")
              if stats.get(k)}
    seen = {k: v for k, v in stats.get("seen_registry_metrics", {}).items() if v}
    print(f"  samples:           {stats.get('total_entities')}  {stats.get('total_entities_by_type', {})}")
    print(f"  metrics matched:   {seen if seen else ' none'}")
    print(f"  advisories:        {stats.get('total_advisories')}  by-level={lv}")
    print(f"  registry coverage: {stats.get('registry_coverage', 0)*100:.1f}%")
    print(f"  non-registry names:{nonreg if nonreg else ' none'}")
    if stats.get("total_entities", 0) == 0:
        print("  WARNING: zero samples reached weaver — a PASS here is vacuous.")
else:
    print("  (no stats object in report; see out/)")
PY
else
  echo "  (no report file written; check: docker logs netlab-weaver)"
fi
echo "--------------------------------------------------------"
# Guard against a vacuous pass: weaver exits 0 on an empty stream, so treat
# "zero samples reached weaver" as a failure regardless of weaver's own code.
samples_seen=0
if [[ -n "$report" ]]; then
  samples_seen="$(python3 -c "import json;print((json.load(open('$report')).get('statistics') or {}).get('total_entities',0))" 2>/dev/null || echo 0)"
fi
if [[ "${samples_seen:-0}" == "0" ]]; then
  echo "  FAIL: no samples reached weaver — nothing was actually checked."
  echo "        (see: docker logs netlab-otelcol)"
  rc=1
elif [[ "$rc" == "0" ]]; then
  echo "  PASS: weaver found no violations — every emitted name is registry-defined."
else
  echo "  FAIL: weaver exited $rc — a violation was found (see report above)."
fi
echo "========================================================"
exit "${rc:-1}"
