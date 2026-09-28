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
    filas_por_periodo,
    preparar_consulta,
    validar_consulta,
    validar_lectura_masiva,
    validar_spread,
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


# --- preparar_consulta de spread: tipos de parámetro --------------------------------

SPREAD_MINIMO = {"ActivityObjectId": "4835", "SpreadField": "PlannedLaborUnits"}


@pytest.mark.parametrize(("escrito", "enviado"), [("WEEK", "Week"), (" month ", "Month")])
def test_period_type_sin_distinguir_mayusculas_se_envia_canonico(
    escrito: str, enviado: str
) -> None:
    consulta = preparar_consulta(SPREAD, {**SPREAD_MINIMO, "PeriodType": escrito})

    assert consulta["PeriodType"] == enviado


def test_period_type_fuera_de_las_opciones() -> None:
    with pytest.raises(UsageError) as capturado:
        preparar_consulta(SPREAD, {**SPREAD_MINIMO, "PeriodType": "Weekly"})

    assert capturado.value.motivo is MotivoUso.VALOR_NO_PERMITIDO
    assert capturado.value.datos["parametro"] == "PeriodType"
    assert "FinancialPeriod" in capturado.value.datos["opciones"]


@pytest.mark.parametrize(("escrito", "enviado"), [("FALSE", "false"), ("true", "true")])
def test_include_cumulative_se_envia_canonico(escrito: str, enviado: str) -> None:
    consulta = preparar_consulta(SPREAD, {**SPREAD_MINIMO, "IncludeCumulative": escrito})

    assert consulta["IncludeCumulative"] == enviado


@pytest.mark.parametrize("valor", ["si", "1", "yes"])
def test_include_cumulative_invalido(valor: str) -> None:
    with pytest.raises(UsageError) as capturado:
        preparar_consulta(SPREAD, {**SPREAD_MINIMO, "IncludeCumulative": valor})

    assert capturado.value.motivo is MotivoUso.VALOR_NO_PERMITIDO


def test_fechas_se_envian_con_hora_cero() -> None:
    params = {**SPREAD_MINIMO, "StartDate": " 2026-01-05 ", "EndDate": "2026-01-05"}

    consulta = preparar_consulta(SPREAD, params)

    assert consulta["StartDate"] == "2026-01-05T00:00:00"
    assert consulta["EndDate"] == "2026-01-05T00:00:00"


@pytest.mark.parametrize(
    "fecha", ["2026-02-30", "05/01/2026", "2026-1-5", "2026-01-05T00:00:00", "hoy"]
)
def test_fecha_invalida(fecha: str) -> None:
    with pytest.raises(UsageError) as capturado:
        preparar_consulta(SPREAD, {**SPREAD_MINIMO, "EndDate": fecha})

    assert capturado.value.motivo is MotivoUso.FECHA_INVALIDA
    assert capturado.value.datos == {"parametro": "EndDate", "valor": fecha}


def test_inicio_posterior_al_fin() -> None:
    params = {**SPREAD_MINIMO, "StartDate": "2026-02-01", "EndDate": "2026-01-31"}

    with pytest.raises(UsageError) as capturado:
        preparar_consulta(SPREAD, params)

    assert capturado.value.motivo is MotivoUso.RANGO_FECHAS
    assert capturado.value.datos == {"inicio": "2026-02-01", "fin": "2026-01-31"}


def test_ids_de_spread_se_normalizan() -> None:
    consulta = preparar_consulta(SPREAD, {**SPREAD_MINIMO, "ActivityObjectId": "4845, 4835,4845"})

    assert consulta["ActivityObjectId"] == "4845,4835"


def test_id_invalido_en_spread() -> None:
    with pytest.raises(UsageError) as capturado:
        preparar_consulta(SPREAD, {**SPREAD_MINIMO, "ActivityObjectId": "4835,abc"})

    assert capturado.value.motivo is MotivoUso.ID_INVALIDO


# --- get_all (§9) ------------------------------------------------------------------

# Lotes de 2 IDs y pausa de 0,25 s: 5 IDs dan 3 lotes.
PERFIL_LOTES = Profile.desde_toml(
    "demo",
    {
        "host": "https://localhost:7001",
        "database_name": "orcl",
        "username": "admin",
        "id_chunk_size": 2,
        "throttle_seconds": 0.25,
    },
)
PARAMS_LOTES = {"Fields": "ObjectId,Id", "Filter": FILTRO}


