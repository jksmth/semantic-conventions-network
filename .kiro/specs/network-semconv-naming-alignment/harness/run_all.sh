#!/usr/bin/env bash
# Run all three validation-driven checks (Weaver, token scan, field-diff).
#
# Intended for the validation tasks (13.1-13.3). Each check reports its own
# pass/fail; the script exits non-zero if any gate fails.
#
# Flags:
#   --assert-zero          pass --assert-zero to the token scan (post-sweep gate)
#   --baseline <dir>       baseline dir for the field-diff (else uses git HEAD)
#
# PyYAML is provisioned via `uv run --with pyyaml`.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ASSERT_ZERO=0
BASELINE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --assert-zero) ASSERT_ZERO=1; shift ;;
    --baseline) BASELINE="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

PY="uv run --with pyyaml --no-project python3"
rc=0

echo "==================================================================="
echo "1/3  Weaver registry check"
echo "==================================================================="
if ! "${SCRIPT_DIR}/weaver_check.sh" check; then
  echo ">> Weaver check FAILED"; rc=1
fi

echo
echo "==================================================================="
echo "2/3  Complete-token occurrence scan"
echo "==================================================================="
SCAN_ARGS=()
[[ "${ASSERT_ZERO}" -eq 1 ]] && SCAN_ARGS+=(--assert-zero)
if ! (cd "${SCRIPT_DIR}" && ${PY} token_scan.py "${SCAN_ARGS[@]}"); then
  echo ">> Token scan FAILED"; rc=1
fi

echo
echo "==================================================================="
echo "3/3  Structured field-diff (name-only preservation)"
echo "==================================================================="
DIFF_ARGS=()
if [[ -n "${BASELINE}" ]]; then
  DIFF_ARGS+=(--baseline "${BASELINE}")
fi
if ! (cd "${SCRIPT_DIR}" && ${PY} field_diff.py diff "${DIFF_ARGS[@]}"); then
  echo ">> Field-diff FAILED"; rc=1
fi

echo
if [[ "${rc}" -eq 0 ]]; then
  echo "ALL CHECKS PASSED"
else
  echo "ONE OR MORE CHECKS FAILED"
fi
exit "${rc}"
