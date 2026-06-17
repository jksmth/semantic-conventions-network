#!/usr/bin/env bash
# Validation gate. Default is LIVE and direct:
#
#   running device  ->  collect  ->  map to network.*  ->  weaver live-check  ->  verdict
#
# Nothing is committed in the live path; the device is the source of truth.
#
#   ./run.sh              boot the lab (if needed), collect live, validate
#   ./run.sh --offline    use the committed fixtures snapshot (CI without the lab)
#   ./run.sh --capture    boot the lab, refresh the fixtures snapshot, exit
#   ./run.sh --down       tear the lab down afterwards
#
# Requires: docker, python3.
set -euo pipefail
cd "$(dirname "$0")"

REPO_ROOT="$(cd .. && pwd)"
WEAVER_IMAGE="${WEAVER_IMAGE:-otel/weaver:latest}"
LAB="labs/frr"
MODE="live"
DOWN=0
CAPTURE=0
for a in "$@"; do
  case "$a" in
    --offline) MODE="offline" ;;
    --capture) CAPTURE=1 ;;
    --down) DOWN=1 ;;
  esac
done

ensure_venv() {
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
    ./.venv/bin/pip -q install pyyaml
  fi
}

boot_lab() {
  ( cd "$LAB" && docker compose up -d >/dev/null )
  echo "waiting for BGP to establish..."
  for _ in $(seq 1 30); do
    state=$(docker exec netlab-r1 vtysh -c "show ip bgp summary json" 2>/dev/null \
      | ./.venv/bin/python -c "import sys,json;d=json.load(sys.stdin);print(list(d['ipv4Unicast']['peers'].values())[0]['state'])" 2>/dev/null || true)
    [[ "$state" == "Established" ]] && { echo "  BGP Established"; return; }
    sleep 2
  done
  echo "  (warning: BGP not Established yet — continuing anyway)"
}

teardown() { ( cd "$LAB" && docker compose down >/dev/null 2>&1 ); echo "lab torn down"; }

ensure_venv

if [[ "$CAPTURE" == 1 ]]; then
  boot_lab
  ./.venv/bin/python engine/run.py --capture
  [[ "$DOWN" == 1 ]] && teardown
  exit 0
fi

[[ "$MODE" == "live" ]] && boot_lab

# 1. reconciliation — do the independent methods converge on one identity?
./.venv/bin/python engine/reconcile.py --mode "$MODE"

# 2. map -> live-check, streamed via stdin (no committed intermediate)
REPORT="$(mktemp)"
./.venv/bin/python engine/run.py --mode "$MODE" \
  | docker run --rm -i -v "$REPO_ROOT":/work -w /work "$WEAVER_IMAGE" --quiet registry live-check \
      -r model --input-source stdin --input-format json --format json \
  > "$REPORT" 2>/dev/null

# 3. verdict
./.venv/bin/python engine/report.py "$REPORT"
rc=$?
rm -f "$REPORT"

[[ "$DOWN" == 1 ]] && teardown
exit $rc