class Registro:
    """Pausas pedidas y avisos de progreso recibidos."""

    def __init__(self) -> None:
        self.pausas: list[float] = []
        self.avisos: list[tuple[int, int]] = []

    def dormir(self, segundos: float) -> None:
        self.pausas.append(segundos)

    def avisar(self, hechos: int, total: int) -> None:
        self.avisos.append((hechos, total))


def cliente_lotes(registro: Registro, perfil: Profile = PERFIL_LOTES) -> Cliente:
    return Cliente(Sesion(perfil, CLAVE), dormir=registro.dormir)


def consultas_get(simulado: responses.RequestsMock) -> list[dict[str, str]]:
    return [
        dict(parse_qsl(urlsplit(str(llamada.request.url)).query))
        for llamada in simulado.calls
        if llamada.request.method == "GET"
    ]


def registrar_lotes(simulado: responses.RequestsMock, ruta: str, *respuestas: Simulada) -> None:
    """Login y, en orden, cada respuesta del GET a ``ruta``."""
    simulado.add(LOGIN_OK.respuesta("POST", f"{BASE}/login"))
    for respuesta in respuestas:
        simulado.add(respuesta.respuesta("GET", f"{BASE}{ruta}"))


def ids_simulados(*ids: object) -> Simulada:
    return json_simulado([{"ObjectId": numero} for numero in ids])


def lote(*ids: int) -> Simulada:
    return json_simulado([{"ObjectId": numero, "Id": f"A{numero}"} for numero in ids])


def test_get_all_sondea_ids_y_pide_lotes_por_rango(
    http_simulado: responses.RequestsMock,
) -> None:
    # Desordenados y con un repetido: se ordenan y se agrupan de a 2.
    registrar_lotes(
        http_simulado, "/activity", ids_simulados(5, 1, 3, 2, 4, 3), lote(1, 2), lote(3, 4), lote(5)
    )

    filas = cliente_lotes(Registro()).get_all(ACTIVITY, PARAMS_LOTES)

    assert [fila["ObjectId"] for fila in filas] == [1, 2, 3, 4, 5]
    sondeo, *lotes = consultas_get(http_simulado)
    assert sondeo == {
        "Fields": "ObjectId",
        "Filter": FILTRO,
        "OrderBy": ORDEN_NEUTRO,
        "DatabaseName": "orcl",
    }
    assert [consulta["Filter"] for consulta in lotes] == [
        f"{FILTRO} :and: ObjectId:gte:1 :and: ObjectId:lte:2",
        f"{FILTRO} :and: ObjectId:gte:3 :and: ObjectId:lte:4",
        f"{FILTRO} :and: ObjectId:gte:5 :and: ObjectId:lte:5",
    ]
    assert all(consulta["Fields"] == "ObjectId,Id" for consulta in lotes)
    assert all(consulta["OrderBy"] == ORDEN_NEUTRO for consulta in lotes)
    assert llamadas(http_simulado, "POST", "/login") == 1


def test_get_all_pausa_solo_entre_lotes_y_avisa_el_progreso(
    http_simulado: responses.RequestsMock,
) -> None:
    registrar_lotes(
        http_simulado, "/activity", ids_simulados(1, 2, 3, 4, 5), lote(1, 2), lote(3, 4), lote(5)
    )
    registro = Registro()

    cliente_lotes(registro).get_all(ACTIVITY, PARAMS_LOTES, on_progress=registro.avisar)

    assert registro.pausas == [0.25, 0.25]
    assert registro.avisos == [(0, 3), (1, 3), (2, 3), (3, 3)]


def test_get_all_tamano_de_lote_reemplaza_al_del_perfil(
    http_simulado: responses.RequestsMock,
) -> None:
    registrar_lotes(http_simulado, "/activity", ids_simulados(1, 2, 3, 4, 5), lote(1, 2, 3, 4, 5))
    registro = Registro()

    filas = cliente_lotes(registro).get_all(ACTIVITY, PARAMS_LOTES, tamano_lote=10)

    assert len(filas) == 5
    assert len(consultas_get(http_simulado)) == 2
    assert registro.pausas == []


