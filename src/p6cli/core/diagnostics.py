"""Prueba de conexión y clasificación de fallos (especificación §7).

Secuencia: ``POST /login`` → ``GET /project/fields`` → ``GET`` a una ruta canario
inexistente. DNS, TCP y TLS se deducen del error de red del primer paso que falle; un error
de red corta la secuencia. Se hace **un** intento de login: cuenta para el bloqueo de la
cuenta.

El reporte no contiene textos para el usuario: ``cli`` los arma a partir de ``status`` y
``causa_red``. Tampoco contiene cabeceras, claves ni tokens.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

import requests

from p6cli.core.errors import MotivoHTTP, P6HTTPError
from p6cli.core.profiles import Profile
from p6cli.core.session import Sesion, es_contenido_json, fragmento, mensaje_p6

RUTA_FIELDS = "/project/fields"
RUTA_CANARIO = "/__p6cli_canary__"
LARGO_FRAGMENTO = 200

_MARCA_INTERFAZ_WEB = "/p6/action/login"
_MARCA_DATABASE_INVALIDA = "Invalid database name"


class EstadoDiagnostico(StrEnum):
    """Resultado de la prueba de conexión, en el orden de evaluación de §7."""

    NETWORK = "NETWORK"
    TLS = "TLS"
    CATCH_ALL = "CATCH_ALL"
    ROUTE_NOT_FOUND = "ROUTE_NOT_FOUND"
    UI_NOT_API = "UI_NOT_API"
    INVALID_DATABASE = "INVALID_DATABASE"
    CREDENTIALS_REJECTED = "CREDENTIALS_REJECTED"
    AUTH_FAILED = "AUTH_FAILED"
    OK = "OK"
    UNKNOWN = "UNKNOWN"


def _fragmento(texto: str) -> str:
    return fragmento(texto, LARGO_FRAGMENTO)


def _content_type(respuesta: requests.Response) -> str:
    return respuesta.headers.get("Content-Type", "")


@dataclass(frozen=True)
class PasoObservado:
    """Una petición del diagnóstico, sin cabeceras ni credenciales."""

    metodo: str
    url: str
    codigo: int | None
    content_type: str
    tamano: int
    fragmento: str

    @classmethod
    def desde_respuesta(cls, respuesta: requests.Response) -> PasoObservado:
        return cls(
            metodo=str(respuesta.request.method),
            url=respuesta.url,
            codigo=respuesta.status_code,
            content_type=_content_type(respuesta),
            tamano=len(respuesta.content),
            fragmento=_fragmento(respuesta.text),
        )

    @classmethod
    def desde_error(cls, error: P6HTTPError) -> PasoObservado:
        """Paso que no obtuvo respuesta; el fragmento es el tipo del error de red."""
        return cls(
            metodo=error.datos["metodo"],
            url=error.datos["url"],
            codigo=None,
            content_type="",
            tamano=0,
            fragmento=error.datos["tipo"],
        )


@dataclass(frozen=True)
class DiagnosticReport:
    """Resultado de la prueba de conexión.

    ``detalle`` trae datos no sensibles para armar el mensaje (``mensaje_p6`` en
    ``AUTH_FAILED``; ``metodo``, ``url``, ``codigo``, ``content_type`` y ``fragmento`` en
    ``UNKNOWN``). ``causa_red`` indica el error de red cuando no hubo respuesta.
    """

    status: EstadoDiagnostico
    pasos: tuple[PasoObservado, ...]
    detalle: Mapping[str, str] = field(default_factory=dict)
    causa_red: MotivoHTTP | None = None


def _es_html(respuesta: requests.Response) -> bool:
    return _content_type(respuesta).split(";", 1)[0].strip().lower() == "text/html"


def _es_json(respuesta: requests.Response) -> bool:
    return es_contenido_json(_content_type(respuesta))


def _redirige_a_interfaz_web(respuesta: requests.Response) -> bool:
    if respuesta.is_redirect and _MARCA_INTERFAZ_WEB in respuesta.headers.get("Location", ""):
        return True
    return _es_html(respuesta) and _MARCA_INTERFAZ_WEB in respuesta.text


def _mensaje_p6(respuesta: requests.Response) -> str:
    return mensaje_p6(respuesta, LARGO_FRAGMENTO)


def _detalle_desconocido(respuesta: requests.Response) -> dict[str, str]:
    paso = PasoObservado.desde_respuesta(respuesta)
    return {
        "metodo": paso.metodo,
        "url": paso.url,
        "codigo": str(paso.codigo),
        "content_type": paso.content_type,
        "fragmento": paso.fragmento,
    }


def clasificar_login(login: requests.Response) -> tuple[EstadoDiagnostico, dict[str, str]]:
    """Filas 5 a 9 de la tabla §7 a partir de la respuesta del login.

    Devuelve ``OK`` con un login 200 JSON y ``UNKNOWN`` con cualquier otro caso. No hace
    peticiones: sirve para explicar un login fallido sin repetir el diagnóstico completo.
    """
    if login.status_code == 404 and _es_html(login):
        return EstadoDiagnostico.ROUTE_NOT_FOUND, {}
    if _redirige_a_interfaz_web(login):
        return EstadoDiagnostico.UI_NOT_API, {}
    if login.status_code == 401 and _es_json(login):
        mensaje = _mensaje_p6(login)
        if _MARCA_DATABASE_INVALIDA in mensaje:
            return EstadoDiagnostico.INVALID_DATABASE, {}
    if login.status_code == 500:
        return EstadoDiagnostico.CREDENTIALS_REJECTED, {}
    if login.status_code == 401 and _es_json(login):
        return EstadoDiagnostico.AUTH_FAILED, {"mensaje_p6": _mensaje_p6(login)}
    if not (login.status_code == 200 and _es_json(login)):
        return EstadoDiagnostico.UNKNOWN, _detalle_desconocido(login)
    return EstadoDiagnostico.OK, {}


def _clasificar(
    login: requests.Response, fields: requests.Response, canario: requests.Response
) -> tuple[EstadoDiagnostico, dict[str, str]]:
    """Filas 4 a 10 de la tabla §7, en ese orden, más el caso ``UNKNOWN``."""
    if canario.status_code != 404:
        return EstadoDiagnostico.CATCH_ALL, {}
    estado, detalle = clasificar_login(login)
    if estado is not EstadoDiagnostico.OK:
        return estado, detalle
    if not (fields.status_code == 200 and _es_json(fields)):
        return EstadoDiagnostico.UNKNOWN, _detalle_desconocido(fields)
    return EstadoDiagnostico.OK, {}


_ESTADO_POR_CAUSA_RED = {
    MotivoHTTP.SIN_RESOLUCION: EstadoDiagnostico.NETWORK,
    MotivoHTTP.SIN_CONEXION: EstadoDiagnostico.NETWORK,
    MotivoHTTP.TLS: EstadoDiagnostico.TLS,
    MotivoHTTP.TIEMPO_AGOTADO: EstadoDiagnostico.UNKNOWN,
}


def diagnosticar(sesion: Sesion) -> DiagnosticReport:
    """Hace el login de ``sesion`` y clasifica el resultado.

    Si el estado es ``OK``, la sesión queda autenticada y se puede seguir usando.
    """
    pasos: list[PasoObservado] = []
    try:
        login = sesion.login()
        pasos.append(PasoObservado.desde_respuesta(login))
        fields = sesion.get(RUTA_FIELDS)
        pasos.append(PasoObservado.desde_respuesta(fields))
        canario = sesion.get(RUTA_CANARIO)
        pasos.append(PasoObservado.desde_respuesta(canario))
    except P6HTTPError as error:
        pasos.append(PasoObservado.desde_error(error))
        causa = MotivoHTTP(error.motivo)
        return DiagnosticReport(
            status=_ESTADO_POR_CAUSA_RED[causa], pasos=tuple(pasos), causa_red=causa
        )
    estado, detalle = _clasificar(login, fields, canario)
    return DiagnosticReport(status=estado, pasos=tuple(pasos), detalle=detalle)


def probar_conexion(perfil: Profile, clave: str) -> DiagnosticReport:
    """Prueba de conexión completa: diagnostica y cierra la sesión (logout si hubo login)."""
    with Sesion(perfil, clave) as sesion:
        return diagnosticar(sesion)
