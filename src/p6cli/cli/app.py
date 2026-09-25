"""Aplicación Typer: comandos con flags; sin argumentos abre los menús."""

import json
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Annotated, Any

import typer
from rich.console import Console

from p6cli import __version__
from p6cli.cli import forms, menus, messages, render
from p6cli.cli.prompter import PrompterQuestionary, PrompterTexto
from p6cli.core import catalog, profiles, secrets
from p6cli.core.catalog import FIELDS, FILTER, ORDER_BY, Endpoint, Plantilla
from p6cli.core.client import Cliente, validar_consulta
from p6cli.core.diagnostics import EstadoDiagnostico
from p6cli.core.errors import (
    AuthError,
    GuardrailError,
    MotivoAuth,
    MotivoPerfil,
    MotivoUso,
    P6CliError,
    P6HTTPError,
    ProfileError,
    SecretStoreError,
    UsageError,
)
from p6cli.core.profiles import Profile, ProfileStore
from p6cli.core.session import Sesion

# Códigos de salida (especificación §12).
SALIDA_ERROR_P6 = 1
SALIDA_ERROR_USO = 2
SALIDA_GUARDARRAIL = 3
SALIDA_INTERRUMPIDO = 130

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
        with _errores_a_salida():
            menus.ejecutar(PrompterQuestionary())


def main() -> None:
    """Ejecuta la aplicación; usado por el script ``p6`` y por ``python -m p6cli``."""
    app()


# --- Errores ---------------------------------------------------------------------


def _codigo_salida(error: P6CliError) -> int:
    """Código de §12: 1 error de P6 o HTTP · 2 uso o configuración · 3 guardarraíl."""
    if isinstance(error, P6HTTPError):
        return SALIDA_ERROR_P6
    if isinstance(error, AuthError) and error.motivo is MotivoAuth.LOGIN_FALLIDO:
        return SALIDA_ERROR_P6
    if isinstance(error, GuardrailError):
        return SALIDA_GUARDARRAIL
    return SALIDA_ERROR_USO


@contextmanager
def _errores_a_salida() -> Iterator[None]:
    """Traduce los errores de ``core`` a un mensaje y al código de salida de §12.

    Una interrupción (Ctrl+C, también dentro de una pregunta) sale con 130 y el mensaje
    estándar ``Aborted!``.
    """
    try:
        yield
    except P6CliError as error:
        typer.echo(render.texto_error(error), err=True)
        raise typer.Exit(code=_codigo_salida(error)) from None
    except KeyboardInterrupt:
        typer.echo("", err=True)
        typer.echo(messages.ABORTADO, err=True)
        raise typer.Exit(code=SALIDA_INTERRUMPIDO) from None
    except typer.Abort:
        typer.echo(messages.ABORTADO, err=True)
        raise typer.Exit(code=SALIDA_INTERRUMPIDO) from None


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
    """Asistente para agregar un perfil (§10.3). La clave nunca se recibe por flag."""
    with _errores_a_salida():
        forms.agregar_perfil(PrompterTexto(), ProfileStore())


