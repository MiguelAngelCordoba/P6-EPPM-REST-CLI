"""GET genérico, lecturas por lotes y spread (especificación §9).

Toda la validación (parámetros, guardarraíl, largo de URL) ocurre antes de tocar la red:
un error de uso nunca gasta el único intento de login. El login se hace en la primera
petición que lo necesita.
"""

import json
from collections.abc import Mapping
from typing import Any

import requests

from p6cli.core.catalog import (
    FILTER,
    ORDER_BY,
    Endpoint,
    ParamKind,
    ParamSpec,
    Plantilla,
    es_campo_valido,
    normalizar_campos,
    parametros,
)
from p6cli.core.diagnostics import clasificar_login
from p6cli.core.errors import (
    AuthError,
    GuardrailError,
    MotivoAuth,
    MotivoGuardarrail,
    MotivoHTTP,
    MotivoUso,
    P6HTTPError,
    UsageError,
)
from p6cli.core.profiles import Profile
from p6cli.core.session import Sesion, es_contenido_json, fragmento, mensaje_p6, url_get

LARGO_MAXIMO_URL = 7000
LARGO_FRAGMENTO_ERROR = 500

# Valores neutros que el cliente envía cuando Filter u OrderBy quedan vacíos (§8.2).
FILTRO_NEUTRO = "ObjectId:gte:0"
ORDEN_NEUTRO = "ObjectId asc"

type Fila = dict[str, Any]


def _valor_por_omision(endpoint: Endpoint, spec: ParamSpec, allow_unfiltered: bool) -> str | None:
    """Valor que se envía si el parámetro queda vacío; aplica el guardarraíl ``large``."""
    if endpoint.template is Plantilla.ENTITY and spec.name == FILTER:
        if endpoint.large and not allow_unfiltered:
            raise GuardrailError(MotivoGuardarrail.SIN_FILTRO, endpoint=endpoint.key)
        return FILTRO_NEUTRO
    if endpoint.template is Plantilla.ENTITY and spec.name == ORDER_BY:
        return ORDEN_NEUTRO
    return spec.default


def preparar_consulta(
    endpoint: Endpoint, params: Mapping[str, str], *, allow_unfiltered: bool = False
) -> dict[str, str]:
    """Valida los parámetros según la plantilla y devuelve la consulta lista para enviar.

    Rechaza parámetros ajenos a la plantilla, exige los obligatorios, normaliza los de tipo
    FIELDS, aplica el guardarraíl de endpoints ``large`` y completa los valores neutros y
    por defecto. Filter y OrderBy escritos por el usuario se envían tal cual.
    """
    especificacion = parametros(endpoint)
    nombres = {spec.name for spec in especificacion}
    for nombre in params:
        if nombre not in nombres:
            raise UsageError(
                MotivoUso.PARAMETRO_DESCONOCIDO, parametro=nombre, endpoint=endpoint.key
            )

    consulta: dict[str, str] = {}
    for spec in especificacion:
        valor = params.get(spec.name, "")
        if spec.kind is ParamKind.FIELDS and (valor.strip() or spec.required):
            consulta[spec.name] = ",".join(normalizar_campos(valor, spec.name))
        elif valor.strip():
            consulta[spec.name] = valor
        elif (omision := _valor_por_omision(endpoint, spec, allow_unfiltered)) is not None:
            consulta[spec.name] = omision
        elif spec.required:
            raise UsageError(MotivoUso.PARAMETRO_REQUERIDO, parametro=spec.name)
    return consulta


def validar_consulta(
    perfil: Profile,
    endpoint: Endpoint,
    params: Mapping[str, str],
    *,
    allow_unfiltered: bool = False,
) -> dict[str, str]:
    """``preparar_consulta`` más el límite de largo de la URL. No necesita la clave."""
    consulta = preparar_consulta(endpoint, params, allow_unfiltered=allow_unfiltered)
    largo = len(url_get(perfil, endpoint.path, consulta))
    if largo > LARGO_MAXIMO_URL:
        raise UsageError(
            MotivoUso.URL_DEMASIADO_LARGA, largo=str(largo), maximo=str(LARGO_MAXIMO_URL)
        )
    return consulta


