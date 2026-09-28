"""GET genérico, lecturas por lotes y spread (especificación §9).

Toda la validación (parámetros, guardarraíl, largo de URL) ocurre antes de tocar la red:
un error de uso nunca gasta el único intento de login. El login se hace en la primera
petición que lo necesita.

La API no pagina. ``get_all`` la simula: pide primero solo los ObjectId que cumplen el
filtro y luego trae los campos en lotes por rango de ObjectId. ``get_spread`` trocea la
lista de ObjectId. Ambos pausan entre lotes y avisan el progreso por callback.
"""

import datetime
import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import requests

from p6cli.core.catalog import (
    END_DATE,
    FIELDS,
    FILTER,
    ORDER_BY,
    START_DATE,
    Endpoint,
    ParamKind,
    ParamSpec,
    Plantilla,
    es_campo_valido,
    normalizar_campos,
    normalizar_ids,
    param_ids,
    parametros,
)
from p6cli.core.diagnostics import clasificar_login
from p6cli.core.errors import (
    AuthError,
    GuardrailError,
    MotivoAuth,
    MotivoGuardarrail,
    MotivoHTTP,
    MotivoUso,
    P6HTTPError,
    UsageError,
)
from p6cli.core.profiles import Profile
from p6cli.core.session import Sesion, es_contenido_json, fragmento, mensaje_p6, url_get

LARGO_MAXIMO_URL = 7000
LARGO_FRAGMENTO_ERROR = 500

# Valores neutros que el cliente envía cuando Filter u OrderBy quedan vacíos (§8.2).
FILTRO_NEUTRO = "ObjectId:gte:0"
ORDEN_NEUTRO = "ObjectId asc"

# Campo identificador de toda entidad de P6: base del sondeo y de los rangos de get_all.
OBJECT_ID = "ObjectId"
# Un ObjectId de P6 cabe en 19 dígitos: con él se mide la URL del peor lote antes del login.
_ID_MAS_LARGO = 10**19 - 1
_OR = re.compile(r":or:", re.IGNORECASE)
_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# Formato de fecha enviado a spread (§8.2): AAAA-MM-DDT00:00:00.
SUFIJO_FECHA = "T00:00:00"

type Fila = dict[str, Any]
# on_progress(hechos, total), contado en lotes.
type Progreso = Callable[[int, int], None]


def _valor_por_omision(endpoint: Endpoint, spec: ParamSpec, allow_unfiltered: bool) -> str | None:
    """Valor que se envía si el parámetro queda vacío; aplica el guardarraíl ``large``."""
    if endpoint.template is Plantilla.ENTITY and spec.name == FILTER:
        if endpoint.large and not allow_unfiltered:
            raise GuardrailError(MotivoGuardarrail.SIN_FILTRO, endpoint=endpoint.key)
        return FILTRO_NEUTRO
    if endpoint.template is Plantilla.ENTITY and spec.name == ORDER_BY:
        return ORDEN_NEUTRO
    return spec.default


def preparar_consulta(
    endpoint: Endpoint, params: Mapping[str, str], *, allow_unfiltered: bool = False
) -> dict[str, str]:
    """Valida los parámetros según la plantilla y devuelve la consulta lista para enviar.

    Rechaza parámetros ajenos a la plantilla, exige los obligatorios, normaliza los de tipo
    FIELDS, aplica el guardarraíl de endpoints ``large`` y completa los valores neutros y
    por defecto. Filter y OrderBy escritos por el usuario se envían tal cual; los demás
    tipos se validan con ``_valor_tipado``.
    """
    especificacion = parametros(endpoint)
    nombres = {spec.name for spec in especificacion}
    for nombre in params:
        if nombre not in nombres:
            raise UsageError(
                MotivoUso.PARAMETRO_DESCONOCIDO, parametro=nombre, endpoint=endpoint.key
            )

    consulta: dict[str, str] = {}
    for spec in especificacion:
        valor = params.get(spec.name, "")
        if spec.kind is ParamKind.FIELDS and (valor.strip() or spec.required):
            consulta[spec.name] = ",".join(normalizar_campos(valor, spec.name))
        elif valor.strip():
            consulta[spec.name] = _valor_tipado(spec, valor)
        elif (omision := _valor_por_omision(endpoint, spec, allow_unfiltered)) is not None:
            consulta[spec.name] = omision
        elif spec.required:
            raise UsageError(MotivoUso.PARAMETRO_REQUERIDO, parametro=spec.name)
    _validar_rango_fechas(consulta)
    return consulta


