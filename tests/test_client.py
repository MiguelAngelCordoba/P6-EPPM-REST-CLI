"""Cliente GET y guardarraíles (especificación §9 y §14)."""

import json
from urllib.parse import parse_qsl, urlsplit

import pytest
import responses

from p6cli.core import catalog
from p6cli.core.client import (
    FILTRO_NEUTRO,
    LARGO_FRAGMENTO_ERROR,
    LARGO_MAXIMO_URL,
    ORDEN_NEUTRO,
    Cliente,
    preparar_consulta,
    validar_consulta,
)
from p6cli.core.diagnostics import EstadoDiagnostico
from p6cli.core.errors import (
    AuthError,
    GuardrailError,
    MotivoAuth,
    MotivoGuardarrail,
    MotivoHTTP,
    MotivoUso,
    P6CliError,
    P6HTTPError,
    UsageError,
)
from p6cli.core.profiles import Profile
from p6cli.core.session import Sesion, token_autenticacion, url_get
from tests.conftest import (
    APACHE_404,
    BASE,
    FIELDS_OK,
    LOGIN_DATABASE_INVALIDA,
    LOGIN_OK,
    LOGIN_RECHAZADO,
    Simulada,
    error_tcp,
    leer_fixture,
    llamadas,
)

CLAVE = "ClaveDePrueba1"
PERFIL = Profile.desde_toml(
    "demo", {"host": "https://localhost:7001", "database_name": "orcl", "username": "admin"}
)
PROJECT = catalog.obtener("project")
ACTIVITY = catalog.obtener("activity")
SPREAD = catalog.obtener("spread.activity")

ACTIVIDADES = Simulada(200, "activity_ok.json")
FILTRO = "ProjectObjectId:eq:1234"


def json_simulado(datos: object, codigo: int = 200) -> Simulada:
    return Simulada(codigo, cuerpo=json.dumps(datos), content_type="application/json")


def registrar(
    simulado: responses.RequestsMock, ruta: str, respuesta: Simulada, login: Simulada = LOGIN_OK
) -> None:
    simulado.add(login.respuesta("POST", f"{BASE}/login"))
    simulado.add(respuesta.respuesta("GET", f"{BASE}{ruta}"))


def cliente() -> Cliente:
    return Cliente(Sesion(PERFIL, CLAVE))


def consulta_enviada(simulado: responses.RequestsMock) -> dict[str, str]:
    peticion = simulado.calls[-1].request
    assert peticion.method == "GET"
    return dict(parse_qsl(urlsplit(str(peticion.url)).query))


# --- preparar_consulta ------------------------------------------------------------


@pytest.mark.parametrize("fields", ["", "  ", ","])
def test_fields_vacio(fields: str) -> None:
    with pytest.raises(UsageError) as capturado:
        preparar_consulta(PROJECT, {"Fields": fields})

    assert capturado.value.motivo is MotivoUso.CAMPOS_VACIOS


def test_fields_ausente() -> None:
    with pytest.raises(UsageError) as capturado:
        preparar_consulta(PROJECT, {})

    assert capturado.value.motivo is MotivoUso.CAMPOS_VACIOS


def test_completa_filter_y_order_by_neutros() -> None:
    consulta = preparar_consulta(PROJECT, {"Fields": "ObjectId, Id,Id", "Filter": " "})

    assert consulta == {"Fields": "ObjectId,Id", "Filter": FILTRO_NEUTRO, "OrderBy": ORDEN_NEUTRO}


def test_filter_y_order_by_del_usuario_van_tal_cual() -> None:
    params = {"Fields": "ObjectId", "Filter": " Name :like: 'a%' ", "OrderBy": "Name desc"}

    consulta = preparar_consulta(PROJECT, params)

    assert consulta["Filter"] == " Name :like: 'a%' "
    assert consulta["OrderBy"] == "Name desc"


def test_parametro_ajeno_a_la_plantilla() -> None:
    with pytest.raises(UsageError) as capturado:
        preparar_consulta(PROJECT, {"Fields": "ObjectId", "PeriodType": "Week"})

    assert capturado.value.motivo is MotivoUso.PARAMETRO_DESCONOCIDO
    assert capturado.value.datos["parametro"] == "PeriodType"


