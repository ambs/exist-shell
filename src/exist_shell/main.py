import typer

from exist_shell import __version__
from exist_shell.commands import collection, server

app = typer.Typer(
    name="exsh",
    help="eXist-db shell — interact with eXist-db via REST",
    no_args_is_help=True,
)

app.add_typer(server.app, name="server", help="Manage servers.")
app.add_typer(collection.app, name="collection", help="Manage collections.")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"exsh {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."),
) -> None:
    pass


if __name__ == "__main__":
    app()