def _valor_tipado(spec: ParamSpec, valor: str) -> str:
    """Valor escrito de un parámetro, validado y normalizado según su tipo.

    Una lista de IDs se normaliza; un enum o un booleano se envía con el valor canónico del
    catálogo (sin distinguir mayúsculas al escribirlo); una fecha ``AAAA-MM-DD`` se envía
    como ``AAAA-MM-DDT00:00:00``. Filter, OrderBy y demás textos libres van tal cual.
    """
    texto = valor.strip()
    if spec.kind is ParamKind.ID_LIST:
        return ",".join(str(numero) for numero in normalizar_ids(valor))
    if spec.kind in (ParamKind.ENUM, ParamKind.BOOL):
        canonico = next((c for c in spec.choices if c.casefold() == texto.casefold()), None)
        if canonico is None:
            raise UsageError(
                MotivoUso.VALOR_NO_PERMITIDO,
                parametro=spec.name,
                valor=texto[:40],
                opciones=", ".join(spec.choices),
            )
        return canonico
    if spec.kind is ParamKind.DATE:
        return _fecha(spec.name, texto).isoformat() + SUFIJO_FECHA
    return valor


def _fecha(parametro: str, texto: str) -> datetime.date:
    """Fecha ``AAAA-MM-DD`` válida; ``FECHA_INVALIDA`` si no."""
    if _FECHA.fullmatch(texto):
        try:
            return datetime.date.fromisoformat(texto)
        except ValueError:
            pass
    raise UsageError(MotivoUso.FECHA_INVALIDA, parametro=parametro, valor=texto[:40])


def _validar_rango_fechas(consulta: Mapping[str, str]) -> None:
    """``RANGO_FECHAS`` si StartDate es posterior a EndDate (ambas ya normalizadas)."""
    inicio, fin = consulta.get(START_DATE), consulta.get(END_DATE)
    if inicio is not None and fin is not None and inicio > fin:
        raise UsageError(
            MotivoUso.RANGO_FECHAS,
            inicio=inicio.removesuffix(SUFIJO_FECHA),
            fin=fin.removesuffix(SUFIJO_FECHA),
        )


def validar_consulta(
    perfil: Profile,
    endpoint: Endpoint,
    params: Mapping[str, str],
    *,
    allow_unfiltered: bool = False,
) -> dict[str, str]:
    """``preparar_consulta`` más el límite de largo de la URL. No necesita la clave."""
    consulta = preparar_consulta(endpoint, params, allow_unfiltered=allow_unfiltered)
    _validar_largo(perfil, endpoint, consulta)
    return consulta


def _validar_largo(perfil: Profile, endpoint: Endpoint, consulta: Mapping[str, str]) -> None:
    largo = len(url_get(perfil, endpoint.path, consulta))
    if largo > LARGO_MAXIMO_URL:
        raise UsageError(
            MotivoUso.URL_DEMASIADO_LARGA, largo=str(largo), maximo=str(LARGO_MAXIMO_URL)
        )


# --- Lecturas por lotes (§9) -------------------------------------------------------


def filtro_de_lote(filtro: str, primero: int, ultimo: int) -> str:
    """Filtro del usuario acotado al rango de ObjectId de un lote."""
    return f"{filtro.strip()} :and: {OBJECT_ID}:gte:{primero} :and: {OBJECT_ID}:lte:{ultimo}"


def _exigir_filtro(endpoint: Endpoint, filtro: str) -> None:
    """El sondeo de IDs y las lecturas por lotes exigen Filter, sin excepción posible."""
    if endpoint.template is not Plantilla.ENTITY:
        raise UsageError(MotivoUso.PLANTILLA_NO_SOPORTADA, endpoint=endpoint.key)
    if not filtro.strip():
        raise GuardrailError(MotivoGuardarrail.SIN_FILTRO_LOTES, endpoint=endpoint.key)


