"""Flujo interactivo con menús (especificación §10).

``p6`` sin argumentos abre este flujo. Cada ambiente usa una ``Sesion`` con un único intento
de login, que se hace al elegir «Continuar» con la prueba de conexión completa (§7): si da
OK, la misma sesión atiende todas las consultas del ambiente. La sesión vive en un ``with``,
así que el logout ocurre al cambiar de ambiente, al salir y también ante Ctrl+C.
"""

import dataclasses
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

import typer

from p6cli.cli import forms, messages, render
from p6cli.cli.forms import ValoresEntity, ValoresSpread
from p6cli.cli.prompter import Opcion, Prompter, Separador
from p6cli.core import catalog, profiles, secrets
from p6cli.core.catalog import Endpoint, Plantilla
from p6cli.core.client import Cliente, Fila, filas_por_periodo
from p6cli.core.diagnostics import EstadoDiagnostico, diagnosticar
from p6cli.core.errors import P6CliError
from p6cli.core.export import (
    CARPETA_EXPORTACION,
    Formato,
    escribir_csv,
    escribir_json,
    filas_spread_largo,
    nombre_archivo,
)
from p6cli.core.profiles import Profile, ProfileStore
from p6cli.core.session import Sesion

# Por encima de estas filas, ver la salida completa pide confirmación: en la terminal tarda
# y el inicio queda fuera de la pantalla.
FILAS_AVISO_SALIDA_COMPLETA = 500


class Accion(Enum):
    """Opciones fijas de los menús: todo lo que no es un perfil ni un endpoint."""

    AGREGAR = "agregar"
    ADMINISTRAR = "administrar"
    CONTINUAR = "continuar"
    ACTUALIZAR = "actualizar"
    VOLVER = "volver"
    CAMBIAR_AMBIENTE = "cambiar_ambiente"
    SALIR = "salir"
    VER_TABLA = "ver_tabla"
    VER_JSON = "ver_json"
    EXPORTAR_CSV = "exportar_csv"
    EXPORTAR_JSON = "exportar_json"
    DE_ACUERDO = "de_acuerdo"
    CAMBIAR_RUTA = "cambiar_ruta"
    NUEVA_CONSULTA = "nueva_consulta"
    OTRO_ENDPOINT = "otro_endpoint"
    EDITAR = "editar"
    PROBAR = "probar"
    PREDETERMINADO = "predeterminado"
    ELIMINAR = "eliminar"


def ejecutar(prompter: Prompter) -> None:
    """Punto de entrada del flujo interactivo. Termina al elegir «Salir»."""
    store = ProfileStore()
    render.banner()
    if not store.listar():
        # Solo al abrir: si se cancela, se sigue al menú de inicio.
        typer.echo(messages.BIENVENIDA)
        _agregar(prompter, store)
    while (perfil := _inicio(prompter, store)) is not None:
        sesion = _credenciales(prompter, store, perfil)
        if sesion is None:
            continue
        with sesion:
            if _consultar(prompter, sesion) is Accion.SALIR:
                return


# --- Inicio (§10.1) -------------------------------------------------------------


def _host_sin_esquema(perfil: Profile) -> str:
    return perfil.host.split("://", 1)[-1]


def _opciones_perfiles(
    perfiles: list[Profile], predeterminado: str | None
) -> list[Opcion[Profile]]:
    """Una fila alineada por perfil: nombre, host, DatabaseName y marca de predeterminado."""
    ancho_nombre = max(len(p.name) for p in perfiles)
    ancho_host = max(len(_host_sin_esquema(p)) for p in perfiles)
    ancho_base = max(len(p.database_name) for p in perfiles)
    opciones = []
    for perfil in perfiles:
        fila = (
            f"{perfil.name:<{ancho_nombre}}   {_host_sin_esquema(perfil):<{ancho_host}}   "
            f"{perfil.database_name:<{ancho_base}}"
        )
        if perfil.name == predeterminado:
            fila = f"{fila}   {messages.MARCA_PREDETERMINADO_MENU}"
        opciones.append(Opcion(fila.rstrip(), perfil))
    return opciones


