#!/usr/bin/env bash
# End-to-end tests for exsh against a live eXist-db instance in Docker.
# See e2e_plan.md for the task list and architecture notes.
#
# Usage:
#   bash scripts/e2e.sh              # run against existdb/existdb:release (default)
#   bash scripts/e2e.sh --latest     # run against existdb/existdb:latest
#   bash scripts/e2e.sh --elemental  # run against evolvedbinary/elemental:latest
#   bash scripts/e2e.sh --no-pull    # skip docker pull (faster re-runs)
#   bash scripts/e2e.sh --list-images # list available image options and exit
set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing — must happen before mktemp/trap so --list-images can
# exit cleanly without triggering teardown.
# ---------------------------------------------------------------------------

_IMAGE_RELEASE="existdb/existdb:release"
_IMAGE_LATEST="existdb/existdb:latest"
_IMAGE_ELEMENTAL="evolvedbinary/elemental:latest"

IMAGE="${_IMAGE_RELEASE}"
NO_PULL=false

for _arg in "$@"; do
    case "${_arg}" in
        --release)     IMAGE="${_IMAGE_RELEASE}" ;;
        --latest)      IMAGE="${_IMAGE_LATEST}" ;;
        --elemental)   IMAGE="${_IMAGE_ELEMENTAL}" ;;
        --no-pull)     NO_PULL=true ;;
        --list-images)
            printf "Available images (pass the flag to select):\n"
            printf "  %-13s  %s  (default)\n" "--release"   "${_IMAGE_RELEASE}"
            printf "  %-13s  %s\n"             "--latest"    "${_IMAGE_LATEST}"
            printf "  %-13s  %s\n"             "--elemental" "${_IMAGE_ELEMENTAL}"
            exit 0
            ;;
        *) printf "Unknown flag: %s\n" "${_arg}" >&2; exit 1 ;;
    esac
done
export IMAGE NO_PULL

# ---------------------------------------------------------------------------
# Paths and helpers
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=e2e/lib.sh
source "${SCRIPT_DIR}/e2e/lib.sh"
# shellcheck source=e2e/docker.sh
source "${SCRIPT_DIR}/e2e/docker.sh"

# ---------------------------------------------------------------------------
# exsh invocation — use "uv run exsh" in dev, override for an installed binary:
#   EXSH=(exsh) bash scripts/e2e.sh
# ---------------------------------------------------------------------------

PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
EXSH=(uv run --directory "${PROJECT_ROOT}" exsh)

# ---------------------------------------------------------------------------
# Config isolation — tests never touch the real config or cache.
# EXSH_CONFIG points to a temp file; that file declares cache_dir so the
# cache is also isolated inside TMPDIR_E2E.
# ---------------------------------------------------------------------------

TMPDIR_E2E="$(mktemp -d)"
export EXSH_CONFIG="${TMPDIR_E2E}/config.toml"
printf 'cache_dir = "%s/cache"\n' "${TMPDIR_E2E}" > "${EXSH_CONFIG}"

# Trap here so TMPDIR_E2E is always removed, even if sourcing a section fails.
trap teardown EXIT

# ---------------------------------------------------------------------------
# Source section files
# ---------------------------------------------------------------------------

source "${SCRIPT_DIR}/e2e/sections/T02_server.sh"
source "${SCRIPT_DIR}/e2e/sections/T03_collection.sh"
source "${SCRIPT_DIR}/e2e/sections/T04_ls.sh"
source "${SCRIPT_DIR}/e2e/sections/T05_put.sh"
source "${SCRIPT_DIR}/e2e/sections/T06_ls_after.sh"
source "${SCRIPT_DIR}/e2e/sections/T07_cat.sh"
source "${SCRIPT_DIR}/e2e/sections/T08_cp.sh"
source "${SCRIPT_DIR}/e2e/sections/T09_rm.sh"
source "${SCRIPT_DIR}/e2e/sections/T10_mkdir.sh"
source "${SCRIPT_DIR}/e2e/sections/T11_edit.sh"
source "${SCRIPT_DIR}/e2e/sections/T12_sync.sh"
source "${SCRIPT_DIR}/e2e/sections/T13_mv.sh"
source "${SCRIPT_DIR}/e2e/sections/T14_exec.sh"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    echo "Using image: ${IMAGE}"
    start_existdb
    bootstrap

    section_T02_server
    section_T03_collection
    section_T04_ls
    section_T05_put
    section_T06_ls_after
    section_T07_cat
    section_T08_cp
    section_T09_rm
    section_T10_mkdir
    section_T11_edit
    section_T12_sync
    section_T13_mv
    section_T14_exec
}

main
