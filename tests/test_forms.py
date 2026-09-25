"""Formulario ``entity`` (§11.1, §11.3) y asistente de perfil (§10.3) con un Prompter guionizado."""

from collections.abc import Iterator
from pathlib import Path

import pytest
import responses

from p6cli.cli import forms, messages
from p6cli.cli.forms import (
    Confirmacion,
    ConsultaEntity,
    Decision,
    ModoTLS,
    ValoresEntity,
    comando_equivalente,
    formulario_entity,
)
from p6cli.core import catalog, secrets
from p6cli.core.catalog import FIELDS, FILTER, ORDER_BY
from p6cli.core.client import Cliente, validar_consulta
from p6cli.core.profiles import Profile, ProfileStore
from p6cli.core.session import Sesion
from tests.conftest import LOGIN_RECHAZADO, Simulada, llamadas, registrar_p6
from tests.guion import PrompterGuion, confirmar, elegir, escribir, oculta

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
