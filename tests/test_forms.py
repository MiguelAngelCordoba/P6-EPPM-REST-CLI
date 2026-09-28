"""Formulario ``entity`` (§11.1, §11.3) y asistente de perfil (§10.3) con un Prompter guionizado."""

import json
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest
import responses

from p6cli.cli import forms, messages
from p6cli.cli.forms import (
    Confirmacion,
    ConsultaEntity,
    ConsultaSpread,
    Decision,
    ModoTLS,
    OrigenIds,
    ValoresEntity,
    ValoresSpread,
    comando_equivalente,
    comando_equivalente_spread,
    formulario_entity,
    formulario_spread,
)
from p6cli.core import catalog, secrets
from p6cli.core.catalog import FIELDS, FILTER, ORDER_BY
from p6cli.core.client import Cliente, validar_consulta, validar_spread
from p6cli.core.profiles import Profile, ProfileStore
from p6cli.core.session import Sesion
from tests.conftest import BASE, LOGIN_RECHAZADO, Simulada, llamadas, registrar_p6
from tests.guion import Pregunta, PrompterGuion, confirmar, elegir, escribir, oculta

CLAVE = "ClaveDePrueba1"
PERFIL = Profile.desde_toml(
    "demo", {"host": "https://localhost:7001", "database_name": "orcl", "username": "admin"}
)
PROYECTOS = catalog.obtener("project")
ACTIVIDADES = catalog.obtener("activity")

EJECUTAR = elegir(Confirmacion.EJECUTAR)


@pytest.fixture(autouse=True)
def terminal_ancha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "300")


@pytest.fixture
def cliente(http_simulado: responses.RequestsMock) -> Iterator[Cliente]:
    registrar_p6(http_simulado)
    with Sesion(PERFIL, CLAVE) as sesion:
        yield Cliente(sesion)


def llenar(fields: str, filtro: str = "", orden: str = "") -> list[tuple[str, object]]:
    return [escribir(fields), escribir(filtro), escribir(orden)]


def formulario(
    guion: PrompterGuion, cliente: Cliente, endpoint: catalog.Endpoint = PROYECTOS
) -> ConsultaEntity | None:
    consulta = formulario_entity(guion, cliente, PERFIL, endpoint, ValoresEntity())
    assert guion.terminado
    return consulta


def por_defecto_de_textos(guion: PrompterGuion) -> list[str]:
    return [pregunta.por_defecto for pregunta in guion.de_tipo("text")]


# --- Reglas de §11.1 --------------------------------------------------------------