def _inicio(prompter: Prompter, store: ProfileStore) -> Profile | None:
    """Menú de inicio; devuelve el perfil elegido o ``None`` al salir."""
    while True:
        perfiles = store.listar()
        predeterminado = store.predeterminado()
        opciones: list[Opcion[Profile | Accion] | Separador] = []
        if perfiles:
            opciones += _opciones_perfiles(perfiles, predeterminado)
            opciones.append(Separador())
        opciones += [
            Opcion(messages.OPCION_AGREGAR, Accion.AGREGAR),
            Opcion(messages.OPCION_ADMINISTRAR, Accion.ADMINISTRAR),
            Opcion(messages.OPCION_SALIR, Accion.SALIR),
        ]
        por_defecto = next((p for p in perfiles if p.name == predeterminado), None)
        eleccion = prompter.select(messages.PREGUNTA_AMBIENTE, opciones, por_defecto)
        if isinstance(eleccion, Profile):
            return eleccion
        if eleccion is Accion.AGREGAR:
            _agregar(prompter, store)
        elif eleccion is Accion.ADMINISTRAR:
            _administrar(prompter, store)
        else:
            return None


def _agregar(prompter: Prompter, store: ProfileStore) -> None:
    """Asistente de §10.3; un error (p. ej. del keyring) se muestra y se vuelve al menú."""
    try:
        forms.agregar_perfil(prompter, store)
    except P6CliError as error:
        render.mostrar_error(error)


# --- Administrar ambientes (§10.4) ------------------------------------------------


def _administrar(prompter: Prompter, store: ProfileStore) -> None:
    """Lista de perfiles y, para el elegido, sus acciones. Vuelve al inicio con «Volver»."""
    while True:
        perfiles = store.listar()
        if not perfiles:
            typer.echo(messages.SIN_PERFILES_MENU)
            return
        opciones: list[Opcion[Profile | Accion] | Separador] = [
            *_opciones_perfiles(perfiles, store.predeterminado()),
            Separador(),
            Opcion(messages.OPCION_VOLVER, Accion.VOLVER),
        ]
        eleccion = prompter.select(messages.PREGUNTA_ADMINISTRAR, opciones)
        if not isinstance(eleccion, Profile):
            return
        try:
            _accion_perfil(prompter, store, eleccion)
        except P6CliError as error:
            render.mostrar_error(error)


def _accion_perfil(prompter: Prompter, store: ProfileStore, perfil: Profile) -> None:
    """Ejecuta una acción sobre el perfil elegido."""
    opciones = (
        Opcion(messages.OPCION_EDITAR, Accion.EDITAR),
        Opcion(messages.OPCION_PROBAR, Accion.PROBAR),
        Opcion(messages.OPCION_PREDETERMINADO, Accion.PREDETERMINADO),
        Opcion(messages.OPCION_ELIMINAR, Accion.ELIMINAR),
        Opcion(messages.OPCION_VOLVER, Accion.VOLVER),
    )
    accion = prompter.select(messages.PREGUNTA_ACCION_PERFIL.format(nombre=perfil.name), opciones)
    if accion is Accion.EDITAR:
        forms.editar_perfil(prompter, store, perfil.name)
    elif accion is Accion.PROBAR:
        _probar(prompter, perfil)
    elif accion is Accion.PREDETERMINADO:
        store.marcar_predeterminado(perfil.name)
        typer.echo(messages.PREDETERMINADO_MARCADO.format(nombre=perfil.name))
    elif accion is Accion.ELIMINAR:
        _eliminar(prompter, store, perfil)


def _probar(prompter: Prompter, perfil: Profile) -> None:
    """Prueba de conexión (§7). Sin clave guardada, la pide y no la guarda."""
    clave = secrets.leer_clave(perfil.name)
    if clave is None:
        typer.echo(messages.AVISO_CLAVE_PRUEBA_MENU.format(nombre=perfil.name))
        clave = forms.pedir_clave_nueva(prompter, messages.PEDIR_CLAVE_TEMPORAL)
    render.reporte_diagnostico(forms.probar(perfil, clave))


