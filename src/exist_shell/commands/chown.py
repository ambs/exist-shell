"""chown command — change the owner and/or group of a document or collection."""

import typer

from exist_shell.client import ExistClient
from exist_shell.completions import chown_spec_completer, collection_target_completer
from exist_shell.exceptions import ExistQueryError
from exist_shell.models import CollectionEntry
from exist_shell.utils import handle_exist_errors, parse_target, resolve_collection


def _parse_spec(spec: str) -> tuple[str | None, str | None]:
    """Parse an owner spec into ``(owner, group)``, stripping any ``server@`` prefix.

    Accepted forms: ``owner``, ``:group``, ``owner:group``,
    ``server@owner``, ``server@:group``, ``server@owner:group``.
    The ``server@`` prefix is used only for tab completion and is discarded here.

    Args:
        spec: The raw owner spec from the CLI.

    Returns:
        Tuple ``(owner, group)`` where either element is ``None`` when not
        specified.
    """
    if "@" in spec:
        _, _, spec = spec.partition("@")
    if ":" in spec:
        owner, _, group = spec.partition(":")
        return owner.strip() or None, group.strip() or None
    return spec.strip() or None, None


def _chown_tree(client: ExistClient, path: str, owner: str | None, group: str | None) -> int:
    """Recursively change ownership of a collection and all its contents.

    Args:
        client: Active ExistClient.
        path: Full eXist path to the root collection.
        owner: New owner username, or ``None`` to leave unchanged.
        group: New group name, or ``None`` to leave unchanged.

    Returns:
        Total number of resources and collections whose ownership was changed.
    """
    client.chown_resource(path, owner, group)
    count = 1
    for item in client.list_collection(path):
        child = f"{path}/{item.name}"
        if isinstance(item, CollectionEntry):
            count += _chown_tree(client, child, owner, group)
        else:
            client.chown_resource(child, owner, group)
            count += 1
    return count


def chown(
    owner_spec: str = typer.Argument(
        help=(
            "Owner/group spec: 'owner', ':group', 'owner:group'. "
            "Prefix with 'server@' to pin a server for tab completion "
            "(e.g. 'prod@alice:editors')."
        ),
        autocompletion=chown_spec_completer,
    ),
    target: str = typer.Argument(
        help="Remote path: <nick>:<path>.",
        autocompletion=collection_target_completer("any"),
    ),
    recursive: bool = typer.Option(
        False, "--recursive", "-R",
        help="Apply recursively to all contents of a collection.",
    ),
) -> None:
    """Change the owner and/or group of a document or collection on the server."""
    owner, group = _parse_spec(owner_spec)
    if owner is None and group is None:
        typer.echo(
            "Error: specify at least an owner or a group "
            "(e.g. 'alice', ':editors', 'alice:editors').",
            err=True,
        )
        raise typer.Exit(1)

    nick, path = parse_target(target, path_required=False)
    collection, server, full_path = resolve_collection(nick, path)

    try:
        with handle_exist_errors(path, nick, collection.server_nick):
            with ExistClient(server) as client:
                if recursive:
                    if not client.is_collection(full_path):
                        typer.echo(
                            f"Error: '{path}' is not a collection. "
                            "Omit -R to chown a single document.",
                            err=True,
                        )
                        raise typer.Exit(1)
                    count = _chown_tree(client, full_path, owner, group)
                    typer.echo(f"Ownership of '{path}' updated ({count} items).")
                else:
                    client.chown_resource(full_path, owner, group)
                    typer.echo(f"Ownership of '{path}' updated.")
    except ExistQueryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
