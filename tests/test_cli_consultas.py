"""Comandos ``p6 endpoints``, ``p6 fields`` y ``p6 get`` (especificación §12 y §13)."""

import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest
import responses
import typer
from typer.testing import CliRunner, Result

from p6cli.cli import app as modulo_app
from p6cli.cli import messages, render
from p6cli.cli.app import app
from p6cli.cli.prompter import PrompterTexto
from p6cli.core import catalog, profiles, secrets
from p6cli.core.diagnostics import EstadoDiagnostico
from p6cli.core.errors import MotivoUso
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

    monkeypatch.setattr(PrompterTexto, "password", abortar)

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


# --- get-all -----------------------------------------------------------------------


def crear_lotes() -> None:
    """Perfil con lotes de 2 IDs y sin pausa, para no esperar en los tests."""
    crear(id_chunk_size=2, throttle_seconds=0)


def registrar_respuestas(
    simulado: responses.RequestsMock, ruta: str, *respuestas: Simulada
) -> None:
    """Login, logout y, en orden, cada respuesta del GET a ``ruta``."""
    simulado.add(LOGIN_OK.respuesta("POST", f"{BASE}/login"))
    simulado.add(LOGOUT_OK.respuesta("POST", f"{BASE}/logout"))
    for respuesta in respuestas:
        simulado.add(respuesta.respuesta("GET", f"{BASE}{ruta}"))


def consultas_get(simulado: responses.RequestsMock) -> list[dict[str, str]]:
    return [
        dict(parse_qsl(urlsplit(str(c.request.url)).query))
        for c in simulado.calls
        if c.request.method == "GET"
    ]


def filas_actividad(*ids: int) -> Simulada:
    return json_simulado([{"ObjectId": numero, "Id": f"A{numero}"} for numero in ids])


def registrar_get_all(simulado: responses.RequestsMock) -> None:
    """Sondeo con 3 IDs y sus 2 lotes."""
    sondeo = json_simulado([{"ObjectId": numero} for numero in (1003, 1001, 1002)])
    registrar_respuestas(
        simulado, "/activity", sondeo, filas_actividad(1001, 1002), filas_actividad(1003)
    )


def get_all_actividades(*extra: str) -> Result:
    return p6("get-all", "activity", "--fields", "ObjectId,Id", "--filter", FILTRO, *extra)


def test_get_all_tabla_con_todas_las_filas_de_los_lotes(
    http_simulado: responses.RequestsMock,
) -> None:
    crear_lotes()
    registrar_get_all(http_simulado)

    resultado = get_all_actividades()

    assert resultado.exit_code == 0, resultado.output
    assert "activity · 3 filas · " in resultado.stdout
    for id_actividad in ("A1001", "A1002", "A1003"):
        assert id_actividad in resultado.stdout
    filtros = [consulta["Filter"] for consulta in consultas_get(http_simulado)]
    assert filtros == [
        FILTRO,
        f"{FILTRO} :and: ObjectId:gte:1001 :and: ObjectId:lte:1002",
        f"{FILTRO} :and: ObjectId:gte:1003 :and: ObjectId:lte:1003",
    ]
    assert llamadas(http_simulado, "POST", "/logout") == 1


def test_get_all_json_con_stdout_limpio(http_simulado: responses.RequestsMock) -> None:
    crear_lotes()
    registrar_get_all(http_simulado)

    resultado = get_all_actividades("--json")

    assert resultado.exit_code == 0, resultado.output
    assert json.loads(resultado.stdout) == [
        {"ObjectId": 1001, "Id": "A1001"},
        {"ObjectId": 1002, "Id": "A1002"},
        {"ObjectId": 1003, "Id": "A1003"},
    ]


def test_get_all_max_rows(http_simulado: responses.RequestsMock) -> None:
    crear_lotes()
    registrar_get_all(http_simulado)

    resultado = get_all_actividades("--max-rows", "2")

    assert "A1002" in resultado.stdout
    assert "A1003" not in resultado.stdout
    assert "Mostrando 2 de 3 filas" in resultado.stdout


def test_get_all_chunk_reemplaza_el_tamano_del_perfil(
    http_simulado: responses.RequestsMock,
) -> None:
    crear_lotes()
    sondeo = json_simulado([{"ObjectId": numero} for numero in (1001, 1002, 1003)])
    registrar_respuestas(http_simulado, "/activity", sondeo, filas_actividad(1001, 1002, 1003))

    resultado = get_all_actividades("--chunk", "5")

    assert resultado.exit_code == 0, resultado.output
    assert len(consultas_get(http_simulado)) == 2