def test_large_sin_filtro_bloqueado() -> None:
    with pytest.raises(GuardrailError) as capturado:
        preparar_consulta(ACTIVITY, {"Fields": "ObjectId", "Filter": ""})

    assert capturado.value.motivo is MotivoGuardarrail.SIN_FILTRO
    assert capturado.value.datos["endpoint"] == "activity"


def test_large_sin_filtro_permitido_envia_filtro_neutro() -> None:
    consulta = preparar_consulta(ACTIVITY, {"Fields": "ObjectId"}, allow_unfiltered=True)

    assert consulta["Filter"] == FILTRO_NEUTRO


def test_large_con_filtro_pasa() -> None:
    consulta = preparar_consulta(ACTIVITY, {"Fields": "ObjectId", "Filter": FILTRO})

    assert consulta["Filter"] == FILTRO


def test_no_large_sin_filtro_pasa() -> None:
    assert preparar_consulta(PROJECT, {"Fields": "ObjectId"})["Filter"] == FILTRO_NEUTRO


def test_spread_aplica_valores_por_defecto_y_exige_ids() -> None:
    consulta = preparar_consulta(SPREAD, {"ActivityObjectId": "1,2", "SpreadField": "Units"})

    assert consulta["PeriodType"] == "Week"
    assert consulta["IncludeCumulative"] == "true"
    assert "StartDate" not in consulta
    with pytest.raises(UsageError) as capturado:
        preparar_consulta(SPREAD, {"SpreadField": "Units"})
    assert capturado.value.motivo is MotivoUso.PARAMETRO_REQUERIDO


# --- Largo de URL ------------------------------------------------------------------


def _params_con_largo(largo: int) -> dict[str, str]:
    """Parámetros cuya URL final mide exactamente ``largo`` caracteres."""
    base = {"Fields": "ObjectId", "Filter": "", "OrderBy": "ObjectId asc"}
    sin_filtro = len(url_get(PERFIL, PROJECT.path, base))
    return {"Fields": "ObjectId", "Filter": "a" * (largo - sin_filtro)}


def test_url_en_el_limite_pasa() -> None:
    consulta = validar_consulta(PERFIL, PROJECT, _params_con_largo(LARGO_MAXIMO_URL))

    assert len(url_get(PERFIL, PROJECT.path, consulta)) == LARGO_MAXIMO_URL


def test_url_demasiado_larga_no_envia_nada(http_simulado: responses.RequestsMock) -> None:
    registrar(http_simulado, "/project", json_simulado([]))

    with pytest.raises(UsageError) as capturado:
        cliente().get(PROJECT, _params_con_largo(LARGO_MAXIMO_URL + 1))

    assert capturado.value.motivo is MotivoUso.URL_DEMASIADO_LARGA
    assert capturado.value.datos["largo"] == str(LARGO_MAXIMO_URL + 1)
    assert len(http_simulado.calls) == 0


# --- get ---------------------------------------------------------------------------


def test_get_envia_consulta_completa_y_devuelve_filas(
    http_simulado: responses.RequestsMock,
) -> None:
    registrar(http_simulado, "/activity", ACTIVIDADES)

    filas = cliente().get(ACTIVITY, {"Fields": "ObjectId, Id,Name", "Filter": FILTRO})

    assert filas == json.loads(leer_fixture("activity_ok.json"))
    assert consulta_enviada(http_simulado) == {
        "Fields": "ObjectId,Id,Name",
        "Filter": FILTRO,
        "OrderBy": ORDEN_NEUTRO,
        "DatabaseName": "orcl",
    }
    peticion = http_simulado.calls[-1].request
    assert peticion.headers["authToken"] == token_autenticacion("admin", CLAVE)
    assert peticion.headers["Accept"] == "application/json"


@pytest.mark.parametrize(
    "params",
    [{"Fields": ""}, {"Fields": "ObjectId", "Otro": "x"}, {"Fields": "ObjectId"}],
    ids=["fields-vacio", "parametro-ajeno", "guardarrail"],
)
def test_errores_previos_no_hacen_peticiones(
    http_simulado: responses.RequestsMock, params: dict[str, str]
) -> None:
    registrar(http_simulado, "/activity", ACTIVIDADES)

    with pytest.raises((UsageError, GuardrailError)):
        cliente().get(ACTIVITY, params)

    assert len(http_simulado.calls) == 0


