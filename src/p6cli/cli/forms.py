"""Formularios: asistente de perfil (§10.3) y parámetros de las plantillas (§11).

Todo se pregunta con un ``Prompter``: los menús usan listas con flechas y los comandos
``p6 profiles add/edit`` preguntas de texto, con la misma lógica.
"""

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.text import Text

from p6cli.cli import messages, render
from p6cli.cli.prompter import Opcion, Prompter
from p6cli.core import profiles, secrets
from p6cli.core.catalog import (
    END_DATE,
    FIELDS,
    FILTER,
    INCLUDE_CUMULATIVE,
    ORDER_BY,
    PERIOD_TYPE,
    PERIODO_POR_DEFECTO,
    PERIODOS,
    SPREAD_FIELD,
    START_DATE,
    Endpoint,
    campos_spread,
    entidad_base,
    normalizar_ids,
    param_ids,
)
from p6cli.core.client import Cliente, validar_consulta, validar_spread
from p6cli.core.diagnostics import DiagnosticReport, EstadoDiagnostico, probar_conexion
from p6cli.core.errors import ConfigError, MotivoPerfil, P6CliError, ProfileError, UsageError
from p6cli.core.export import leer_ids
from p6cli.core.profiles import Profile, ProfileStore
from p6cli.core.urls import AdvertenciaUrl, normalizar_url

# --- Datos del perfil -------------------------------------------------------------


def pedir_texto(prompter: Prompter, texto: str, actual: str | None) -> str:
    """Pide un dato obligatorio; recorta espacios y repregunta si queda vacío."""
    while True:
        valor = prompter.text(texto, actual or "")
        if valor.strip():
            return valor.strip()
        typer.echo(messages.DATO_OBLIGATORIO, err=True)


def pedir_clave_nueva(prompter: Prompter, texto: str = messages.PEDIR_CLAVE) -> str:
    """Pide la clave oculta; no se acepta vacía."""
    while True:
        clave = prompter.password(texto)
        if clave:
            return clave
        typer.echo(messages.CLAVE_VACIA, err=True)


def pedir_clave_opcional(prompter: Prompter) -> str | None:
    """Pide la clave oculta al editar; vacía significa conservar la actual (``None``)."""
    return prompter.password(messages.PEDIR_CLAVE_EDITAR) or None


def _pedir_nombre(
    prompter: Prompter, store: ProfileStore, actual: str | None, nombre_original: str | None
) -> str:
    """Pide el nombre. ``nombre_original`` (perfil que se edita) no cuenta como duplicado."""
    existentes = {perfil.name for perfil in store.listar()}
    while True:
        nombre = pedir_texto(prompter, messages.PEDIR_NOMBRE, actual)
        try:
            profiles.validar_nombre(nombre)
            if nombre != nombre_original and nombre in existentes:
                raise ProfileError(MotivoPerfil.YA_EXISTE, nombre=nombre)
        except ProfileError as error:
            render.mostrar_error(error)
            continue
        return nombre


def _pedir_url(prompter: Prompter, actual: Profile | None) -> tuple[str, str]:
    """Pide la URL, muestra la normalización y la hace confirmar. Devuelve (host, context)."""
    por_defecto = f"{actual.host}/{actual.context}" if actual else None
    while True:
        texto = pedir_texto(prompter, messages.PEDIR_URL, por_defecto)
        try:
            url = normalizar_url(texto)
        except ConfigError as error:
            render.mostrar_error(error)
            continue
        typer.echo(messages.URL_NORMALIZADA.format(host=url.host, context=url.context))
        if AdvertenciaUrl.SIN_CIFRADO in url.advertencias:
            typer.echo(messages.ADVERTENCIA_SIN_CIFRADO)
        if prompter.confirm(messages.CONFIRMAR_URL, por_defecto=True):
            return url.host, url.context


def _pedir_ca(prompter: Prompter, actual: str | None) -> str:
    while True:
        ruta = Path(pedir_texto(prompter, messages.PEDIR_CA, actual)).expanduser()
        if ruta.is_file():
            return str(ruta.resolve())
        typer.echo(messages.CA_NO_EXISTE.format(ruta=ruta), err=True)