def _eliminar(prompter: Prompter, store: ProfileStore, perfil: Profile) -> None:
    """Elimina el perfil y su clave tras confirmar (por defecto, no)."""
    confirmar = messages.CONFIRMAR_ELIMINAR.format(nombre=perfil.name)
    if not prompter.confirm(confirmar, por_defecto=False):
        typer.echo(messages.CANCELADO)
        return
    era_predeterminado = store.predeterminado() == perfil.name
    profiles.eliminar_perfil(store, perfil.name)
    typer.echo(messages.PERFIL_ELIMINADO.format(nombre=perfil.name))
    if era_predeterminado and store.listar():
        typer.echo(messages.SIN_PREDETERMINADO_MENU)


# --- Credenciales (§10.2) ---------------------------------------------------------


def _conectar(perfil: Profile, clave: str) -> Sesion | None:
    """Único intento de login del perfil, con la prueba de conexión completa (§7).

    Devuelve la sesión autenticada si el estado es OK. Si no, muestra el diagnóstico, cierra
    la sesión y devuelve ``None``: nunca se reintenta.
    """
    sesion = Sesion(perfil, clave)
    try:
        typer.echo(messages.PROBANDO_CONEXION.format(nombre=perfil.name))
        with render.progreso_consulta():
            reporte = diagnosticar(sesion)
    except P6CliError as error:
        sesion.cerrar()
        render.mostrar_error(error)
        return None
    except BaseException:
        sesion.cerrar()
        raise
    if reporte.status is EstadoDiagnostico.OK:
        typer.echo(messages.CONEXION_EXITOSA)
        return sesion
    sesion.cerrar()
    render.reporte_diagnostico(reporte)
    return None


def _actualizar(prompter: Prompter, store: ProfileStore, perfil: Profile) -> Sesion | None:
    """Pide usuario y clave, prueba la conexión y, si pasa, los guarda (§10.2).

    Devuelve la sesión ya autenticada, para seguir sin un segundo login.
    """
    usuario = forms.pedir_texto(prompter, messages.PEDIR_USUARIO, perfil.username)
    clave = forms.pedir_clave_nueva(prompter)
    nuevo = dataclasses.replace(perfil, username=usuario)
    sesion = _conectar(nuevo, clave)
    if sesion is None:
        return None
    try:
        profiles.editar_perfil(store, perfil.name, nuevo, clave)
    except P6CliError as error:
        # La conexión funciona; solo falló guardar. Se sigue con la sesión abierta.
        render.mostrar_error(error)
    else:
        typer.echo(messages.CREDENCIALES_GUARDADAS.format(nombre=perfil.name))
    return sesion


def _credenciales(prompter: Prompter, store: ProfileStore, perfil: Profile) -> Sesion | None:
    """Pantalla de credenciales; devuelve una sesión autenticada o ``None`` para volver."""
    try:
        clave = secrets.leer_clave(perfil.name)
    except P6CliError as error:
        render.mostrar_error(error)
        return None
    temporal = clave is None
    if clave is None:
        # Se usa solo en esta sesión: no se guarda (§18).
        typer.echo(messages.AVISO_CLAVE_SESION.format(nombre=perfil.name))
        clave = forms.pedir_clave_nueva(prompter, messages.PEDIR_CLAVE_TEMPORAL)
    render.pantalla_credenciales(perfil, temporal)
    accion = prompter.select(
        messages.PREGUNTA_CREDENCIALES,
        (
            Opcion(messages.OPCION_CONTINUAR, Accion.CONTINUAR),
            Opcion(messages.OPCION_ACTUALIZAR, Accion.ACTUALIZAR),
            Opcion(messages.OPCION_VOLVER, Accion.VOLVER),
        ),
    )
    while accion is not Accion.VOLVER:
        if accion is Accion.CONTINUAR:
            sesion = _conectar(perfil, clave)
        else:
            sesion = _actualizar(prompter, store, perfil)
        if sesion is not None:
            return sesion
        # Tras un login fallido solo se ofrece corregir o volver: nunca se reintenta solo.
        accion = prompter.select(
            messages.PREGUNTA_LOGIN_FALLIDO,
            (
                Opcion(messages.OPCION_ACTUALIZAR, Accion.ACTUALIZAR),
                Opcion(messages.OPCION_VOLVER_INICIO, Accion.VOLVER),
            ),
        )
    return None


