"""Shell completion helpers for eXist collection and document paths."""

from typing import Literal

from exist_shell.cache import get_cached_groups, get_cached_prefix_match, get_cached_users, set_cached, set_cached_groups, set_cached_users
from exist_shell.client import DEFAULT_CHILD_NAMES_LIMIT, ExistClient
from exist_shell.config import Config
from exist_shell.models import CollectionEntry

Kind = Literal["any", "collection", "resource"]

# A tab press blocks the shell for up to connect + read timeout, so connect
# stays short (an unreachable server should fail fast) while read allows
# margin for large/cold listings (a full unfiltered listing measured ~6.9s
# wall against a ~222k-resource collection).
_COMPLETION_CONNECT_TIMEOUT = 2.0
_COMPLETION_READ_TIMEOUT = 10.0

# Typer's stock bash completion script does two things that break on exsh's
# "nick:path" argument syntax, since ":" is one of bash's default
# COMP_WORDBREAKS characters:
#   1. It drives the completion subprocess from bash's own COMP_WORDS/
#      COMP_CWORD, which arrive pre-fragmented on ":" (e.g. "dlp" ":" "acad"
#      instead of "dlp:acad"), so exsh can never see the full word.
#   2. Even once exsh is driven correctly (by rebuilding the word list from
#      COMP_LINE/COMP_POINT, which COMP_WORDBREAKS doesn't affect), bash
#      still only *inserts* completions in place of the COMP_WORDBREAKS
#      fragment ("acad"), not the full word. Handing back full "nick:path"
#      candidates unmodified makes bash insert them after "dlp:" instead of
#      over it, producing "dlp:dlp:...".
# Both are fixed here in one script, with the fix scoped to the exsh
# completion function only — no global COMP_WORDBREAKS change.
_FIXED_COMPLETION_SCRIPT_BASH = """
%(complete_func)s() {
    local -a __exsh_words
    local __exsh_cword __exsh_full

    if declare -F _get_comp_words_by_ref >/dev/null 2>&1; then
        # bash-completion is loaded: it reconstructs words/cword from
        # bash's own (quote-aware) COMP_WORDS, and "-n :" excludes ":"
        # from word-breaking so "dlp:acad" arrives as one word instead of
        # being fragmented like the naive fallback below.
        local cur words cword
        _get_comp_words_by_ref -n : cur words cword
        __exsh_words=( "${words[@]}" )
        __exsh_cword=$cword
        __exsh_full=$cur
    else
        # Fallback: reconstruct words from COMP_LINE with plain whitespace
        # splitting. Quoted arguments containing spaces (e.g.
        # exsh put "my file.xml" dlp:) are mis-tokenized here, which can
        # throw off COMP_CWORD for words typed after them. Install the
        # bash-completion package for correct handling of that case.
        local __exsh_line=${COMP_LINE:0:COMP_POINT}
        read -ra __exsh_words <<< "$__exsh_line"
        __exsh_cword=${#__exsh_words[@]}
        [[ $__exsh_line != *[[:space:]] ]] && __exsh_cword=$((__exsh_cword - 1))
        __exsh_full=${__exsh_words[__exsh_cword]-}
    fi

    local IFS=$'\n'
    local -a __exsh_raw
    mapfile -t __exsh_raw < <( env COMP_WORDS="${__exsh_words[*]}" \\
                    COMP_CWORD=$__exsh_cword \\
                    %(autocomplete_var)s=complete_bash $1 )

    # A bracket expression built directly from $COMP_WORDBREAKS misparses if
    # it were ever customized to contain "]" (closes the class early) or to
    # start with "!"/"^" (negates the class); strip those glob-special
    # characters first. Losing them as recognized word-break characters in
    # that rare case is preferable to a misparsed pattern.
    local __exsh_wb=${COMP_WORDBREAKS//[]!^]/}
    local __exsh_cur=${__exsh_full##*[$__exsh_wb]}
    local __exsh_strip=$(( ${#__exsh_full} - ${#__exsh_cur} ))
    COMPREPLY=()
    local __exsh_c
    for __exsh_c in "${__exsh_raw[@]}"; do
        COMPREPLY+=( "${__exsh_c:__exsh_strip}" )
    done

    # A single collection candidate ends in "/" and will be inserted in
    # full; suppress bash's default trailing space so the next tab press
    # can continue straight into the subcollection.
    if (( ${#COMPREPLY[@]} == 1 )) && [[ ${COMPREPLY[0]} == */ ]]; then
        compopt -o nospace
    fi
    return 0
}

complete -o default -F %(complete_func)s %(prog_name)s
"""