@perfiles_app.command("edit", help=messages.AYUDA_PERFILES_EDIT)
def editar_perfil(name: ArgumentoNombre) -> None:
    """Repite el asistente con los valores actuales como predeterminados."""
    with _errores_a_salida():
        forms.editar_perfil(PrompterTexto(), ProfileStore(), name)


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
        if not yes and not PrompterTexto().confirm(
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


# --- Perfil y clave de una ejecución ---------------------------------------------


def _perfil(nombre: str | None) -> Profile:
    """El perfil indicado o, sin nombre, el predeterminado."""
    store = ProfileStore()
    nombre = nombre if nombre is not None else store.predeterminado()
    if nombre is None:
        raise ProfileError(MotivoPerfil.SIN_PREDETERMINADO)
    return store.obtener(nombre)


def _clave(perfil: Profile, aviso: str, *, err: bool = False) -> str:
    """Clave guardada del perfil; si no hay, la pide oculta para esta ejecución sin guardarla."""
    clave = secrets.leer_clave(perfil.name)
    if clave is None:
        typer.echo(aviso.format(nombre=perfil.name), err=err)
        clave = forms.pedir_clave_nueva(PrompterTexto(err=err), messages.PEDIR_CLAVE_TEMPORAL)
    return clave


# --- Diagnóstico ----------------------------------------------------------------


@app.command("doctor", help=messages.AYUDA_DOCTOR)
def doctor(
    name: Annotated[str | None, typer.Argument(help=messages.AYUDA_ARG_NOMBRE_DOCTOR)] = None,
) -> None:
    """Prueba de conexión con diagnóstico. Sale con 0 si conecta y con 1 si no."""
    with _errores_a_salida():
        perfil = _perfil(name)
        clave = _clave(perfil, messages.AVISO_CLAVE_NO_GUARDADA)
        reporte = forms.probar(perfil, clave)
        render.reporte_diagnostico(reporte)
        if reporte.status is not EstadoDiagnostico.OK:
            raise typer.Exit(code=SALIDA_ERROR_P6)


# --- Catálogo y consultas -------------------------------------------------------

ArgumentoEndpoint = Annotated[str, typer.Argument(help=messages.AYUDA_ARG_ENDPOINT)]
OpcionEnv = Annotated[str | None, typer.Option("--env", help=messages.AYUDA_OPCION_ENV)]


def _endpoint_entity(clave: str) -> Endpoint:
    """Endpoint del catálogo que admite lectura simple (plantilla ``entity``)."""
    endpoint = catalog.obtener(clave)
    if endpoint.template is not Plantilla.ENTITY:
        raise UsageError(MotivoUso.PLANTILLA_NO_SOPORTADA, endpoint=endpoint.key)
    return endpoint


def _esperando() -> AbstractContextManager[Any]:
    """Indicador de espera en stderr, para no mezclarse con la salida de datos."""
    return Console(stderr=True).status(messages.ESPERANDO_RESPUESTA)


@app.command("endpoints", help=messages.AYUDA_ENDPOINTS)
def endpoints(
    group: Annotated[str | None, typer.Option("--group", help=messages.AYUDA_OPCION_GRUPO)] = None,
) -> None:
    """Lista el catálogo, opcionalmente filtrado por grupo (sin distinguir mayúsculas)."""
    entradas = list(enumerate(catalog.CATALOGO, start=1))
    if group is not None:
        buscado = group.strip().casefold()
        grupo = next((g for g in catalog.grupos() if g.casefold() == buscado), None)
        if grupo is None:
            typer.echo(
                messages.GRUPO_INEXISTENTE.format(grupo=group, grupos=", ".join(catalog.grupos())),
                err=True,
            )
            raise typer.Exit(code=SALIDA_ERROR_USO)
        entradas = [(numero, e) for numero, e in entradas if e.group == grupo]
    render.tabla_endpoints(entradas)


@app.command("syntax", help=messages.AYUDA_SYNTAX)
def sintaxis(
    tema: Annotated[str | None, typer.Argument(help=messages.AYUDA_ARG_TEMA)] = None,
) -> None:
    """Guía de sintaxis de un tema; sin tema, lista los temas. No toca la red ni los perfiles."""
    guias = messages.GUIAS_SINTAXIS
    if tema is None:
        render.lista_temas(guias)
        return
    guia = guias.get(tema.strip().lower())
    if guia is None:
        typer.echo(
            messages.TEMA_INEXISTENTE.format(tema=tema, temas=", ".join(guias)),
            err=True,
        )
        raise typer.Exit(code=SALIDA_ERROR_USO)
    render.guia_sintaxis(guia)


@app.command("fields", help=messages.AYUDA_FIELDS)
def campos(endpoint: ArgumentoEndpoint, env: OpcionEnv = None) -> None:
    """Campos válidos de un endpoint ``entity``, consultados en vivo."""
    with _errores_a_salida():
        destino = _endpoint_entity(endpoint)
        perfil = _perfil(env)
        clave = _clave(perfil, messages.AVISO_CLAVE_NO_GUARDADA_CONSULTA, err=True)
        with Sesion(perfil, clave) as sesion, _esperando():
            lista = Cliente(sesion).fields(destino)
        render.lista_campos(destino.key, lista)


@app.command("get", help=messages.AYUDA_GET)
def get(
    endpoint: ArgumentoEndpoint,
    fields: Annotated[str, typer.Option("--fields", help=messages.AYUDA_OPCION_FIELDS)],
    filtro: Annotated[str, typer.Option("--filter", help=messages.AYUDA_OPCION_FILTER)] = "",
    orden: Annotated[str, typer.Option("--order-by", help=messages.AYUDA_OPCION_ORDER_BY)] = "",
    env: OpcionEnv = None,
    allow_unfiltered: Annotated[
        bool, typer.Option("--allow-unfiltered", help=messages.AYUDA_OPCION_ALLOW_UNFILTERED)
    ] = False,
    max_rows: Annotated[
        int, typer.Option("--max-rows", min=0, help=messages.AYUDA_OPCION_MAX_ROWS)
    ] = render.FILAS_TABLA,
    como_json: Annotated[bool, typer.Option("--json", help=messages.AYUDA_OPCION_JSON)] = False,
) -> None:
    """Lectura simple. Valida todo antes de pedir la clave y de hacer el login."""
    with _errores_a_salida():
        destino = _endpoint_entity(endpoint)
        perfil = _perfil(env)
        params = {FIELDS: fields, FILTER: filtro, ORDER_BY: orden}
        consulta = validar_consulta(perfil, destino, params, allow_unfiltered=allow_unfiltered)
        clave = _clave(perfil, messages.AVISO_CLAVE_NO_GUARDADA_CONSULTA, err=True)
        inicio = time.perf_counter()
        with Sesion(perfil, clave) as sesion, _esperando():
            filas = Cliente(sesion).get(destino, params, allow_unfiltered=allow_unfiltered)
        segundos = time.perf_counter() - inicio
        if como_json:
            typer.echo(json.dumps(filas, indent=2, ensure_ascii=False))
            return
        render.tabla_resultados(
            filas,
            consulta[FIELDS].split(","),
            max_rows,
            render.encabezado_resultados(destino.key, len(filas), segundos),
        )