def test_get_all_sin_ids_no_pide_lotes(http_simulado: responses.RequestsMock) -> None:
    registrar_lotes(http_simulado, "/activity", ids_simulados())
    registro = Registro()

    filas = cliente_lotes(registro).get_all(ACTIVITY, PARAMS_LOTES, on_progress=registro.avisar)

    assert filas == []
    assert len(consultas_get(http_simulado)) == 1
    assert registro.avisos == [(0, 0)]


@pytest.mark.parametrize(
    "fila",
    [{"Id": "A1"}, {"ObjectId": "abc"}, {"ObjectId": 0}, {"ObjectId": True}, "texto"],
    ids=["sin-objectid", "texto", "cero", "booleano", "no-objeto"],
)
def test_get_all_sondeo_con_formato_inesperado(
    http_simulado: responses.RequestsMock, fila: object
) -> None:
    registrar_lotes(http_simulado, "/activity", json_simulado([{"ObjectId": 1}, fila]))

    with pytest.raises(P6HTTPError) as capturado:
        cliente_lotes(Registro()).get_all(ACTIVITY, PARAMS_LOTES)

    assert capturado.value.motivo is MotivoHTTP.FORMATO_INESPERADO
    assert len(consultas_get(http_simulado)) == 1


def test_sondeo_acepta_objectid_como_texto(http_simulado: responses.RequestsMock) -> None:
    registrar_lotes(http_simulado, "/activity", ids_simulados("12", 3))

    assert cliente_lotes(Registro()).ids(ACTIVITY, FILTRO) == [3, 12]


def test_get_all_error_en_un_lote_se_propaga_y_no_sigue(
    http_simulado: responses.RequestsMock,
) -> None:
    registrar_lotes(
        http_simulado,
        "/activity",
        ids_simulados(1, 2, 3, 4, 5),
        lote(1, 2),
        json_simulado({"message": "Request failed."}, 500),
        lote(5),
    )

    with pytest.raises(P6HTTPError) as capturado:
        cliente_lotes(Registro()).get_all(ACTIVITY, PARAMS_LOTES)

    assert capturado.value.motivo is MotivoHTTP.CODIGO_HTTP
    assert capturado.value.datos["codigo"] == "500"
    assert len(consultas_get(http_simulado)) == 3


@pytest.mark.parametrize("filtro", ["", "   "])
def test_get_all_exige_filtro_aunque_el_endpoint_no_sea_grande(
    http_simulado: responses.RequestsMock, filtro: str
) -> None:
    with pytest.raises(GuardrailError) as capturado:
        cliente_lotes(Registro()).get_all(PROJECT, {"Fields": "ObjectId", "Filter": filtro})

    assert capturado.value.motivo is MotivoGuardarrail.SIN_FILTRO_LOTES
    assert capturado.value.datos["endpoint"] == "project"
    assert len(http_simulado.calls) == 0


@pytest.mark.parametrize("operador", [":or:", ":OR:", ":Or:"])
def test_get_all_rechaza_or(http_simulado: responses.RequestsMock, operador: str) -> None:
    filtro = f"ObjectId:eq:1 {operador} ObjectId:eq:2"

    with pytest.raises(UsageError) as capturado:
        cliente_lotes(Registro()).get_all(ACTIVITY, {"Fields": "ObjectId", "Filter": filtro})

    assert capturado.value.motivo is MotivoUso.FILTRO_CON_OR
    assert len(http_simulado.calls) == 0


def test_get_all_no_acepta_order_by(http_simulado: responses.RequestsMock) -> None:
    with pytest.raises(UsageError) as capturado:
        cliente_lotes(Registro()).get_all(ACTIVITY, {**PARAMS_LOTES, "OrderBy": "Name desc"})

    assert capturado.value.motivo is MotivoUso.PARAMETRO_DESCONOCIDO
    assert capturado.value.datos["parametro"] == "OrderBy"
    assert len(http_simulado.calls) == 0


def test_get_all_de_spread_no_se_admite(http_simulado: responses.RequestsMock) -> None:
    with pytest.raises(UsageError) as capturado:
        cliente_lotes(Registro()).get_all(SPREAD, {"Filter": FILTRO})

    assert capturado.value.motivo is MotivoUso.PLANTILLA_NO_SOPORTADA
    assert len(http_simulado.calls) == 0