class ModoTLS(Enum):
    """Respuestas a la pregunta de TLS del asistente."""

    VALIDAR = "validar"
    NO_VALIDAR = "no_validar"
    CA_PROPIA = "ca_propia"


OPCIONES_TLS = (
    Opcion(messages.TITULO_TLS_SI, ModoTLS.VALIDAR, tecla=messages.TLS_SI),
    Opcion(messages.TITULO_TLS_NO, ModoTLS.NO_VALIDAR, tecla=messages.TLS_NO),
    Opcion(messages.TITULO_TLS_CA, ModoTLS.CA_PROPIA, tecla=messages.TLS_CA),
)


def _pedir_tls(prompter: Prompter, actual: bool | str) -> bool | str:
    if actual is True:
        por_defecto = ModoTLS.VALIDAR
    elif actual is False:
        por_defecto = ModoTLS.NO_VALIDAR
    else:
        por_defecto = ModoTLS.CA_PROPIA
    modo = prompter.select(messages.PEDIR_TLS, OPCIONES_TLS, por_defecto)
    if modo is ModoTLS.VALIDAR:
        return True
    if modo is ModoTLS.NO_VALIDAR:
        typer.echo(messages.ADVERTENCIA_TLS_DESACTIVADO)
        return False
    return _pedir_ca(prompter, actual if isinstance(actual, str) else None)


def asistente_perfil[T](
    prompter: Prompter,
    store: ProfileStore,
    actual: Profile | None,
    nombre_original: str | None,
    pedir_clave: Callable[[Prompter], T],
) -> tuple[Profile, T]:
    """Pide los datos de un perfil (§10.3). Con ``actual``, sus valores son los predeterminados.

    ``nombre_original`` es el nombre guardado del perfil que se edita (``None`` al agregar).
    """
    nombre = _pedir_nombre(prompter, store, actual.name if actual else None, nombre_original)
    host, context = _pedir_url(prompter, actual)
    database_name = pedir_texto(
        prompter, messages.PEDIR_DATABASE, actual.database_name if actual else None
    )
    username = pedir_texto(prompter, messages.PEDIR_USUARIO, actual.username if actual else None)
    clave = pedir_clave(prompter)
    verify_ssl = _pedir_tls(prompter, actual.verify_ssl if actual else True)
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


# --- Prueba de conexión -----------------------------------------------------------


class Decision(Enum):
    """Qué hacer con un perfil cuya prueba de conexión falló."""

    GUARDAR = "guardar"
    CORREGIR = "corregir"
    CANCELAR = "cancelar"


OPCIONES_FALLO = (
    Opcion(messages.TITULO_CORREGIR, Decision.CORREGIR, tecla=messages.TECLA_CORREGIR),
    Opcion(messages.TITULO_GUARDAR, Decision.GUARDAR, tecla=messages.TECLA_GUARDAR),
    Opcion(messages.TITULO_CANCELAR, Decision.CANCELAR, tecla=messages.TECLA_CANCELAR),
)


def probar(perfil: Profile, clave: str) -> DiagnosticReport:
    """Avisa del intento de login y ejecuta la prueba de conexión (§7)."""
    typer.echo(messages.PROBANDO_CONEXION.format(nombre=perfil.name))
    with Console().status(messages.ESPERANDO_RESPUESTA):
        return probar_conexion(perfil, clave)


def probar_y_decidir(prompter: Prompter, perfil: Profile, clave: str) -> Decision:
    """Prueba la conexión; si falla, muestra el diagnóstico y pregunta qué hacer (§10.3)."""
    reporte = probar(perfil, clave)
    if reporte.status is EstadoDiagnostico.OK:
        typer.echo(messages.CONEXION_EXITOSA)
        return Decision.GUARDAR
    render.reporte_diagnostico(reporte)
    return prompter.select(messages.PREGUNTA_FALLO_CONEXION, OPCIONES_FALLO, Decision.CORREGIR)


