"""Tablas, paneles y progreso con rich."""

from collections.abc import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from p6cli.cli import messages
from p6cli.core.diagnostics import DiagnosticReport, EstadoDiagnostico
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


def textos_diagnostico(reporte: DiagnosticReport) -> tuple[str, str]:
    """Mensaje y sugerencia del reporte, completados con su detalle."""
    if reporte.causa_red is not None:
        mensaje, sugerencia = messages.DIAGNOSTICO_RED[reporte.causa_red]
    else:
        mensaje, sugerencia = messages.DIAGNOSTICO[reporte.status]
    return mensaje.format(**reporte.detalle), sugerencia.format(**reporte.detalle)


def reporte_diagnostico(reporte: DiagnosticReport) -> None:
    """Imprime el estado con su mensaje y sugerencia, y la tabla de pasos observados."""
    mensaje, sugerencia = textos_diagnostico(reporte)
    exito = reporte.status is EstadoDiagnostico.OK
    # Text evita que rich interprete como marcado lo que venga en los cuerpos de P6.
    cuerpo = Text()
    cuerpo.append(mensaje, style="bold")
    if sugerencia:
        cuerpo.append("\n" + sugerencia)
    titulo = Text(messages.TITULO_DIAGNOSTICO.format(estado=reporte.status))
    consola = Console()
    consola.print(Panel(cuerpo, title=titulo, border_style="green" if exito else "red"))

    tabla = Table()
    tabla.add_column(messages.COLUMNA_METODO, no_wrap=True)
    # La URL es el dato clave de cada paso: se parte en líneas en lugar de recortarse.
    tabla.add_column(messages.COLUMNA_URL, overflow="fold")
    tabla.add_column(messages.COLUMNA_CODIGO, no_wrap=True)
    tabla.add_column(messages.COLUMNA_CONTENT_TYPE)
    tabla.add_column(messages.COLUMNA_TAMANO, no_wrap=True)
    tabla.add_column(messages.COLUMNA_FRAGMENTO, overflow="fold")
    for paso in reporte.pasos:
        celdas = (
            paso.metodo,
            paso.url,
            messages.SIN_CODIGO if paso.codigo is None else str(paso.codigo),
            paso.content_type,
            str(paso.tamano),
            paso.fragmento,
        )
        tabla.add_row(*(Text(celda) for celda in celdas))
    consola.print(tabla)