def test_get_all_mide_la_url_del_peor_lote_antes_del_login(
    http_simulado: responses.RequestsMock,
) -> None:
    # Cabe como consulta simple, pero no con el rango de ObjectId agregado.
    params = _params_con_largo(LARGO_MAXIMO_URL - 20)
    params["Fields"] = "ObjectId"
    validar_consulta(PERFIL, ACTIVITY, params)

    with pytest.raises(UsageError) as capturado:
        validar_lectura_masiva(PERFIL, ACTIVITY, params)

    assert capturado.value.motivo is MotivoUso.URL_DEMASIADO_LARGA
    assert len(http_simulado.calls) == 0


def test_sondeo_admite_or(http_simulado: responses.RequestsMock) -> None:
    # Solo las lecturas por lotes agregan un rango: el sondeo envía el filtro tal cual.
    registrar_lotes(http_simulado, "/activity", ids_simulados(1, 2))
    filtro = "ObjectId:eq:1 :or: ObjectId:eq:2"

    assert cliente_lotes(Registro()).ids(ACTIVITY, filtro) == [1, 2]
    assert consultas_get(http_simulado)[0]["Filter"] == filtro


# --- get_spread (§9) -----------------------------------------------------------------

PARAMS_SPREAD = {
    "ActivityObjectId": "1,2,3,4,5",
    "SpreadField": "PlannedLaborUnits",
    "PeriodType": "month",
}


def spread_de(*ids: int) -> Simulada:
    return json_simulado([{"ActivityObjectId": numero, "Period": []} for numero in ids])


def test_get_spread_trocea_los_ids_y_junta_las_respuestas(
    http_simulado: responses.RequestsMock,
) -> None:
    registrar_lotes(http_simulado, SPREAD.path, spread_de(1, 2), spread_de(3, 4), spread_de(5))

    respuesta = cliente_lotes(Registro()).get_spread(SPREAD, PARAMS_SPREAD)

    assert [objeto["ActivityObjectId"] for objeto in respuesta] == [1, 2, 3, 4, 5]
    lotes = consultas_get(http_simulado)
    assert [consulta["ActivityObjectId"] for consulta in lotes] == ["1,2", "3,4", "5"]
    assert lotes[0] == {
        "ActivityObjectId": "1,2",
        "SpreadField": "PlannedLaborUnits",
        "PeriodType": "Month",
        "IncludeCumulative": "true",
        "DatabaseName": "orcl",
    }


def test_get_spread_pausa_entre_lotes_y_avisa_el_progreso(
    http_simulado: responses.RequestsMock,
) -> None:
    registrar_lotes(http_simulado, SPREAD.path, spread_de(1, 2), spread_de(3, 4), spread_de(5))
    registro = Registro()

    cliente_lotes(registro).get_spread(SPREAD, PARAMS_SPREAD, on_progress=registro.avisar)

    assert registro.pausas == [0.25, 0.25]
    assert registro.avisos == [(0, 3), (1, 3), (2, 3), (3, 3)]


def test_get_spread_tamano_de_lote_reemplaza_al_del_perfil(
    http_simulado: responses.RequestsMock,
) -> None:
    registrar_lotes(http_simulado, SPREAD.path, spread_de(1, 2, 3), spread_de(4, 5))

    cliente_lotes(Registro()).get_spread(SPREAD, PARAMS_SPREAD, tamano_lote=3)

    assert [c["ActivityObjectId"] for c in consultas_get(http_simulado)] == ["1,2,3", "4,5"]


def test_get_spread_url_larga_se_detecta_antes_del_login(
    http_simulado: responses.RequestsMock,
) -> None:
    # 1.000 IDs de 7 dígitos en un solo lote: unos 8.000 caracteres.
    ids = ",".join(str(1_000_000 + numero) for numero in range(1000))

    with pytest.raises(UsageError) as capturado:
        cliente_lotes(Registro()).get_spread(
            SPREAD, {**PARAMS_SPREAD, "ActivityObjectId": ids}, tamano_lote=1000
        )

    assert capturado.value.motivo is MotivoUso.URL_DEMASIADO_LARGA
    assert len(http_simulado.calls) == 0