# --- Agregar y editar perfiles ------------------------------------------------------


def agregar_perfil(prompter: Prompter, store: ProfileStore) -> Profile | None:
    """Asistente para agregar un perfil; ``None`` si se cancela.

    Antes de guardar se prueba la conexión; si falla, el usuario decide si corrige, guarda
    de todas formas o cancela. Cada nueva prueba ocurre solo porque el usuario lo pidió.
    """
    perfil, clave = asistente_perfil(prompter, store, None, None, pedir_clave_nueva)
    while (decision := probar_y_decidir(prompter, perfil, clave)) is Decision.CORREGIR:
        typer.echo(messages.AVISO_EDITAR)
        perfil, otra_clave = asistente_perfil(prompter, store, perfil, None, pedir_clave_opcional)
        clave = otra_clave or clave
    if decision is Decision.CANCELAR:
        typer.echo(messages.CANCELADO)
        return None
    profiles.crear_perfil(store, perfil, clave)
    mensaje = (
        messages.PERFIL_GUARDADO_PREDETERMINADO
        if store.predeterminado() == perfil.name
        else messages.PERFIL_GUARDADO
    )
    typer.echo(mensaje.format(nombre=perfil.name))
    return perfil


def editar_perfil(prompter: Prompter, store: ProfileStore, nombre: str) -> Profile | None:
    """Repite el asistente con los valores actuales como predeterminados; ``None`` si se cancela.

    La prueba de conexión usa la clave nueva o, si se conservó, la guardada.
    """
    actual = store.obtener(nombre)
    typer.echo(messages.AVISO_EDITAR)
    perfil, clave_nueva = asistente_perfil(prompter, store, actual, nombre, pedir_clave_opcional)
    clave_guardada = secrets.leer_clave(nombre)
    while True:
        clave_prueba = clave_nueva or clave_guardada
        if clave_prueba is None:
            typer.echo(messages.CLAVE_REQUERIDA_PRUEBA)
            clave_nueva = clave_prueba = pedir_clave_nueva(prompter)
        decision = probar_y_decidir(prompter, perfil, clave_prueba)
        if decision is not Decision.CORREGIR:
            break
        typer.echo(messages.AVISO_EDITAR)
        perfil, otra_clave = asistente_perfil(prompter, store, perfil, nombre, pedir_clave_opcional)
        clave_nueva = otra_clave or clave_nueva
    if decision is Decision.CANCELAR:
        typer.echo(messages.CANCELADO)
        return None
    profiles.editar_perfil(store, nombre, perfil, clave_nueva)
    typer.echo(messages.PERFIL_ACTUALIZADO.format(nombre=perfil.name))
    return perfil


# --- Formulario entity (§11.1 y §11.3) --------------------------------------------


@dataclass(frozen=True)
class ValoresEntity:
    """Lo que el usuario escribió en el formulario, tal cual."""

    fields: str = ""
    filtro: str = ""
    orden: str = ""

    def params(self) -> dict[str, str]:
        """Parámetros para ``Cliente.get``."""
        return {FIELDS: self.fields, FILTER: self.filtro, ORDER_BY: self.orden}


@dataclass(frozen=True)
class ConsultaEntity:
    """Consulta confirmada: lo escrito, la consulta que se enviará y el permiso sin filtro."""

    endpoint: Endpoint
    valores: ValoresEntity
    enviada: Mapping[str, str]
    allow_unfiltered: bool

    @property
    def campos(self) -> list[str]:
        """Campos normalizados, en el orden en que se escribieron."""
        return self.enviada[FIELDS].split(",")


class Confirmacion(Enum):
    """Respuestas a «¿Ejecutar?» (§11.3)."""

    EJECUTAR = "ejecutar"
    EDITAR = "editar"
    CANCELAR = "cancelar"


OPCIONES_CONFIRMACION = (
    Opcion(messages.OPCION_EJECUTAR, Confirmacion.EJECUTAR),
    Opcion(messages.OPCION_EDITAR_CONSULTA, Confirmacion.EDITAR),
    Opcion(messages.OPCION_CANCELAR_CONSULTA, Confirmacion.CANCELAR),
)


