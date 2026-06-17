#!/usr/bin/env bash
# Weaver resolve/check invocation (validation-driven check 1).
#
# Runs the OpenTelemetry Weaver semantic-convention tooling over the registry
# at `model/` (the registry root holding manifest.yaml). This is the
# reference-resolution and well-formedness gate behind Property 11 (the
# post-sweep registry resolves cleanly: zero broken refs, zero validation
# errors) and the backstop for Properties 2/6/10.
#
# There is no repo Makefile; Weaver is invoked directly via Docker, matching
# the sibling `otel-semantic-conventions` repos which pin `otel/weaver:v0.23.0`.
#
# Usage:
#   harness/weaver_check.sh           # registry check (well-formedness + policy)
#   harness/weaver_check.sh resolve   # registry resolve (full reference resolution)
#   WEAVER_VERSION=v0.24.0 harness/weaver_check.sh   # override pinned version
#
# Exit code is Weaver's: 0 = clean (zero errors / zero broken refs).

set -euo pipefail

WEAVER_IMAGE="${WEAVER_IMAGE:-otel/weaver}"
WEAVER_VERSION="${WEAVER_VERSION:-v0.23.0}"   # pinned to match sibling repos
REGISTRY_DIR="${REGISTRY_DIR:-model}"

# Resolve the repo root from this script's location:
#   harness -> <spec> -> specs -> .kiro -> <repo root>
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

SUBCMD="${1:-check}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found on PATH; Weaver runs via the ${WEAVER_IMAGE}:${WEAVER_VERSION} image." >&2
  exit 127
fi

if [[ ! -f "${REPO_ROOT}/${REGISTRY_DIR}/manifest.yaml" ]]; then
  echo "ERROR: no registry manifest at ${REGISTRY_DIR}/manifest.yaml (repo root: ${REPO_ROOT})." >&2
  exit 2
fi

echo "Weaver ${SUBCMD} over '${REGISTRY_DIR}' using ${WEAVER_IMAGE}:${WEAVER_VERSION}"
echo "Repo root: ${REPO_ROOT}"

case "${SUBCMD}" in
  check)
    exec docker run --rm -v "${REPO_ROOT}:/home/weaver" \
      "${WEAVER_IMAGE}:${WEAVER_VERSION}" \
      registry check --registry "${REGISTRY_DIR}"
    ;;
  resolve)
    exec docker run --rm -v "${REPO_ROOT}:/home/weaver" \
      "${WEAVER_IMAGE}:${WEAVER_VERSION}" \
      registry resolve --registry "${REGISTRY_DIR}" --format yaml
    ;;
  *)
    echo "ERROR: unknown subcommand '${SUBCMD}' (expected 'check' or 'resolve')." >&2
    exit 2
    ;;
esac
