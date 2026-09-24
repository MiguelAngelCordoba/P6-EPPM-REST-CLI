"""Aplicación Typer: comandos con flags; sin argumentos abre los menús."""

from typing import Annotated

import typer

from p6cli import __version__
from p6cli.cli import messages

app = typer.Typer(help=messages.AYUDA_APP, add_completion=False)


def _mostrar_version(valor: bool) -> None:
    """Imprime la versión y termina, antes de procesar cualquier otra opción."""
    if valor:
        typer.echo(messages.VERSION.format(version=__version__))
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def principal(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_mostrar_version,
            is_eager=True,
            help=messages.AYUDA_VERSION,
        ),
    ] = False,
) -> None:
    """Punto de entrada del comando ``p6``."""
    if ctx.invoked_subcommand is None:
        # Hasta que existan los menús (M5), sin argumentos solo se muestra un aviso.
        typer.echo(messages.AVISO_SIN_MENUS)


def main() -> None:
    """Ejecuta la aplicación; usado por el script ``p6`` y por ``python -m p6cli``."""
    app()