@pytest.mark.parametrize("chunk", ["0", "-3"])
def test_get_all_chunk_menor_que_1_sale_con_2(chunk: str) -> None:
    crear_lotes()

    assert get_all_actividades("--chunk", chunk).exit_code == 2


def test_get_all_sin_filter_sale_con_2() -> None:
    crear_lotes()

    resultado = p6("get-all", "activity", "--fields", "ObjectId")

    assert resultado.exit_code == 2


def test_get_all_filtro_vacio_sale_con_3_sin_pedir_la_clave(
    http_simulado: responses.RequestsMock,
) -> None:
    crear_lotes()
    secrets.borrar_clave("demo")

    resultado = p6("get-all", "project", "--fields", "ObjectId", "--filter", " ")

    assert resultado.exit_code == 3
    assert "--filter" in resultado.output
    assert "--allow-unfiltered" not in resultado.output
    assert messages.PEDIR_CLAVE_TEMPORAL not in resultado.output
    assert len(http_simulado.calls) == 0


def test_get_all_con_or_sale_con_2(http_simulado: responses.RequestsMock) -> None:
    crear_lotes()

    resultado = p6(
        "get-all", "activity", "--fields", "ObjectId", "--filter", "Id:eq:'A' :or: Id:eq:'B'"
    )

    assert resultado.exit_code == 2
    assert ":or:" in resultado.output
    assert len(http_simulado.calls) == 0


def test_get_all_de_spread_sale_con_2() -> None:
    crear_lotes()

    resultado = p6("get-all", "spread.activity", "--fields", "ObjectId", "--filter", FILTRO)

    assert resultado.exit_code == 2
    assert "p6 spread" in resultado.output


def test_get_all_error_de_p6_sale_con_1(http_simulado: responses.RequestsMock) -> None:
    crear_lotes()
    registrar_respuestas(
        http_simulado, "/activity", json_simulado({"message": "Request failed."}, 500)
    )

    resultado = get_all_actividades()

    assert resultado.exit_code == 1
    assert messages.PISTAS_HTTP[500] in resultado.output
    assert llamadas(http_simulado, "POST", "/logout") == 1


# --- spread ------------------------------------------------------------------------

SPREAD_OK = Simulada(200, "activity_spread_ok.json")


def spread_actividades(*extra: str) -> Result:
    return p6("spread", "spread.activity", "--spread-fields", "PlannedLaborUnits", *extra)


def test_spread_con_ids_muestra_la_tabla_por_periodo(
    http_simulado: responses.RequestsMock,
) -> None:
    crear_lotes()
    registrar_respuestas(http_simulado, "/spread/activitySpread", SPREAD_OK)

    resultado = spread_actividades("--ids", "4835,4845", "--max-rows", "0")

    assert resultado.exit_code == 0, resultado.output
    salida = resultado.stdout
    assert "spread.activity · 2 objetos · 3 períodos · " in salida
    assert "CumulativePlannedLaborUnits" in salida
    assert "2026-01-12T00:00:00" in salida
    assert "72.0" in salida
    assert consultas_get(http_simulado) == [
        {
            "ActivityObjectId": "4835,4845",
            "SpreadField": "PlannedLaborUnits",
            "PeriodType": "Week",
            "IncludeCumulative": "true",
            "DatabaseName": "orcl",
        }
    ]
    assert llamadas(http_simulado, "POST", "/logout") == 1


def test_spread_trocea_los_ids_segun_el_perfil(http_simulado: responses.RequestsMock) -> None:
    crear_lotes()
    vacio = json_simulado([])
    registrar_respuestas(http_simulado, "/spread/activitySpread", vacio, vacio)

    resultado = spread_actividades("--ids", "1,2,3", "--json")

    assert resultado.exit_code == 0, resultado.output
    assert [c["ActivityObjectId"] for c in consultas_get(http_simulado)] == ["1,2", "3"]


def test_spread_con_ids_desde_un_csv(http_simulado: responses.RequestsMock, tmp_path: Path) -> None:
    crear_lotes()
    registrar_respuestas(http_simulado, "/spread/activitySpread", SPREAD_OK)
    archivo = tmp_path / "actividades.csv"
    archivo.write_text("ObjectId;Id\n4835;A1000\n4845;A1010\n", encoding="utf-8-sig")

    resultado = spread_actividades("--ids-from", str(archivo))

    assert resultado.exit_code == 0, resultado.output
    assert consultas_get(http_simulado)[0]["ActivityObjectId"] == "4835,4845"