def validar_lectura_masiva(
    perfil: Profile, endpoint: Endpoint, params: Mapping[str, str]
) -> dict[str, str]:
    """Valida una lectura por lotes sin tocar la red; devuelve la consulta base de los lotes.

    Exige Filter y rechaza ``:or:`` (sin distinguir mayúsculas): la API no define
    paréntesis y, al agregar el rango con ``:and:``, la precedencia no está garantizada.
    Los lotes van siempre en orden de ObjectId, así que no se acepta OrderBy. El largo de
    la URL se mide con el rango más largo posible.
    """
    filtro = params.get(FILTER, "")
    _exigir_filtro(endpoint, filtro)
    if _OR.search(filtro):
        raise UsageError(MotivoUso.FILTRO_CON_OR)
    if params.get(ORDER_BY, "").strip():
        raise UsageError(MotivoUso.PARAMETRO_DESCONOCIDO, parametro=ORDER_BY, endpoint=endpoint.key)
    consulta = preparar_consulta(endpoint, {**params, ORDER_BY: ""})
    peor = {**consulta, FILTER: filtro_de_lote(filtro, _ID_MAS_LARGO, _ID_MAS_LARGO)}
    _validar_largo(perfil, endpoint, peor)
    return consulta


def trocear[T](valores: Sequence[T], tamano: int) -> list[Sequence[T]]:
    """Parte ``valores`` en lotes consecutivos de ``tamano`` elementos (el último, menor)."""
    return [valores[inicio : inicio + tamano] for inicio in range(0, len(valores), tamano)]


def validar_spread(
    perfil: Profile,
    endpoint: Endpoint,
    params: Mapping[str, str],
    *,
    tamano_lote: int | None = None,
) -> list[dict[str, str]]:
    """Valida un spread sin tocar la red; devuelve la consulta de cada lote de IDs.

    ``tamano_lote`` reemplaza al ``id_chunk_size`` del perfil. Se mide el largo de la URL
    de cada lote.
    """
    nombre_ids = param_ids(endpoint).name
    consulta = preparar_consulta(endpoint, params)
    ids = consulta[nombre_ids].split(",")
    lotes = [
        {**consulta, nombre_ids: ",".join(lote)}
        for lote in trocear(ids, tamano_lote or perfil.id_chunk_size)
    ]
    for lote in lotes:
        _validar_largo(perfil, endpoint, lote)
    return lotes


def filas_por_periodo(
    respuesta: Sequence[Fila], endpoint: Endpoint, campos: Sequence[str]
) -> tuple[list[str], list[Fila]] | None:
    """Aplana la respuesta de un spread para la tabla: una fila por objeto y período.

    Columnas: el ObjectId del objeto, StartDate y EndDate del período y cada campo pedido,
    seguido de su ``Cumulative<campo>`` si aparece. Devuelve ``None`` si la respuesta no
    tiene la forma documentada por Oracle (objetos con su ObjectId y un arreglo ``Period``).
    """
    nombre_ids = param_ids(endpoint).name
    por_objeto: list[tuple[Any, list[Fila]]] = []
    for objeto in respuesta:
        periodos = objeto.get("Period", [])
        if (
            nombre_ids not in objeto
            or not isinstance(periodos, list)
            or not all(isinstance(periodo, dict) for periodo in periodos)
        ):
            return None
        por_objeto.append((objeto[nombre_ids], periodos))
    presentes = {clave for _, periodos in por_objeto for periodo in periodos for clave in periodo}
    columnas = [nombre_ids, START_DATE, END_DATE]
    for campo in campos:
        columnas.append(campo)
        if f"Cumulative{campo}" in presentes:
            columnas.append(f"Cumulative{campo}")
    filas = [
        {nombre_ids: objeto, **{columna: periodo.get(columna) for columna in columnas[1:]}}
        for objeto, periodos in por_objeto
        for periodo in periodos
    ]
    return columnas, filas


# --- Cliente -------------------------------------------------------------------------


