"""Catálogo de endpoints, plantillas y especificación de parámetros (especificación §8).

La identidad de un endpoint es su ``key``. El número visible en los listados es un índice
derivado del orden de ``CATALOGO`` y nunca se persiste.
"""

import re
from dataclasses import dataclass
from enum import Enum, StrEnum

from p6cli.core.errors import MotivoUso, UsageError


class ParamKind(Enum):
    """Tipo de un parámetro de consulta."""

    FIELDS = "fields"  # lista separada por comas
    FILTER = "filter"  # expresión de filtro de P6, texto libre
    ORDER = "order"  # "Campo asc|desc"
    ENUM = "enum"  # una opción de una lista
    DATE = "date"  # AAAA-MM-DD
    BOOL = "bool"
    ID_LIST = "id_list"  # lista de ObjectId


class Plantilla(StrEnum):
    """Forma de los parámetros de un endpoint (§8.2)."""

    ENTITY = "entity"
    SPREAD = "spread"
    CUSTOM = "custom"


@dataclass(frozen=True)
class ParamSpec:
    """Un query param de P6, con su nombre exacto."""

    name: str
    kind: ParamKind
    required: bool
    default: str | None = None
    choices: tuple[str, ...] = ()
    help: str = ""


@dataclass(frozen=True)
class Endpoint:
    """Una entrada del catálogo. ``params`` solo se declara en plantillas spread y custom.

    ``doc_name`` es el título exacto de la operación en la documentación de Oracle (24.x),
    para buscarla allí; ``description`` es la descripción en español para la interfaz.
    """

    key: str
    path: str
    group: str
    template: Plantilla
    doc_name: str
    description: str
    large: bool = False
    doc_verified: bool = False
    params: tuple[ParamSpec, ...] = ()


# --- Plantillas ------------------------------------------------------------------

FIELDS = "Fields"
FILTER = "Filter"
ORDER_BY = "OrderBy"

# Oracle marca Filter y OrderBy como obligatorios; aquí son opcionales porque el cliente
# completa valores neutros (§8.2).
PARAMS_ENTITY: tuple[ParamSpec, ...] = (
    ParamSpec(FIELDS, ParamKind.FIELDS, required=True),
    ParamSpec(FILTER, ParamKind.FILTER, required=False),
    ParamSpec(ORDER_BY, ParamKind.ORDER, required=False),
)

PERIODOS = ("Hour", "Day", "Week", "Month", "Quarter", "Year", "FinancialPeriod")


def params_spread(param_ids: str) -> tuple[ParamSpec, ...]:
    """Parámetros de la plantilla spread; ``param_ids`` es el nombre del param de IDs."""
    return (
        ParamSpec(param_ids, ParamKind.ID_LIST, required=True),
        ParamSpec("SpreadField", ParamKind.FIELDS, required=True),
        ParamSpec("PeriodType", ParamKind.ENUM, required=True, default="Week", choices=PERIODOS),
        ParamSpec("StartDate", ParamKind.DATE, required=False),
        ParamSpec("EndDate", ParamKind.DATE, required=False),
        ParamSpec("IncludeCumulative", ParamKind.BOOL, required=False, default="true"),
    )


def parametros(endpoint: Endpoint) -> tuple[ParamSpec, ...]:
    """Parámetros aceptados por el endpoint según su plantilla."""
    if endpoint.template is Plantilla.ENTITY:
        return PARAMS_ENTITY
    return endpoint.params


# --- Catálogo inicial (§8.3) -------------------------------------------------------

_PROYECTOS = "Proyectos"
_ACTIVIDADES = "Actividades"
_CODIGOS = "Códigos"
_RECURSOS = "Recursos"
_UDF = "UDF"
_SERIES = "Series temporales"


def _entity(
    key: str, group: str, doc_name: str, description: str, *, large: bool = False
) -> Endpoint:
    # Todas las páginas de la rama 24.x se revisaron: ruta y parámetros Fields/Filter/OrderBy.
    return Endpoint(
        key=key,
        path=f"/{key}",
        group=group,
        template=Plantilla.ENTITY,
        doc_name=doc_name,
        description=description,
        large=large,
        doc_verified=True,
    )