def test_spread_archivo_sin_columna_sale_con_2(
    http_simulado: responses.RequestsMock, tmp_path: Path
) -> None:
    crear_lotes()
    archivo = tmp_path / "actividades.csv"
    archivo.write_text("Id\nA1000\n", encoding="utf-8")

    resultado = spread_actividades("--ids-from", str(archivo))

    assert resultado.exit_code == 2
    assert "ObjectId" in resultado.output
    assert len(http_simulado.calls) == 0


@pytest.mark.parametrize(
    "opciones", [(), ("--ids", "1", "--ids-from", "ids.csv")], ids=["ninguna", "ambas"]
)
def test_spread_exige_ids_o_ids_from(
    http_simulado: responses.RequestsMock, opciones: tuple[str, ...]
) -> None:
    crear_lotes()

    resultado = spread_actividades(*opciones)

    assert resultado.exit_code == 2
    assert "--ids-from" in resultado.output
    assert len(http_simulado.calls) == 0


def test_spread_envia_periodo_fechas_y_sin_acumulados(
    http_simulado: responses.RequestsMock,
) -> None:
    crear_lotes()
    registrar_respuestas(http_simulado, "/spread/activitySpread", json_simulado([]))

    resultado = spread_actividades(
        "--ids",
        "4835",
        "--period",
        "month",
        "--start",
        "2026-01-01",
        "--end",
        "2026-03-31",
        "--no-cumulative",
    )

    assert resultado.exit_code == 0, resultado.output
    assert consultas_get(http_simulado)[0] == {
        "ActivityObjectId": "4835",
        "SpreadField": "PlannedLaborUnits",
        "PeriodType": "Month",
        "StartDate": "2026-01-01T00:00:00",
        "EndDate": "2026-03-31T00:00:00",
        "IncludeCumulative": "false",
        "DatabaseName": "orcl",
    }


@pytest.mark.parametrize(
    "opciones",
    [
        ("--period", "Weekly"),
        ("--start", "05/01/2026"),
        ("--start", "2026-02-01", "--end", "2026-01-01"),
        ("--ids", "abc"),
    ],
    ids=["periodo", "fecha", "rango", "id"],
)
def test_spread_parametro_invalido_sale_con_2_sin_pedir_la_clave(
    http_simulado: responses.RequestsMock, opciones: tuple[str, ...]
) -> None:
    crear_lotes()
    secrets.borrar_clave("demo")
    extra = opciones if "--ids" in opciones else ("--ids", "4835", *opciones)

    resultado = spread_actividades(*extra)

    assert resultado.exit_code == 2
    assert messages.PEDIR_CLAVE_TEMPORAL not in resultado.output
    assert len(http_simulado.calls) == 0


def test_spread_json_imprime_la_respuesta_tal_cual(
    http_simulado: responses.RequestsMock,
) -> None:
    crear_lotes()
    registrar_respuestas(http_simulado, "/spread/activitySpread", SPREAD_OK)

    resultado = spread_actividades("--ids", "4835,4845", "--json")

    assert resultado.exit_code == 0, resultado.output
    assert json.loads(resultado.stdout) == json.loads(leer_fixture("activity_spread_ok.json"))


def test_spread_forma_inesperada_avisa_y_sale_con_0(
    http_simulado: responses.RequestsMock,
) -> None:
    crear_lotes()
    registrar_respuestas(
        http_simulado, "/spread/activitySpread", json_simulado([{"Otra": "forma"}])
    )

    resultado = spread_actividades("--ids", "4835")

    assert resultado.exit_code == 0, resultado.output
    assert "spread.activity · 1 fila · " in resultado.stdout
    assert messages.AVISO_SPREAD_SIN_TABLA in resultado.stderr


def test_spread_de_un_entity_sale_con_2() -> None:
    crear_lotes()

    resultado = p6("spread", "activity", "--spread-fields", "X", "--ids", "1")

    assert resultado.exit_code == 2
    assert "p6 get" in resultado.output


