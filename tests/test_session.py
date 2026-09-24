"""Sesión autenticada (especificación §6)."""

import base64

import pytest
import requests
import responses

from p6cli.core.errors import AuthError, MotivoAuth, MotivoHTTP, P6HTTPError
from p6cli.core.profiles import Profile
from p6cli.core.session import TIEMPO_CONEXION, Sesion, token_autenticacion
from tests.conftest import (
    BASE,
    LOGIN_OK,
    LOGIN_RECHAZADO,
    Simulada,
    error_dns,
    error_tcp,
    error_tls,
    llamadas,
)

CLAVE = "ClaveDePrueba1"


def perfil(**cambios: object) -> Profile:
    datos: dict[str, object] = {
        "host": "https://localhost:7001",
        "database_name": "orcl",
        "username": "admin",
        **cambios,
    }
    return Profile.desde_toml("demo", datos)


def sesion(clave: str = CLAVE, **cambios: object) -> Sesion:
    return Sesion(perfil(**cambios), clave)


def registrar(simulado: responses.RequestsMock, metodo: str, ruta: str, r: Simulada) -> None:
    simulado.add(r.respuesta(metodo, f"{BASE}{ruta}"))


# --- Login ------------------------------------------------------------------------


def test_token_es_base64_de_usuario_y_clave() -> None:
    token = token_autenticacion("admin", CLAVE)

    assert base64.b64decode(token).decode() == f"admin:{CLAVE}"


def test_login_envia_cabeceras_y_database_name(http_simulado: responses.RequestsMock) -> None:
    registrar(http_simulado, "POST", "/login", LOGIN_OK)

    respuesta = sesion().login()

    assert respuesta.status_code == 200
    peticion = http_simulado.calls[0].request
    assert peticion.method == "POST"
    assert peticion.url == f"{BASE}/login?DatabaseName=orcl"
    assert peticion.headers["username"] == "admin"
    assert peticion.headers["password"] == CLAVE
    assert peticion.headers["authToken"] == token_autenticacion("admin", CLAVE)
    assert peticion.headers["Accept"] == "*/*"


def test_login_200_json_deja_la_sesion_autenticada(
    http_simulado: responses.RequestsMock,
) -> None:
    registrar(http_simulado, "POST", "/login", LOGIN_OK)
    s = sesion()

    s.login()

    assert s.autenticada


@pytest.mark.parametrize(
    "respuesta",
    [LOGIN_RECHAZADO, Simulada(200, cuerpo="", content_type="text/html")],
    ids=["500", "200-html"],
)
def test_login_fallido_o_sin_json_no_autentica(
    http_simulado: responses.RequestsMock, respuesta: Simulada
) -> None:
    registrar(http_simulado, "POST", "/login", respuesta)
    s = sesion()

    s.login()

    assert not s.autenticada


def test_segundo_login_falla_sin_enviar_peticion(http_simulado: responses.RequestsMock) -> None:
    registrar(http_simulado, "POST", "/login", LOGIN_RECHAZADO)
    s = sesion()
    s.login()

    with pytest.raises(AuthError) as error:
        s.login()

    assert error.value.motivo is MotivoAuth.LOGIN_YA_INTENTADO
    assert llamadas(http_simulado, "POST", "/login") == 1


def test_login_tras_error_de_red_tampoco_se_repite(
    http_simulado: responses.RequestsMock,
) -> None:
    registrar(http_simulado, "POST", "/login", Simulada(error=error_tcp()))
    s = sesion()
    with pytest.raises(P6HTTPError):
        s.login()

    with pytest.raises(AuthError):
        s.login()

    assert llamadas(http_simulado, "POST", "/login") == 1


@pytest.mark.parametrize(
    "clave", ["Clave€", " inicia-con-espacio", "con\nsalto"], ids=["no-latin1", "espacio", "salto"]
)
def test_clave_no_enviable_como_cabecera(http_simulado: responses.RequestsMock, clave: str) -> None:
    with pytest.raises(AuthError) as error:
        sesion(clave=clave).login()

    assert error.value.motivo is MotivoAuth.CLAVE_NO_CODIFICABLE
    assert clave not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert len(http_simulado.calls) == 0


def test_no_sigue_redirecciones(http_simulado: responses.RequestsMock) -> None:
    redireccion = Simulada(302, cabeceras={"Location": "https://otro.example.com/robar"})
    registrar(http_simulado, "POST", "/login", redireccion)

    respuesta = sesion().login()

    assert respuesta.status_code == 302
    assert len(http_simulado.calls) == 1