def patch_bash_completion_template() -> None:
    """Override Typer's stock bash completion script with a fixed one.

    Must run before Typer processes ``--install-completion``/
    ``--show-completion`` (i.e. at import time, before the app is invoked),
    so that both commands emit the fixed script on every machine rather
    than requiring a hand-patched local completion file. See
    ``_FIXED_COMPLETION_SCRIPT_BASH`` for what it fixes and why.

    ``--install-completion``/``--show-completion`` read the bash template
    from ``typer._completion_shared._completion_scripts["bash"]`` (a dict
    built once at import time), not from ``BashComplete.source_template``
    — both are patched here for consistency, but the dict entry is the one
    that actually matters for those two commands.

    Silently no-ops if Typer's internal completion layout has changed
    underneath this pinned dependency, so a future Typer upgrade degrades
    to stock (colon-broken) bash completion instead of crashing the CLI.
    """
    try:
        from typer._completion_classes import BashComplete
        from typer import _completion_shared

        BashComplete.source_template = _FIXED_COMPLETION_SCRIPT_BASH
        _completion_shared._completion_scripts["bash"] = _FIXED_COMPLETION_SCRIPT_BASH
    except Exception:
        pass


def collection_target_completer(kind: Kind = "any", *, allow_local: bool = False):
    """Return a completion function for ``<nick>:<path>`` arguments filtered by item kind.

    Args:
        kind: Which item types to include — ``"collection"`` for subcollections
            only, ``"resource"`` for documents only, ``"any"`` for both.
        allow_local: When True and the incomplete string contains no ``:``,
            return an empty list so the shell falls back to its default
            filesystem completion.  When False (default), offer collection
            nick completions instead.

    Returns:
        A completion function compatible with Typer's ``autocompletion`` parameter.
    """
    def _complete(incomplete: str) -> list[str]:
        try:
            config = Config.load()
        except Exception:
            return []

        if ":" not in incomplete:
            if allow_local:
                return []
            return [f"{nick}:" for nick in config.collections if nick.startswith(incomplete)]

        nick, partial_path = incomplete.split(":", 1)
        if nick not in config.collections:
            return []

        # Directory portion as typed by the user, with no leading "/" added —
        # candidates are built from this so they stay a literal prefix of
        # `incomplete` (Typer/Click drops any candidate that isn't).
        out_dir = partial_path[: partial_path.rfind("/") + 1]

        query_path = partial_path if partial_path.startswith("/") else "/" + partial_path
        last_slash = query_path.rfind("/")
        dir_path = query_path[: last_slash + 1]
        prefix = query_path[last_slash + 1:]

        collection = config.collections[nick]
        server = config.servers[collection.server_nick]
        full_dir = f"/db/{collection.name}{dir_path}"

        try:
            items = get_cached_prefix_match(nick, dir_path, prefix)
            if items is None:
                with ExistClient(server, connect_timeout=_COMPLETION_CONNECT_TIMEOUT, read_timeout=_COMPLETION_READ_TIMEOUT) as client:
                    items = client.list_child_names(full_dir, prefix)
                truncated = len(items) >= DEFAULT_CHILD_NAMES_LIMIT
                set_cached(nick, dir_path, items, prefix, truncated=truncated)
        except Exception:
            return []

        results = []
        for item in items:
            is_col = isinstance(item, CollectionEntry)
            if kind == "collection" and not is_col:
                continue
            if kind == "resource" and is_col:
                continue
            item_name = item.name + ("/" if is_col else "")
            if item_name.startswith(prefix):
                results.append(f"{nick}:{out_dir}{item_name}")
        return results

    return _complete


