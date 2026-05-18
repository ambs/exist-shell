#!/usr/bin/env bash
# T13 — mv (document rename, document move, trailing slash, collection rename,
#           collection move with contents, multi-level tree move, errors)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T13_mv() {
    step "T13 — mv"

    # ---------------------------------------------------------------------------
    # Setup: upload documents that will be used as mv sources.
    # ---------------------------------------------------------------------------
    printf '<mv>test</mv>' > "${TMPDIR_E2E}/mv_src.xml"

    assert_exit0 "T13 setup: upload mv_src.xml" \
        "${EXSH[@]}" put testcol:/mv_src.xml -f "${TMPDIR_E2E}/mv_src.xml"

    assert_exit0 "T13 setup: upload mv_src2.xml for move test" \
        "${EXSH[@]}" put testcol:/mv_src2.xml -f "${TMPDIR_E2E}/mv_src.xml"

    # ---------------------------------------------------------------------------
    # T13.1 — rename a document within the same collection
    # ---------------------------------------------------------------------------
    assert_exit0 "T13.1 mv renames a document" \
        "${EXSH[@]}" mv testcol:/mv_src.xml testcol:/mv_renamed.xml

    # T13.2 — new name appears in listing
    assert_output "mv_renamed.xml" \
        "T13.2 mv_renamed.xml appears in ls after rename" \
        "${EXSH[@]}" ls testcol

    # T13.3 — old name is gone
    assert_output_absent "mv_src.xml" \
        "T13.3 mv_src.xml no longer in ls after rename" \
        "${EXSH[@]}" ls testcol

    # T13.4 — content is preserved (cat the renamed file)
    assert_output "<mv>test</mv>" \
        "T13.4 renamed file content is intact" \
        "${EXSH[@]}" cat testcol:/mv_renamed.xml

    # ---------------------------------------------------------------------------
    # T13.5 — move a document into a subcollection using trailing slash
    # ---------------------------------------------------------------------------
    assert_exit0 "T13.5 setup: create subcollection mv_dest" \
        "${EXSH[@]}" mkdir testcol:/mv_dest

    assert_exit0 "T13.6 mv moves document into collection (trailing slash)" \
        "${EXSH[@]}" mv testcol:/mv_src2.xml "testcol:/mv_dest/"

    # T13.7 — file appears at the expected destination path
    assert_output "mv_src2.xml" \
        "T13.7 moved file appears in ls mv_dest" \
        "${EXSH[@]}" ls "testcol:/mv_dest"

    # T13.8 — source path is gone
    assert_output_absent "mv_src2.xml" \
        "T13.8 mv_src2.xml no longer at testcol root after move" \
        "${EXSH[@]}" ls testcol

    # ---------------------------------------------------------------------------
    # T13.9 — rename a document to a different path (move + rename in one step)
    # ---------------------------------------------------------------------------
    assert_exit0 "T13.9 setup: upload doc for path-change test" \
        "${EXSH[@]}" put testcol:/mv_path_src.xml -f "${TMPDIR_E2E}/mv_src.xml"

    assert_exit0 "T13.10 mv moves and renames in one step" \
        "${EXSH[@]}" mv testcol:/mv_path_src.xml testcol:/mv_dest/mv_path_dst.xml

    assert_output "mv_path_dst.xml" \
        "T13.10 mv_path_dst.xml appears at new location" \
        "${EXSH[@]}" ls "testcol:/mv_dest"

    assert_output_absent "mv_path_src.xml" \
        "T13.10 mv_path_src.xml gone from root" \
        "${EXSH[@]}" ls testcol

    # ---------------------------------------------------------------------------
    # T13.11 — rename a collection (mv renames the whole collection)
    # ---------------------------------------------------------------------------
    assert_exit0 "T13.11 setup: create collection mv_col with a document" \
        "${EXSH[@]}" put testcol:/mv_col/inside.xml -f "${TMPDIR_E2E}/mv_src.xml"

    assert_exit0 "T13.12 mv renames a collection" \
        "${EXSH[@]}" mv testcol:/mv_col testcol:/mv_col_renamed

    # T13.13 — renamed collection appears in root listing
    assert_output "mv_col_renamed" \
        "T13.13 mv_col_renamed appears in ls after collection rename" \
        "${EXSH[@]}" ls testcol

    # T13.14 — original collection name is gone
    assert_output_absent "mv_col" \
        "T13.14 mv_col no longer in ls after rename" \
        "${EXSH[@]}" ls testcol

    # T13.15 — document inside renamed collection is still accessible
    assert_output "<mv>test</mv>" \
        "T13.15 document inside renamed collection is intact" \
        "${EXSH[@]}" cat testcol:/mv_col_renamed/inside.xml

    # ---------------------------------------------------------------------------
    # T13.16 — move a collection with multiple documents into another collection
    # ---------------------------------------------------------------------------
    assert_exit0 "T13.16 setup: create mv_multi with two documents" \
        "${EXSH[@]}" put testcol:/mv_multi/a.xml -f "${TMPDIR_E2E}/mv_src.xml"
    assert_exit0 "T13.16 setup: second document in mv_multi" \
        "${EXSH[@]}" put testcol:/mv_multi/b.xml -f "${TMPDIR_E2E}/mv_src.xml"

    assert_exit0 "T13.16 setup: create mv_parent collection for destination" \
        "${EXSH[@]}" mkdir testcol:/mv_parent

    assert_exit0 "T13.17 mv moves a collection with documents into another collection (trailing slash)" \
        "${EXSH[@]}" mv testcol:/mv_multi "testcol:/mv_parent/"

    assert_output "mv_multi" \
        "T13.17 mv_multi appears inside mv_parent" \
        "${EXSH[@]}" ls testcol:/mv_parent

    assert_output_absent "mv_multi" \
        "T13.17 mv_multi is gone from testcol root" \
        "${EXSH[@]}" ls testcol

    # T13.18 — documents inside moved collection are accessible at new path
    assert_output "a.xml" \
        "T13.18 a.xml accessible inside moved collection" \
        "${EXSH[@]}" ls testcol:/mv_parent/mv_multi

    assert_output "b.xml" \
        "T13.18 b.xml accessible inside moved collection" \
        "${EXSH[@]}" ls testcol:/mv_parent/mv_multi

    # ---------------------------------------------------------------------------
    # T13.19 — move a collection that contains subcollections (multi-level tree)
    # ---------------------------------------------------------------------------
    assert_exit0 "T13.19 setup: create nested tree mv_tree/sub/deep.xml" \
        "${EXSH[@]}" put testcol:/mv_tree/sub/deep.xml -f "${TMPDIR_E2E}/mv_src.xml"
    assert_exit0 "T13.19 setup: root-level doc in mv_tree" \
        "${EXSH[@]}" put testcol:/mv_tree/root.xml -f "${TMPDIR_E2E}/mv_src.xml"

    assert_exit0 "T13.19 mv moves multi-level collection tree" \
        "${EXSH[@]}" mv testcol:/mv_tree testcol:/mv_tree_moved

    # Source is gone
    assert_output_absent "mv_tree" \
        "T13.19 mv_tree no longer in testcol root after move" \
        "${EXSH[@]}" ls testcol

    # Destination exists with root-level doc
    assert_output "root.xml" \
        "T13.19 root.xml accessible at destination root" \
        "${EXSH[@]}" ls testcol:/mv_tree_moved

    # Subcollection exists at destination
    assert_output "sub" \
        "T13.19 subcollection sub present inside mv_tree_moved" \
        "${EXSH[@]}" ls testcol:/mv_tree_moved

    # Deep document is accessible at full new path
    assert_output "<mv>test</mv>" \
        "T13.19 deep document content intact after multi-level move" \
        "${EXSH[@]}" cat testcol:/mv_tree_moved/sub/deep.xml

    # ---------------------------------------------------------------------------
    # Error cases
    # ---------------------------------------------------------------------------

    # T13.20 — both paths local
    assert_output "remote" \
        "T13.20 mv with both local paths fails" \
        "${EXSH[@]}" mv "${TMPDIR_E2E}/mv_src.xml" "${TMPDIR_E2E}/mv_dst.xml"

    # T13.21 — unknown collection nick
    assert_output "collection 'ghost' not found" \
        "T13.21 mv unknown source nick fails" \
        "${EXSH[@]}" mv ghost:/doc.xml testcol:/doc.xml

    # T13.22 — path traversal in source
    assert_output "path traversal not allowed" \
        "T13.22 mv path traversal in source rejected" \
        "${EXSH[@]}" mv "testcol:/../escape.xml" testcol:/dst.xml

    # T13.23 — source document does not exist
    assert_output "not found" \
        "T13.23 mv nonexistent source fails" \
        "${EXSH[@]}" mv testcol:/nonexistent_mv.xml testcol:/dst.xml
}
