"""Aplicación Typer: comandos con flags; sin argumentos abre los menús."""

import dataclasses
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from p6cli import __version__
from p6cli.cli import messages, render
from p6cli.core import profiles, secrets
from p6cli.core.diagnostics import DiagnosticReport, EstadoDiagnostico, probar_conexion
from p6cli.core.errors import (
    ConfigError,
    MotivoPerfil,
    P6CliError,
    ProfileError,
    SecretStoreError,
)
from p6cli.core.profiles import Profile, ProfileStore
from p6cli.core.urls import AdvertenciaUrl, normalizar_url

# Códigos de salida (especificación §12).
SALIDA_ERROR_P6 = 1
SALIDA_ERROR_USO = 2

app = typer.Typer(help=messages.AYUDA_APP, add_completion=False)
perfiles_app = typer.Typer(help=messages.AYUDA_PERFILES, no_args_is_help=True)
app.add_typer(perfiles_app, name="profiles")

ArgumentoNombre = Annotated[str, typer.Argument(help=messages.AYUDA_ARG_NOMBRE)]


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


# --- Errores ---------------------------------------------------------------------


def _texto_error(error: P6CliError) -> str:
    return messages.ERRORES[error.motivo].format(**error.datos)


@contextmanager
def _errores_a_salida() -> Iterator[None]:
    """Traduce los errores de ``core`` a un mensaje y al código de salida de §12."""
    try:
        yield
    except P6CliError as error:
        typer.echo(_texto_error(error), err=True)
        raise typer.Exit(code=SALIDA_ERROR_USO) from None


# --- Preguntas ------------------------------------------------------------------


def _confirmar(texto: str, por_defecto: bool) -> bool:
    """Pregunta sí/no con el estándar ``(Y/n)``: solo acepta y o n; Enter toma el defecto."""
    sufijo = messages.SUFIJO_CONFIRMAR_SI if por_defecto else messages.SUFIJO_CONFIRMAR_NO
    while True:
        respuesta = str(typer.prompt(texto + sufijo, default="", show_default=False))
        respuesta = respuesta.strip().lower()
        if not respuesta:
            return por_defecto
        if respuesta == messages.RESPUESTA_SI:
            return True
        if respuesta == messages.RESPUESTA_NO:
            return False
        typer.echo(messages.RESPUESTA_SI_NO_INVALIDA, err=True)


# --- Asistente de perfil --------------------------------------------------------


def _pedir_texto(texto: str, actual: str | None) -> str:
    """Pide un dato obligatorio; recorta espacios y repregunta si queda vacío."""
    while True:
        valor = str(typer.prompt(texto, default=actual, show_default=actual is not None))
        if valor.strip():
            return valor.strip()
        typer.echo(messages.DATO_OBLIGATORIO, err=True)


def _pedir_nombre(store: ProfileStore, actual: str | None, nombre_original: str | None) -> str:
    """Pide el nombre. ``nombre_original`` (perfil que se edita) no cuenta como duplicado."""
    existentes = {perfil.name for perfil in store.listar()}
    while True:
        nombre = _pedir_texto(messages.PEDIR_NOMBRE, actual)
        try:
            profiles.validar_nombre(nombre)
            if nombre != nombre_original and nombre in existentes:
                raise ProfileError(MotivoPerfil.YA_EXISTE, nombre=nombre)
        except ProfileError as error:
            typer.echo(_texto_error(error), err=True)
            continue
        return nombre


def _pedir_url(actual: Profile | None) -> tuple[str, str]:
    """Pide la URL, muestra la normalización y la hace confirmar. Devuelve (host, context)."""
    por_defecto = f"{actual.host}/{actual.context}" if actual else None
    while True:
        texto = _pedir_texto(messages.PEDIR_URL, por_defecto)
        try:
            url = normalizar_url(texto)
        except ConfigError as error:
            typer.echo(_texto_error(error), err=True)
            continue
        typer.echo(messages.URL_NORMALIZADA.format(host=url.host, context=url.context))
        if AdvertenciaUrl.SIN_CIFRADO in url.advertencias:
            typer.echo(messages.ADVERTENCIA_SIN_CIFRADO)
        if _confirmar(messages.CONFIRMAR_URL, por_defecto=True):
            return url.host, url.context


def _pedir_oculto(texto: str) -> str:
    return str(typer.prompt(texto, default="", show_default=False, hide_input=True))


def _pedir_clave_nueva(texto: str = messages.PEDIR_CLAVE) -> str:
    """Pide la clave oculta; no se acepta vacía."""
    while True:
        clave = _pedir_oculto(texto)
        if clave:
            return clave
        typer.echo(messages.CLAVE_VACIA, err=True)


def _pedir_clave_opcional() -> str | None:
    """Pide la clave oculta al editar; vacía significa conservar la actual (``None``)."""
    return _pedir_oculto(messages.PEDIR_CLAVE_EDITAR) or None


