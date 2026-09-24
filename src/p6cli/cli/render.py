"""Tablas, paneles y progreso con rich."""

from collections.abc import Sequence

from rich.console import Console
from rich.table import Table
from rich.text import Text

from p6cli.cli import messages
from p6cli.core.profiles import Profile


def _texto_tls(verify_ssl: bool | str) -> str:
    if verify_ssl is True:
        return messages.TLS_VALIDADO
    if verify_ssl is False:
        return messages.TLS_SIN_VALIDAR
    return messages.TLS_CA_PROPIA


def tabla_perfiles(
    perfiles: Sequence[Profile], predeterminado: str | None, estado_claves: Sequence[str]
) -> None:
    """Imprime los perfiles. ``estado_claves`` trae el texto ya enmascarado de cada uno."""
    tabla = Table()
    for columna in (
        messages.COLUMNA_NOMBRE,
        messages.COLUMNA_URL,
        messages.COLUMNA_DATABASE,
        messages.COLUMNA_USUARIO,
        messages.COLUMNA_CLAVE,
        messages.COLUMNA_TLS,
        messages.COLUMNA_PREDETERMINADO,
    ):
        tabla.add_column(columna, no_wrap=True)
    for perfil, clave in zip(perfiles, estado_claves, strict=True):
        # Text evita que rich interprete corchetes de los datos como marcado.
        celdas = (
            perfil.name,
            f"{perfil.host}/{perfil.context}",
            perfil.database_name,
            perfil.username,
            clave,
            _texto_tls(perfil.verify_ssl),
            messages.MARCA_PREDETERMINADO if perfil.name == predeterminado else "",
        )
        tabla.add_row(*(Text(celda) for celda in celdas))
    Console().print(tabla)