def test_primera_vez_sin_valores_preseleccionados(
    cliente: Cliente, http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    guion = PrompterGuion(*llenar("ObjectId,Id,Name"), EJECUTAR)

    consulta = formulario(guion, cliente)

    assert consulta is not None
    assert por_defecto_de_textos(guion) == ["", "", ""]
    assert [p.mensaje for p in guion.de_tipo("text")] == [
        messages.ETIQUETA_FIELDS,
        messages.ETIQUETA_FILTER,
        messages.ETIQUETA_ORDER_BY,
    ]
    salida = capsys.readouterr().out
    assert "GET /project — Proyectos" in salida
    assert all(linea in salida for linea in messages.AYUDA_FORMULARIO)
    # El formulario no toca P6: la consulta la ejecuta el menú.
    assert len(http_simulado.calls) == 0


def test_fields_vacio_reaparece_conservando_filter_y_orderby(
    cliente: Cliente, capsys: pytest.CaptureFixture[str]
) -> None:
    guion = PrompterGuion(
        *llenar("  ", "ProjectObjectId:eq:1", "Id desc"),
        *llenar("Id", "ProjectObjectId:eq:1", "Id desc"),
        EJECUTAR,
    )

    consulta = formulario(guion, cliente)

    assert consulta is not None
    assert "Se necesita al menos un campo en Fields." in capsys.readouterr().err
    assert por_defecto_de_textos(guion)[3:] == ["  ", "ProjectObjectId:eq:1", "Id desc"]


def test_interrogacion_lista_los_campos_y_vuelve_a_pedir_fields(
    cliente: Cliente, http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    guion = PrompterGuion(escribir(" ? "), *llenar("ObjectId"), EJECUTAR)

    consulta = formulario(guion, cliente)

    assert consulta is not None
    assert llamadas(http_simulado, "GET", "/project/fields") == 1
    salida = capsys.readouterr().out
    assert "Campos de project (6)" in salida
    assert "FinishDate" in salida
    textos = [p.mensaje for p in guion.de_tipo("text")]
    assert textos[:2] == [messages.ETIQUETA_FIELDS, messages.ETIQUETA_FIELDS]


def test_interrogacion_con_error_de_p6_lo_muestra_y_vuelve_a_pedir_fields(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    registrar_p6(http_simulado, fields=Simulada(404, cuerpo="", content_type="text/html"))
    guion = PrompterGuion(escribir("?"), *llenar("ObjectId"), EJECUTAR)

    with Sesion(PERFIL, CLAVE) as sesion:
        consulta = formulario(guion, Cliente(sesion))

    assert consulta is not None
    assert "P6 respondió 404" in capsys.readouterr().err


def test_interrogacion_en_filter_muestra_la_guia_y_vuelve_a_pedir_filter(
    cliente: Cliente, http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    guion = PrompterGuion(
        escribir("ObjectId"),
        escribir("?"),
        escribir("ProjectObjectId:eq:1234"),
        escribir(""),
        EJECUTAR,
    )

    consulta = formulario(guion, cliente)

    assert consulta is not None
    assert consulta.enviada[FILTER] == "ProjectObjectId:eq:1234"
    salida = capsys.readouterr().out
    assert messages.GUIAS_SINTAXIS["filter"].titulo in salida
    assert messages.GUIAS_SINTAXIS["order-by"].titulo not in salida
    assert messages.AVISO_SINTAXIS_FORMULARIO in salida
    assert [p.mensaje for p in guion.de_tipo("text")] == [
        messages.ETIQUETA_FIELDS,
        messages.ETIQUETA_FILTER,
        messages.ETIQUETA_FILTER,
        messages.ETIQUETA_ORDER_BY,
    ]
    # La guía no toca P6.
    assert len(http_simulado.calls) == 0


def test_interrogacion_en_orderby_muestra_la_guia_y_vuelve_a_pedir_orderby(
    cliente: Cliente, capsys: pytest.CaptureFixture[str]
) -> None:
    guion = PrompterGuion(*llenar("ObjectId", "", " ? "), escribir("Id desc"), EJECUTAR)

    consulta = formulario(guion, cliente)

    assert consulta is not None
    assert consulta.enviada[ORDER_BY] == "Id desc"
    salida = capsys.readouterr().out
    assert messages.GUIAS_SINTAXIS["order-by"].titulo in salida
    assert messages.AVISO_SINTAXIS_FORMULARIO in salida
    assert [p.mensaje for p in guion.de_tipo("text")][-2:] == [
        messages.ETIQUETA_ORDER_BY,
        messages.ETIQUETA_ORDER_BY,
    ]


def test_interrogacion_conserva_lo_escrito_en_cada_campo(cliente: Cliente) -> None:
    guion = PrompterGuion(
        *llenar("ObjectId", "ProjectObjectId:eq:1", "Id"),
        elegir(Confirmacion.EDITAR),
        escribir("ObjectId,Name"),
        escribir("?"),
        escribir("ProjectObjectId:eq:2"),
        escribir("?"),
        escribir("Name"),
        EJECUTAR,
    )

    consulta = formulario(guion, cliente)

    assert consulta is not None
    # Tras cada ?, el campo vuelve a ofrecer lo que tenía antes.
    assert por_defecto_de_textos(guion)[3:] == [
        "ObjectId",
        "ProjectObjectId:eq:1",
        "ProjectObjectId:eq:1",
        "Id",
        "Id",
    ]
    assert dict(consulta.enviada) == {
        FIELDS: "ObjectId,Name",
        FILTER: "ProjectObjectId:eq:2",
        ORDER_BY: "Name",
    }


def test_normaliza_fields_y_conserva_lo_escrito(cliente: Cliente) -> None:
    guion = PrompterGuion(*llenar(" ObjectId, Id ,Id,,Name "), EJECUTAR)

    consulta = formulario(guion, cliente)

    assert consulta is not None
    assert consulta.enviada[FIELDS] == "ObjectId,Id,Name"
    assert consulta.campos == ["ObjectId", "Id", "Name"]
    assert consulta.valores.fields == " ObjectId, Id ,Id,,Name "


def test_campo_invalido_reaparece_con_lo_escrito(
    cliente: Cliente, capsys: pytest.CaptureFixture[str]
) -> None:
    guion = PrompterGuion(*llenar("ObjectId,Object-Id"), *llenar("ObjectId"), EJECUTAR)

    formulario(guion, cliente)

    assert "Campo «Object-Id» no válido en Fields" in capsys.readouterr().err
    assert por_defecto_de_textos(guion)[3] == "ObjectId,Object-Id"


def test_filter_y_orderby_se_envian_tal_cual(cliente: Cliente) -> None:
    guion = PrompterGuion(*llenar("ObjectId", "Name :like: 'act%'", "Id desc"), EJECUTAR)

    consulta = formulario(guion, cliente)

    assert consulta is not None
    assert consulta.enviada[FILTER] == "Name :like: 'act%'"
    assert consulta.enviada[ORDER_BY] == "Id desc"


def test_endpoint_grande_sin_filtro_pide_confirmacion_por_defecto_no(cliente: Cliente) -> None:
    guion = PrompterGuion(
        *llenar("ObjectId"),
        confirmar(False),
        *llenar("ObjectId"),
        confirmar(True),
        EJECUTAR,
    )

    consulta = formulario(guion, cliente, ACTIVIDADES)

    assert consulta is not None
    assert consulta.allow_unfiltered is True
    assert consulta.enviada[FILTER] == "ObjectId:gte:0"
    confirmaciones = guion.de_tipo("confirm")
    assert confirmaciones[0].mensaje == messages.CONFIRMAR_SIN_FILTRO.format(endpoint="activity")
    assert confirmaciones[0].por_defecto is False


def test_endpoint_grande_con_filtro_no_pregunta(cliente: Cliente) -> None:
    guion = PrompterGuion(*llenar("ObjectId", "ProjectObjectId:eq:1234"), EJECUTAR)

    consulta = formulario(guion, cliente, ACTIVIDADES)

    assert consulta is not None
    assert consulta.allow_unfiltered is False
    assert guion.de_tipo("confirm") == []


def test_url_demasiado_larga_reaparece_sin_tocar_p6(
    cliente: Cliente, http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    muchos = ",".join(f"Campo{numero}" for numero in range(900))
    guion = PrompterGuion(*llenar(muchos), *llenar("ObjectId"), EJECUTAR)

    formulario(guion, cliente)

    assert "La consulta genera una URL de" in capsys.readouterr().err
    assert len(http_simulado.calls) == 0


# --- Confirmación (§11.3) -----------------------------------------------------------


def test_confirmacion_marca_los_valores_por_defecto_y_muestra_el_equivalente(
    cliente: Cliente, capsys: pytest.CaptureFixture[str]
) -> None:
    guion = PrompterGuion(*llenar("ObjectId,Id", "ProjectObjectId:eq:1234"), EJECUTAR)

    formulario(guion, cliente)

    salida = capsys.readouterr().out
    assert "  Fields  : ObjectId, Id\n" in salida
    assert "  Filter  : ProjectObjectId:eq:1234\n" in salida
    assert "  OrderBy : ObjectId asc   (por defecto)" in salida
    assert (
        'Equivale a: p6 get project --env demo --fields "ObjectId,Id" '
        '--filter "ProjectObjectId:eq:1234"'
    ) in salida
    assert guion.de_tipo("select")[0].mensaje == messages.PREGUNTA_EJECUTAR


def test_editar_reabre_el_formulario_con_lo_escrito(cliente: Cliente) -> None:
    guion = PrompterGuion(
        *llenar("ObjectId", "Id:eq:'A1'", "Id"),
        elegir(Confirmacion.EDITAR),
        *llenar("ObjectId,Name", "Id:eq:'A1'", "Id"),
        EJECUTAR,
    )

    consulta = formulario(guion, cliente)

    assert consulta is not None
    assert por_defecto_de_textos(guion)[3:] == ["ObjectId", "Id:eq:'A1'", "Id"]
    assert consulta.enviada[FIELDS] == "ObjectId,Name"


def test_cancelar_no_consulta(cliente: Cliente, http_simulado: responses.RequestsMock) -> None:
    guion = PrompterGuion(*llenar("ObjectId"), elegir(Confirmacion.CANCELAR))

    assert formulario(guion, cliente) is None
    assert len(http_simulado.calls) == 0


def consulta_de(
    endpoint: catalog.Endpoint, valores: ValoresEntity, allow_unfiltered: bool = False
) -> ConsultaEntity:
    enviada = validar_consulta(PERFIL, endpoint, valores.params(), allow_unfiltered=True)
    return ConsultaEntity(endpoint, valores, enviada, allow_unfiltered)


@pytest.mark.parametrize(
    ("valores", "allow_unfiltered", "comando"),
    [
        (
            ValoresEntity(" ObjectId, Id "),
            False,
            'p6 get activity --env demo --fields "ObjectId,Id"',
        ),
        (
            ValoresEntity("ObjectId", "Status:eq:'Not Started'"),
            False,
            'p6 get activity --env demo --fields "ObjectId" --filter "Status:eq:\'Not Started\'"',
        ),
        (
            ValoresEntity("ObjectId", "", "Id desc"),
            True,
            'p6 get activity --env demo --fields "ObjectId" --order-by "Id desc" '
            "--allow-unfiltered",
        ),
    ],
)
def test_comando_equivalente(valores: ValoresEntity, allow_unfiltered: bool, comando: str) -> None:
    consulta = consulta_de(ACTIVIDADES, valores, allow_unfiltered)

    assert comando_equivalente("demo", consulta) == comando


# --- Asistente de perfil con listas -------------------------------------------------


def alta(*tls: tuple[str, object]) -> list[tuple[str, object]]:
    return [
        escribir("demo"),
        escribir("https://localhost:7001/p6ws"),
        confirmar(True),
        escribir("orcl"),
        escribir("admin"),
        oculta(CLAVE),
        *tls,
    ]


def test_asistente_con_ca_propia(tmp_path: Path, http_simulado: responses.RequestsMock) -> None:
    registrar_p6(http_simulado)
    ca = tmp_path / "ca.pem"
    ca.write_text("no es un certificado real", encoding="utf-8")
    guion = PrompterGuion(
        *alta(elegir(ModoTLS.CA_PROPIA), escribir(str(tmp_path / "no.pem")), escribir(str(ca)))
    )

    perfil = forms.agregar_perfil(guion, ProfileStore())

    assert guion.terminado
    assert perfil is not None
    assert ProfileStore().obtener("demo").verify_ssl == str(ca.resolve())
    tls = guion.de_tipo("select")[0]
    assert tls.titulos() == ["Sí", "No", "Usar CA propia (.pem)"]
    assert tls.por_defecto is ModoTLS.VALIDAR


def test_asistente_fallo_ofrece_corregir_guardar_o_cancelar(
    http_simulado: responses.RequestsMock,
) -> None:
    registrar_p6(http_simulado, login=LOGIN_RECHAZADO)
    guion = PrompterGuion(*alta(elegir(ModoTLS.VALIDAR)), elegir(Decision.CANCELAR))

    assert forms.agregar_perfil(guion, ProfileStore()) is None

    assert guion.terminado
    fallo = guion.de_tipo("select")[1]
    assert fallo.elegibles() == [Decision.CORREGIR, Decision.GUARDAR, Decision.CANCELAR]
    assert fallo.por_defecto is Decision.CORREGIR
    assert ProfileStore().listar() == []
    assert secrets.leer_clave("demo") is None


def test_asistente_fallo_guardar_de_todas_formas(http_simulado: responses.RequestsMock) -> None:
    registrar_p6(http_simulado, login=LOGIN_RECHAZADO)
    guion = PrompterGuion(*alta(elegir(ModoTLS.NO_VALIDAR)), elegir(Decision.GUARDAR))

    perfil = forms.agregar_perfil(guion, ProfileStore())

    assert perfil is not None
    assert perfil.verify_ssl is False
    assert secrets.leer_clave("demo") == CLAVE


# --- Formulario spread (§11.2 y §11.3) ----------------------------------------------

SPREAD = catalog.obtener("spread.activity")
FILTRO_IDS = "ProjectObjectId:eq:1234"


def escritos(ids: str = "4835,4845") -> list[tuple[str, object]]:
    return [elegir(OrigenIds.ESCRIBIR), escribir(ids)]


def resto(
    spread_field: str = "PlannedLaborUnits",
    periodo: str = "Week",
    inicio: str = "",
    fin: str = "",
    acumulado: bool = True,
) -> list[tuple[str, object]]:
    """SpreadField, PeriodType, fechas e IncludeCumulative, en el orden del formulario."""
    return [
        escribir(spread_field),
        elegir(periodo),
        escribir(inicio),
        escribir(fin),
        confirmar(acumulado),
    ]


def formulario_s(
    guion: PrompterGuion, cliente: Cliente, valores: ValoresSpread | None = None
) -> ConsultaSpread | None:
    consulta = formulario_spread(guion, cliente, PERFIL, SPREAD, valores or ValoresSpread())
    assert guion.terminado, f"Quedaron respuestas sin usar: {guion.respuestas}"
    return consulta


def preguntas(guion: PrompterGuion, mensaje: str) -> list[Pregunta]:
    return [p for p in guion.preguntas if p.mensaje == mensaje]


def ids_de_actividades(*ids: int) -> Simulada:
    cuerpo = json.dumps([{"ObjectId": numero} for numero in ids])
    return Simulada(200, cuerpo=cuerpo, content_type="application/json")


def test_spread_ids_escritos_sin_tocar_p6(
    cliente: Cliente, http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    guion = PrompterGuion(*escritos(" 4835, 4845,4835"), *resto(), EJECUTAR)

    consulta = formulario_s(guion, cliente)

    assert consulta is not None
    assert consulta.ids == (4835, 4845)
    assert consulta.params()["ActivityObjectId"] == "4835,4845"
    assert consulta.campos == ["PlannedLaborUnits"]
    assert len(consulta.lotes) == 1
    assert len(http_simulado.calls) == 0
    salida = capsys.readouterr().out
    assert "GET /spread/activitySpread — Spread por actividad" in salida
    assert all(linea in salida for linea in messages.AYUDA_FORMULARIO_SPREAD)
    assert "2 ObjectId en 1 lote" in salida


def test_spread_opciones_y_valores_por_defecto(cliente: Cliente) -> None:
    guion = PrompterGuion(*escritos(), *resto(), EJECUTAR)

    formulario_s(guion, cliente)

    origen = preguntas(guion, messages.PREGUNTA_ORIGEN_IDS)[0]
    assert origen.por_defecto is OrigenIds.ESCRIBIR
    assert origen.titulos()[-1] == "Desde una consulta a «activity»"
    periodo = preguntas(guion, messages.PREGUNTA_PERIODO)[0]
    assert periodo.por_defecto == "Week"
    assert periodo.elegibles() == list(catalog.PERIODOS)
    assert guion.de_tipo("confirm")[0].por_defecto is True
    # Sin valores preseleccionados en los textos.
    assert por_defecto_de_textos(guion) == ["", "", "", ""]


def test_spread_ids_desde_un_archivo(
    cliente: Cliente, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    archivo = tmp_path / "actividades.json"
    archivo.write_text('[{"ObjectId": 4845}, {"ObjectId": 4835}]', encoding="utf-8")
    guion = PrompterGuion(elegir(OrigenIds.ARCHIVO), escribir(str(archivo)), *resto(), EJECUTAR)

    consulta = formulario_s(guion, cliente)

    assert consulta is not None
    assert consulta.ids == (4845, 4835)
    assert f"Se leyeron 2 ObjectId de {archivo}." in capsys.readouterr().out


def test_spread_archivo_invalido_vuelve_a_elegir_origen(
    cliente: Cliente, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    faltante = str(tmp_path / "no_existe.csv")
    guion = PrompterGuion(
        elegir(OrigenIds.ARCHIVO), escribir(faltante), *escritos(), *resto(), EJECUTAR
    )

    consulta = formulario_s(guion, cliente)

    assert consulta is not None
    assert "No se pudo leer el archivo" in capsys.readouterr().err
    origenes = preguntas(guion, messages.PREGUNTA_ORIGEN_IDS)
    assert [p.por_defecto for p in origenes] == [OrigenIds.ESCRIBIR, OrigenIds.ARCHIVO]


def test_spread_ids_desde_una_consulta(
    cliente: Cliente, http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    http_simulado.add(ids_de_actividades(4845, 4835).respuesta("GET", f"{BASE}/activity"))
    guion = PrompterGuion(elegir(OrigenIds.CONSULTA), escribir(FILTRO_IDS), *resto(), EJECUTAR)

    consulta = formulario_s(guion, cliente)

    assert consulta is not None
    assert consulta.ids == (4835, 4845)
    peticion = next(c.request for c in http_simulado.calls if c.request.method == "GET")
    enviada = dict(parse_qsl(urlsplit(str(peticion.url)).query))
    assert enviada["Fields"] == "ObjectId"
    assert enviada["Filter"] == FILTRO_IDS
    assert guion.de_tipo("text")[0].mensaje == "(Obligatorio) Filter sobre activity :"
    assert "Se obtuvieron 2 ObjectId de «activity»." in capsys.readouterr().out
    assert consulta.valores.filtro == FILTRO_IDS


def test_spread_consulta_sin_resultados_vuelve_a_elegir_origen(
    cliente: Cliente, http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    http_simulado.add(ids_de_actividades().respuesta("GET", f"{BASE}/activity"))
    guion = PrompterGuion(
        elegir(OrigenIds.CONSULTA), escribir(FILTRO_IDS), *escritos(), *resto(), EJECUTAR
    )

    consulta = formulario_s(guion, cliente)

    assert consulta is not None
    assert "Ningún registro de «activity» cumple ese filtro." in capsys.readouterr().err


def test_spread_consulta_con_filtro_vacio_no_toca_p6(
    cliente: Cliente, http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    guion = PrompterGuion(
        elegir(OrigenIds.CONSULTA), escribir("  "), *escritos(), *resto(), EJECUTAR
    )

    formulario_s(guion, cliente)

    assert messages.FILTRO_IDS_VACIO in capsys.readouterr().err
    assert len(http_simulado.calls) == 0


def test_spread_interrogacion_en_el_filtro_muestra_la_guia(
    cliente: Cliente, http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    http_simulado.add(ids_de_actividades(4835).respuesta("GET", f"{BASE}/activity"))
    guion = PrompterGuion(
        elegir(OrigenIds.CONSULTA), escribir("?"), escribir(FILTRO_IDS), *resto(), EJECUTAR
    )

    formulario_s(guion, cliente)

    salida = capsys.readouterr().out
    assert messages.GUIAS_SINTAXIS["filter"].titulo in salida
    assert messages.AVISO_SINTAXIS_FORMULARIO in salida


def test_spread_consulta_con_error_de_p6_vuelve_a_elegir_origen(
    cliente: Cliente, http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    error = Simulada(400, cuerpo='{"message":"Bad filter"}', content_type="application/json")
    http_simulado.add(error.respuesta("GET", f"{BASE}/activity"))
    guion = PrompterGuion(
        elegir(OrigenIds.CONSULTA), escribir("Mal"), *escritos(), *resto(), EJECUTAR
    )

    consulta = formulario_s(guion, cliente)

    assert consulta is not None
    assert "Bad filter" in capsys.readouterr().err


def test_spread_mismo_filtro_no_repite_la_consulta_de_ids(
    cliente: Cliente, http_simulado: responses.RequestsMock
) -> None:
    http_simulado.add(ids_de_actividades(4835).respuesta("GET", f"{BASE}/activity"))
    guion = PrompterGuion(
        elegir(OrigenIds.CONSULTA),
        escribir(FILTRO_IDS),
        *resto(inicio="2026-02-30"),
        # El formulario reaparece: mismo origen y mismo filtro.
        elegir(OrigenIds.CONSULTA),
        escribir(FILTRO_IDS),
        *resto(),
        EJECUTAR,
    )

    consulta = formulario_s(guion, cliente)

    assert consulta is not None
    assert llamadas(http_simulado, "GET", "/activity") == 1


def test_spread_field_vacio_reaparece_con_lo_escrito(
    cliente: Cliente, capsys: pytest.CaptureFixture[str]
) -> None:
    guion = PrompterGuion(
        *escritos(),
        *resto(spread_field=" ", inicio="2026-01-05"),
        *escritos(),
        *resto(inicio="2026-01-05"),
        EJECUTAR,
    )

    consulta = formulario_s(guion, cliente)

    assert consulta is not None
    assert "Se necesita al menos un campo en SpreadField." in capsys.readouterr().err
    assert por_defecto_de_textos(guion)[4:] == ["4835,4845", " ", "2026-01-05", ""]


def test_spread_fecha_invalida_reaparece_con_lo_escrito(
    cliente: Cliente, capsys: pytest.CaptureFixture[str]
) -> None:
    guion = PrompterGuion(
        *escritos(),
        *resto(periodo="Month", inicio="05/01/2026", acumulado=False),
        *escritos(),
        *resto(periodo="Month", inicio="2026-01-05", acumulado=False),
        EJECUTAR,
    )

    consulta = formulario_s(guion, cliente)

    assert consulta is not None
    assert "Fecha «05/01/2026» no válida en StartDate" in capsys.readouterr().err
    segundo_periodo = preguntas(guion, messages.PREGUNTA_PERIODO)[1]
    assert segundo_periodo.por_defecto == "Month"
    assert guion.de_tipo("confirm")[1].por_defecto is False
    assert consulta.lotes[0]["StartDate"] == "2026-01-05T00:00:00"


def test_spread_editar_reabre_con_lo_escrito(cliente: Cliente) -> None:
    guion = PrompterGuion(
        *escritos(),
        *resto(),
        elegir(Confirmacion.EDITAR),
        *escritos("4835"),
        *resto(),
        EJECUTAR,
    )

    consulta = formulario_s(guion, cliente)

    assert consulta is not None
    assert consulta.ids == (4835,)
    assert por_defecto_de_textos(guion)[4] == "4835,4845"


def test_spread_cancelar(cliente: Cliente, http_simulado: responses.RequestsMock) -> None:
    guion = PrompterGuion(*escritos(), *resto(), elegir(Confirmacion.CANCELAR))

    assert formulario_s(guion, cliente) is None
    assert len(http_simulado.calls) == 0


def consulta_spread(valores: ValoresSpread, ids: tuple[int, ...]) -> ConsultaSpread:
    params = {
        "ActivityObjectId": ",".join(map(str, ids)),
        "SpreadField": valores.spread_field,
        "PeriodType": valores.periodo,
        "StartDate": valores.inicio,
        "EndDate": valores.fin,
        "IncludeCumulative": "true" if valores.acumulado else "false",
    }
    return ConsultaSpread(SPREAD, valores, ids, validar_spread(PERFIL, SPREAD, params))


@pytest.mark.parametrize(
    ("valores", "comando"),
    [
        (
            ValoresSpread(spread_field="PlannedLaborUnits"),
            'p6 spread spread.activity --env demo --ids "4835,4845" '
            '--spread-fields "PlannedLaborUnits"',
        ),
        (
            ValoresSpread(origen=OrigenIds.CONSULTA, filtro=FILTRO_IDS, spread_field="A, B,A"),
            'p6 spread spread.activity --env demo --ids "4835,4845" --spread-fields "A,B"',
        ),
        (
            ValoresSpread(
                origen=OrigenIds.ARCHIVO,
                archivo="exports/ids.csv",
                spread_field="A",
                periodo="Month",
                inicio=" 2026-01-01 ",
                fin="2026-01-31",
                acumulado=False,
            ),
            'p6 spread spread.activity --env demo --ids-from "exports/ids.csv" '
            '--spread-fields "A" --period Month --start 2026-01-01 --end 2026-01-31 '
            "--no-cumulative",
        ),
    ],
    ids=["escritos", "consulta", "archivo-con-flags"],
)
def test_comando_equivalente_spread(valores: ValoresSpread, comando: str) -> None:
    assert comando_equivalente_spread("demo", consulta_spread(valores, (4835, 4845))) == comando


def test_spread_interrogacion_en_spread_field_lista_los_validos_sin_red(
    cliente: Cliente, http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    guion = PrompterGuion(
        *escritos(), escribir(" ? "), *resto(spread_field="PlannedLaborUnits"), EJECUTAR
    )

    consulta = formulario_s(guion, cliente)

    assert consulta is not None
    assert consulta.campos == ["PlannedLaborUnits"]
    salida = capsys.readouterr().out
    assert "SpreadField válidos de spread.activity (72)" in salida
    assert all(campo in salida for campo in catalog.CAMPOS_SPREAD_ACTIVIDAD)
    assert len(http_simulado.calls) == 0
    etiquetas = [p.mensaje for p in guion.de_tipo("text")]
    assert etiquetas[1:3] == [messages.ETIQUETA_SPREAD_FIELD] * 2


def test_spread_interrogacion_conserva_lo_escrito_en_spread_field(cliente: Cliente) -> None:
    guion = PrompterGuion(*escritos(), escribir("?"), *resto(spread_field="ActualCost"), EJECUTAR)

    formulario_s(guion, cliente, ValoresSpread(spread_field="ActualCost"))

    assert por_defecto_de_textos(guion)[1:3] == ["ActualCost", "ActualCost"]


def test_spread_interrogacion_en_asignaciones_lista_sus_campos(
    cliente: Cliente, capsys: pytest.CaptureFixture[str]
) -> None:
    asignaciones = catalog.obtener("spread.resourceAssignment")
    guion = PrompterGuion(*escritos(), escribir("?"), *resto(spread_field="PlannedUnits"), EJECUTAR)

    consulta = formulario_spread(guion, cliente, PERFIL, asignaciones, ValoresSpread())

    assert consulta is not None
    assert guion.terminado
    salida = capsys.readouterr().out
    assert "SpreadField válidos de spread.resourceAssignment (26)" in salida
    assert "StaffedRemainingUnits" in salida
    assert "Baseline1PlannedTotalCost" not in salida