def _entre_comillas(valor: str) -> str:
    return f'"{valor}"'


def comando_equivalente(perfil: str, consulta: ConsultaEntity) -> str:
    """Comando ``p6 get`` que repite la consulta en modo flags (§11.3)."""
    partes = [
        "p6",
        "get",
        consulta.endpoint.key,
        "--env",
        perfil,
        "--fields",
        _entre_comillas(consulta.enviada[FIELDS]),
    ]
    if consulta.valores.filtro.strip():
        partes += ["--filter", _entre_comillas(consulta.enviada[FILTER])]
    if consulta.valores.orden.strip():
        partes += ["--order-by", _entre_comillas(consulta.enviada[ORDER_BY])]
    if consulta.allow_unfiltered:
        partes.append("--allow-unfiltered")
    return " ".join(partes)


def _mostrar_campos(cliente: Cliente, endpoint: Endpoint) -> None:
    """Regla 3: lista en vivo los campos válidos del endpoint."""
    try:
        with render.progreso_consulta():
            campos = cliente.fields(endpoint)
    except P6CliError as error:
        render.mostrar_error(error)
        return
    render.lista_campos(endpoint.key, campos)


def _mostrar_guia(tema: str) -> None:
    """Guía de ``p6 syntax TEMA`` y el aviso de comillas del formulario. No toca la red."""
    render.guia_sintaxis(messages.GUIAS_SINTAXIS[tema])
    Console().print(Text(messages.AVISO_SINTAXIS_FORMULARIO, style="bold"), soft_wrap=True)


def _pedir_con_ayuda(
    prompter: Prompter, etiqueta: str, actual: str, mostrar_ayuda: Callable[[], None]
) -> str:
    """Pide un campo; con ? (con o sin espacios) muestra la ayuda y lo vuelve a pedir."""
    valor = prompter.text(etiqueta, actual)
    while valor.strip() == messages.PEDIR_AYUDA:
        mostrar_ayuda()
        valor = prompter.text(etiqueta, actual)
    return valor


def _pedir_valores(
    prompter: Prompter, cliente: Cliente, endpoint: Endpoint, valores: ValoresEntity
) -> ValoresEntity:
    """Fields, Filter y OrderBy; cada uno ofrece lo escrito antes (vacío la primera vez).

    Regla 3: ? en Fields lista los campos válidos en vivo; en Filter y OrderBy muestra la
    guía de sintaxis. Después se vuelve a pedir el mismo campo.
    """
    fields = _pedir_con_ayuda(
        prompter,
        messages.ETIQUETA_FIELDS,
        valores.fields,
        lambda: _mostrar_campos(cliente, endpoint),
    )
    filtro = _pedir_con_ayuda(
        prompter, messages.ETIQUETA_FILTER, valores.filtro, lambda: _mostrar_guia("filter")
    )
    orden = _pedir_con_ayuda(
        prompter, messages.ETIQUETA_ORDER_BY, valores.orden, lambda: _mostrar_guia("order-by")
    )
    return ValoresEntity(fields=fields, filtro=filtro, orden=orden)


def _mostrar_confirmacion(perfil: Profile, consulta: ConsultaEntity) -> None:
    valores = consulta.valores
    parametros = (
        (FIELDS, ", ".join(consulta.campos), False),
        (FILTER, consulta.enviada[FILTER], not valores.filtro.strip()),
        (ORDER_BY, consulta.enviada[ORDER_BY], not valores.orden.strip()),
    )
    render.confirmacion_consulta(
        consulta.endpoint.path, parametros, comando_equivalente(perfil.name, consulta)
    )