# --- Endpoints, consulta y resultados (§10.5 a §10.7) -----------------------------


def _elegir_endpoint(prompter: Prompter) -> Endpoint | Accion:
    """Catálogo agrupado (§10.5)."""
    ancho = max(len(endpoint.key) for endpoint in catalog.CATALOGO)
    opciones: list[Opcion[Endpoint | Accion] | Separador] = []
    for grupo in catalog.grupos():
        opciones.append(Separador(messages.TITULO_GRUPO.format(grupo=grupo)))
        opciones += [
            Opcion(f"{endpoint.key:<{ancho}}   {endpoint.description}", endpoint)
            for endpoint in catalog.CATALOGO
            if endpoint.group == grupo
        ]
    opciones += [
        Separador(),
        Opcion(messages.OPCION_CAMBIAR_AMBIENTE, Accion.CAMBIAR_AMBIENTE),
        Opcion(messages.OPCION_SALIR, Accion.SALIR),
    ]
    return prompter.select(messages.PREGUNTA_ENDPOINT, opciones)


def _consultar(prompter: Prompter, sesion: Sesion) -> Accion:
    """Menú de endpoints y consultas; devuelve ``CAMBIAR_AMBIENTE`` o ``SALIR``."""
    cliente = Cliente(sesion)
    while True:
        eleccion = _elegir_endpoint(prompter)
        if isinstance(eleccion, Accion):
            return eleccion
        if eleccion.template is Plantilla.SPREAD:
            accion = _consultar_spread(prompter, cliente, sesion.perfil, eleccion)
        else:
            accion = _consultar_entity(prompter, cliente, sesion.perfil, eleccion)
        if accion is not Accion.OTRO_ENDPOINT:
            return accion


@dataclass(frozen=True)
class Resultado:
    """Lo recibido de P6 y cómo se muestra.

    ``tabla`` y ``columnas`` son las filas de la tabla; ``respuesta`` es lo que devolvió P6,
    para «Ver el JSON completo» y «Exportar a JSON». En ``entity`` son lo mismo; en spread,
    la tabla tiene una fila por objeto y período. ``csv`` son las columnas y filas de
    «Exportar a CSV» (spread en formato largo); ``None`` si no se puede exportar a CSV.
    ``unidades`` nombra los elementos de ``respuesta`` (filas u objetos).
    """

    tabla: Sequence[Fila]
    columnas: Sequence[str]
    respuesta: Sequence[Fila]
    encabezado: str
    perfil: str
    endpoint: str
    csv: tuple[Sequence[str], Sequence[Fila]] | None
    unidades: tuple[str, str] = (messages.UNIDAD_FILA, messages.UNIDAD_FILAS)


def _consultar_entity(
    prompter: Prompter, cliente: Cliente, perfil: Profile, endpoint: Endpoint
) -> Accion:
    """Formulario, ejecución, resultados y siguiente paso para un endpoint ``entity``."""
    valores = ValoresEntity()
    while True:
        consulta = forms.formulario_entity(prompter, cliente, perfil, endpoint, valores)
        if consulta is None:
            return Accion.OTRO_ENDPOINT
        valores = consulta.valores
        inicio = time.perf_counter()
        try:
            with render.progreso_consulta():
                filas = cliente.get(
                    endpoint, valores.params(), allow_unfiltered=consulta.allow_unfiltered
                )
        except P6CliError as error:
            # Regla 7: se muestra el error y el formulario reaparece con lo escrito.
            render.mostrar_error(error)
            continue
        segundos = time.perf_counter() - inicio
        encabezado = render.encabezado_resultados(endpoint.key, len(filas), segundos)
        resultado = Resultado(
            filas,
            consulta.campos,
            filas,
            encabezado,
            perfil.name,
            endpoint.key,
            csv=(consulta.campos, filas),
        )
        _mostrar_tabla(resultado)
        siguiente = _siguiente_paso(prompter, resultado)
        if siguiente is not Accion.NUEVA_CONSULTA:
            return siguiente


