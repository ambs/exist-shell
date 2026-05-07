"""Entry point and top-level CLI app for exsh."""

import typer

from exist_shell import __version__
from exist_shell.commands import collection, server
from exist_shell.commands.cat import cat
from exist_shell.commands.cp import cp
from exist_shell.commands.mkdir import mkdir
from exist_shell.commands.edit import edit
from exist_shell.commands.ls import ls
from exist_shell.commands.put import put
from exist_shell.commands.rm import rm
from exist_shell.commands.sync import sync

app = typer.Typer(
    name="exsh",
    help="eXist-db shell — interact with eXist-db via REST",
    no_args_is_help=True,
)

app.add_typer(server.app, name="server", help="Manage servers.")
app.add_typer(collection.app, name="collection", help="Manage collections.")
app.command("ls", help="List contents of a collection path.")(ls)
app.command("cat", help="Print document content to stdout.")(cat)
app.command("put", help="Upload a document to a collection path.")(put)
app.command("edit", help="Edit a document in $VISUAL/$EDITOR and re-upload if changed.")(edit)
app.command("cp", help="Copy a document between local paths and remote collections.")(cp)
app.command("rm", help="Delete one or more documents from a collection path.")(rm)
app.command("mkdir", help="Create a collection at a path inside a registered collection.")(mkdir)
app.command("sync", help="Sync a local folder and a remote collection.")(sync)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"exsh {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."),
) -> None:
    """eXist-db shell — interact with eXist-db via REST."""


if __name__ == "__main__":
    app()