def chown_spec_completer(incomplete: str) -> list[str]:
    """Complete an ``owner_spec`` argument for the ``chown`` command.

    Accepts an optional ``server@`` prefix to select which server to query for
    user and group names.  All six forms are supported:

    - ``user`` / ``:group`` / ``user:group`` — uses the first reachable server.
    - ``server@user`` / ``server@:group`` / ``server@user:group`` — uses the
      named server; the ``server@`` prefix is stripped by the command before
      the ownership change is applied.

    When no ``@`` is present and multiple servers are configured, server-nick
    completions (``server@``) are also offered so the user can pin a server.

    Args:
        incomplete: The partially typed owner spec.

    Returns:
        List of completion candidates.
    """
    try:
        config = Config.load()
    except Exception:
        return []

    # --- resolve server and the "rest" to complete ----------------------------
    server = None
    resolved_nick = ""
    prefix = ""   # "server@" to prepend to every candidate
    rest = incomplete

    if "@" in incomplete:
        server_nick, _, rest = incomplete.partition("@")
        if server_nick in config.servers:
            server = config.servers[server_nick]
            resolved_nick = server_nick
            prefix = f"{server_nick}@"
        else:
            # Still typing the server nick: offer matching "server@" completions.
            return [f"{s}@" for s in config.servers if s.startswith(server_nick)]
    else:
        # Pick the first configured server as a default.
        for nick, s in config.servers.items():
            server = s
            resolved_nick = nick
            break

    if server is None:
        return []

    # --- fetch users / groups and build candidates ----------------------------
    try:
        if ":" in rest:
            user_part, _, partial_group = rest.partition(":")
            groups = get_cached_groups(resolved_nick)
            if groups is None:
                with ExistClient(server) as client:
                    groups = client.list_groups()
                set_cached_groups(resolved_nick, groups)
            return [
                f"{prefix}{user_part}:{g.name}"
                for g in groups
                if g.name.startswith(partial_group)
            ]
        else:
            users = get_cached_users(resolved_nick)
            if users is None:
                with ExistClient(server) as client:
                    users = client.list_users()
                set_cached_users(resolved_nick, users)
            results = [
                f"{prefix}{u.username}"
                for u in users
                if u.username.startswith(rest)
            ]
            # When no server pin typed yet and multiple servers exist,
            # also offer "server@" so the user can pick a specific server.
            if not prefix and len(config.servers) > 1:
                results += [f"{s}@" for s in config.servers if s.startswith(rest)]
            return results
    except Exception:
        return []


def server_nick_completer(incomplete: str) -> list[str]:
    """Complete a ``--server`` option value from configured server nicks.

    Args:
        incomplete: The partially typed server nick.

    Returns:
        List of server nicks that start with ``incomplete``.
    """
    try:
        config = Config.load()
    except Exception:
        return []
    return [nick for nick in config.servers if nick.startswith(incomplete)]


def user_arg_completer(incomplete: str) -> list[str]:
    """Complete ``user@server`` arguments by offering server-profile suffixes.

    Handles three forms:

    - No ``@`` present: returns nothing (usernames are open-ended).
    - ``alice@``: returns ``alice@<nick>`` for each server whose nick starts
      with the text after ``@``.
    - ``alice@prod``: already resolved, returns nothing.

    Args:
        incomplete: The partially typed argument value.

    Returns:
        List of completion candidates.
    """
    try:
        config = Config.load()
    except Exception:
        return []
    if "@" in incomplete:
        user_part, _, server_part = incomplete.rpartition("@")
        return [f"{user_part}@{nick}" for nick in config.servers if nick.startswith(server_part)]
    return []


def server_at_completer(incomplete: str) -> list[str]:
    """Complete a bare ``@server`` argument (used by commands like ``user ls``).

    Args:
        incomplete: The partially typed argument value (e.g. ``@`` or ``@pr``).

    Returns:
        List of ``@nick`` candidates whose nick starts with the text after ``@``.
    """
    try:
        config = Config.load()
    except Exception:
        return []
    if incomplete.startswith("@"):
        prefix = incomplete[1:]
        return [f"@{nick}" for nick in config.servers if nick.startswith(prefix)]
    if not incomplete:
        return [f"@{nick}" for nick in config.servers]
    return []
