"""Aislamiento común: keyring en memoria, configuración temporal y HTTP simulado.

Las fixtures automáticas garantizan que ningún test toque el keyring, la configuración
ni la red reales del usuario: cualquier petición HTTP no registrada falla.
"""

import socket
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import keyring
import pytest
import requests
import responses
from keyring.backend import KeyringBackend
from keyring.backends import fail
from keyring.errors import KeyringLocked, PasswordDeleteError
from urllib3.exceptions import MaxRetryError, NameResolutionError


class KeyringMemoria(KeyringBackend):
    """Backend de keyring que guarda las claves en un diccionario."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.claves: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.claves.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.claves[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        try:
            del self.claves[(service, username)]
        except KeyError:
            raise PasswordDeleteError("no existe") from None


@pytest.fixture(autouse=True)
def keyring_memoria() -> Iterator[KeyringMemoria]:
    """Sustituye el keyring del sistema por uno en memoria durante cada test."""
    anterior = keyring.get_keyring()
    memoria = KeyringMemoria()
    keyring.set_keyring(memoria)
    yield memoria
    keyring.set_keyring(anterior)


@pytest.fixture(autouse=True)
def dir_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Apunta ``P6CLI_CONFIG_DIR`` a un directorio temporal."""
    ruta = tmp_path / "config"
    monkeypatch.setenv("P6CLI_CONFIG_DIR", str(ruta))
    return ruta


@pytest.fixture
def keyring_sin_backend() -> None:
    """Simula un sistema sin backend de keyring disponible."""
    keyring.set_keyring(fail.Keyring())


class KeyringBloqueado(KeyringMemoria):
    """Keyring en memoria cuyas escrituras y borrados fallan (p. ej. almacén bloqueado)."""

    def set_password(self, service: str, username: str, password: str) -> None:
        raise KeyringLocked("bloqueado")

    def delete_password(self, service: str, username: str) -> None:
        raise KeyringLocked("bloqueado")


# --- HTTP simulado ----------------------------------------------------------------


@pytest.fixture(autouse=True)
def http_simulado() -> Iterator[responses.RequestsMock]:
    """Intercepta requests en cada test: una petición no registrada lanza ConnectionError."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as simulado:
        yield simulado


DIR_FIXTURES = Path(__file__).parent / "fixtures"
_TIPOS_POR_EXTENSION = {
    ".json": "application/json",
    ".html": "text/html; charset=UTF-8",
    ".txt": "text/plain",
}

BASE = "https://localhost:7001/p6ws/restapi"


def leer_fixture(nombre: str) -> str:
    """Contenido de un archivo de ``tests/fixtures/``."""
    return (DIR_FIXTURES / nombre).read_text(encoding="utf-8")


@dataclass(frozen=True)
class Simulada:
    """Respuesta simulada: un fixture (o cuerpo literal) con su código, o un error de red."""

    codigo: int = 200
    fixture: str | None = None
    cuerpo: str = ""
    content_type: str | None = None
    cabeceras: Mapping[str, str] = field(default_factory=dict)
    error: Exception | None = None

    def respuesta(self, metodo: str, url: str) -> responses.Response:
        if self.error is not None:
            return responses.Response(metodo, url, body=self.error)
        content_type = self.content_type
        if self.fixture is not None and content_type is None:
            content_type = _TIPOS_POR_EXTENSION[Path(self.fixture).suffix]
        return responses.Response(
            metodo,
            url,
            status=self.codigo,
            body=leer_fixture(self.fixture) if self.fixture is not None else self.cuerpo,
            content_type=content_type,
            headers=dict(self.cabeceras),
        )


# Casos de referencia de la especificación §16 (anonimizados).
LOGIN_OK = Simulada(200, "login_ok.json")
LOGIN_DATABASE_INVALIDA = Simulada(401, "login_401_database.json")
LOGIN_RECHAZADO = Simulada(500, "login_500.txt")
APACHE_404 = Simulada(404, "apache_404.html")
INTERFAZ_WEB_401 = Simulada(401, "ui_401_login.html")
COMODIN_POST = Simulada(200, content_type=None)
COMODIN_GET = Simulada(405, "comodin_405.html")
FIELDS_OK = Simulada(200, "project_fields.json")
CANARIO_404 = Simulada(404, cuerpo="", content_type=None)
LOGOUT_OK = Simulada(200, content_type=None)


def registrar_p6(
    simulado: responses.RequestsMock,
    *,
    base: str = BASE,
    login: Simulada = LOGIN_OK,
    fields: Simulada = FIELDS_OK,
    canario: Simulada = CANARIO_404,
    logout: Simulada = LOGOUT_OK,
) -> None:
    """Registra las rutas que toca la prueba de conexión (sin exigir que se usen todas)."""
    simulado.add(login.respuesta("POST", f"{base}/login"))
    simulado.add(fields.respuesta("GET", f"{base}/project/fields"))
    simulado.add(canario.respuesta("GET", f"{base}/__p6cli_canary__"))
    simulado.add(logout.respuesta("POST", f"{base}/logout"))


def llamadas(simulado: responses.RequestsMock, metodo: str, ruta: str) -> int:
    """Cuántas peticiones ``metodo`` recibió una ruta (sin contar la consulta)."""
    return sum(
        1
        for llamada in simulado.calls
        if llamada.request.method == metodo
        and str(llamada.request.url).split("?", 1)[0].endswith(ruta)
    )


# --- Errores de red tal como los produce requests -----------------------------------


def error_dns() -> requests.ConnectionError:
    """Cadena real de requests + urllib3 cuando el nombre no resuelve."""
    try:
        try:
            raise socket.gaierror(11001, "getaddrinfo failed")
        except socket.gaierror as causa:
            raise NameResolutionError("localhost", None, causa) from causa  # type: ignore[arg-type]
    except NameResolutionError as razon:
        return requests.ConnectionError(MaxRetryError(None, "/p6ws/restapi/login", razon))  # type: ignore[arg-type]


def error_tcp() -> requests.ConnectionError:
    return requests.ConnectionError(ConnectionRefusedError(10061, "Connection refused"))


def error_tls() -> requests.exceptions.SSLError:
    return requests.exceptions.SSLError("certificate verify failed: self-signed certificate")
