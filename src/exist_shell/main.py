"""Entry point and top-level CLI app for exsh."""

from pathlib import Path

import typer

from exist_shell import __version__
from exist_shell.commands import collection, group, server, user
from exist_shell.completions import patch_bash_completion_template
from exist_shell.config import app_state
from exist_shell.commands.cat import cat
from exist_shell.commands.chmod import chmod
from exist_shell.commands.chown import chown
from exist_shell.commands.exec import exec as exec_query
from exist_shell.commands.find import find
from exist_shell.commands.cp import cp
from exist_shell.commands.mkdir import mkdir
from exist_shell.commands.mv import mv
from exist_shell.commands.edit import edit
from exist_shell.commands.ls import ls
from exist_shell.commands.put import put
from exist_shell.commands.rm import rm
from exist_shell.commands.sync import sync

patch_bash_completion_template()

app = typer.Typer(
    name="exsh",
    help="eXist-db shell — interact with eXist-db via REST",
    no_args_is_help=True,
)

app.add_typer(server.app, name="server", help="Manage servers.")
app.add_typer(collection.app, name="collection", help="Manage collections.")
app.add_typer(user.app, name="user", help="Manage users.")
app.add_typer(group.app, name="group", help="Manage groups.")
app.command("ls", help="List contents of a collection path.")(ls)
app.command("chown", help="Change the owner and/or group of a document or collection.")(chown)
app.command("chmod", help="Change POSIX permissions of a document or collection.")(chmod)
app.command("cat", help="Print document content to stdout.")(cat)
app.command("put", help="Upload a document to a collection path.")(put)
app.command("edit", help="Edit a document in $VISUAL/$EDITOR and re-upload if changed.")(edit)
app.command("cp", help="Copy a document between local paths and remote collections.")(cp)
app.command("mv", help="Move or rename a document or collection on the server.")(mv)
app.command("rm", help="Delete one or more documents from a collection path.")(rm)
app.command("find", help="Find documents by XPath expression, with optional deletion.")(find)
app.command("mkdir", help="Create a collection at a path inside a registered collection.")(mkdir)
app.command("sync", help="Sync a local folder and a remote collection.")(sync)
app.command("exec", help="Execute an XQuery script on an eXist-db server.")(exec_query)
app.command("ping", help="Check server connectivity, reporting version and latency (all servers if no nick).")(server.server_status)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"exsh {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."),
    config: Path | None = typer.Option(None, "--config", help="Path to config file (overrides EXSH_CONFIG env var and default)."),
) -> None:
    """eXist-db shell — interact with eXist-db via REST."""
    if config is not None:
        app_state.set_config_path(config)


def cli() -> None:
    """Run the Typer app.

    Catches ``KeyboardInterrupt`` raised during shell completion (Typer/click
    don't handle it there — completion runs outside their own try/except) as
    well as any other stray Ctrl+C, exiting 130 instead of printing a
    traceback.
    """
    try:
        app()
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    cli()
