"""Prueba de conexión y clasificación (especificación §7): un test por estado de la tabla."""

import pytest
import requests
import responses

from p6cli.core.diagnostics import (
    LARGO_FRAGMENTO,
    DiagnosticReport,
    EstadoDiagnostico,
    clasificar_login,
    diagnosticar,
    probar_conexion,
)
from p6cli.core.errors import MotivoHTTP
from p6cli.core.profiles import Profile
from p6cli.core.session import Sesion, token_autenticacion
from tests.conftest import (
    APACHE_404,
    BASE,
    COMODIN_GET,
    COMODIN_POST,
    FIELDS_OK,
    INTERFAZ_WEB_401,
    LOGIN_DATABASE_INVALIDA,
    LOGIN_OK,
    LOGIN_RECHAZADO,
    Simulada,
    error_dns,
    error_tcp,
    error_tls,
    llamadas,
    registrar_p6,
)

CLAVE = "ClaveDePrueba1"
PERFIL = Profile.desde_toml(
    "demo", {"host": "https://localhost:7001", "database_name": "orcl", "username": "admin"}
)


def diagnostico(simulado: responses.RequestsMock, **escenario: Simulada) -> DiagnosticReport:
    registrar_p6(simulado, **escenario)
    return probar_conexion(PERFIL, CLAVE)


# --- Filas 1 a 3: red y TLS -----------------------------------------------------


@pytest.mark.parametrize(
    ("error", "causa"),
    [
        (error_dns(), MotivoHTTP.SIN_RESOLUCION),
        (error_tcp(), MotivoHTTP.SIN_CONEXION),
        (requests.exceptions.ConnectTimeout(), MotivoHTTP.SIN_CONEXION),
    ],
    ids=["dns", "tcp-rechazado", "tcp-timeout"],
)
def test_network(
    http_simulado: responses.RequestsMock, error: Exception, causa: MotivoHTTP
) -> None:
    reporte = diagnostico(http_simulado, login=Simulada(error=error))

    assert reporte.status is EstadoDiagnostico.NETWORK
    assert reporte.causa_red is causa


def test_tls(http_simulado: responses.RequestsMock) -> None:
    reporte = diagnostico(http_simulado, login=Simulada(error=error_tls()))

    assert reporte.status is EstadoDiagnostico.TLS
    assert reporte.causa_red is MotivoHTTP.TLS


def test_error_de_red_corta_la_secuencia(http_simulado: responses.RequestsMock) -> None:
    reporte = diagnostico(http_simulado, login=Simulada(error=error_dns()))

    assert len(http_simulado.calls) == 1
    assert len(reporte.pasos) == 1
    paso = reporte.pasos[0]
    assert paso.metodo == "POST"
    assert paso.codigo is None
    assert paso.fragmento == "ConnectionError"


# --- Fila 4: comodín ------------------------------------------------------------


@pytest.mark.parametrize(
    "canario", [COMODIN_GET, Simulada(200, cuerpo="")], ids=["canario-405", "canario-200"]
)
def test_catch_all(http_simulado: responses.RequestsMock, canario: Simulada) -> None:
    reporte = diagnostico(http_simulado, login=COMODIN_POST, fields=COMODIN_GET, canario=canario)

    assert reporte.status is EstadoDiagnostico.CATCH_ALL


def test_canario_distinto_de_404_gana_a_database_invalida(
    http_simulado: responses.RequestsMock,
) -> None:
    reporte = diagnostico(http_simulado, login=LOGIN_DATABASE_INVALIDA, canario=COMODIN_GET)

    assert reporte.status is EstadoDiagnostico.CATCH_ALL


def test_canario_distinto_de_404_impide_ok(http_simulado: responses.RequestsMock) -> None:
    reporte = diagnostico(http_simulado, canario=Simulada(200, "login_ok.json"))

    assert reporte.status is EstadoDiagnostico.CATCH_ALL


def test_el_canario_se_consulta_con_get(http_simulado: responses.RequestsMock) -> None:
    diagnostico(http_simulado)

    assert llamadas(http_simulado, "GET", "/__p6cli_canary__") == 1
    assert llamadas(http_simulado, "POST", "/__p6cli_canary__") == 0


# --- Filas 5 a 9 -----------------------------------------------------------------


def test_route_not_found(http_simulado: responses.RequestsMock) -> None:
    reporte = diagnostico(http_simulado, login=APACHE_404, fields=APACHE_404, canario=APACHE_404)

    assert reporte.status is EstadoDiagnostico.ROUTE_NOT_FOUND