CATALOGO: tuple[Endpoint, ...] = (
    _entity("project", _PROYECTOS, "Read Projects", "Proyectos"),
    _entity("eps", _PROYECTOS, "Read EPS", "Estructura empresarial de proyectos (EPS)"),
    _entity("wbs", _PROYECTOS, "Read WBS", "Estructura WBS", large=True),
    _entity("activity", _ACTIVIDADES, "Read Activities", "Actividades", large=True),
    _entity(
        "relationship",
        _ACTIVIDADES,
        "Read Relationship",
        "Relaciones entre actividades",
        large=True,
    ),
    _entity("activityCodeType", _CODIGOS, "Read ActivityCodeTypes", "Tipos de código de actividad"),
    _entity(
        "activityCode",
        _CODIGOS,
        "Read ActivityCodes",
        "Valores de código de actividad",
        large=True,
    ),
    _entity(
        "activityCodeAssignment",
        _CODIGOS,
        "Read ActivityCodeAssignments",
        "Asignaciones de códigos a actividades",
        large=True,
    ),
    _entity("resource", _RECURSOS, "Read Resources", "Recursos"),
    _entity(
        "resourceAssignment",
        _RECURSOS,
        "Read ResourceAssignments",
        "Asignaciones de recursos",
        large=True,
    ),
    _entity("udfType", _UDF, "Read UDFTypes", "Tipos de campo definido por el usuario (UDF)"),
    _entity("udfValue", _UDF, "Read UDFValues", "Valores de UDF", large=True),
    Endpoint(
        key="spread.activity",
        path="/spread/activitySpread",
        group=_SERIES,
        template=Plantilla.SPREAD,
        doc_name="ReadActivitySpread",
        description="Spread por actividad",
        doc_verified=True,
        params=params_spread("ActivityObjectId"),
    ),
    Endpoint(
        key="spread.resourceAssignment",
        path="/spread/resourceAssignmentSpread",
        group=_SERIES,
        template=Plantilla.SPREAD,
        doc_name="ReadResourceAssignmentSpread",
        description="Spread por asignación de recurso",
        doc_verified=True,
        params=params_spread("ResourceAssignmentObjectId"),
    ),
)

_POR_CLAVE = {endpoint.key: endpoint for endpoint in CATALOGO}


def obtener(key: str) -> Endpoint:
    """Endpoint por su clave; ``UsageError`` si no está en el catálogo."""
    try:
        return _POR_CLAVE[key]
    except KeyError:
        raise UsageError(MotivoUso.ENDPOINT_DESCONOCIDO, endpoint=key) from None


def grupos() -> tuple[str, ...]:
    """Grupos del catálogo en orden de aparición."""
    return tuple(dict.fromkeys(endpoint.group for endpoint in CATALOGO))


# --- Normalización de campos (§11.1, regla 4) --------------------------------------

_CAMPO_VALIDO = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def es_campo_valido(nombre: str) -> bool:
    """``True`` si ``nombre`` tiene forma de campo de P6: letra y luego letras, dígitos o _."""
    return _CAMPO_VALIDO.fullmatch(nombre) is not None


def normalizar_campos(texto: str, param: str = FIELDS) -> tuple[str, ...]:
    """Separa por comas, quita espacios y duplicados (preservando el orden) y valida cada campo.

    ``param`` es el nombre del parámetro que se informa en el error.
    """
    campos = tuple(dict.fromkeys(parte.strip() for parte in texto.split(",") if parte.strip()))
    if not campos:
        raise UsageError(MotivoUso.CAMPOS_VACIOS, parametro=param)
    for campo in campos:
        if not es_campo_valido(campo):
            raise UsageError(MotivoUso.CAMPO_INVALIDO, parametro=param, campo=campo)
    return campos