def test_varias_consultas_un_solo_login(http_simulado: responses.RequestsMock) -> None:
    registrar(http_simulado, "/project", json_simulado([{"ObjectId": 1}]))
    c = cliente()

    c.get(PROJECT, {"Fields": "ObjectId"})
    c.get(PROJECT, {"Fields": "ObjectId"})

    assert llamadas(http_simulado, "POST", "/login") == 1
    assert llamadas(http_simulado, "GET", "/project") == 2


@pytest.mark.parametrize(
    ("login", "estado"),
    [
        (LOGIN_DATABASE_INVALIDA, EstadoDiagnostico.INVALID_DATABASE),
        (LOGIN_RECHAZADO, EstadoDiagnostico.CREDENTIALS_REJECTED),
        (APACHE_404, EstadoDiagnostico.ROUTE_NOT_FOUND),
    ],
    ids=["database", "rechazo", "ruta"],
)
def test_login_fallido_se_clasifica_sin_reintentar(
    http_simulado: responses.RequestsMock, login: Simulada, estado: EstadoDiagnostico
) -> None:
    registrar(http_simulado, "/project", json_simulado([]), login=login)
    c = cliente()

    with pytest.raises(AuthError) as capturado:
        c.get(PROJECT, {"Fields": "ObjectId"})

    assert capturado.value.motivo is MotivoAuth.LOGIN_FALLIDO
    assert capturado.value.datos["estado"] == estado
    assert capturado.value.datos["perfil"] == "demo"
    assert llamadas(http_simulado, "POST", "/login") == 1
    assert llamadas(http_simulado, "GET", "/project") == 0

    # Una segunda consulta con la misma sesión no gasta otro intento.
    with pytest.raises(AuthError) as otra:
        c.get(PROJECT, {"Fields": "ObjectId"})
    assert otra.value.motivo is MotivoAuth.LOGIN_YA_INTENTADO
    assert llamadas(http_simulado, "POST", "/login") == 1


@pytest.mark.parametrize("codigo", [400, 401, 403, 404, 405, 500, 503])
def test_codigo_distinto_de_200(http_simulado: responses.RequestsMock, codigo: int) -> None:
    registrar(
        http_simulado, "/project", json_simulado({"message": "Invalid field: Nombre"}, codigo)
    )

    with pytest.raises(P6HTTPError) as capturado:
        cliente().get(PROJECT, {"Fields": "Nombre"})

    error = capturado.value
    assert error.motivo is MotivoHTTP.CODIGO_HTTP
    assert error.datos["codigo"] == str(codigo)
    assert error.datos["metodo"] == "GET"
    assert error.datos["url"].startswith(f"{BASE}/project?")
    assert error.datos["mensaje_p6"] == "Invalid field: Nombre"


def test_cuerpo_de_error_se_recorta(http_simulado: responses.RequestsMock) -> None:
    registrar(
        http_simulado, "/project", Simulada(500, cuerpo="x" * 2000, content_type="text/plain")
    )

    with pytest.raises(P6HTTPError) as capturado:
        cliente().get(PROJECT, {"Fields": "ObjectId"})

    assert len(capturado.value.datos["mensaje_p6"]) == LARGO_FRAGMENTO_ERROR


def test_200_sin_json(http_simulado: responses.RequestsMock) -> None:
    registrar(
        http_simulado,
        "/project",
        Simulada(200, cuerpo="<html>login</html>", content_type="text/html"),
    )

    with pytest.raises(P6HTTPError) as capturado:
        cliente().get(PROJECT, {"Fields": "ObjectId"})

    assert capturado.value.motivo is MotivoHTTP.RESPUESTA_NO_JSON
    assert capturado.value.datos["content_type"] == "text/html"
    assert capturado.value.datos["fragmento"] == "<html>login</html>"


