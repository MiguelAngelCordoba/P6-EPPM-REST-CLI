"""Comandos ``p6 endpoints``, ``p6 fields`` y ``p6 get`` (especificación §12 y §13)."""

import json
from urllib.parse import parse_qsl, urlsplit

import pytest
import responses
import typer
from typer.testing import CliRunner, Result

from p6cli.cli import app as modulo_app
from p6cli.cli import messages, render
from p6cli.cli.app import app
from p6cli.core import catalog, profiles, secrets
from p6cli.core.diagnostics import EstadoDiagnostico
from p6cli.core.profiles import Profile, ProfileStore
from p6cli.core.session import token_autenticacion
from tests.conftest import (
    BASE,
    FIELDS_OK,
    LOGIN_DATABASE_INVALIDA,
    LOGIN_OK,
    LOGOUT_OK,
    Simulada,
    leer_fixture,
    llamadas,
)

CLAVE = "ClaveDePrueba1"
BASE_OTRO = "https://p6ws.example.com/p6ws/restapi"
ACTIVIDADES = Simulada(200, "activity_ok.json")
FILTRO = "ProjectObjectId:eq:1234"
FILAS_FIXTURE = json.loads(leer_fixture("activity_ok.json"))

runner = CliRunner()


@pytest.fixture(autouse=True)
def terminal_ancha(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evita que rich recorte o parta columnas en la salida capturada."""
    monkeypatch.setenv("COLUMNS", "300")


def p6(*argumentos: str, entrada: str | None = None) -> Result:
    return runner.invoke(app, list(argumentos), input=entrada)


def crear(nombre: str = "demo", clave: str | None = CLAVE, **cambios: object) -> None:
    datos: dict[str, object] = {
        "host": "https://localhost:7001",
        "database_name": "orcl",
        "username": "admin",
        **cambios,
    }
    perfil = Profile.desde_toml(nombre, datos)
    if clave is None:
        ProfileStore().agregar(perfil)
    else:
        profiles.crear_perfil(ProfileStore(), perfil, clave)


def registrar(
    simulado: responses.RequestsMock,
    ruta: str,
    respuesta: Simulada,
    *,
    login: Simulada = LOGIN_OK,
    base: str = BASE,
) -> None:
    simulado.add(login.respuesta("POST", f"{base}/login"))
    simulado.add(respuesta.respuesta("GET", f"{base}{ruta}"))
    simulado.add(LOGOUT_OK.respuesta("POST", f"{base}/logout"))


def json_simulado(datos: object, codigo: int = 200) -> Simulada:
    return Simulada(codigo, cuerpo=json.dumps(datos), content_type="application/json")


def consulta_enviada(simulado: responses.RequestsMock) -> dict[str, str]:
    peticion = next(c.request for c in simulado.calls if c.request.method == "GET")
    return dict(parse_qsl(urlsplit(str(peticion.url)).query))


def get_actividades(*extra: str, entrada: str | None = None) -> Result:
    return p6(
        "get",
        "activity",
        "--fields",
        "ObjectId,Id,Name",
        "--filter",
        FILTRO,
        *extra,
        entrada=entrada,
    )


# --- endpoints ---------------------------------------------------------------------


def test_endpoints_lista_todo_el_catalogo() -> None:
    resultado = p6("endpoints")

    assert resultado.exit_code == 0, resultado.output
    for grupo in catalog.grupos():
        assert messages.TITULO_GRUPO.format(grupo=grupo) in resultado.output
    assert messages.COLUMNA_TASKS in resultado.output
    assert messages.COLUMNA_NAME in resultado.output
    for endpoint in catalog.CATALOGO:
        assert endpoint.key in resultado.output
        assert endpoint.doc_name in resultado.output
        assert endpoint.path in resultado.output


def test_endpoints_no_recorta_clave_nombre_ni_ruta_a_120_columnas() -> None:
    resultado = runner.invoke(app, ["endpoints"], env={"COLUMNS": "120"})

    assert "…" not in resultado.output
    for endpoint in catalog.CATALOGO:
        assert endpoint.key in resultado.output
        assert endpoint.doc_name in resultado.output
        assert endpoint.path in resultado.output


def test_endpoints_filtra_por_grupo_sin_distinguir_mayusculas() -> None:
    resultado = p6("endpoints", "--group", "proyectos")

    assert resultado.exit_code == 0, resultado.output
    for clave in ("project", "eps", "wbs"):
        assert f"/{clave}" in resultado.output
    assert "/activity" not in resultado.output
    assert "/spread" not in resultado.output


def test_endpoints_grupo_inexistente_sale_con_2() -> None:
    resultado = p6("endpoints", "--group", "Nada")

    assert resultado.exit_code == 2
    assert "Nada" in resultado.output
    assert "Series temporales" in resultado.output


# --- syntax ------------------------------------------------------------------------


def test_syntax_sin_tema_lista_los_temas(http_simulado: responses.RequestsMock) -> None:
    resultado = p6("syntax")

    assert resultado.exit_code == 0, resultado.output
    for tema, guia in messages.GUIAS_SINTAXIS.items():
        assert tema in resultado.output
        assert guia.resumen in resultado.output
    assert len(http_simulado.calls) == 0


def test_syntax_filter_muestra_operadores_y_referencia(
    http_simulado: responses.RequestsMock,
) -> None:
    resultado = p6("syntax", "filter")

    assert resultado.exit_code == 0, resultado.output
    for operador in (
        ":eq:",
        "!=",
        ":gt:",
        ":gte:",
        ":lt:",
        ":lte:",
        ":like:",
        "IN(",
        ":and:",
        ":or:",
    ):
        assert operador in resultado.output
    assert "Status:eq:'Not Started'" in resultado.output
    assert "Name :like: '%act%'" in resultado.output
    assert messages.GUIAS_SINTAXIS["filter"].referencia in resultado.output
    assert len(http_simulado.calls) == 0


def test_syntax_ejemplos_en_una_sola_linea() -> None:
    resultado = runner.invoke(app, ["syntax", "filter"], env={"COLUMNS": "80"})

    for ejemplo in messages.GUIAS_SINTAXIS["filter"].ejemplos:
        assert ejemplo in resultado.output


@pytest.mark.parametrize("tema", ["order-by", "fields", "FILTER"])
def test_syntax_otros_temas(tema: str) -> None:
    resultado = p6("syntax", tema)

    assert resultado.exit_code == 0, resultado.output
    guia = messages.GUIAS_SINTAXIS[tema.lower()]
    assert guia.titulo in resultado.output
    assert guia.referencia in resultado.output


def test_syntax_tema_inexistente_sale_con_2() -> None:
    resultado = p6("syntax", "nada")

    assert resultado.exit_code == 2
    assert "«nada»" in resultado.output
    assert "filter, order-by, fields" in resultado.output


def test_ayuda_de_get_menciona_la_guia() -> None:
    resultado = p6("get", "--help")

    assert "p6 syntax filter" in resultado.output
    assert "p6 syntax order-by" in resultado.output


def test_pista_400_menciona_la_guia() -> None:
    assert "p6 syntax filter" in messages.PISTAS_HTTP[400]


# --- fields ------------------------------------------------------------------------


def test_fields_muestra_los_campos(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar(http_simulado, "/project/fields", FIELDS_OK)

    resultado = p6("fields", "project")

    assert resultado.exit_code == 0, resultado.output
    for campo in leer_fixture("project_fields.txt").split(","):
        assert campo in resultado.output
    assert llamadas(http_simulado, "POST", "/logout") == 1


def test_fields_de_spread_sale_con_2(http_simulado: responses.RequestsMock) -> None:
    crear()

    resultado = p6("fields", "spread.activity")

    assert resultado.exit_code == 2
    assert "p6 spread" in resultado.output
    assert len(http_simulado.calls) == 0


def test_endpoint_desconocido_sale_con_2_sin_peticiones(
    http_simulado: responses.RequestsMock,
) -> None:
    crear()

    for argumentos in (("fields", "actividad"), ("get", "actividad", "--fields", "ObjectId")):
        resultado = p6(*argumentos)
        assert resultado.exit_code == 2
        assert "p6 endpoints" in resultado.output
    assert len(http_simulado.calls) == 0


# --- get: tabla --------------------------------------------------------------------


def test_get_tabla_con_encabezado_y_25_filas(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar(http_simulado, "/activity", ACTIVIDADES)

    resultado = get_actividades()

    assert resultado.exit_code == 0, resultado.output
    assert "activity · 30 filas · " in resultado.output
    assert "1025" in resultado.output
    assert "1026" not in resultado.output
    assert "Mostrando 25 de 30 filas" in resultado.output


def test_get_columnas_en_el_orden_de_fields(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar(http_simulado, "/activity", ACTIVIDADES)

    resultado = p6("get", "activity", "--fields", "Status,Name,ObjectId", "--filter", FILTRO)

    assert resultado.exit_code == 0, resultado.output
    salida = resultado.output
    assert salida.index("Status") < salida.index("Name") < salida.index("ObjectId")
    assert "A1000" not in salida  # Id no se pidió


@pytest.mark.parametrize(
    ("max_rows", "visible", "oculto"), [("3", "1003", "1004"), ("0", "1029", None)]
)
def test_get_max_rows(
    http_simulado: responses.RequestsMock, max_rows: str, visible: str, oculto: str | None
) -> None:
    crear()
    registrar(http_simulado, "/activity", ACTIVIDADES)

    resultado = get_actividades("--max-rows", max_rows)

    assert resultado.exit_code == 0, resultado.output
    assert visible in resultado.output
    if oculto is not None:
        assert oculto not in resultado.output
    else:
        assert "Mostrando" not in resultado.output


def test_get_max_rows_negativo_sale_con_2() -> None:
    crear()

    assert get_actividades("--max-rows", "-1").exit_code == 2


def test_get_celdas_recortadas_y_anidados_como_json(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar(http_simulado, "/activity", ACTIVIDADES)

    resultado = p6("get", "activity", "--fields", "Name,Codigos", "--filter", FILTRO)

    nombre_largo = FILAS_FIXTURE[0]["Name"]
    assert nombre_largo not in resultado.output
    assert nombre_largo[: render.LARGO_CELDA - 1] + "…" in resultado.output
    assert '[{"Tipo": "Fase", "Valor": "Diseño"}]' in resultado.output


def test_get_no_interpreta_marcado(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar(http_simulado, "/project", json_simulado([{"Name": "[bold]hola[/bold]"}]))

    resultado = p6("get", "project", "--fields", "Name")

    assert "[bold]hola[/bold]" in resultado.output


def test_get_sin_resultados(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar(http_simulado, "/project", json_simulado([]))

    resultado = p6("get", "project", "--fields", "ObjectId")

    assert resultado.exit_code == 0, resultado.output
    assert "project · 0 filas" in resultado.output
    assert messages.SIN_RESULTADOS in resultado.output


# --- get: JSON ---------------------------------------------------------------------


def test_get_json_completo_y_stdout_limpio(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar(http_simulado, "/activity", ACTIVIDADES)

    resultado = get_actividades("--json", "--max-rows", "3")

    assert resultado.exit_code == 0, resultado.output
    assert json.loads(resultado.stdout) == FILAS_FIXTURE
    assert '  "ObjectId": 1001' in resultado.stdout
    assert "Diseño" in resultado.stdout  # ensure_ascii=False


def test_get_json_sin_clave_pide_la_clave_por_stderr(http_simulado: responses.RequestsMock) -> None:
    crear(clave=None)
    registrar(http_simulado, "/activity", ACTIVIDADES)

    resultado = get_actividades("--json", entrada=f"{CLAVE}\n")

    assert resultado.exit_code == 0, resultado.output
    assert json.loads(resultado.stdout) == FILAS_FIXTURE
    assert messages.AVISO_CLAVE_NO_GUARDADA_CONSULTA.format(nombre="demo") in resultado.stderr


# --- get: validación y guardarraíl ---------------------------------------------------


def test_get_sin_fields_sale_con_2(http_simulado: responses.RequestsMock) -> None:
    crear()

    resultado = p6("get", "project")

    assert resultado.exit_code == 2
    assert len(http_simulado.calls) == 0


def test_get_fields_vacio_sale_con_2(http_simulado: responses.RequestsMock) -> None:
    crear()

    resultado = p6("get", "project", "--fields", " , ")

    assert resultado.exit_code == 2
    assert "Se necesita al menos un campo en Fields." in resultado.output
    assert len(http_simulado.calls) == 0


def test_get_campo_invalido_sale_con_2() -> None:
    crear()

    resultado = p6("get", "project", "--fields", "ObjectId,1Id")

    assert resultado.exit_code == 2
    assert "«1Id»" in resultado.output


def test_get_large_sin_filtro_sale_con_3_sin_peticiones(
    http_simulado: responses.RequestsMock,
) -> None:
    crear(clave=None)

    resultado = p6("get", "activity", "--fields", "ObjectId")

    assert resultado.exit_code == 3
    assert "--allow-unfiltered" in resultado.output
    # Se valida antes de pedir la clave y de hacer login.
    assert messages.PEDIR_CLAVE_TEMPORAL not in resultado.output
    assert len(http_simulado.calls) == 0


def test_get_allow_unfiltered_envia_filtro_neutro(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar(http_simulado, "/activity", ACTIVIDADES)

    resultado = p6("get", "activity", "--fields", "ObjectId", "--allow-unfiltered")

    assert resultado.exit_code == 0, resultado.output
    assert consulta_enviada(http_simulado)["Filter"] == "ObjectId:gte:0"


def test_get_envia_filter_y_order_by(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar(http_simulado, "/activity", ACTIVIDADES)

    get_actividades("--order-by", "Name desc")

    assert consulta_enviada(http_simulado) == {
        "Fields": "ObjectId,Id,Name",
        "Filter": FILTRO,
        "OrderBy": "Name desc",
        "DatabaseName": "orcl",
    }


def test_get_de_spread_sale_con_2() -> None:
    crear()

    resultado = p6("get", "spread.activity", "--fields", "ObjectId")

    assert resultado.exit_code == 2
    assert "p6 spread" in resultado.output


# --- get: errores de P6 ------------------------------------------------------------


def test_get_400_sale_con_1_con_pista_y_mensaje(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar(http_simulado, "/project", json_simulado({"message": "Invalid field Nombre"}, 400))

    resultado = p6("get", "project", "--fields", "Nombre")

    assert resultado.exit_code == 1
    assert "400" in resultado.output
    assert "Invalid field Nombre" in resultado.output
    assert messages.PISTAS_HTTP[400] in resultado.output
    assert llamadas(http_simulado, "POST", "/logout") == 1


def test_get_codigo_sin_pista_sale_con_1(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar(http_simulado, "/project", json_simulado({"message": "Conflict"}, 409))

    resultado = p6("get", "project", "--fields", "ObjectId")

    assert resultado.exit_code == 1
    assert "409" in resultado.output
    assert "Pista:" not in resultado.output


def test_get_200_html_sale_con_1(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar(http_simulado, "/project", Simulada(200, cuerpo="<html/>", content_type="text/html"))

    resultado = p6("get", "project", "--fields", "ObjectId")

    assert resultado.exit_code == 1
    assert "proxy" in resultado.output


def test_get_login_fallido_sale_con_1_con_diagnostico(
    http_simulado: responses.RequestsMock,
) -> None:
    crear()
    registrar(http_simulado, "/project", json_simulado([]), login=LOGIN_DATABASE_INVALIDA)

    resultado = p6("get", "project", "--fields", "ObjectId")

    assert resultado.exit_code == 1
    mensaje, sugerencia = messages.DIAGNOSTICO[EstadoDiagnostico.INVALID_DATABASE]
    assert mensaje in resultado.output
    assert sugerencia in resultado.output
    assert messages.SUGERENCIA_DOCTOR.format(perfil="demo") in resultado.output
    assert llamadas(http_simulado, "POST", "/login") == 1
    assert llamadas(http_simulado, "GET", "/project") == 0
    assert llamadas(http_simulado, "POST", "/logout") == 0


# --- get: perfil y clave -----------------------------------------------------------


def test_get_sin_clave_la_pide_y_no_la_guarda(http_simulado: responses.RequestsMock) -> None:
    crear(clave=None)
    registrar(http_simulado, "/project", json_simulado([]))

    resultado = p6("get", "project", "--fields", "ObjectId", entrada=f"{CLAVE}\n")

    assert resultado.exit_code == 0, resultado.output
    assert http_simulado.calls[0].request.headers["password"] == CLAVE
    assert secrets.leer_clave("demo") is None


def test_get_usa_env(http_simulado: responses.RequestsMock) -> None:
    crear("demo")
    crear("otro", host="https://p6ws.example.com")
    registrar(http_simulado, "/project", json_simulado([]), base=BASE_OTRO)

    resultado = p6("get", "project", "--fields", "ObjectId", "--env", "otro")

    assert resultado.exit_code == 0, resultado.output
    assert llamadas(http_simulado, "GET", "/project") == 1


def test_get_usa_el_predeterminado(http_simulado: responses.RequestsMock) -> None:
    crear("demo")
    crear("otro", host="https://p6ws.example.com")
    ProfileStore().marcar_predeterminado("otro")
    registrar(http_simulado, "/project", json_simulado([]), base=BASE_OTRO)

    resultado = p6("get", "project", "--fields", "ObjectId")

    assert resultado.exit_code == 0, resultado.output


def test_get_sin_perfiles_sale_con_2() -> None:
    resultado = p6("get", "project", "--fields", "ObjectId")

    assert resultado.exit_code == 2
    assert "No hay perfil predeterminado" in resultado.output


def test_get_env_inexistente_sale_con_2() -> None:
    crear()

    resultado = p6("get", "project", "--fields", "ObjectId", "--env", "nada")

    assert resultado.exit_code == 2
    assert "nada" in resultado.output


def test_get_hace_logout_al_terminar(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar(http_simulado, "/activity", ACTIVIDADES)

    get_actividades()

    assert llamadas(http_simulado, "POST", "/login") == 1
    assert llamadas(http_simulado, "POST", "/logout") == 1
    assert http_simulado.calls[-1].request.method == "POST"


@pytest.mark.parametrize(
    "respuesta",
    [ACTIVIDADES, json_simulado({"message": "Bad"}, 400)],
    ids=["ok", "error-400"],
)
def test_la_clave_nunca_aparece_en_la_salida(
    http_simulado: responses.RequestsMock, respuesta: Simulada
) -> None:
    crear()
    registrar(http_simulado, "/activity", respuesta)

    resultado = get_actividades()

    assert CLAVE not in resultado.output
    assert token_autenticacion("admin", CLAVE) not in resultado.output


# --- Interrupción (§12: código 130) ------------------------------------------------


def test_ctrl_c_durante_la_consulta_sale_con_130(
    http_simulado: responses.RequestsMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    crear()
    registrar(http_simulado, "/activity", ACTIVIDADES)

    def interrumpir(*_: object, **__: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(modulo_app.Cliente, "get", interrumpir)

    resultado = get_actividades()

    assert resultado.exit_code == 130
    assert messages.ABORTADO in resultado.output


def test_ctrl_c_en_una_pregunta_sale_con_130(monkeypatch: pytest.MonkeyPatch) -> None:
    crear(clave=None)

    def abortar(*_: object, **__: object) -> str:
        raise typer.Abort

    monkeypatch.setattr(modulo_app, "_pedir_oculto", abortar)

    resultado = get_actividades()

    assert resultado.exit_code == 130
    assert messages.ABORTADO in resultado.output


def test_profiles_add_interrumpido_sale_con_130() -> None:
    resultado = runner.invoke(app, ["profiles", "add"], input="")

    assert resultado.exit_code == 130
    assert messages.ABORTADO in resultado.output


# --- Formato de la salida -----------------------------------------------------------


def test_encabezado_con_separadores_en_espanol() -> None:
    assert render.encabezado_resultados("activity", 1284, 3.24) == "activity · 1.284 filas · 3,2 s"
    assert render.encabezado_resultados("project", 1, 0.04) == "project · 1 fila · 0,0 s"


@pytest.mark.parametrize(
    ("valor", "texto"),
    [
        (None, ""),
        ("Diseño", "Diseño"),
        (12, "12"),
        (1.5, "1.5"),
        (True, "true"),
        ({"a": "ñ"}, '{"a": "ñ"}'),
        ("linea1\nlinea2", "linea1 linea2"),
        ("x" * 41, "x" * 39 + "…"),
        ("x" * 40, "x" * 40),
    ],
)
def test_texto_celda(valor: object, texto: str) -> None:
    assert render.texto_celda(valor) == texto