def _pedir_ca(actual: str | None) -> str:
    while True:
        ruta = Path(_pedir_texto(messages.PEDIR_CA, actual)).expanduser()
        if ruta.is_file():
            return str(ruta.resolve())
        typer.echo(messages.CA_NO_EXISTE.format(ruta=ruta), err=True)


def _pedir_tls(actual: bool | str) -> bool | str:
    if actual is True:
        por_defecto = messages.TLS_SI
    elif actual is False:
        por_defecto = messages.TLS_NO
    else:
        por_defecto = messages.TLS_CA
    while True:
        opcion = _pedir_texto(messages.PEDIR_TLS, por_defecto).lower()
        if opcion == messages.TLS_SI:
            return True
        if opcion == messages.TLS_NO:
            typer.echo(messages.ADVERTENCIA_TLS_DESACTIVADO)
            return False
        if opcion == messages.TLS_CA:
            return _pedir_ca(actual if isinstance(actual, str) else None)
        typer.echo(messages.OPCION_TLS_INVALIDA, err=True)


def _asistente_perfil[T](
    store: ProfileStore,
    actual: Profile | None,
    nombre_original: str | None,
    pedir_clave: Callable[[], T],
) -> tuple[Profile, T]:
    """Pide los datos de un perfil (§10.3). Con ``actual``, sus valores son los predeterminados.

    ``nombre_original`` es el nombre guardado del perfil que se edita (``None`` al agregar).
    """
    nombre = _pedir_nombre(store, actual.name if actual else None, nombre_original)
    host, context = _pedir_url(actual)
    database_name = _pedir_texto(messages.PEDIR_DATABASE, actual.database_name if actual else None)
    username = _pedir_texto(messages.PEDIR_USUARIO, actual.username if actual else None)
    clave = pedir_clave()
    verify_ssl = _pedir_tls(actual.verify_ssl if actual else True)
    if actual is None:
        perfil = Profile(
            name=nombre,
            host=host,
            context=context,
            database_name=database_name,
            username=username,
            verify_ssl=verify_ssl,
        )
    else:
        # Los campos avanzados (timeout, lotes, pausa) se conservan: solo se editan en el TOML.
        perfil = dataclasses.replace(
            actual,
            name=nombre,
            host=host,
            context=context,
            database_name=database_name,
            username=username,
            verify_ssl=verify_ssl,
        )
    return perfil, clave


# --- Prueba de conexión ---------------------------------------------------------


class _Decision(Enum):
    GUARDAR = "guardar"
    CORREGIR = "corregir"
    CANCELAR = "cancelar"


def _probar(perfil: Profile, clave: str) -> DiagnosticReport:
    """Avisa del intento de login y ejecuta la prueba de conexión (§7)."""
    typer.echo(messages.PROBANDO_CONEXION.format(nombre=perfil.name))
    with Console().status(messages.ESPERANDO_RESPUESTA):
        return probar_conexion(perfil, clave)


def _probar_y_decidir(perfil: Profile, clave: str) -> _Decision:
    """Prueba la conexión; si falla, muestra el diagnóstico y pregunta qué hacer (§10.3)."""
    reporte = _probar(perfil, clave)
    if reporte.status is EstadoDiagnostico.OK:
        typer.echo(messages.CONEXION_EXITOSA)
        return _Decision.GUARDAR
    render.reporte_diagnostico(reporte)
    opciones = {
        messages.OPCION_CORREGIR: _Decision.CORREGIR,
        messages.OPCION_GUARDAR: _Decision.GUARDAR,
        messages.OPCION_CANCELAR: _Decision.CANCELAR,
    }
    while True:
        opcion = _pedir_texto(messages.PREGUNTA_FALLO_CONEXION, messages.OPCION_CORREGIR)
        if opcion.lower() in opciones:
            return opciones[opcion.lower()]
        typer.echo(messages.OPCION_FALLO_INVALIDA, err=True)


# --- Comandos de perfiles -------------------------------------------------------


@perfiles_app.command("list", help=messages.AYUDA_PERFILES_LIST)
def listar_perfiles() -> None:
    """Lista los perfiles con la clave enmascarada."""
    with _errores_a_salida():
        store = ProfileStore()
        perfiles = store.listar()
        if not perfiles:
            typer.echo(messages.SIN_PERFILES)
            return
        estado_claves: list[str] = []
        for perfil in perfiles:
            try:
                tiene_clave = secrets.leer_clave(perfil.name) is not None
            except SecretStoreError:
                estado_claves = [messages.CLAVE_KEYRING_NO_DISPONIBLE] * len(perfiles)
                break
            estado_claves.append(
                messages.CLAVE_ENMASCARADA if tiene_clave else messages.CLAVE_AUSENTE
            )
        render.tabla_perfiles(perfiles, store.predeterminado(), estado_claves)