@pytest.mark.parametrize(
    "respuesta",
    [
        json_simulado({"ObjectId": 1}),
        json_simulado([1, 2]),
        Simulada(200, cuerpo="{no es json", content_type="application/json"),
    ],
    ids=["objeto", "lista-de-numeros", "json-roto"],
)
def test_200_json_con_formato_inesperado(
    http_simulado: responses.RequestsMock, respuesta: Simulada
) -> None:
    registrar(http_simulado, "/project", respuesta)

    with pytest.raises(P6HTTPError) as capturado:
        cliente().get(PROJECT, {"Fields": "ObjectId"})

    assert capturado.value.motivo is MotivoHTTP.FORMATO_INESPERADO
    assert capturado.value.__cause__ is None
    assert capturado.value.__context__ is None


def test_lista_vacia(http_simulado: responses.RequestsMock) -> None:
    registrar(http_simulado, "/project", json_simulado([]))

    assert cliente().get(PROJECT, {"Fields": "ObjectId"}) == []


def test_error_de_red(http_simulado: responses.RequestsMock) -> None:
    registrar(http_simulado, "/project", Simulada(error=error_tcp()))

    with pytest.raises(P6HTTPError) as capturado:
        cliente().get(PROJECT, {"Fields": "ObjectId"})

    assert capturado.value.motivo is MotivoHTTP.SIN_CONEXION


# --- fields ------------------------------------------------------------------------


def test_fields_acepta_el_texto_plano_real(http_simulado: responses.RequestsMock) -> None:
    registrar(http_simulado, "/project/fields", FIELDS_OK)

    campos = cliente().fields(PROJECT)

    assert campos == leer_fixture("project_fields.txt").split(",")
    assert llamadas(http_simulado, "GET", "/project/fields") == 1


def test_fields_acepta_lista_json(http_simulado: responses.RequestsMock) -> None:
    registrar(http_simulado, "/project/fields", json_simulado(["ObjectId", "Id"]))

    assert cliente().fields(PROJECT) == ["ObjectId", "Id"]


def test_fields_acepta_texto_separado_por_comas(http_simulado: responses.RequestsMock) -> None:
    registrar(http_simulado, "/activity/fields", json_simulado("ObjectId, Id,Name,"))

    assert cliente().fields(ACTIVITY) == ["ObjectId", "Id", "Name"]


@pytest.mark.parametrize(
    "cuerpo",
    ['{"campos": []}', "<html><body>login</body></html>", "", "ObjectId,Id;Name", "[1, 2]"],
    ids=["objeto", "html", "vacio", "token-invalido", "lista-de-numeros"],
)
def test_fields_con_formato_inesperado(http_simulado: responses.RequestsMock, cuerpo: str) -> None:
    registrar(
        http_simulado,
        "/project/fields",
        Simulada(200, cuerpo=cuerpo, content_type="application/json"),
    )

    with pytest.raises(P6HTTPError) as capturado:
        cliente().fields(PROJECT)

    assert capturado.value.motivo is MotivoHTTP.FORMATO_INESPERADO
    assert capturado.value.datos["url"].startswith(f"{BASE}/project/fields")


def test_fields_de_spread_no_se_admite(http_simulado: responses.RequestsMock) -> None:
    with pytest.raises(UsageError) as capturado:
        cliente().fields(SPREAD)

    assert capturado.value.motivo is MotivoUso.PLANTILLA_NO_SOPORTADA
    assert len(http_simulado.calls) == 0


# --- Secretos ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("login", "respuesta"),
    [
        (LOGIN_RECHAZADO, json_simulado([])),
        (
            Simulada(401, cuerpo='{"message":"Denied"}', content_type="application/json"),
            json_simulado([]),
        ),
        (LOGIN_OK, json_simulado({"message": "Bad"}, 400)),
        (LOGIN_OK, Simulada(200, cuerpo="<html/>", content_type="text/html")),
    ],
    ids=["login-500", "login-401", "get-400", "get-html"],
)
def test_ningun_error_contiene_la_clave_ni_el_token(
    http_simulado: responses.RequestsMock, login: Simulada, respuesta: Simulada
) -> None:
    registrar(http_simulado, "/project", respuesta, login=login)

    with pytest.raises(P6CliError) as capturado:
        cliente().get(PROJECT, {"Fields": "ObjectId"})

    texto = str(capturado.value) + repr(capturado.value.datos)
    assert CLAVE not in texto
    assert token_autenticacion("admin", CLAVE) not in texto