def _consultar_spread(
    prompter: Prompter, cliente: Cliente, perfil: Profile, endpoint: Endpoint
) -> Accion:
    """Formulario, ejecución por lotes, resultados y siguiente paso para un spread (§11.2)."""
    valores = ValoresSpread()
    while True:
        consulta = forms.formulario_spread(prompter, cliente, perfil, endpoint, valores)
        if consulta is None:
            return Accion.OTRO_ENDPOINT
        valores = consulta.valores
        inicio = time.perf_counter()
        try:
            with render.progreso_lotes() as avisar:
                respuesta = cliente.get_spread(endpoint, consulta.params(), on_progress=avisar)
        except P6CliError as error:
            # Regla 7: se muestra el error y el formulario reaparece con lo escrito.
            render.mostrar_error(error)
            continue
        segundos = time.perf_counter() - inicio
        tabla = filas_por_periodo(respuesta, endpoint, consulta.campos)
        columnas: list[str] = []
        filas: list[Fila] = []
        if tabla is None:
            encabezado = render.encabezado_resultados(endpoint.key, len(respuesta), segundos)
            render.aviso_sin_tabla(encabezado, messages.AVISO_SPREAD_SIN_TABLA_MENU)
        else:
            columnas, filas = tabla
            encabezado = render.encabezado_spread(
                endpoint.key, len(respuesta), len(filas), segundos
            )
        resultado = Resultado(
            filas,
            columnas,
            respuesta,
            encabezado,
            perfil.name,
            endpoint.key,
            csv=filas_spread_largo(respuesta, endpoint, consulta.campos),
            unidades=(messages.UNIDAD_OBJETO, messages.UNIDAD_OBJETOS),
        )
        if tabla is not None:
            _mostrar_tabla(resultado)
        siguiente = _siguiente_paso(prompter, resultado)
        if siguiente is not Accion.NUEVA_CONSULTA:
            return siguiente


def _mostrar_tabla(resultado: Resultado) -> None:
    """Las primeras filas de la tabla, con el aviso del menú si no caben todas."""
    render.tabla_resultados(
        resultado.tabla,
        resultado.columnas,
        render.FILAS_TABLA,
        resultado.encabezado,
        aviso=messages.AVISO_FILAS_MOSTRADAS_MENU,
    )


def _siguiente_paso(prompter: Prompter, resultado: Resultado) -> Accion:
    """«¿Qué sigue?» (§10.7). Ver o exportar usa lo ya recibido y vuelve aquí."""
    while True:
        siguiente = prompter.select(messages.PREGUNTA_SIGUIENTE, _opciones_siguiente(resultado))
        if siguiente in (Accion.VER_TABLA, Accion.VER_JSON):
            _ver_completo(prompter, siguiente, resultado)
        elif siguiente in (Accion.EXPORTAR_CSV, Accion.EXPORTAR_JSON):
            _exportar(prompter, siguiente, resultado)
        else:
            return siguiente


