#!/usr/bin/env bash
# End-to-end tests for exsh against a live eXist-db instance in Docker.
# See e2e_plan.md for the task list and architecture notes.
#
# Usage:
#   bash scripts/e2e.sh           # run all sections
#   bash scripts/e2e.sh --no-pull # skip docker pull (faster re-runs)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Source helpers and Docker lifecycle
# ---------------------------------------------------------------------------

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
# Source section files (add one line per task as sections are implemented)
# ---------------------------------------------------------------------------

source "${SCRIPT_DIR}/e2e/sections/T02_server.sh"
source "${SCRIPT_DIR}/e2e/sections/T03_collection.sh"
source "${SCRIPT_DIR}/e2e/sections/T04_ls.sh"
source "${SCRIPT_DIR}/e2e/sections/T05_put.sh"
# source "${SCRIPT_DIR}/e2e/sections/T06_ls_after.sh"
# source "${SCRIPT_DIR}/e2e/sections/T07_cat.sh"
# source "${SCRIPT_DIR}/e2e/sections/T08_cp.sh"
# source "${SCRIPT_DIR}/e2e/sections/T09_rm.sh"
# source "${SCRIPT_DIR}/e2e/sections/T10_mkdir.sh"
# source "${SCRIPT_DIR}/e2e/sections/T11_edit.sh"
# source "${SCRIPT_DIR}/e2e/sections/T12_sync.sh"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    start_existdb "${1:-}"
    bootstrap

    # Section calls go here (uncomment as sections are implemented):
    section_T02_server
    section_T03_collection
    section_T04_ls
    section_T05_put
    # section_T06_ls_after
    # section_T07_cat
    # section_T08_cp
    # section_T09_rm
    # section_T10_mkdir
    # section_T11_edit
    # section_T12_sync

    echo ""
    echo "Scaffold OK — Docker up, helpers verified, teardown wired."
}

main "$@"