@perfiles_app.command("add", help=messages.AYUDA_PERFILES_ADD)
def agregar_perfil() -> None:
    """Asistente para agregar un perfil. La clave nunca se recibe por flag.

    Antes de guardar se prueba la conexión; si falla, el usuario decide si corrige, guarda
    de todas formas o cancela. Cada nueva prueba ocurre solo porque el usuario lo pidió.
    """
    with _errores_a_salida():
        store = ProfileStore()
        perfil, clave = _asistente_perfil(store, None, None, _pedir_clave_nueva)
        while (decision := _probar_y_decidir(perfil, clave)) is _Decision.CORREGIR:
            typer.echo(messages.AVISO_EDITAR)
            perfil, otra_clave = _asistente_perfil(store, perfil, None, _pedir_clave_opcional)
            clave = otra_clave or clave
        if decision is _Decision.CANCELAR:
            typer.echo(messages.CANCELADO)
            return
        profiles.crear_perfil(store, perfil, clave)
        mensaje = (
            messages.PERFIL_GUARDADO_PREDETERMINADO
            if store.predeterminado() == perfil.name
            else messages.PERFIL_GUARDADO
        )
        typer.echo(mensaje.format(nombre=perfil.name))


@perfiles_app.command("edit", help=messages.AYUDA_PERFILES_EDIT)
def editar_perfil(name: ArgumentoNombre) -> None:
    """Repite el asistente con los valores actuales como predeterminados.

    La prueba de conexión usa la clave nueva o, si se conservó, la guardada.
    """
    with _errores_a_salida():
        store = ProfileStore()
        actual = store.obtener(name)
        typer.echo(messages.AVISO_EDITAR)
        perfil, clave_nueva = _asistente_perfil(store, actual, name, _pedir_clave_opcional)
        clave_guardada = secrets.leer_clave(name)
        while True:
            clave_prueba = clave_nueva or clave_guardada
            if clave_prueba is None:
                typer.echo(messages.CLAVE_REQUERIDA_PRUEBA)
                clave_nueva = clave_prueba = _pedir_clave_nueva()
            decision = _probar_y_decidir(perfil, clave_prueba)
            if decision is not _Decision.CORREGIR:
                break
            typer.echo(messages.AVISO_EDITAR)
            perfil, otra_clave = _asistente_perfil(store, perfil, name, _pedir_clave_opcional)
            clave_nueva = otra_clave or clave_nueva
        if decision is _Decision.CANCELAR:
            typer.echo(messages.CANCELADO)
            return
        profiles.editar_perfil(store, name, perfil, clave_nueva)
        typer.echo(messages.PERFIL_ACTUALIZADO.format(nombre=perfil.name))


@perfiles_app.command("remove", help=messages.AYUDA_PERFILES_REMOVE)
def eliminar_perfil(
    name: ArgumentoNombre,
    yes: Annotated[bool, typer.Option("--yes", "-y", help=messages.AYUDA_YES)] = False,
) -> None:
    """Elimina el perfil y su clave, con confirmación salvo ``--yes``."""
    with _errores_a_salida():
        store = ProfileStore()
        store.obtener(name)
        era_predeterminado = store.predeterminado() == name
        if not yes and not _confirmar(
            messages.CONFIRMAR_ELIMINAR.format(nombre=name), por_defecto=False
        ):
            typer.echo(messages.CANCELADO)
            return
        profiles.eliminar_perfil(store, name)
        typer.echo(messages.PERFIL_ELIMINADO.format(nombre=name))
        if era_predeterminado and store.listar():
            typer.echo(messages.SIN_PREDETERMINADO)


@perfiles_app.command("default", help=messages.AYUDA_PERFILES_DEFAULT)
def marcar_predeterminado(name: ArgumentoNombre) -> None:
    """Marca el perfil como predeterminado."""
    with _errores_a_salida():
        ProfileStore().marcar_predeterminado(name)
        typer.echo(messages.PREDETERMINADO_MARCADO.format(nombre=name))


# --- Diagnóstico ----------------------------------------------------------------


@app.command("doctor", help=messages.AYUDA_DOCTOR)
def doctor(
    name: Annotated[str | None, typer.Argument(help=messages.AYUDA_ARG_NOMBRE_DOCTOR)] = None,
) -> None:
    """Prueba de conexión con diagnóstico. Sale con 0 si conecta y con 1 si no."""
    with _errores_a_salida():
        store = ProfileStore()
        nombre = name if name is not None else store.predeterminado()
        if nombre is None:
            raise ProfileError(MotivoPerfil.SIN_PREDETERMINADO)
        perfil = store.obtener(nombre)
        clave = secrets.leer_clave(perfil.name)
        if clave is None:
            typer.echo(messages.AVISO_CLAVE_NO_GUARDADA.format(nombre=perfil.name))
            clave = _pedir_clave_nueva(messages.PEDIR_CLAVE_DOCTOR)
        reporte = _probar(perfil, clave)
        render.reporte_diagnostico(reporte)
        if reporte.status is not EstadoDiagnostico.OK:
            raise typer.Exit(code=SALIDA_ERROR_P6)