def test_ui_not_api(http_simulado: responses.RequestsMock) -> None:
    reporte = diagnostico(http_simulado, login=INTERFAZ_WEB_401, fields=INTERFAZ_WEB_401)

    assert reporte.status is EstadoDiagnostico.UI_NOT_API


def test_ui_not_api_por_redireccion(http_simulado: responses.RequestsMock) -> None:
    redireccion = Simulada(
        302,
        content_type=None,
        cabeceras={"Location": "https://localhost:7001/p6/action/login?sessionExpired=true"},
    )

    reporte = diagnostico(http_simulado, login=redireccion)

    assert reporte.status is EstadoDiagnostico.UI_NOT_API
    assert len(http_simulado.calls) == 3  # no se siguió la redirección


def test_invalid_database(http_simulado: responses.RequestsMock) -> None:
    reporte = diagnostico(http_simulado, login=LOGIN_DATABASE_INVALIDA)

    assert reporte.status is EstadoDiagnostico.INVALID_DATABASE


def test_fields_200_no_basta_con_database_invalida(http_simulado: responses.RequestsMock) -> None:
    # /project/fields responde 200 JSON aun con DatabaseName inválido (APRENDIZAJES §6).
    reporte = diagnostico(http_simulado, login=LOGIN_DATABASE_INVALIDA, fields=FIELDS_OK)

    assert reporte.status is not EstadoDiagnostico.OK


def test_credentials_rejected(http_simulado: responses.RequestsMock) -> None:
    reporte = diagnostico(http_simulado, login=LOGIN_RECHAZADO)

    assert reporte.status is EstadoDiagnostico.CREDENTIALS_REJECTED


def test_auth_failed_con_mensaje_de_p6(http_simulado: responses.RequestsMock) -> None:
    rechazo = Simulada(401, cuerpo='{"message":"User is locked."}', content_type="application/json")

    reporte = diagnostico(http_simulado, login=rechazo)

    assert reporte.status is EstadoDiagnostico.AUTH_FAILED
    assert reporte.detalle["mensaje_p6"] == "User is locked."


@pytest.mark.parametrize("cuerpo", ["no es json", '["sin", "message"]'], ids=["invalido", "lista"])
def test_auth_failed_sin_message_usa_el_inicio_del_cuerpo(
    http_simulado: responses.RequestsMock, cuerpo: str
) -> None:
    rechazo = Simulada(401, cuerpo=cuerpo, content_type="application/json")

    reporte = diagnostico(http_simulado, login=rechazo)

    assert reporte.status is EstadoDiagnostico.AUTH_FAILED
    assert reporte.detalle["mensaje_p6"] == cuerpo


# --- Fila 10 y casos desconocidos ------------------------------------------------


def test_ok(http_simulado: responses.RequestsMock) -> None:
    reporte = diagnostico(http_simulado, login=LOGIN_OK, fields=FIELDS_OK)

    assert reporte.status is EstadoDiagnostico.OK
    assert [paso.codigo for paso in reporte.pasos] == [200, 200, 404]


def test_unknown_login_200_html(http_simulado: responses.RequestsMock) -> None:
    html = Simulada(200, cuerpo="<html>hola</html>", content_type="text/html")

    reporte = diagnostico(http_simulado, login=html)

    assert reporte.status is EstadoDiagnostico.UNKNOWN
    assert reporte.detalle["codigo"] == "200"
    assert reporte.detalle["content_type"] == "text/html"
    assert reporte.detalle["fragmento"] == "<html>hola</html>"
    assert reporte.detalle["url"].endswith("/login?DatabaseName=orcl")


def test_unknown_fields_sin_json(http_simulado: responses.RequestsMock) -> None:
    reporte = diagnostico(http_simulado, fields=Simulada(200, cuerpo="x", content_type="text/html"))

    assert reporte.status is EstadoDiagnostico.UNKNOWN
    assert reporte.detalle["url"].endswith("/project/fields?DatabaseName=orcl")


def test_unknown_por_tiempo_agotado(http_simulado: responses.RequestsMock) -> None:
    reporte = diagnostico(http_simulado, login=Simulada(error=requests.exceptions.ReadTimeout()))

    assert reporte.status is EstadoDiagnostico.UNKNOWN
    assert reporte.causa_red is MotivoHTTP.TIEMPO_AGOTADO


# --- Pasos, login único y logout -------------------------------------------------


def test_un_solo_login_por_diagnostico(http_simulado: responses.RequestsMock) -> None:
    diagnostico(http_simulado, login=LOGIN_RECHAZADO)

    assert llamadas(http_simulado, "POST", "/login") == 1