class Cliente:
    """Lecturas contra P6 sobre una ``Sesion``. Solo emite GET.

    ``dormir`` hace la pausa entre lotes; los tests inyectan una que no espera.
    """

    def __init__(self, sesion: Sesion, *, dormir: Callable[[float], None] = time.sleep) -> None:
        self._sesion = sesion
        self._dormir = dormir

    def get(
        self, endpoint: Endpoint, params: Mapping[str, str], *, allow_unfiltered: bool = False
    ) -> list[Fila]:
        """Lectura simple: una petición con los parámetros validados y completados."""
        consulta = validar_consulta(
            self._sesion.perfil, endpoint, params, allow_unfiltered=allow_unfiltered
        )
        return self._filas(endpoint.path, consulta)

    def ids(self, endpoint: Endpoint, filtro: str) -> list[int]:
        """Sondeo: los ObjectId que cumplen el filtro, ordenados y sin repetir.

        Una sola petición que pide solo ObjectId, en orden de ObjectId. Exige Filter.
        """
        _exigir_filtro(endpoint, filtro)
        params = {FIELDS: OBJECT_ID, FILTER: filtro, ORDER_BY: ""}
        consulta = validar_consulta(self._sesion.perfil, endpoint, params)
        respuesta = self._pedir(endpoint.path, consulta)
        ids = _ids_de(_cuerpo_json(respuesta))
        if ids is None:
            raise _formato_inesperado(respuesta)
        return ids

    def get_all(
        self,
        endpoint: Endpoint,
        params: Mapping[str, str],
        *,
        tamano_lote: int | None = None,
        on_progress: Progreso | None = None,
    ) -> list[Fila]:
        """Lectura masiva: sondeo de IDs y luego lotes por rango de ObjectId (§9).

        ``tamano_lote`` reemplaza al ``id_chunk_size`` del perfil. Sin IDs no pide lotes.
        """
        consulta = validar_lectura_masiva(self._sesion.perfil, endpoint, params)
        ids = self.ids(endpoint, consulta[FILTER])
        lotes = [
            {**consulta, FILTER: filtro_de_lote(consulta[FILTER], lote[0], lote[-1])}
            for lote in trocear(ids, tamano_lote or self._sesion.perfil.id_chunk_size)
        ]
        return self._por_lotes(endpoint, lotes, on_progress)

    def get_spread(
        self,
        endpoint: Endpoint,
        params: Mapping[str, str],
        *,
        tamano_lote: int | None = None,
        on_progress: Progreso | None = None,
    ) -> list[Fila]:
        """Spread troceado en lotes de ObjectId; junta la respuesta de todos los lotes."""
        lotes = validar_spread(self._sesion.perfil, endpoint, params, tamano_lote=tamano_lote)
        return self._por_lotes(endpoint, lotes, on_progress)

    def fields(self, endpoint: Endpoint) -> list[str]:
        """Campos válidos de un endpoint ``entity`` (``GET {path}/fields``).

        P6 responde 200 con Content-Type JSON, pero el cuerpo es texto plano con los campos
        separados por comas (no es JSON válido). También se aceptan una lista JSON de textos o
        un texto JSON. Cada nombre debe ser un campo válido; si no, ``FORMATO_INESPERADO``.
        """
        if endpoint.template is not Plantilla.ENTITY:
            raise UsageError(MotivoUso.PLANTILLA_NO_SOPORTADA, endpoint=endpoint.key)
        respuesta = self._pedir(f"{endpoint.path}/fields", {})
        campos = _campos_de(respuesta.text)
        if campos is None:
            raise _formato_inesperado(respuesta)
        return campos

    def _por_lotes(
        self,
        endpoint: Endpoint,
        lotes: Sequence[Mapping[str, str]],
        on_progress: Progreso | None,
    ) -> list[Fila]:
        """Pide cada lote, con una pausa entre lotes consecutivos, y avisa el progreso.

        Un error en cualquier lote se propaga y lo ya recibido se descarta.
        """
        total = len(lotes)
        if on_progress is not None:
            on_progress(0, total)
        filas: list[Fila] = []
        for numero, consulta in enumerate(lotes, start=1):
            if numero > 1:
                self._dormir(self._sesion.perfil.throttle_seconds)
            filas.extend(self._filas(endpoint.path, consulta))
            if on_progress is not None:
                on_progress(numero, total)
        return filas

    def _filas(self, ruta: str, consulta: Mapping[str, str]) -> list[Fila]:
        """GET cuya respuesta debe ser una lista de objetos."""
        respuesta = self._pedir(ruta, consulta)
        datos = _cuerpo_json(respuesta)
        if not isinstance(datos, list) or not all(isinstance(fila, dict) for fila in datos):
            raise _formato_inesperado(respuesta)
        return datos

    def _asegurar_login(self) -> None:
        """Hace el único intento de login si aún no hay sesión autenticada."""
        if self._sesion.autenticada:
            return
        respuesta = self._sesion.login()
        if not self._sesion.autenticada:
            estado, detalle = clasificar_login(respuesta)
            raise AuthError(
                MotivoAuth.LOGIN_FALLIDO,
                perfil=self._sesion.perfil.name,
                estado=str(estado),
                **detalle,
            )

    def _pedir(self, ruta: str, consulta: Mapping[str, str]) -> requests.Response:
        """GET autenticado; devuelve la respuesta solo si es 200 con Content-Type JSON."""
        self._asegurar_login()
        respuesta = self._sesion.get(ruta, consulta)
        _validar_respuesta(respuesta)
        return respuesta


