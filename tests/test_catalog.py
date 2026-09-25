"""Catálogo de endpoints, plantillas y normalización de campos (especificación §8 y §11.1)."""

import pytest

from p6cli.core import catalog
from p6cli.core.catalog import PARAMS_ENTITY, ParamKind, Plantilla
from p6cli.core.errors import MotivoUso, UsageError

# Tabla §8.3: key, path, plantilla, grupo, large y nombre en la documentación de Oracle.
# Las 14 páginas de la rama 24.x se revisaron: todas quedan con doc_verified.
TABLA_8_3 = [
    ("project", "/project", Plantilla.ENTITY, "Proyectos", False, "Read Projects"),
    ("eps", "/eps", Plantilla.ENTITY, "Proyectos", False, "Read EPS"),
    ("wbs", "/wbs", Plantilla.ENTITY, "Proyectos", True, "Read WBS"),
    ("activity", "/activity", Plantilla.ENTITY, "Actividades", True, "Read Activities"),
    ("relationship", "/relationship", Plantilla.ENTITY, "Actividades", True, "Read Relationship"),
    (
        "activityCodeType",
        "/activityCodeType",
        Plantilla.ENTITY,
        "Códigos",
        False,
        "Read ActivityCodeTypes",
    ),
    ("activityCode", "/activityCode", Plantilla.ENTITY, "Códigos", True, "Read ActivityCodes"),
    (
        "activityCodeAssignment",
        "/activityCodeAssignment",
        Plantilla.ENTITY,
        "Códigos",
        True,
        "Read ActivityCodeAssignments",
    ),
    ("resource", "/resource", Plantilla.ENTITY, "Recursos", False, "Read Resources"),
    (
        "resourceAssignment",
        "/resourceAssignment",
        Plantilla.ENTITY,
        "Recursos",
        True,
        "Read ResourceAssignments",
    ),
    ("udfType", "/udfType", Plantilla.ENTITY, "UDF", False, "Read UDFTypes"),
    ("udfValue", "/udfValue", Plantilla.ENTITY, "UDF", True, "Read UDFValues"),
    (
        "spread.activity",
        "/spread/activitySpread",
        Plantilla.SPREAD,
        "Series temporales",
        False,
        "ReadActivitySpread",
    ),
    (
        "spread.resourceAssignment",
        "/spread/resourceAssignmentSpread",
        Plantilla.SPREAD,
        "Series temporales",
        False,
        "ReadResourceAssignmentSpread",
    ),
]


def test_catalogo_tiene_las_entradas_de_la_tabla_en_orden() -> None:
    assert [endpoint.key for endpoint in catalog.CATALOGO] == [fila[0] for fila in TABLA_8_3]


@pytest.mark.parametrize(
    ("key", "path", "plantilla", "grupo", "large", "doc_name"),
    TABLA_8_3,
    ids=[fila[0] for fila in TABLA_8_3],
)
def test_entrada_coincide_con_la_tabla(
    key: str, path: str, plantilla: Plantilla, grupo: str, large: bool, doc_name: str
) -> None:
    endpoint = catalog.obtener(key)

    assert endpoint.path == path
    assert endpoint.template is plantilla
    assert endpoint.group == grupo
    assert endpoint.large is large
    assert endpoint.doc_name == doc_name
    assert endpoint.doc_verified is True
    assert endpoint.description.strip()


def test_obtener_clave_inexistente() -> None:
    with pytest.raises(UsageError) as capturado:
        catalog.obtener("actividad")

    assert capturado.value.motivo is MotivoUso.ENDPOINT_DESCONOCIDO
    assert capturado.value.datos["endpoint"] == "actividad"


def test_grupos_en_orden_de_aparicion() -> None:
    assert catalog.grupos() == (
        "Proyectos",
        "Actividades",
        "Códigos",
        "Recursos",
        "UDF",
        "Series temporales",
    )


def test_parametros_de_entity() -> None:
    especificacion = catalog.parametros(catalog.obtener("activity"))

    assert especificacion is PARAMS_ENTITY
    assert [(p.name, p.kind, p.required) for p in especificacion] == [
        ("Fields", ParamKind.FIELDS, True),
        ("Filter", ParamKind.FILTER, False),
        ("OrderBy", ParamKind.ORDER, False),
    ]
    # Sin valores preseleccionados (§11.1, regla 1).
    assert all(p.default is None for p in especificacion)


def test_parametros_de_spread() -> None:
    especificacion = {p.name: p for p in catalog.parametros(catalog.obtener("spread.activity"))}

    assert list(especificacion) == [
        "ActivityObjectId",
        "SpreadField",
        "PeriodType",
        "StartDate",
        "EndDate",
        "IncludeCumulative",
    ]
    assert especificacion["ActivityObjectId"].kind is ParamKind.ID_LIST
    assert especificacion["ActivityObjectId"].required
    assert especificacion["SpreadField"].required
    assert especificacion["PeriodType"].default == "Week"
    assert especificacion["PeriodType"].choices == (
        "Hour",
        "Day",
        "Week",
        "Month",
        "Quarter",
        "Year",
        "FinancialPeriod",
    )
    assert especificacion["StartDate"].kind is ParamKind.DATE
    assert not especificacion["EndDate"].required
    assert especificacion["IncludeCumulative"].default == "true"


def test_spread_de_asignaciones_usa_su_parametro_de_ids() -> None:
    especificacion = catalog.parametros(catalog.obtener("spread.resourceAssignment"))

    assert especificacion[0].name == "ResourceAssignmentObjectId"


# --- normalizar_campos -----------------------------------------------------------


def test_normalizar_quita_espacios_y_duplicados_en_orden() -> None:
    assert catalog.normalizar_campos(" ObjectId , Id,Name,Id , ,ObjectId") == (
        "ObjectId",
        "Id",
        "Name",
    )


@pytest.mark.parametrize("texto", ["", "   ", " , ,"])
def test_normalizar_vacio(texto: str) -> None:
    with pytest.raises(UsageError) as capturado:
        catalog.normalizar_campos(texto)

    assert capturado.value.motivo is MotivoUso.CAMPOS_VACIOS
    assert capturado.value.datos["parametro"] == "Fields"


@pytest.mark.parametrize("campo", ["1Id", "Id;x", "Nombre Largo", "_Id", "Ñame"])
def test_normalizar_campo_invalido(campo: str) -> None:
    with pytest.raises(UsageError) as capturado:
        catalog.normalizar_campos(f"ObjectId,{campo}")

    assert capturado.value.motivo is MotivoUso.CAMPO_INVALIDO
    assert capturado.value.datos["campo"] == campo


@pytest.mark.parametrize(
    ("nombre", "valido"),
    [("ObjectId", True), ("Udf_1", True), ("", False), ("1Id", False), ("<html>", False)],
)
def test_es_campo_valido(nombre: str, valido: bool) -> None:
    assert catalog.es_campo_valido(nombre) is valido


def test_normalizar_acepta_guion_bajo_y_digitos() -> None:
    assert catalog.normalizar_campos("Udf_1,Campo2") == ("Udf_1", "Campo2")