def test_verify_y_timeout_del_perfil(http_simulado: responses.RequestsMock) -> None:
    registrar(http_simulado, "POST", "/login", LOGIN_OK)

    sesion(verify_ssl="C:/certs/ca.pem", timeout=60).login()

    argumentos = http_simulado.calls[0].request.req_kwargs  # type: ignore[attr-defined]
    assert argumentos["verify"] == "C:/certs/ca.pem"
    assert argumentos["timeout"] == (TIEMPO_CONEXION, 60)


# --- GET ------------------------------------------------------------------------


def test_get_envia_token_accept_y_database_name(http_simulado: responses.RequestsMock) -> None:
    registrar(http_simulado, "GET", "/project", Simulada(200, cuerpo="[]"))

    sesion().get("/project", {"Fields": "ObjectId,Id"})

    peticion = http_simulado.calls[0].request
    assert peticion.method == "GET"
    assert peticion.url == f"{BASE}/project?Fields=ObjectId%2CId&DatabaseName=orcl"
    assert peticion.headers["authToken"] == token_autenticacion("admin", CLAVE)
    assert peticion.headers["Accept"] == "application/json"
    assert "password" not in peticion.headers


def test_get_reenvia_las_cookies_del_login(http_simulado: responses.RequestsMock) -> None:
    con_cookie = Simulada(200, "login_ok.json", cabeceras={"Set-Cookie": "JSESSIONID=abc123"})
    registrar(http_simulado, "POST", "/login", con_cookie)
    registrar(http_simulado, "GET", "/project", Simulada(200, cuerpo="[]"))
    s = sesion()

    s.login()
    s.get("/project")

    assert "JSESSIONID=abc123" in http_simulado.calls[1].request.headers["Cookie"]


def test_sesion_no_expone_otros_verbos() -> None:
    for verbo in ("post", "put", "patch", "delete", "request"):
        assert not hasattr(Sesion, verbo)


# --- Logout y cierre ------------------------------------------------------------


@pytest.mark.parametrize(
    "respuesta", [Simulada(500, cuerpo="error"), Simulada(error=error_tcp())], ids=["500", "red"]
)
def test_logout_ignora_fallos(http_simulado: responses.RequestsMock, respuesta: Simulada) -> None:
    registrar(http_simulado, "POST", "/logout", respuesta)

    sesion().logout()

    assert llamadas(http_simulado, "POST", "/logout") == 1


def test_cerrar_hace_logout_tras_login_exitoso(http_simulado: responses.RequestsMock) -> None:
    registrar(http_simulado, "POST", "/login", LOGIN_OK)
    registrar(http_simulado, "POST", "/logout", Simulada(200))

    with sesion() as s:
        s.login()

    assert llamadas(http_simulado, "POST", "/logout") == 1
    assert not s.autenticada


def test_cerrar_sin_login_exitoso_no_hace_logout(http_simulado: responses.RequestsMock) -> None:
    registrar(http_simulado, "POST", "/login", LOGIN_RECHAZADO)

    with sesion() as s:
        s.login()

    assert llamadas(http_simulado, "POST", "/logout") == 0


# --- Errores de red -------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "motivo"),
    [
        (error_dns(), MotivoHTTP.SIN_RESOLUCION),
        (error_tcp(), MotivoHTTP.SIN_CONEXION),
        (requests.exceptions.ConnectTimeout(), MotivoHTTP.SIN_CONEXION),
        (error_tls(), MotivoHTTP.TLS),
        (requests.exceptions.ReadTimeout(), MotivoHTTP.TIEMPO_AGOTADO),
    ],
    ids=["dns", "tcp", "timeout-conexion", "tls", "timeout-lectura"],
)
def test_errores_de_red_se_traducen_sin_encadenar(
    http_simulado: responses.RequestsMock, error: Exception, motivo: MotivoHTTP
) -> None:
    registrar(http_simulado, "POST", "/login", Simulada(error=error))

    with pytest.raises(P6HTTPError) as capturado:
        sesion().login()

    assert capturado.value.motivo is motivo
    assert capturado.value.datos["metodo"] == "POST"
    assert capturado.value.datos["url"] == f"{BASE}/login?DatabaseName=orcl"
    assert capturado.value.__cause__ is None
    assert capturado.value.__context__ is None
    assert CLAVE not in str(capturado.value)


# --- Secretos -------------------------------------------------------------------


def test_repr_no_revela_clave_ni_token() -> None:
    texto = repr(sesion())

    assert CLAVE not in texto
    assert token_autenticacion("admin", CLAVE) not in texto
