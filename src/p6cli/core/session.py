"""Sesión HTTP autenticada: login, logout y cabeceras.

Esquema Username Token Profile (especificación §6). La sesión solo expone GET; los únicos
POST son el login y el logout. Reglas de seguridad:

- Un solo intento de login por instancia: un segundo ``login()`` falla sin enviar nada.
- Ninguna petición sigue redirecciones: requests reenviaría las cabeceras ``username``,
  ``password`` y ``authToken`` al destino de la redirección.
- Los errores de red se traducen a ``P6HTTPError`` fuera del bloque ``except``, para que la
  excepción original (que guarda las cabeceras en ``.request``) no quede encadenada.
"""

import base64
import contextlib
import re
import socket
from collections.abc import Iterator, Mapping
from types import TracebackType
from typing import Self
from urllib.parse import urlencode

import requests

from p6cli.core.errors import AuthError, MotivoAuth, MotivoHTTP, P6HTTPError
from p6cli.core.profiles import Profile

# Segundos para establecer la conexión TCP/TLS; la lectura usa el timeout del perfil.
TIEMPO_CONEXION = 10

RUTA_LOGIN = "/login"
RUTA_LOGOUT = "/logout"

# Mismo criterio que requests para valores de cabecera: sin espacio inicial ni saltos de línea.
_CABECERA_VALIDA = re.compile(r"\S[^\r\n]*|")


def token_autenticacion(usuario: str, clave: str) -> str:
    """Valor de la cabecera ``authToken``: base64 de ``usuario:clave``."""
    return base64.b64encode(f"{usuario}:{clave}".encode()).decode("ascii")


def es_contenido_json(content_type: str) -> bool:
    """``True`` si el Content-Type es JSON (``application/json`` o ``*+json``)."""
    tipo = content_type.split(";", 1)[0].strip().lower()
    return tipo == "application/json" or tipo.endswith("+json")


def _causas(error: BaseException) -> Iterator[BaseException]:
    """Recorre la cadena de causas: ``__cause__``, ``__context__``, ``reason`` y ``args``."""
    pendientes = [error]
    vistas: set[int] = set()
    while pendientes:
        actual = pendientes.pop()
        if id(actual) in vistas:
            continue
        vistas.add(id(actual))
        yield actual
        candidatos = (
            actual.__cause__,
            actual.__context__,
            getattr(actual, "reason", None),
            *actual.args,
        )
        pendientes.extend(c for c in candidatos if isinstance(c, BaseException))


def _motivo_red(error: requests.RequestException) -> MotivoHTTP:
    if isinstance(error, requests.exceptions.SSLError):
        return MotivoHTTP.TLS
    if isinstance(error, requests.exceptions.ConnectTimeout):
        return MotivoHTTP.SIN_CONEXION
    if isinstance(error, requests.exceptions.Timeout):
        return MotivoHTTP.TIEMPO_AGOTADO
    if any(isinstance(causa, socket.gaierror) for causa in _causas(error)):
        return MotivoHTTP.SIN_RESOLUCION
    return MotivoHTTP.SIN_CONEXION


def _cabecera_valida(valor: str) -> bool:
    try:
        valor.encode("latin-1")
    except UnicodeEncodeError:
        return False
    return bool(_CABECERA_VALIDA.fullmatch(valor))


class Sesion:
    """Sesión autenticada contra un perfil. Conserva las cookies que devuelva el servidor."""

    def __init__(
        self, perfil: Profile, clave: str, *, http: requests.Session | None = None
    ) -> None:
        self.perfil = perfil
        self.base = f"{perfil.host}/{perfil.context}/restapi"
        self.autenticada = False
        self._clave = clave
        self._token = token_autenticacion(perfil.username, clave)
        self._http = http if http is not None else requests.Session()
        self._login_intentado = False

    def __repr__(self) -> str:
        return (
            f"Sesion(perfil={self.perfil.name!r}, base={self.base!r}, "
            f"autenticada={self.autenticada})"
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        error: BaseException | None,
        traza: TracebackType | None,
    ) -> None:
        self.cerrar()

    def login(self) -> requests.Response:
        """Único intento de login. Devuelve la respuesta tal cual; no la clasifica."""
        if self._login_intentado:
            raise AuthError(MotivoAuth.LOGIN_YA_INTENTADO, perfil=self.perfil.name)
        cabeceras = {
            "username": self.perfil.username,
            "password": self._clave,
            "authToken": self._token,
            "Accept": "*/*",
        }
        if not all(_cabecera_valida(valor) for valor in cabeceras.values()):
            raise AuthError(MotivoAuth.CLAVE_NO_CODIFICABLE)
        self._login_intentado = True
        respuesta = self._enviar(
            "POST", RUTA_LOGIN, {"DatabaseName": self.perfil.database_name}, cabeceras
        )
        self.autenticada = respuesta.status_code == 200 and es_contenido_json(
            respuesta.headers.get("Content-Type", "")
        )
        return respuesta

    def get(self, ruta: str, params: Mapping[str, str] | None = None) -> requests.Response:
        """GET a ``{base}{ruta}``; ``DatabaseName`` siempre va en la consulta."""
        consulta = {**(params or {}), "DatabaseName": self.perfil.database_name}
        cabeceras = {"authToken": self._token, "Accept": "application/json"}
        return self._enviar("GET", ruta, consulta, cabeceras)

    def logout(self) -> None:
        """Cierra la sesión en el servidor. Sus fallos se ignoran."""
        with contextlib.suppress(P6HTTPError):
            self._enviar("POST", RUTA_LOGOUT, {}, {"authToken": self._token, "Accept": "*/*"})
        self.autenticada = False

    def cerrar(self) -> None:
        """Hace logout si hubo un login exitoso y libera las conexiones."""
        if self.autenticada:
            self.logout()
        self._http.close()

    def _url(self, ruta: str, consulta: Mapping[str, str]) -> str:
        url = f"{self.base}{ruta}"
        return f"{url}?{urlencode(consulta)}" if consulta else url

    def _enviar(
        self, metodo: str, ruta: str, consulta: Mapping[str, str], cabeceras: Mapping[str, str]
    ) -> requests.Response:
        url = self._url(ruta, consulta)
        try:
            return self._http.request(
                metodo,
                url,
                headers=dict(cabeceras),
                verify=self.perfil.verify_ssl,
                timeout=(TIEMPO_CONEXION, self.perfil.timeout),
                allow_redirects=False,
            )
        except requests.RequestException as error:
            fallo = P6HTTPError(
                _motivo_red(error), metodo=metodo, url=url, tipo=type(error).__name__
            )
        # Se lanza fuera del except para no encadenar la excepción original.
        raise fallo