def formulario_entity(
    prompter: Prompter,
    cliente: Cliente,
    perfil: Profile,
    endpoint: Endpoint,
    valores: ValoresEntity,
) -> ConsultaEntity | None:
    """Formulario de §11.1 con la confirmación de §11.3; ``None`` si se cancela.

    ``valores`` es lo escrito antes (vacío en la primera consulta de un endpoint). Si algo
    no es válido, el formulario reaparece con lo escrito. Todo se valida antes de tocar P6.
    """
    while True:
        render.cabecera_formulario(endpoint)
        valores = _pedir_valores(prompter, cliente, endpoint, valores)
        try:
            # El guardarraíl de endpoints grandes se resuelve con la confirmación de abajo.
            enviada = validar_consulta(perfil, endpoint, valores.params(), allow_unfiltered=True)
        except UsageError as error:
            render.mostrar_error(error)
            continue
        sin_filtro = endpoint.large and not valores.filtro.strip()
        if sin_filtro and not prompter.confirm(
            messages.CONFIRMAR_SIN_FILTRO.format(endpoint=endpoint.key), por_defecto=False
        ):
            continue
        consulta = ConsultaEntity(endpoint, valores, enviada, allow_unfiltered=sin_filtro)
        _mostrar_confirmacion(perfil, consulta)
        eleccion = prompter.select(messages.PREGUNTA_EJECUTAR, OPCIONES_CONFIRMACION)
        if eleccion is Confirmacion.EJECUTAR:
            return consulta
        if eleccion is Confirmacion.CANCELAR:
            return None


# --- Formulario spread (§11.2 y §11.3) --------------------------------------------


class OrigenIds(Enum):
    """De dónde salen los ObjectId de un spread (§11.2, regla 1)."""

    ESCRIBIR = "escribir"
    ARCHIVO = "archivo"
    CONSULTA = "consulta"


@dataclass(frozen=True)
class ValoresSpread:
    """Lo que el usuario escribió en el formulario spread, tal cual.

    Se conserva lo escrito en cada origen, para que «Editar» y «Nueva consulta» lo ofrezcan.
    """

    origen: OrigenIds = OrigenIds.ESCRIBIR
    ids: str = ""
    archivo: str = ""
    filtro: str = ""
    spread_field: str = ""
    periodo: str = PERIODO_POR_DEFECTO
    inicio: str = ""
    fin: str = ""
    acumulado: bool = True


@dataclass(frozen=True)
class ConsultaSpread:
    """Consulta confirmada: lo escrito, los ObjectId y la consulta de cada lote."""

    endpoint: Endpoint
    valores: ValoresSpread
    ids: tuple[int, ...]
    lotes: Sequence[Mapping[str, str]]

    def params(self) -> dict[str, str]:
        """Parámetros para ``Cliente.get_spread``."""
        return _params_spread(self.endpoint, self.valores, self.ids)

    @property
    def campos(self) -> list[str]:
        """SpreadField normalizados, en el orden en que se escribieron."""
        return self.lotes[0][SPREAD_FIELD].split(",")


def _params_spread(
    endpoint: Endpoint, valores: ValoresSpread, ids: Sequence[int]
) -> dict[str, str]:
    return {
        param_ids(endpoint).name: ",".join(str(numero) for numero in ids),
        SPREAD_FIELD: valores.spread_field,
        PERIOD_TYPE: valores.periodo,
        START_DATE: valores.inicio,
        END_DATE: valores.fin,
        INCLUDE_CUMULATIVE: "true" if valores.acumulado else "false",
    }


def _opciones_origen(entidad: Endpoint) -> tuple[Opcion[OrigenIds], ...]:
    return (
        Opcion(messages.OPCION_ORIGEN_ESCRIBIR, OrigenIds.ESCRIBIR),
        Opcion(messages.OPCION_ORIGEN_ARCHIVO, OrigenIds.ARCHIVO),
        Opcion(messages.OPCION_ORIGEN_CONSULTA.format(entidad=entidad.key), OrigenIds.CONSULTA),
    )


