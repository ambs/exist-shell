#!/usr/bin/env bash
# T11 — edit (modified, no-change, editor error, not-found)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T11_edit() {
    step "T11 — edit"

    # T11.1 — create fake editor: replaces "world" with "eXist" using perl
    # (perl -i avoids BSD/GNU sed -i incompatibility)
    printf '#!/usr/bin/env bash\nperl -i -pe "s/world/eXist/" "$1"\n' \
        > "${TMPDIR_E2E}/fake_editor.sh"
    chmod +x "${TMPDIR_E2E}/fake_editor.sh"
    ok "T11.1 fake editor script created"

    # T11.2 — editor modifies file → re-uploaded
    assert_exit0 "T11.2 edit with modifying editor succeeds" \
        env EDITOR="${TMPDIR_E2E}/fake_editor.sh" "${EXSH[@]}" edit testcol:/hello.xml

    # T11.3 — verify change was persisted
    assert_output "eXist" \
        "T11.3 cat after edit shows updated content" \
        "${EXSH[@]}" cat testcol:/hello.xml

    # T11.4 — editor exits 0 without touching the file → No changes.
    assert_output "No changes." \
        "T11.4 edit with no-op editor prints No changes." \
        env EDITOR=true "${EXSH[@]}" edit testcol:/hello.xml

    # T11.5 — editor exits non-zero → error reported
    assert_output "editor exited with code" \
        "T11.5 edit with failing editor reports exit code" \
        env EDITOR=false "${EXSH[@]}" edit testcol:/hello.xml

    # T11.6 — document not found
    assert_output "not found in collection" \
        "T11.6 edit non-existent document fails" \
        env EDITOR=true "${EXSH[@]}" edit testcol:/nonexistent.xml

    # T11.7 — unknown collection nick
    assert_output "collection 'ghost' not found" \
        "T11.7 edit unknown nick fails" \
        env EDITOR=true "${EXSH[@]}" edit ghost:/hello.xml

    # T11.8 — $VISUAL takes precedence over $EDITOR: fake_editor.sh is used, not EDITOR=false
    assert_exit0 "T11.8 \$VISUAL wins over \$EDITOR (fake_editor used, not EDITOR=false)" \
        env VISUAL="${TMPDIR_E2E}/fake_editor.sh" EDITOR=false "${EXSH[@]}" edit testcol:/hello.xml

    # T11.9 — editor that produces malformed XML: exsh warns and re-opens; second save is valid
    # First call: writes malformed XML. Second call (after user presses Enter): writes valid XML.
    local _call_count_file="${TMPDIR_E2E}/t11_calls"
    printf '0' > "${_call_count_file}"
    printf '#!/usr/bin/env bash\n' \
        'n=$(cat "%s")\n' \
        'if [[ $n -eq 0 ]]; then printf "<broken>" > "$1"; else printf "<repaired/>\\n" > "$1"; fi\n' \
        'printf "%s" $((n+1)) > "%s"\n' \
        "${_call_count_file}" "${_call_count_file}" \
        > "${TMPDIR_E2E}/edit_malformed.sh"
    chmod +x "${TMPDIR_E2E}/edit_malformed.sh"

    local _edit_output
    _edit_output="$(printf '\n' | env EDITOR="${TMPDIR_E2E}/edit_malformed.sh" "${EXSH[@]}" edit testcol:/hello.xml 2>&1)"
    local _edit_code=$?
    if [[ ${_edit_code} -eq 0 ]] && printf '%s' "${_edit_output}" | grep -q "not well-formed XML"; then
        ok "T11.9 edit warns on malformed XML and re-opens editor"
    else
        fail "T11.9 edit warns on malformed XML and re-opens editor (exit=${_edit_code}, output=${_edit_output})"
    fi

    # T11.10 — --allow-malformed uploads without validation
    printf '#!/usr/bin/env bash\nprintf "<broken>" > "$1"\n' > "${TMPDIR_E2E}/always_broken.sh"
    chmod +x "${TMPDIR_E2E}/always_broken.sh"
    assert_exit0 "T11.10 edit --allow-malformed uploads malformed XML" \
        env EDITOR="${TMPDIR_E2E}/always_broken.sh" "${EXSH[@]}" edit testcol:/hello.xml --allow-malformed
}
