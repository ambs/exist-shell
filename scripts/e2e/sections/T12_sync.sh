#!/usr/bin/env bash
# T12 — sync (push, unchanged, modified, dry-run, pull, --delete, conflict, --force, errors)
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
    _run "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" testcol:/syncroot
    assert_in_last "= a.xml  (unchanged)" "T12.4 second push skips unchanged a.xml"
    assert_in_last "= b.xml  (unchanged)" "T12.4 second push skips unchanged b.xml"

    # T12.5 — modify a.xml locally and push: uploaded as modified, b.xml still skipped
    printf '<a2/>' > "${TMPDIR_E2E}/syncdir/a.xml"
    _run "${EXSH[@]}" sync "${TMPDIR_E2E}/syncdir" testcol:/syncroot
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
}
