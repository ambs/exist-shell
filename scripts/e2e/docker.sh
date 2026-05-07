#!/usr/bin/env bash
# Docker/Colima lifecycle for e2e tests.
# Sourced by scripts/e2e.sh — do not execute directly.

CONTAINER=exsh-e2e
IMAGE=existdb/existdb:latest
PORT=8080
EXIST_URL="http://localhost:${PORT}/exist/rest"
ADMIN_AUTH="admin:"

# ---------------------------------------------------------------------------
# Colima (macOS only)
# ---------------------------------------------------------------------------

_ensure_colima() {
    if ! command -v colima &>/dev/null; then
        echo "colima not found — install it with: brew install colima" >&2
        exit 1
    fi
    if ! colima status 2>/dev/null | grep -q "Running"; then
        echo "Starting Colima..."
        colima start
    fi
}

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

start_existdb() {
    local no_pull="${1:-}"

    if [[ "$(uname)" == "Darwin" ]]; then
        _ensure_colima
    fi

    [[ "$no_pull" != "--no-pull" ]] && docker pull "$IMAGE"

    # Remove any leftover container from a previous run.
    docker rm -f "$CONTAINER" &>/dev/null || true

    docker run -d \
        --name "$CONTAINER" \
        -p "${PORT}:8080" \
        "$IMAGE" >/dev/null

    echo -n "Waiting for eXist-db"
    local i=0
    until curl -sf "${EXIST_URL}/db" -u "${ADMIN_AUTH}" >/dev/null 2>&1; do
        sleep 2
        i=$(( i + 2 ))
        echo -n "."
        if [[ $i -ge 60 ]]; then
            echo " TIMEOUT"
            docker logs "$CONTAINER" | tail -30
            exit 1
        fi
    done
    echo " ready."
}

bootstrap() {
    # Create /db/testcol so "exsh collection add" has a real collection to register.
    # Use PUT .keep + DELETE to avoid the stray resource that PUT /path/ (trailing
    # slash, empty body) creates in eXist, which would mask the collection listing.
    curl -sf -u "${ADMIN_AUTH}" -X PUT \
        -H "Content-Type: application/octet-stream" \
        --data-binary "" \
        "${EXIST_URL}/db/testcol/.keep" >/dev/null
    curl -sf -u "${ADMIN_AUTH}" -X DELETE "${EXIST_URL}/db/testcol/.keep" >/dev/null
}

teardown() {
    print_summary
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    rm -rf "${TMPDIR_E2E:-}"
    [[ $FAIL -eq 0 ]] && exit 0 || exit 1
}