def test_pasos_observados(http_simulado: responses.RequestsMock) -> None:
    reporte = diagnostico(http_simulado)

    login, fields, canario = reporte.pasos
    assert (login.metodo, login.url) == ("POST", f"{BASE}/login?DatabaseName=orcl")
    assert (fields.metodo, fields.url) == ("GET", f"{BASE}/project/fields?DatabaseName=orcl")
    assert (canario.metodo, canario.url) == ("GET", f"{BASE}/__p6cli_canary__?DatabaseName=orcl")
    assert fields.content_type == "application/json"
    assert fields.tamano > 0
    assert fields.fragmento.startswith("ObjectId,Id")


def test_fragmento_acotado_y_sin_caracteres_de_control(
    http_simulado: responses.RequestsMock,
) -> None:
    cuerpo = "\x1b[31mrojo\x1b[0m\r\nlinea\t" + "x" * 500
    reporte = diagnostico(
        http_simulado, login=Simulada(200, cuerpo=cuerpo, content_type="text/html")
    )

    fragmento = reporte.pasos[0].fragmento
    assert len(fragmento) == LARGO_FRAGMENTO
    assert fragmento.isprintable()
    assert "\x1b" not in fragmento


def test_logout_solo_tras_login_exitoso(http_simulado: responses.RequestsMock) -> None:
    diagnostico(http_simulado)

    assert llamadas(http_simulado, "POST", "/logout") == 1


def test_sin_logout_si_el_login_falla(http_simulado: responses.RequestsMock) -> None:
    diagnostico(http_simulado, login=LOGIN_RECHAZADO)

    assert llamadas(http_simulado, "POST", "/logout") == 0


def test_diagnosticar_deja_la_sesion_autenticada_si_ok(
    http_simulado: responses.RequestsMock,
) -> None:
    registrar_p6(http_simulado)
    sesion = Sesion(PERFIL, CLAVE)

    reporte = diagnosticar(sesion)

    assert reporte.status is EstadoDiagnostico.OK
    assert sesion.autenticada
    assert llamadas(http_simulado, "POST", "/logout") == 0


# --- Secretos -------------------------------------------------------------------

ESCENARIOS = {
    "ok": {},
    "dns": {"login": Simulada(error=error_dns())},
    "tls": {"login": Simulada(error=error_tls())},
    "comodin": {"login": COMODIN_POST, "canario": COMODIN_GET},
    "apache": {"login": APACHE_404, "canario": APACHE_404},
    "interfaz": {"login": INTERFAZ_WEB_401},
    "database": {"login": LOGIN_DATABASE_INVALIDA},
    "rechazo": {"login": LOGIN_RECHAZADO},
    "desconocido": {"login": Simulada(418, cuerpo="teapot")},
}


@pytest.mark.parametrize("escenario", ESCENARIOS.values(), ids=ESCENARIOS.keys())
def test_el_reporte_no_contiene_secretos(
    http_simulado: responses.RequestsMock, escenario: dict[str, Simulada]
) -> None:
    reporte = diagnostico(http_simulado, **escenario)

    texto = repr(reporte)
    assert CLAVE not in texto
    assert token_autenticacion("admin", CLAVE) not in texto


# --- Clasificación del login sin diagnóstico completo ------------------------------


@pytest.mark.parametrize(
    ("login", "estado"),
    [
        (APACHE_404, EstadoDiagnostico.ROUTE_NOT_FOUND),
        (INTERFAZ_WEB_401, EstadoDiagnostico.UI_NOT_API),
        (LOGIN_DATABASE_INVALIDA, EstadoDiagnostico.INVALID_DATABASE),
        (LOGIN_RECHAZADO, EstadoDiagnostico.CREDENTIALS_REJECTED),
        (
            Simulada(401, cuerpo='{"message":"User locked."}', content_type="application/json"),
            EstadoDiagnostico.AUTH_FAILED,
        ),
        (LOGIN_OK, EstadoDiagnostico.OK),
        (
            Simulada(200, cuerpo="<html></html>", content_type="text/html"),
            EstadoDiagnostico.UNKNOWN,
        ),
    ],
    ids=["route", "ui", "database", "rechazo", "auth", "ok", "unknown"],
)
def test_clasificar_login(
    http_simulado: responses.RequestsMock, login: Simulada, estado: EstadoDiagnostico
) -> None:
    http_simulado.add(login.respuesta("POST", f"{BASE}/login"))

    respuesta = Sesion(PERFIL, CLAVE).login()

    assert clasificar_login(respuesta)[0] is estado
    assert len(http_simulado.calls) == 1
