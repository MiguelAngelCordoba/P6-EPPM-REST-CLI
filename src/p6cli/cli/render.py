"""Tablas, paneles y progreso con rich."""

import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from p6cli import __version__
from p6cli.cli import messages
from p6cli.core.catalog import Endpoint
from p6cli.core.diagnostics import DiagnosticReport, EstadoDiagnostico
from p6cli.core.errors import MotivoAuth, MotivoHTTP, P6CliError
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


# --- Errores --------------------------------------------------------------------


def texto_error(error: P6CliError) -> str:
    """Mensaje del error; agrega la pista por código HTTP o el diagnóstico del login."""
    lineas = [messages.ERRORES[error.motivo].format(**error.datos)]
    if error.motivo is MotivoHTTP.CODIGO_HTTP:
        pista = messages.PISTAS_HTTP.get(int(error.datos["codigo"]))
        if pista is not None:
            lineas.append(messages.PISTA.format(pista=pista))
    elif error.motivo is MotivoAuth.LOGIN_FALLIDO:
        estado = EstadoDiagnostico(error.datos["estado"])
        lineas.extend(texto for texto in textos_estado(estado, error.datos) if texto)
        lineas.append(messages.SUGERENCIA_DOCTOR.format(perfil=error.datos["perfil"]))
    return "\n".join(lineas)


def mostrar_error(error: P6CliError) -> None:
    """Imprime el mensaje del error en stderr."""
    # Text evita que rich interprete como marcado lo que venga en los mensajes de P6.
    Console(stderr=True).print(Text(texto_error(error)), soft_wrap=True)


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


def numero(valor: int) -> str:
    """Entero con punto de miles: 1.284."""
    return f"{valor:,}".replace(",", ".")


def encabezado_resultados(endpoint: str, filas: int, segundos: float) -> str:
    """«activity · 1.284 filas · 3,2 s»."""
    return messages.ENCABEZADO_RESULTADOS.format(
        endpoint=endpoint,
        filas=numero(filas),
        unidad=messages.UNIDAD_FILA if filas == 1 else messages.UNIDAD_FILAS,
        segundos=f"{segundos:.1f}".replace(".", ","),
    )


def tabla_resultados(
    filas: Sequence[Mapping[str, Any]],
    campos: Sequence[str],
    max_filas: int,
    encabezado: str,
    aviso: str = messages.AVISO_FILAS_MOSTRADAS,
) -> None:
    """Imprime las primeras ``max_filas`` filas (0 = todas) con columnas en el orden de Fields.

    ``aviso`` es el texto que se muestra cuando la tabla no incluye todas las filas.
    """
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
        consola.print(aviso.format(mostradas=numero(len(mostradas)), total=numero(len(filas))))


def json_resultados(filas: Sequence[Mapping[str, Any]]) -> None:
    """Imprime la respuesta completa como JSON (indentación 2, sin escapar tildes)."""
    texto = json.dumps(filas, indent=2, ensure_ascii=False)
    # Text sin resaltado: corchetes y % de los datos no se interpretan; sin cortes de línea.
    Console().print(Text(texto), soft_wrap=True, highlight=False)


# --- Flujo interactivo (§10 y §11) ------------------------------------------------


def banner() -> None:
    """Título del flujo interactivo con la versión instalada."""
    Console().print(Text(messages.BANNER.format(version=__version__), style="bold"))


def pantalla_credenciales(perfil: Profile, temporal: bool) -> None:
    """Datos del ambiente elegido (§10.2). La clave siempre se muestra enmascarada.

    ``temporal`` indica que la clave se escribió para esta sesión y no está guardada.
    """
    clave = messages.CLAVE_ENMASCARADA
    if temporal:
        clave = f"{clave}   {messages.CLAVE_NO_GUARDADA}"
    consola = Console()
    consola.print()
    for linea in (
        messages.ETIQUETA_AMBIENTE.format(
            nombre=perfil.name,
            host=perfil.host,
            context=perfil.context,
            database=perfil.database_name,
        ),
        messages.ETIQUETA_USUARIO.format(usuario=perfil.username),
        messages.ETIQUETA_CLAVE.format(clave=clave),
    ):
        consola.print(Text(linea), soft_wrap=True)
    consola.print()


def cabecera_formulario(endpoint: Endpoint) -> None:
    """Encabezado del formulario ``entity`` con la ayuda de §11.1."""
    consola = Console()
    consola.print()
    titulo = messages.CABECERA_FORMULARIO.format(
        ruta=endpoint.path, descripcion=endpoint.description
    )
    consola.print(Text(titulo, style="bold"))
    for linea in messages.AYUDA_FORMULARIO:
        consola.print(Text(linea))
    consola.print()


def confirmacion_consulta(
    ruta: str, parametros: Sequence[tuple[str, str, bool]], equivalente: str
) -> None:
    """Resumen de la consulta antes de ejecutarla (§11.3).

    Cada parámetro es ``(nombre, valor, por_defecto)``; ``por_defecto`` marca los valores
    neutros que completa el cliente. El comando equivalente no se parte: se copia tal cual.
    """
    ancho = max((len(nombre) for nombre, _, _ in parametros), default=0)
    consola = Console()
    consola.print()
    consola.print(Text(messages.CONFIRMACION_RUTA.format(ruta=ruta), style="bold"))
    for nombre, valor, por_defecto in parametros:
        linea = f"  {nombre:<{ancho}} : {valor}"
        if por_defecto:
            linea = f"{linea}   {messages.MARCA_POR_DEFECTO}"
        consola.print(Text(linea), soft_wrap=True)
    consola.print(Text("  " + messages.EQUIVALE_A.format(comando=equivalente)), soft_wrap=True)
    consola.print()


@contextmanager
def progreso_consulta() -> Iterator[None]:
    """Indicador de espera con el tiempo transcurrido; desaparece al terminar."""
    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        TimeElapsedColumn(),
        transient=True,
    ) as progreso:
        progreso.add_task(messages.ESPERANDO_RESPUESTA, total=None)
        yield


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