def _ids_de_consulta(
    prompter: Prompter,
    cliente: Cliente,
    entidad: Endpoint,
    valores: ValoresSpread,
    sondeos: dict[str, tuple[int, ...]],
) -> tuple[ValoresSpread, tuple[int, ...] | None]:
    """Pide un Filter sobre la entidad base y busca sus ObjectId (una petición).

    ``sondeos`` guarda los IDs ya obtenidos por filtro: si el formulario reaparece con el
    mismo filtro, no se vuelve a consultar a P6. Devuelve ``None`` si no hay IDs que usar.
    """
    filtro = _pedir_con_ayuda(
        prompter,
        messages.ETIQUETA_FILTRO_IDS.format(entidad=entidad.key),
        valores.filtro,
        lambda: _mostrar_guia("filter"),
    )
    valores = dataclasses.replace(valores, filtro=filtro)
    if not filtro.strip():
        typer.echo(messages.FILTRO_IDS_VACIO, err=True)
        return valores, None
    if filtro not in sondeos:
        with render.progreso_consulta():
            sondeos[filtro] = tuple(cliente.ids(entidad, filtro))
    ids = sondeos[filtro]
    if not ids:
        typer.echo(messages.SIN_IDS.format(entidad=entidad.key), err=True)
        return valores, None
    typer.echo(messages.IDS_OBTENIDOS.format(cantidad=render.numero(len(ids)), entidad=entidad.key))
    return valores, ids


def _pedir_ids(
    prompter: Prompter,
    cliente: Cliente,
    endpoint: Endpoint,
    valores: ValoresSpread,
    sondeos: dict[str, tuple[int, ...]],
) -> tuple[ValoresSpread, tuple[int, ...]]:
    """Regla 1: origen de los ObjectId. Ante un error se muestra y se vuelve a elegir origen."""
    entidad = entidad_base(endpoint)
    while True:
        origen = prompter.select(
            messages.PREGUNTA_ORIGEN_IDS, _opciones_origen(entidad), valores.origen
        )
        valores = dataclasses.replace(valores, origen=origen)
        ids: tuple[int, ...] | None
        try:
            if origen is OrigenIds.ESCRIBIR:
                etiqueta = messages.ETIQUETA_IDS.format(parametro=param_ids(endpoint).name)
                texto = prompter.text(etiqueta, valores.ids)
                valores = dataclasses.replace(valores, ids=texto)
                ids = normalizar_ids(texto)
            elif origen is OrigenIds.ARCHIVO:
                ruta = pedir_texto(prompter, messages.ETIQUETA_ARCHIVO_IDS, valores.archivo)
                valores = dataclasses.replace(valores, archivo=ruta)
                ids = leer_ids(Path(ruta).expanduser())
                cantidad = render.numero(len(ids))
                typer.echo(messages.IDS_LEIDOS.format(cantidad=cantidad, ruta=ruta))
            else:
                valores, ids = _ids_de_consulta(prompter, cliente, entidad, valores, sondeos)
        except P6CliError as error:
            render.mostrar_error(error)
            continue
        if ids is not None:
            return valores, ids


def _mostrar_campos_spread(endpoint: Endpoint) -> None:
    """? en SpreadField: los valores válidos del catálogo (documentación de Oracle), sin red."""
    render.lista_campos(endpoint.key, campos_spread(endpoint), messages.TITULO_CAMPOS_SPREAD)


def _pedir_valores_spread(
    prompter: Prompter, endpoint: Endpoint, valores: ValoresSpread
) -> ValoresSpread:
    """Reglas 2 a 5: SpreadField (con ? lista los válidos), PeriodType, fechas e
    IncludeCumulative."""
    spread_field = _pedir_con_ayuda(
        prompter,
        messages.ETIQUETA_SPREAD_FIELD,
        valores.spread_field,
        lambda: _mostrar_campos_spread(endpoint),
    )
    periodo = prompter.select(
        messages.PREGUNTA_PERIODO, [Opcion(p, p) for p in PERIODOS], valores.periodo
    )
    inicio = prompter.text(messages.ETIQUETA_INICIO, valores.inicio)
    fin = prompter.text(messages.ETIQUETA_FIN, valores.fin)
    acumulado = prompter.confirm(messages.CONFIRMAR_ACUMULADO, por_defecto=valores.acumulado)
    return dataclasses.replace(
        valores,
        spread_field=spread_field,
        periodo=periodo,
        inicio=inicio,
        fin=fin,
        acumulado=acumulado,
    )