def test_spread_400_sale_con_1_con_pista(http_simulado: responses.RequestsMock) -> None:
    crear_lotes()
    registrar_respuestas(
        http_simulado,
        "/spread/activitySpread",
        json_simulado({"message": "Invalid SpreadField"}, 400),
    )

    resultado = spread_actividades("--ids", "4835")

    assert resultado.exit_code == 1
    assert "Invalid SpreadField" in resultado.output
    assert messages.PISTAS_HTTP[400] in resultado.output
    assert llamadas(http_simulado, "POST", "/logout") == 1


def test_spread_login_fallido_sale_con_1(http_simulado: responses.RequestsMock) -> None:
    crear_lotes()
    http_simulado.add(LOGIN_DATABASE_INVALIDA.respuesta("POST", f"{BASE}/login"))

    resultado = spread_actividades("--ids", "4835")

    assert resultado.exit_code == 1
    assert "p6 doctor demo" in resultado.output
    assert llamadas(http_simulado, "POST", "/login") == 1


@pytest.mark.parametrize(
    ("comando", "opciones"),
    [
        ("get-all", ["--fields", "--filter", "--chunk", "--max-rows", "--json"]),
        (
            "spread",
            ["--ids", "--ids-from", "--spread-fields", "--period", "--start", "--end"],
        ),
    ],
)
def test_ayuda_de_los_comandos_por_lotes(comando: str, opciones: list[str]) -> None:
    resultado = p6(comando, "--help")

    assert resultado.exit_code == 0, resultado.output
    # En GitHub Actions, Typer fuerza colores en la ayuda: se quitan antes de comparar.
    ayuda = re.sub(r"\x1b\[[0-9;]*m", "", resultado.output)
    for opcion in opciones:
        assert opcion in ayuda


# --- --output (§13) -------------------------------------------------------------------


def exportado(ruta: Path, cantidad: str) -> str:
    return messages.EXPORTADO.format(ruta=ruta, cantidad=cantidad, unidad="filas")


@pytest.mark.parametrize("comando", ["get", "get-all", "spread"])
def test_ayuda_menciona_output(comando: str) -> None:
    ayuda = re.sub(r"\x1b\[[0-9;]*m", "", p6(comando, "--help").output)

    assert "--output" in ayuda


def test_get_output_csv_escribe_el_archivo_sin_tabla(
    http_simulado: responses.RequestsMock, tmp_path: Path
) -> None:
    crear()
    registrar(http_simulado, "/activity", ACTIVIDADES)
    ruta = tmp_path / "salida" / "actividades.csv"

    resultado = get_actividades("--output", str(ruta))

    assert resultado.exit_code == 0, resultado.output
    assert f"activity · {len(FILAS_FIXTURE)} filas · " in resultado.stdout
    assert exportado(ruta, str(len(FILAS_FIXTURE))) in resultado.stdout
    assert "A1010" not in resultado.stdout  # sin tabla
    lineas = ruta.read_text(encoding="utf-8-sig").splitlines()
    assert lineas[0] == "ObjectId,Id,Name"
    assert len(lineas) == len(FILAS_FIXTURE) + 1
    assert llamadas(http_simulado, "POST", "/logout") == 1


def test_get_output_json_con_la_lista_completa(
    http_simulado: responses.RequestsMock, tmp_path: Path
) -> None:
    crear()
    registrar(http_simulado, "/activity", ACTIVIDADES)
    ruta = tmp_path / "actividades.JSON"

    resultado = get_actividades("--output", str(ruta))

    assert resultado.exit_code == 0, resultado.output
    assert json.loads(ruta.read_text(encoding="utf-8")) == FILAS_FIXTURE


@pytest.mark.parametrize(
    "extra",
    [["--output", "actividades.xlsx"], ["--output", "actividades.csv", "--json"]],
)
def test_get_output_invalido_sale_con_2_sin_pedir_la_clave(
    http_simulado: responses.RequestsMock, tmp_path: Path, extra: list[str]
) -> None:
    crear(clave=None)
    destino = tmp_path / "salida"
    extra = [str(destino / valor) if valor.startswith("actividades") else valor for valor in extra]

    resultado = get_actividades(*extra)

    assert resultado.exit_code == 2
    assert messages.PEDIR_CLAVE_TEMPORAL not in resultado.output
    assert len(http_simulado.calls) == 0
    assert not destino.exists()


def test_get_output_con_json_explica_el_conflicto(tmp_path: Path) -> None:
    crear()

    resultado = get_actividades("--json", "--output", str(tmp_path / "a.csv"))

    assert resultado.exit_code == 2
    assert messages.ERRORES[MotivoUso.JSON_CON_OUTPUT] in resultado.stderr