def _opciones_siguiente(resultado: Resultado) -> tuple[Opcion[Accion], ...]:
    """Opciones de «¿Qué sigue?» (§10.7) según lo recibido."""
    opciones: list[Opcion[Accion]] = []
    if len(resultado.tabla) > render.FILAS_TABLA:
        titulo = messages.OPCION_VER_TABLA.format(filas=render.numero(len(resultado.tabla)))
        opciones.append(Opcion(titulo, Accion.VER_TABLA))
    if resultado.respuesta:
        opciones.append(Opcion(messages.OPCION_VER_JSON, Accion.VER_JSON))
    # Un spread que no se pudo aplanar solo se exporta tal cual, en JSON.
    sin_csv = messages.SPREAD_SIN_CSV if resultado.csv is None else None
    return (
        *opciones,
        Opcion(messages.OPCION_EXPORTAR_CSV, Accion.EXPORTAR_CSV, deshabilitada=sin_csv),
        Opcion(messages.OPCION_EXPORTAR_JSON, Accion.EXPORTAR_JSON),
        Opcion(messages.OPCION_NUEVA_CONSULTA, Accion.NUEVA_CONSULTA),
        Opcion(messages.OPCION_OTRO_ENDPOINT, Accion.OTRO_ENDPOINT),
        Opcion(messages.OPCION_CAMBIAR_AMBIENTE, Accion.CAMBIAR_AMBIENTE),
        Opcion(messages.OPCION_SALIR, Accion.SALIR),
    )


def _ver_completo(prompter: Prompter, accion: Accion, resultado: Resultado) -> None:
    """Tabla o JSON completos; con muchas filas, pide confirmar (por defecto, no)."""
    filas = resultado.tabla if accion is Accion.VER_TABLA else resultado.respuesta
    if len(filas) > FILAS_AVISO_SALIDA_COMPLETA:
        pregunta = messages.CONFIRMAR_SALIDA_COMPLETA.format(filas=render.numero(len(filas)))
        if not prompter.confirm(pregunta, por_defecto=False):
            return
    if accion is Accion.VER_TABLA:
        render.tabla_resultados(filas, resultado.columnas, 0, resultado.encabezado)
    else:
        render.json_resultados(filas)


def _exportar(prompter: Prompter, accion: Accion, resultado: Resultado) -> None:
    """Confirma la ruta completa y exporta lo recibido, sin consultar a P6.

    Propone <directorio de trabajo>/exports/<nombre>: «De acuerdo» la acepta y «Cambiar
    ruta» pide otra carpeta (ruta completa); el nombre del archivo siempre lo pone el
    programa. Nunca sobrescribe: si el archivo existe se agrega un sufijo y se informa la
    ruta real. Un error (permisos) se muestra y se vuelve a «¿Qué sigue?».
    """
    formato = Formato.CSV if accion is Accion.EXPORTAR_CSV else Formato.JSON
    nombre = nombre_archivo(resultado.perfil, resultado.endpoint, formato, datetime.now())
    carpeta = Path.cwd() / CARPETA_EXPORTACION
    opciones = (
        Opcion(messages.OPCION_DE_ACUERDO, Accion.DE_ACUERDO),
        Opcion(messages.OPCION_CAMBIAR_RUTA, Accion.CAMBIAR_RUTA),
    )
    while (
        prompter.select(messages.PREGUNTA_RUTA_EXPORTAR.format(ruta=carpeta / nombre), opciones)
        is Accion.CAMBIAR_RUTA
    ):
        carpeta = _pedir_carpeta(prompter, carpeta)
    ruta = carpeta / nombre
    try:
        if formato is Formato.JSON:
            escrita = escribir_json(ruta, resultado.respuesta)
            render.exportado(escrita, len(resultado.respuesta), *resultado.unidades)
            return
        assert resultado.csv is not None
        columnas, filas = resultado.csv
        escrita = escribir_csv(ruta, filas, columnas)
        render.exportado(escrita, len(filas))
    except P6CliError as error:
        render.mostrar_error(error)


def _pedir_carpeta(prompter: Prompter, actual: Path) -> Path:
    """Pide la carpeta destino con la actual ya escrita; exige una ruta completa."""
    while True:
        texto = forms.pedir_texto(prompter, messages.ETIQUETA_CARPETA_EXPORTAR, str(actual))
        carpeta = Path(texto).expanduser()
        if carpeta.is_absolute():
            return carpeta
        typer.echo(messages.CARPETA_NO_COMPLETA, err=True)