def comando_equivalente_spread(perfil: str, consulta: ConsultaSpread) -> str:
    """Comando ``p6 spread`` que repite la consulta en modo flags (§11.3).

    Los IDs escritos o buscados van en ``--ids`` (la lista que se envía); los de un archivo,
    en ``--ids-from``. Los demás flags solo aparecen si difieren del valor por defecto.
    """
    valores = consulta.valores
    primero = consulta.lotes[0]
    partes = ["p6", "spread", consulta.endpoint.key, "--env", perfil]
    if valores.origen is OrigenIds.ARCHIVO:
        partes += ["--ids-from", _entre_comillas(valores.archivo)]
    else:
        partes += ["--ids", _entre_comillas(",".join(str(numero) for numero in consulta.ids))]
    partes += ["--spread-fields", _entre_comillas(primero[SPREAD_FIELD])]
    if primero[PERIOD_TYPE] != PERIODO_POR_DEFECTO:
        partes += ["--period", primero[PERIOD_TYPE]]
    if valores.inicio.strip():
        partes += ["--start", valores.inicio.strip()]
    if valores.fin.strip():
        partes += ["--end", valores.fin.strip()]
    if not valores.acumulado:
        partes.append("--no-cumulative")
    return " ".join(partes)


def _mostrar_confirmacion_spread(perfil: Profile, consulta: ConsultaSpread) -> None:
    primero = consulta.lotes[0]
    lotes = len(consulta.lotes)
    resumen_ids = messages.RESUMEN_IDS.format(
        cantidad=render.numero(len(consulta.ids)),
        lotes=render.numero(lotes),
        unidad=messages.UNIDAD_LOTE if lotes == 1 else messages.UNIDAD_LOTES,
    )
    parametros = [
        (param_ids(consulta.endpoint).name, resumen_ids, False),
        (SPREAD_FIELD, ", ".join(consulta.campos), False),
        (PERIOD_TYPE, primero[PERIOD_TYPE], primero[PERIOD_TYPE] == PERIODO_POR_DEFECTO),
    ]
    for fecha in (START_DATE, END_DATE):
        if fecha in primero:
            parametros.append((fecha, primero[fecha], False))
    parametros.append((INCLUDE_CUMULATIVE, primero[INCLUDE_CUMULATIVE], consulta.valores.acumulado))
    render.confirmacion_consulta(
        consulta.endpoint.path, parametros, comando_equivalente_spread(perfil.name, consulta)
    )


def formulario_spread(
    prompter: Prompter,
    cliente: Cliente,
    perfil: Profile,
    endpoint: Endpoint,
    valores: ValoresSpread,
) -> ConsultaSpread | None:
    """Formulario de §11.2 con la confirmación de §11.3; ``None`` si se cancela.

    ``valores`` es lo escrito antes. Todo se valida antes de la confirmación (IDs, campos,
    fechas y largo de la URL de cada lote); si algo no es válido, el formulario reaparece
    con lo escrito. Solo el origen «Desde una consulta» toca P6, y una vez por filtro.
    """
    sondeos: dict[str, tuple[int, ...]] = {}
    while True:
        render.cabecera_formulario(endpoint, messages.AYUDA_FORMULARIO_SPREAD)
        valores, ids = _pedir_ids(prompter, cliente, endpoint, valores, sondeos)
        valores = _pedir_valores_spread(prompter, endpoint, valores)
        try:
            lotes = validar_spread(perfil, endpoint, _params_spread(endpoint, valores, ids))
        except UsageError as error:
            render.mostrar_error(error)
            continue
        consulta = ConsultaSpread(endpoint, valores, ids, lotes)
        _mostrar_confirmacion_spread(perfil, consulta)
        eleccion = prompter.select(messages.PREGUNTA_EJECUTAR, OPCIONES_CONFIRMACION)
        if eleccion is Confirmacion.EJECUTAR:
            return consulta
        if eleccion is Confirmacion.CANCELAR:
            return None
