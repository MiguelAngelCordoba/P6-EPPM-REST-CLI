"""Normalización de la URL pegada por el usuario.

El usuario pega la URL de P6 Web Services tal como la tenga; aquí se extraen ``host``
(esquema + host + puerto) y ``context`` (contexto web, normalmente ``p6ws``).
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from p6cli.core.errors import ConfigError, MotivoConfig

CONTEXTO_POR_DEFECTO = "p6ws"
_SEGMENTO_API = "restapi"
_SEGMENTO_INTERFAZ_WEB = "p6"
_ESQUEMAS_VALIDOS = ("https", "http")
_CON_ESQUEMA = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


class AdvertenciaUrl(StrEnum):
    """Situaciones aceptadas que el usuario debe conocer antes de guardar."""

    SIN_CIFRADO = "sin_cifrado"


@dataclass(frozen=True)
class UrlNormalizada:
    """Resultado de normalizar una URL."""

    host: str
    context: str
    advertencias: tuple[AdvertenciaUrl, ...] = ()


def normalizar_url(texto: str) -> UrlNormalizada:
    """Extrae ``host`` y ``context`` de la URL escrita por el usuario.

    Lanza ``ConfigError`` si la URL no sirve. El error nunca repite la URL, por si
    trae credenciales incrustadas.
    """
    texto = texto.strip()
    if not texto:
        raise ConfigError(MotivoConfig.URL_VACIA)
    if not _CON_ESQUEMA.match(texto):
        texto = f"https://{texto}"

    partes = urlsplit(texto)
    esquema = partes.scheme.lower()
    if esquema not in _ESQUEMAS_VALIDOS:
        raise ConfigError(MotivoConfig.URL_ESQUEMA, esquema=esquema)
    if "@" in partes.netloc:
        raise ConfigError(MotivoConfig.URL_CREDENCIALES)

    try:
        nombre = partes.hostname
        puerto = partes.port
    except ValueError:
        raise ConfigError(MotivoConfig.URL_SIN_HOST) from None
    if not nombre:
        raise ConfigError(MotivoConfig.URL_SIN_HOST)
    if ":" in nombre:  # IPv6
        nombre = f"[{nombre}]"
    host = f"{esquema}://{nombre}" + (f":{puerto}" if puerto is not None else "")

    segmentos = [segmento for segmento in partes.path.split("/") if segmento]
    if segmentos and segmentos[0] == _SEGMENTO_INTERFAZ_WEB:
        raise ConfigError(MotivoConfig.URL_INTERFAZ_WEB)
    if _SEGMENTO_API in segmentos:
        segmentos = segmentos[: segmentos.index(_SEGMENTO_API)]
    context = segmentos[0] if segmentos else CONTEXTO_POR_DEFECTO

    advertencias = (AdvertenciaUrl.SIN_CIFRADO,) if esquema == "http" else ()
    return UrlNormalizada(host=host, context=context, advertencias=advertencias)