def _validar_respuesta(respuesta: requests.Response) -> None:
    """``P6HTTPError`` con datos no sensibles si no es un 200 con Content-Type JSON."""
    content_type = respuesta.headers.get("Content-Type", "")
    if respuesta.status_code != 200:
        raise P6HTTPError(
            MotivoHTTP.CODIGO_HTTP,
            metodo="GET",
            url=respuesta.url,
            codigo=str(respuesta.status_code),
            mensaje_p6=mensaje_p6(respuesta, LARGO_FRAGMENTO_ERROR),
        )
    if not es_contenido_json(content_type):
        raise P6HTTPError(
            MotivoHTTP.RESPUESTA_NO_JSON,
            metodo="GET",
            url=respuesta.url,
            content_type=content_type,
            fragmento=fragmento(respuesta.text, LARGO_FRAGMENTO_ERROR),
        )


def _cuerpo_json(respuesta: requests.Response) -> Any:
    """Cuerpo JSON de la respuesta; ``FORMATO_INESPERADO`` si no se puede leer."""
    try:
        return respuesta.json()
    except requests.exceptions.JSONDecodeError:
        error = _formato_inesperado(respuesta)
    # Se lanza fuera del except para no encadenar la excepción de requests.
    raise error


def _formato_inesperado(respuesta: requests.Response) -> P6HTTPError:
    return P6HTTPError(
        MotivoHTTP.FORMATO_INESPERADO,
        metodo="GET",
        url=respuesta.url,
        fragmento=fragmento(respuesta.text, LARGO_FRAGMENTO_ERROR),
    )


def _campos_de(texto: str) -> list[str] | None:
    """Nombres de campo del cuerpo de ``/fields``; ``None`` si no tiene esa forma."""
    try:
        datos: Any = json.loads(texto)
    except json.JSONDecodeError:
        datos = texto
    if isinstance(datos, list) and all(isinstance(campo, str) for campo in datos):
        campos = [campo.strip() for campo in datos]
    elif isinstance(datos, str):
        campos = [campo.strip() for campo in datos.split(",") if campo.strip()]
    else:
        return None
    if not campos or not all(es_campo_valido(campo) for campo in campos):
        return None
    return campos


def _ids_de(datos: Any) -> list[int] | None:
    """ObjectId del sondeo, ordenados y sin repetir.

    Devuelve ``None`` si la respuesta no es una lista de objetos con un ObjectId entero
    positivo (se acepta también como texto de dígitos).
    """
    if not isinstance(datos, list):
        return None
    ids: set[int] = set()
    for fila in datos:
        valor = fila.get(OBJECT_ID) if isinstance(fila, dict) else None
        if isinstance(valor, str) and valor.isascii() and valor.isdigit():
            valor = int(valor)
        if not isinstance(valor, int) or isinstance(valor, bool) or valor <= 0:
            return None
        ids.add(valor)
    return sorted(ids)