def test_get_output_existente_agrega_sufijo(
    http_simulado: responses.RequestsMock, tmp_path: Path
) -> None:
    crear()
    registrar(http_simulado, "/activity", ACTIVIDADES)
    ruta = tmp_path / "actividades.csv"
    ruta.write_text("original", encoding="utf-8")

    resultado = get_actividades("--output", str(ruta))

    assert resultado.exit_code == 0, resultado.output
    nueva = tmp_path / "actividades_2.csv"
    assert exportado(nueva, str(len(FILAS_FIXTURE))) in resultado.stdout
    assert ruta.read_text(encoding="utf-8") == "original"
    assert nueva.exists()


def test_get_output_no_escribible_sale_con_2(
    http_simulado: responses.RequestsMock, tmp_path: Path
) -> None:
    crear()
    registrar(http_simulado, "/activity", ACTIVIDADES)
    (tmp_path / "archivo").write_text("", encoding="utf-8")

    resultado = get_actividades("--output", str(tmp_path / "archivo" / "a.csv"))

    assert resultado.exit_code == 2
    assert "No se pudo escribir el archivo" in resultado.stderr


def test_get_all_output_csv(http_simulado: responses.RequestsMock, tmp_path: Path) -> None:
    crear_lotes()
    registrar_get_all(http_simulado)
    ruta = tmp_path / "lotes.csv"

    resultado = get_all_actividades("--output", str(ruta))

    assert resultado.exit_code == 0, resultado.output
    assert exportado(ruta, "3") in resultado.stdout
    assert ruta.read_bytes().decode("utf-8-sig") == (
        "ObjectId,Id\r\n1001,A1001\r\n1002,A1002\r\n1003,A1003\r\n"
    )


def test_spread_output_csv_en_formato_largo(
    http_simulado: responses.RequestsMock, tmp_path: Path
) -> None:
    crear_lotes()
    registrar_respuestas(http_simulado, "/spread/activitySpread", SPREAD_OK)
    ruta = tmp_path / "spread.csv"

    resultado = spread_actividades("--ids", "4835,4845", "--output", str(ruta))

    assert resultado.exit_code == 0, resultado.output
    assert "spread.activity · 2 objetos · 3 períodos · " in resultado.stdout
    assert exportado(ruta, "3") in resultado.stdout
    lineas = ruta.read_text(encoding="utf-8-sig").splitlines()
    assert lineas[0] == "ActivityObjectId,StartDate,EndDate,SpreadField,Valor,Acumulado"
    assert lineas[3] == "4845,2026-01-12T00:00:00,2026-01-18T23:59:59,PlannedLaborUnits,16.0,16.0"


def test_spread_output_json_tal_cual(http_simulado: responses.RequestsMock, tmp_path: Path) -> None:
    crear_lotes()
    registrar_respuestas(http_simulado, "/spread/activitySpread", SPREAD_OK)
    ruta = tmp_path / "spread.json"

    resultado = spread_actividades("--ids", "4835,4845", "--output", str(ruta))

    assert resultado.exit_code == 0, resultado.output
    unidad = messages.UNIDAD_OBJETOS
    assert messages.EXPORTADO.format(ruta=ruta, cantidad="2", unidad=unidad) in resultado.stdout
    respuesta = json.loads(leer_fixture("activity_spread_ok.json"))
    assert json.loads(ruta.read_text(encoding="utf-8")) == respuesta


def test_spread_output_csv_con_forma_inesperada_sale_con_1_sin_archivo(
    http_simulado: responses.RequestsMock, tmp_path: Path
) -> None:
    crear_lotes()
    registrar_respuestas(
        http_simulado, "/spread/activitySpread", json_simulado([{"Otra": "forma"}])
    )

    destino = tmp_path / "salida"

    resultado = spread_actividades("--ids", "4835", "--output", str(destino / "spread.csv"))

    assert resultado.exit_code == 1
    assert messages.AVISO_SPREAD_SIN_CSV in resultado.stderr
    assert not destino.exists()


def test_spread_output_invalido_sale_con_2_sin_peticiones(
    http_simulado: responses.RequestsMock, tmp_path: Path
) -> None:
    crear_lotes()

    resultado = spread_actividades("--ids", "4835", "--output", str(tmp_path / "spread.txt"))

    assert resultado.exit_code == 2
    assert len(http_simulado.calls) == 0
