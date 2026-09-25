"""Tablas, paneles y progreso con rich."""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from p6cli.cli import messages
from p6cli.core.catalog import Endpoint
from p6cli.core.diagnostics import DiagnosticReport, EstadoDiagnostico
from p6cli.core.profiles import Profile

# Salida tabular de resultados (§13).
FILAS_TABLA = 25
LARGO_CELDA = 40


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


def textos_estado(estado: EstadoDiagnostico, detalle: Mapping[str, str]) -> tuple[str, str]:
    """Mensaje y sugerencia de un estado de §7, completados con su detalle."""
    mensaje, sugerencia = messages.DIAGNOSTICO[estado]
    return mensaje.format(**detalle), sugerencia.format(**detalle)


def textos_diagnostico(reporte: DiagnosticReport) -> tuple[str, str]:
    """Mensaje y sugerencia del reporte, completados con su detalle."""
    if reporte.causa_red is not None:
        mensaje, sugerencia = messages.DIAGNOSTICO_RED[reporte.causa_red]
        return mensaje.format(**reporte.detalle), sugerencia.format(**reporte.detalle)
    return textos_estado(reporte.status, reporte.detalle)


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


# --- Catálogo y resultados ------------------------------------------------------


def tabla_endpoints(entradas: Sequence[tuple[int, Endpoint]]) -> None:
    """Imprime el catálogo agrupado (§10.5).

    El número de cada entrada es su posición en el catálogo completo; nunca se persiste.
    Name y Ruta son los de la documentación de Oracle, para buscar la operación allí.
    """
    tabla = Table()
    tabla.add_column(messages.COLUMNA_NUMERO, justify="right", no_wrap=True)
    # Tasks, Name y Ruta nunca se recortan: se copian para buscar en la documentación. Si
    # falta ancho, se parten los encabezados cortos de Grande y Verificado.
    for columna, textos in (
        (messages.COLUMNA_TASKS, [e.key for _, e in entradas]),
        (messages.COLUMNA_NAME, [e.doc_name for _, e in entradas]),
        (messages.COLUMNA_RUTA, [e.path for _, e in entradas]),
    ):
        ancho = max((len(texto) for texto in [columna, *textos]), default=len(columna))
        tabla.add_column(columna, no_wrap=True, min_width=ancho)
    tabla.add_column(messages.COLUMNA_GRANDE, overflow="fold")
    tabla.add_column(messages.COLUMNA_VERIFICADO, overflow="fold")
    grupo_actual: str | None = None
    for numero, endpoint in entradas:
        if endpoint.group != grupo_actual:
            if grupo_actual is not None:
                tabla.add_section()
            grupo_actual = endpoint.group
            tabla.add_row("", Text(messages.TITULO_GRUPO.format(grupo=grupo_actual), style="bold"))
        celdas = (
            str(numero),
            endpoint.key,
            endpoint.doc_name,
            endpoint.path,
            messages.MARCA_SI if endpoint.large else "",
            messages.MARCA_SI if endpoint.doc_verified else "",
        )
        tabla.add_row(*(Text(celda) for celda in celdas))
    Console().print(tabla)


def lista_campos(endpoint: str, campos: Sequence[str]) -> None:
    """Imprime los campos válidos de un endpoint en columnas."""
    consola = Console()
    titulo = messages.TITULO_CAMPOS.format(endpoint=endpoint, cantidad=len(campos))
    consola.print(Text(titulo, style="bold"))
    consola.print(Columns([Text(campo) for campo in campos], padding=(0, 3)))


def texto_celda(valor: Any) -> str:
    """Texto de una celda: vacío para nulos, JSON para anidados, recortado a 40 caracteres."""
    if valor is None:
        texto = ""
    elif isinstance(valor, str):
        texto = valor
    else:
        texto = json.dumps(valor, ensure_ascii=False)
    # Saltos de línea y otros caracteres de control romperían la tabla.
    texto = "".join(caracter if caracter.isprintable() else " " for caracter in texto)
    if len(texto) > LARGO_CELDA:
        return texto[: LARGO_CELDA - 1] + "…"
    return texto


def _numero(valor: int) -> str:
    """Entero con punto de miles: 1.284."""
    return f"{valor:,}".replace(",", ".")


def encabezado_resultados(endpoint: str, filas: int, segundos: float) -> str:
    """«activity · 1.284 filas · 3,2 s»."""
    return messages.ENCABEZADO_RESULTADOS.format(
        endpoint=endpoint,
        filas=_numero(filas),
        unidad=messages.UNIDAD_FILA if filas == 1 else messages.UNIDAD_FILAS,
        segundos=f"{segundos:.1f}".replace(".", ","),
    )


def tabla_resultados(
    filas: Sequence[Mapping[str, Any]], campos: Sequence[str], max_filas: int, encabezado: str
) -> None:
    """Imprime las primeras ``max_filas`` filas (0 = todas) con columnas en el orden de Fields."""
    consola = Console()
    consola.print(Text(encabezado, style="bold"))
    if not filas:
        consola.print(messages.SIN_RESULTADOS)
        return
    mostradas = filas if max_filas == 0 else filas[:max_filas]
    tabla = Table()
    for campo in campos:
        tabla.add_column(campo, no_wrap=True)
    for fila in mostradas:
        # Text evita que rich interprete como marcado los datos de P6.
        tabla.add_row(*(Text(texto_celda(fila.get(campo))) for campo in campos))
    consola.print(tabla)
    if len(mostradas) < len(filas):
        consola.print(
            messages.AVISO_FILAS_MOSTRADAS.format(
                mostradas=_numero(len(mostradas)), total=_numero(len(filas))
            )
        )


# --- Guías de sintaxis ----------------------------------------------------------


def lista_temas(guias: Mapping[str, messages.GuiaSintaxis]) -> None:
    """Imprime los temas disponibles de ``p6 syntax`` con su resumen."""
    consola = Console()
    consola.print(Text(messages.TITULO_TEMAS, style="bold"))
    tabla = Table(show_header=False, box=None, padding=(0, 2))
    for tema, guia in guias.items():
        tabla.add_row(Text(tema, style="bold"), Text(guia.resumen))
    consola.print(tabla)


def guia_sintaxis(guia: messages.GuiaSintaxis) -> None:
    """Imprime una guía. Todo va como ``Text``: corchetes y % no se interpretan como marcado."""
    consola = Console()
    consola.print(Text(guia.titulo, style="bold"))
    for parrafo in guia.intro:
        consola.print(Text(parrafo))
    tabla = Table()
    for columna in guia.columnas:
        tabla.add_column(columna)
    for fila in guia.filas:
        tabla.add_row(*(Text(celda) for celda in fila))
    consola.print(tabla)
    consola.print(Text(messages.TITULO_NOTAS, style="bold"))
    for nota in guia.notas:
        consola.print(Text(f"• {nota}"))
    consola.print()
    consola.print(Text(messages.TITULO_EJEMPLOS, style="bold"))
    for ejemplo in guia.ejemplos:
        # Sin cortes de línea: el ejemplo debe poder copiarse tal cual.
        consola.print(Text(f"  {ejemplo}"), soft_wrap=True)
    consola.print()
    consola.print(Text(messages.TITULO_REFERENCIA.format(url=guia.referencia)), soft_wrap=True)
