#!/usr/bin/env bash
# T12 — sync (push, unchanged, modified, dry-run, pull, --delete, conflict, --force,
#             subdirectory tree, pull --dry-run, pull --delete, pull --force, errors)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T12_sync() {
    step "T12 — sync"

    # T12.1 — setup: local syncdir and remote syncroot collection
    mkdir -p "${TMPDIR_E2E}/syncdir"
    printf '<a/>' > "${TMPDIR_E2E}/syncdir/a.xml"
    printf '<b/>' > "${TMPDIR_E2E}/syncdir/b.xml"
    assert_exit0 "T12.1 setup: create remote syncroot collection" \
        "${EXSH[@]}" mkdir testcol:/syncroot
    ok "T12.1 local syncdir with a.xml and b.xml created"

    # T12.2 — first push: both files uploaded as new (single run, two checks)
    _run "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" testcol:/syncroot
    assert_in_last "↑ a.xml  (new)" "T12.2 sync push uploads a.xml as new"
    assert_in_last "↑ b.xml  (new)" "T12.2 sync push uploads b.xml as new"

    # T12.3 — remote listing shows both files after push (single run, two checks)
    _run "${EXSH[@]}" ls testcol:/syncroot
    assert_in_last "a.xml" "T12.3 ls syncroot shows a.xml"
    assert_in_last "b.xml" "T12.3 ls syncroot shows b.xml"

    # T12.4 — push again with no local changes: both files skipped (single run, two checks)
    _run "${EXSH[@]}" sync --verbose "${TMPDIR_E2E}/syncdir" testcol:/syncroot
    assert_in_last "= a.xml  (unchanged)" "T12.4 second push skips unchanged a.xml"
    assert_in_last "= b.xml  (unchanged)" "T12.4 second push skips unchanged b.xml"

    # T12.5 — modify a.xml locally and push: uploaded as modified, b.xml still skipped
    printf '<a2/>' > "${TMPDIR_E2E}/syncdir/a.xml"
    _run "${EXSH[@]}" sync --verbose "${TMPDIR_E2E}/syncdir" testcol:/syncroot
    assert_in_last "↑ a.xml  (modified)" "T12.5 push uploads modified a.xml"
    assert_in_last "= b.xml  (unchanged)" "T12.5 push skips unchanged b.xml"

    # T12.6 — modify b.xml locally; dry-run shows it would be uploaded but does not upload
    printf '<b2/>' > "${TMPDIR_E2E}/syncdir/b.xml"
    _run "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" testcol:/syncroot --dry-run
    assert_in_last "↑ b.xml  (modified)" "T12.6 dry-run shows b.xml as modified"
    # Verify nothing was actually uploaded: a second dry-run still shows the same
    _run "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" testcol:/syncroot --dry-run
    assert_in_last "↑ b.xml  (modified)" "T12.6 dry-run made no actual upload"

    # T12.7 — pull remote into a fresh local directory using testcol2 (fresh manifest)
    # Must run before T12.10 removes b.xml from remote
    mkdir -p "${TMPDIR_E2E}/pulldir"
    _run "${EXSH[@]}" sync testcol2:/syncroot "${TMPDIR_E2E}/pulldir"
    assert_in_last "↓ a.xml  (new)" "T12.7 pull downloads a.xml as new"
    assert_in_last "↓ b.xml  (new)" "T12.7 pull downloads b.xml as new"

    # T12.8 — pulled a.xml matches the local version (both are <a2/> after T12.5)
    assert_exit0 "T12.8 pulled a.xml matches local a.xml" \
        diff "${TMPDIR_E2E}/pulldir/a.xml" "${TMPDIR_E2E}/syncdir/a.xml"

    # T12.9 — real push after dry-run: b.xml should still be modified (not yet uploaded)
    _run "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" testcol:/syncroot
    assert_in_last "↑ b.xml  (modified)" "T12.9 real push after dry-run uploads b.xml"

    # T12.10 — remove b.xml locally and push with --delete; remote copy removed
    rm "${TMPDIR_E2E}/syncdir/b.xml"
    _run "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" testcol:/syncroot --delete
    assert_in_last "✗ b.xml  (deleted)" "T12.10 push --delete removes b.xml from remote"

    # T12.11 — verify b.xml is gone from remote listing
    assert_output_absent "b.xml" \
        "T12.11 ls syncroot no longer shows b.xml" \
        "${EXSH[@]}" ls testcol:/syncroot

    # T12.12 — conflict: edit a.xml on remote via REST, edit locally differently, push
    curl -sf -u "${ADMIN_AUTH}" -X PUT \
        -H "Content-Type: application/xml" \
        --data-binary '<a_remote_edit/>' \
        "${EXIST_URL}/db/testcol/syncroot/a.xml" >/dev/null
    printf '<a_local_edit/>' > "${TMPDIR_E2E}/syncdir/a.xml"
    assert_output "conflict" \
        "T12.12 push detects conflict when both sides changed" \
        "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" testcol:/syncroot

    # T12.13 — --force bypasses conflict: local a.xml uploaded despite remote divergence
    _run "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" testcol:/syncroot --force
    assert_in_last "↑ a.xml  (modified)" "T12.13 push --force uploads a.xml despite conflict"

    # T12.14 — both remote
    assert_output "both source and destination are remote" \
        "T12.14 sync both remote fails" \
        "${EXSH[@]}" sync testcol:/syncroot testcol2:/syncroot

    # T12.15 — both local
    assert_output "one of source or destination must be a remote collection" \
        "T12.15 sync both local fails" \
        "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" "${TMPDIR_E2E}/pulldir"

    # T12.16 — source is a file, not a directory
    assert_output "is not a directory" \
        "T12.16 sync source not a dir fails" \
        "${EXSH[@]}" sync "${TMPDIR_E2E}/hello.xml" testcol:/syncroot

    # T12.17 — unknown collection nick
    assert_output "collection 'ghost' not found" \
        "T12.17 sync unknown nick fails" \
        "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" ghost:/syncroot

    # ---------------------------------------------------------------------------
    # Subdirectory push / pull / --delete
    # ---------------------------------------------------------------------------

    # T12.18 — push a subdirectory: new remote collection and file created
    mkdir -p "${TMPDIR_E2E}/syncdir/subdir"
    printf '<c/>' > "${TMPDIR_E2E}/syncdir/subdir/c.xml"
    _run "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" testcol:/syncroot
    assert_in_last "+ subdir/  (new collection)" "T12.18 push creates new remote subcollection"
    assert_in_last "↑ subdir/c.xml  (new)" "T12.18 push uploads file in new subcollection"

    # T12.19 — remote listing shows the new subcollection
    assert_output "subdir/" \
        "T12.19 ls syncroot shows new subdir/" \
        "${EXSH[@]}" ls testcol:/syncroot

    # T12.20 — pull into fresh dir: local subdir created and file downloaded (single run)
    mkdir -p "${TMPDIR_E2E}/pulldir2"
    _run "${EXSH[@]}" sync testcol2:/syncroot "${TMPDIR_E2E}/pulldir2"
    assert_in_last "+ subdir/  (new directory)" "T12.20 pull creates local subdirectory"
    assert_in_last "↓ subdir/c.xml  (new)" "T12.20 pull downloads file in new subdirectory"

    # T12.21 — pulled c.xml content matches the local source
    assert_exit0 "T12.21 pulled subdir/c.xml matches local" \
        diff "${TMPDIR_E2E}/pulldir2/subdir/c.xml" "${TMPDIR_E2E}/syncdir/subdir/c.xml"

    # T12.22 — pull --dry-run shows pending downloads but writes nothing
    mkdir -p "${TMPDIR_E2E}/pulldir3"
    _run "${EXSH[@]}" sync testcol2:/syncroot "${TMPDIR_E2E}/pulldir3" --dry-run
    assert_in_last "↓ subdir/c.xml" "T12.22 pull --dry-run shows c.xml would be downloaded"
    if [[ ! -f "${TMPDIR_E2E}/pulldir3/subdir/c.xml" ]]; then
        ok "T12.22 pull --dry-run made no actual downloads"
    else
        fail "T12.22 pull --dry-run made no actual downloads (file unexpectedly written)"
    fi

    # T12.23 — pull --force re-downloads files already in manifest
    _run "${EXSH[@]}" sync testcol2:/syncroot "${TMPDIR_E2E}/pulldir2" --force
    assert_in_last "↓ subdir/c.xml  (modified)" "T12.23 pull --force re-downloads c.xml"

    # T12.24 — push --delete after removing subdir: file and empty collection removed from remote
    rm -rf "${TMPDIR_E2E}/syncdir/subdir"
    _run "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" testcol:/syncroot --delete
    assert_in_last "✗ subdir/c.xml  (deleted)" "T12.24 push --delete removes file in deleted subdir"
    assert_in_last "✗ subdir/  (empty collection deleted)" "T12.24 push --delete removes empty remote subdir"

    # T12.25 — ls no longer shows subdir/ after push --delete
    assert_output_absent "subdir/" \
        "T12.25 ls syncroot no longer shows subdir/ after push --delete" \
        "${EXSH[@]}" ls testcol:/syncroot

    # T12.26 — pull --delete removes local files and dirs absent from remote
    # pulldir2 still has subdir/c.xml from T12.20/T12.23; add an extra local-only file
    printf '<local_only/>' > "${TMPDIR_E2E}/pulldir2/local_only.xml"
    _run "${EXSH[@]}" sync testcol2:/syncroot "${TMPDIR_E2E}/pulldir2" --delete
    assert_in_last "✗ local_only.xml  (deleted)" "T12.26 pull --delete removes local-only file"
    assert_in_last "✗ subdir/c.xml  (deleted)" "T12.26 pull --delete removes stale subdir/c.xml"
    assert_in_last "✗ subdir/  (empty directory deleted)" "T12.26 pull --delete removes empty local subdir"
    if [[ ! -f "${TMPDIR_E2E}/pulldir2/local_only.xml" ]]; then
        ok "T12.26 local_only.xml removed from disk"
    else
        fail "T12.26 local_only.xml removed from disk (file still present)"
    fi

    # ---------------------------------------------------------------------------
    # Pull conflict and combined --delete --dry-run
    # ---------------------------------------------------------------------------

    # T12.27 — pull conflict: modify pulldir2/a.xml locally AND modify the remote copy,
    # then pull without --force → conflict detected on both sides
    printf '<a_local_pulldir/>' > "${TMPDIR_E2E}/pulldir2/a.xml"
    curl -sf -u "${ADMIN_AUTH}" -X PUT \
        -H "Content-Type: application/xml" \
        --data-binary '<a_remote_conflict/>' \
        "${EXIST_URL}/db/testcol/syncroot/a.xml" >/dev/null
    assert_output "conflict" \
        "T12.27 pull detects conflict when both sides changed since last sync" \
        "${EXSH[@]}" sync testcol2:/syncroot "${TMPDIR_E2E}/pulldir2"

    # ---------------------------------------------------------------------------
    # XML well-formedness validation
    # ---------------------------------------------------------------------------

    # T12.29 — malformed XML file is skipped during push
    printf '<unclosed>' > "${TMPDIR_E2E}/syncdir/bad.xml"
    _run "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" testcol:/syncroot
    assert_in_last "! bad.xml  (not well-formed XML, skipping)" "T12.29 push skips malformed XML with ! prefix"
    assert_in_last "1 invalid xml" "T12.29 summary counts invalid xml"
    # Confirm the file was not uploaded
    local _bad_status
    _bad_status="$(curl -s -o /dev/null -w "%{http_code}" -u "${ADMIN_AUTH}" "${EXIST_URL}/db/testcol/syncroot/bad.xml")"
    if [[ "${_bad_status}" == "404" ]]; then
        ok "T12.29 bad.xml not present on server after skipped push"
    else
        fail "T12.29 bad.xml not present on server after skipped push (got HTTP ${_bad_status})"
    fi

    # T12.30 — --fail-fast stops on first problem and exits 1
    printf '<another_broken>' > "${TMPDIR_E2E}/syncdir/c_bad.xml"
    local _ff_output _ff_code=0
    _ff_output="$("${EXSH[@]}" sync --fail-fast "${TMPDIR_E2E}/syncdir" testcol:/syncroot 2>&1)" || _ff_code=$?
    if [[ ${_ff_code} -ne 0 ]]; then
        ok "T12.30 sync --fail-fast exits non-zero on invalid XML"
    else
        fail "T12.30 sync --fail-fast exits non-zero on invalid XML (expected exit 1, got 0)"
    fi
    # Clean up test files
    rm -f "${TMPDIR_E2E}/syncdir/bad.xml" "${TMPDIR_E2E}/syncdir/c_bad.xml"

    # T12.31 — --jobs flag: upload a new file with a custom worker count
    printf '<d/>' > "${TMPDIR_E2E}/syncdir/d.xml"
    _run "${EXSH[@]}" sync --jobs 2 "${TMPDIR_E2E}/syncdir" testcol:/syncroot
    assert_in_last "↑ d.xml  (new)" "T12.31 sync --jobs 2 uploads new file with custom workers"
    rm -f "${TMPDIR_E2E}/syncdir/d.xml"

    # T12.28 — push --delete --dry-run: remote extra file logged as deleted but not removed
    curl -sf -u "${ADMIN_AUTH}" -X PUT \
        -H "Content-Type: application/xml" \
        --data-binary '<extra/>' \
        "${EXIST_URL}/db/testcol/syncroot/dryextra.xml" >/dev/null
    assert_output "✗ dryextra.xml  (deleted)" \
        "T12.28 push --delete --dry-run shows dryextra.xml as deleted" \
        "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" testcol:/syncroot --delete --dry-run
    local _dryextra_status
    _dryextra_status="$(curl -s -o /dev/null -w "%{http_code}" -u "${ADMIN_AUTH}" "${EXIST_URL}/db/testcol/syncroot/dryextra.xml")"
    if [[ "${_dryextra_status}" == "200" ]]; then
        ok "T12.28 dryextra.xml still present on server after --delete --dry-run"
    else
        fail "T12.28 dryextra.xml still present on server after --delete --dry-run (got HTTP ${_dryextra_status})"
    fi
}