def test_get_spread_con_lotes_chicos_la_url_cabe() -> None:
    ids = ",".join(str(1_000_000 + numero) for numero in range(1000))

    lotes = validar_spread(PERFIL, SPREAD, {**PARAMS_SPREAD, "ActivityObjectId": ids})

    assert len(lotes) == 5
    assert all(len(url_get(PERFIL, SPREAD.path, c)) <= LARGO_MAXIMO_URL for c in lotes)


def test_get_spread_respuesta_que_no_es_lista(http_simulado: responses.RequestsMock) -> None:
    registrar_lotes(http_simulado, SPREAD.path, json_simulado({"Period": []}))

    with pytest.raises(P6HTTPError) as capturado:
        cliente_lotes(Registro()).get_spread(SPREAD, {**PARAMS_SPREAD, "ActivityObjectId": "1"})

    assert capturado.value.motivo is MotivoHTTP.FORMATO_INESPERADO


def test_get_spread_de_un_entity_no_se_admite(http_simulado: responses.RequestsMock) -> None:
    with pytest.raises(UsageError) as capturado:
        cliente_lotes(Registro()).get_spread(ACTIVITY, PARAMS_SPREAD)

    assert capturado.value.motivo is MotivoUso.NO_ES_SPREAD
    assert len(http_simulado.calls) == 0


# --- filas_por_periodo ---------------------------------------------------------------

RESPUESTA_SPREAD = json.loads(leer_fixture("activity_spread_ok.json"))


def test_filas_por_periodo_con_acumulados() -> None:
    tabla = filas_por_periodo(RESPUESTA_SPREAD, SPREAD, ["PlannedLaborUnits"])

    assert tabla is not None
    columnas, filas = tabla
    assert columnas == [
        "ActivityObjectId",
        "StartDate",
        "EndDate",
        "PlannedLaborUnits",
        "CumulativePlannedLaborUnits",
    ]
    assert len(filas) == 3
    assert filas[1] == {
        "ActivityObjectId": 4835,
        "StartDate": "2026-01-12T00:00:00",
        "EndDate": "2026-01-18T23:59:59",
        "PlannedLaborUnits": 32.0,
        "CumulativePlannedLaborUnits": 72.0,
    }
    assert filas[2]["ActivityObjectId"] == 4845


def test_filas_por_periodo_sin_acumulados_y_con_campo_ausente() -> None:
    respuesta = [
        {"ActivityObjectId": 1, "Period": [{"StartDate": "a", "EndDate": "b", "X": 1}]},
        {"ActivityObjectId": 2},
    ]

    tabla = filas_por_periodo(respuesta, SPREAD, ["X", "Y"])

    assert tabla == (
        ["ActivityObjectId", "StartDate", "EndDate", "X", "Y"],
        [{"ActivityObjectId": 1, "StartDate": "a", "EndDate": "b", "X": 1, "Y": None}],
    )


@pytest.mark.parametrize(
    "respuesta",
    [
        [{"Id": "A1", "Period": []}],
        [{"ActivityObjectId": 1, "Period": {"StartDate": "a"}}],
        [{"ActivityObjectId": 1, "Period": ["a"]}],
    ],
    ids=["sin-objectid", "period-no-lista", "period-sin-objetos"],
)
def test_filas_por_periodo_forma_inesperada(respuesta: list[dict[str, object]]) -> None:
    assert filas_por_periodo(respuesta, SPREAD, ["X"]) is None


def test_sondeo_que_no_es_lista(http_simulado: responses.RequestsMock) -> None:
    registrar_lotes(http_simulado, "/activity", json_simulado({"ObjectId": 1}))

    with pytest.raises(P6HTTPError) as capturado:
        cliente_lotes(Registro()).ids(ACTIVITY, FILTRO)

    assert capturado.value.motivo is MotivoHTTP.FORMATO_INESPERADO


def test_spread_field_fuera_de_la_lista_de_ayuda_se_envia_igual() -> None:
    # La lista de SpreadField es ayuda con ?: quien valida es P6 (400 si no existe).
    consulta = preparar_consulta(SPREAD, {**SPREAD_MINIMO, "SpreadField": "CampoNuevo"})

    assert consulta["SpreadField"] == "CampoNuevo"