class Cliente:
    """Lecturas contra P6 sobre una ``Sesion``. Solo emite GET."""

    def __init__(self, sesion: Sesion) -> None:
        self._sesion = sesion

    def get(
        self, endpoint: Endpoint, params: Mapping[str, str], *, allow_unfiltered: bool = False
    ) -> list[Fila]:
        """Lectura simple: una petición con los parámetros validados y completados."""
        consulta = validar_consulta(
            self._sesion.perfil, endpoint, params, allow_unfiltered=allow_unfiltered
        )
        respuesta = self._pedir(endpoint.path, consulta)
        datos = _cuerpo_json(respuesta)
        if not isinstance(datos, list) or not all(isinstance(fila, dict) for fila in datos):
            raise _formato_inesperado(respuesta)
        return datos

    def fields(self, endpoint: Endpoint) -> list[str]:
        """Campos válidos de un endpoint ``entity`` (``GET {path}/fields``).

        P6 responde 200 con Content-Type JSON, pero el cuerpo es texto plano con los campos
        separados por comas (no es JSON válido). También se aceptan una lista JSON de textos o
        un texto JSON. Cada nombre debe ser un campo válido; si no, ``FORMATO_INESPERADO``.
        """
        if endpoint.template is not Plantilla.ENTITY:
            raise UsageError(MotivoUso.PLANTILLA_NO_SOPORTADA, endpoint=endpoint.key)
        respuesta = self._pedir(f"{endpoint.path}/fields", {})
        campos = _campos_de(respuesta.text)
        if campos is None:
            raise _formato_inesperado(respuesta)
        return campos

    def _asegurar_login(self) -> None:
        """Hace el único intento de login si aún no hay sesión autenticada."""
        if self._sesion.autenticada:
            return
        respuesta = self._sesion.login()
        if not self._sesion.autenticada:
            estado, detalle = clasificar_login(respuesta)
            raise AuthError(
                MotivoAuth.LOGIN_FALLIDO,
                perfil=self._sesion.perfil.name,
                estado=str(estado),
                **detalle,
            )

    def _pedir(self, ruta: str, consulta: Mapping[str, str]) -> requests.Response:
        """GET autenticado; devuelve la respuesta solo si es 200 con Content-Type JSON."""
        self._asegurar_login()
        respuesta = self._sesion.get(ruta, consulta)
        _validar_respuesta(respuesta)
        return respuesta


def _validar_respuesta(respuesta: requests.Response) -> None:
    """``P6HTTPError`` con datos no sensibles si no es un 200 con Content-Type JSON."""
    content_type = respuesta.headers.get("Content-Type", "")
    if respuesta.status_code != 200:
        raise P6HTTPError(
            MotivoHTTP.CODIGO_HTTP,
            metodo="GET",
            url=respuesta.url,
            codigo=str(respuesta.status_code),
            mensaje_p6=mensaje_p6(respuesta, LARGO_FRAGMENTO_ERROR),
        )
    if not es_contenido_json(content_type):
        raise P6HTTPError(
            MotivoHTTP.RESPUESTA_NO_JSON,
            metodo="GET",
            url=respuesta.url,
            content_type=content_type,
            fragmento=fragmento(respuesta.text, LARGO_FRAGMENTO_ERROR),
        )


def _cuerpo_json(respuesta: requests.Response) -> Any:
    """Cuerpo JSON de la respuesta; ``FORMATO_INESPERADO`` si no se puede leer."""
    try:
        return respuesta.json()
    except requests.exceptions.JSONDecodeError:
        error = _formato_inesperado(respuesta)
    # Se lanza fuera del except para no encadenar la excepción de requests.
    raise error


def _formato_inesperado(respuesta: requests.Response) -> P6HTTPError:
    return P6HTTPError(
        MotivoHTTP.FORMATO_INESPERADO,
        metodo="GET",
        url=respuesta.url,
        fragmento=fragmento(respuesta.text, LARGO_FRAGMENTO_ERROR),
    )


def _campos_de(texto: str) -> list[str] | None:
    """Nombres de campo del cuerpo de ``/fields``; ``None`` si no tiene esa forma."""
    try:
        datos: Any = json.loads(texto)
    except json.JSONDecodeError:
        datos = texto
    if isinstance(datos, list) and all(isinstance(campo, str) for campo in datos):
        campos = [campo.strip() for campo in datos]
    elif isinstance(datos, str):
        campos = [campo.strip() for campo in datos.split(",") if campo.strip()]
    else:
        return None
    if not campos or not all(es_campo_valido(campo) for campo in campos):
        return None
    return campos
