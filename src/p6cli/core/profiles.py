"""Modelo Profile y ProfileStore (TOML).

``ProfileStore`` no guarda estado: cada operación lee el archivo y, si cambia algo, lo
reescribe de forma atómica. Las funciones ``crear_perfil``, ``editar_perfil`` y
``eliminar_perfil`` mantienen el archivo y el keyring consistentes entre sí.
"""

import contextlib
import math
import os
import re
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, cast

import tomli_w

from p6cli.core import secrets
from p6cli.core.config import ruta_perfiles
from p6cli.core.errors import (
    ConfigError,
    MotivoConfig,
    MotivoPerfil,
    MotivoSecreto,
    ProfileError,
    SecretStoreError,
)

PATRON_NOMBRE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
NOMBRES_RESERVADOS = frozenset({"env"})

_PATRON_HOST = re.compile(r"https?://[^/\s?#@]+")
_PATRON_CONTEXTO = re.compile(r"[^/\s?#]+")


def validar_nombre(nombre: str) -> None:
    """Lanza ``ProfileError`` si el nombre no es válido o está reservado."""
    if not PATRON_NOMBRE.fullmatch(nombre):
        raise ProfileError(MotivoPerfil.NOMBRE_INVALIDO, nombre=nombre)
    if nombre in NOMBRES_RESERVADOS:
        raise ProfileError(MotivoPerfil.NOMBRE_RESERVADO, nombre=nombre)


def _es_entero(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _es_texto(valor: object) -> bool:
    return isinstance(valor, str) and bool(valor.strip())


@dataclass(frozen=True)
class Profile:
    """Ambiente de P6 guardado. La contraseña no forma parte del modelo."""

    name: str
    host: str
    database_name: str
    username: str
    context: str = "p6ws"
    verify_ssl: bool | str = True
    timeout: int = 180
    id_chunk_size: int = 200
    throttle_seconds: float = 0.5

    def __post_init__(self) -> None:
        validar_nombre(self.name)
        throttle: object = self.throttle_seconds
        validos = {
            "host": isinstance(self.host, str) and bool(_PATRON_HOST.fullmatch(self.host)),
            "context": isinstance(self.context, str)
            and bool(_PATRON_CONTEXTO.fullmatch(self.context)),
            "database_name": _es_texto(self.database_name),
            "username": _es_texto(self.username),
            "verify_ssl": isinstance(self.verify_ssl, bool) or _es_texto(self.verify_ssl),
            "timeout": _es_entero(self.timeout) and self.timeout > 0,
            "id_chunk_size": _es_entero(self.id_chunk_size) and self.id_chunk_size > 0,
            "throttle_seconds": (_es_entero(throttle) or isinstance(throttle, float))
            and math.isfinite(self.throttle_seconds)
            and self.throttle_seconds >= 0,
        }
        for campo, valido in validos.items():
            if not valido:
                raise ProfileError(MotivoPerfil.CAMPO_INVALIDO, perfil=self.name, campo=campo)

    @classmethod
    def desde_toml(cls, nombre: str, datos: Mapping[str, object]) -> Profile:
        """Construye un perfil a partir de su tabla en ``profiles.toml``."""
        validar_nombre(nombre)
        conocidos = {campo.name for campo in fields(cls)} - {"name"}
        for campo in datos:
            if campo not in conocidos:
                raise ProfileError(MotivoPerfil.CAMPO_INVALIDO, perfil=nombre, campo=campo)
        for campo in ("host", "database_name", "username"):
            if campo not in datos:
                raise ProfileError(MotivoPerfil.CAMPO_INVALIDO, perfil=nombre, campo=campo)
        return cls(name=nombre, **cast(dict[str, Any], datos))

    def a_toml(self) -> dict[str, object]:
        """Tabla del perfil para ``profiles.toml``, sin el nombre (es la clave de la tabla)."""
        return {
            "host": self.host,
            "context": self.context,
            "database_name": self.database_name,
            "username": self.username,
            "verify_ssl": self.verify_ssl,
            "timeout": self.timeout,
            "id_chunk_size": self.id_chunk_size,
            "throttle_seconds": self.throttle_seconds,
        }


@dataclass
class _Contenido:
    predeterminado: str | None
    perfiles: dict[str, Profile]


class ProfileStore:
    """Lectura y escritura de ``profiles.toml``."""

    def __init__(self, ruta: Path | None = None) -> None:
        self.ruta = ruta if ruta is not None else ruta_perfiles()

    def listar(self) -> list[Profile]:
        """Perfiles en el orden del archivo."""
        return list(self._leer().perfiles.values())

    def obtener(self, nombre: str) -> Profile:
        """Perfil por nombre; ``ProfileError`` si no existe."""
        contenido = self._leer()
        self._exigir(contenido, nombre)
        return contenido.perfiles[nombre]

    def predeterminado(self) -> str | None:
        """Nombre del perfil predeterminado, si hay uno."""
        return self._leer().predeterminado

    def agregar(self, perfil: Profile) -> None:
        """Agrega un perfil nuevo. Si el almacén estaba vacío, queda como predeterminado."""
        contenido = self._leer()
        if perfil.name in contenido.perfiles:
            raise ProfileError(MotivoPerfil.YA_EXISTE, nombre=perfil.name)
        if not contenido.perfiles:
            contenido.predeterminado = perfil.name
        contenido.perfiles[perfil.name] = perfil
        self._escribir(contenido)

    def reemplazar(self, nombre: str, perfil: Profile) -> None:
        """Reemplaza el perfil ``nombre``; si ``perfil.name`` es otro, lo renombra."""
        contenido = self._leer()
        self._exigir(contenido, nombre)
        if perfil.name != nombre and perfil.name in contenido.perfiles:
            raise ProfileError(MotivoPerfil.YA_EXISTE, nombre=perfil.name)
        # Reconstruye el diccionario para conservar la posición del perfil renombrado.
        contenido.perfiles = {
            (perfil.name if actual == nombre else actual): (
                perfil if actual == nombre else existente
            )
            for actual, existente in contenido.perfiles.items()
        }
        if contenido.predeterminado == nombre:
            contenido.predeterminado = perfil.name
        self._escribir(contenido)

    def eliminar(self, nombre: str) -> None:
        """Elimina el perfil. Si era el predeterminado, no queda ninguno."""
        contenido = self._leer()
        self._exigir(contenido, nombre)
        del contenido.perfiles[nombre]
        if contenido.predeterminado == nombre:
            contenido.predeterminado = None
        self._escribir(contenido)

    def marcar_predeterminado(self, nombre: str) -> None:
        """Marca el perfil como predeterminado."""
        contenido = self._leer()
        self._exigir(contenido, nombre)
        contenido.predeterminado = nombre
        self._escribir(contenido)

    @staticmethod
    def _exigir(contenido: _Contenido, nombre: str) -> None:
        if nombre not in contenido.perfiles:
            raise ProfileError(MotivoPerfil.NO_EXISTE, nombre=nombre)

    def _invalido(self) -> ConfigError:
        return ConfigError(MotivoConfig.ARCHIVO_INVALIDO, ruta=str(self.ruta))

    def _leer(self) -> _Contenido:
        try:
            with self.ruta.open("rb") as archivo:
                datos = tomllib.load(archivo)
        except FileNotFoundError:
            return _Contenido(predeterminado=None, perfiles={})
        except tomllib.TOMLDecodeError, UnicodeDecodeError:
            raise self._invalido() from None

        predeterminado = datos.get("default")
        tablas = datos.get("profiles", {})
        if predeterminado is not None and not isinstance(predeterminado, str):
            raise self._invalido()
        if not isinstance(tablas, dict) or not all(isinstance(t, dict) for t in tablas.values()):
            raise self._invalido()

        perfiles = {nombre: Profile.desde_toml(nombre, tabla) for nombre, tabla in tablas.items()}
        if predeterminado not in perfiles:
            predeterminado = None
        return _Contenido(predeterminado=predeterminado, perfiles=perfiles)

    def _escribir(self, contenido: _Contenido) -> None:
        datos: dict[str, object] = {}
        if contenido.predeterminado is not None:
            datos["default"] = contenido.predeterminado
        datos["profiles"] = {nombre: p.a_toml() for nombre, p in contenido.perfiles.items()}
        texto = tomli_w.dumps(datos).encode("utf-8")

        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=self.ruta.parent, prefix=".profiles-", suffix=".tmp", delete=False
        ) as temporal:
            temporal.write(texto)
            temporal.flush()
            os.fsync(temporal.fileno())
        try:
            os.replace(temporal.name, self.ruta)
        except BaseException:
            Path(temporal.name).unlink(missing_ok=True)
            raise


def crear_perfil(store: ProfileStore, perfil: Profile, clave: str) -> None:
    """Guarda un perfil nuevo y su clave. Si falla el archivo, la clave se revierte."""
    if any(existente.name == perfil.name for existente in store.listar()):
        raise ProfileError(MotivoPerfil.YA_EXISTE, nombre=perfil.name)
    secrets.guardar_clave(perfil.name, clave)
    try:
        store.agregar(perfil)
    except BaseException:
        with contextlib.suppress(SecretStoreError):
            secrets.borrar_clave(perfil.name)
        raise


def editar_perfil(store: ProfileStore, nombre: str, perfil: Profile, clave: str | None) -> None:
    """Reemplaza el perfil ``nombre``; mueve la clave si se renombra y la cambia si viene.

    Si el keyring falla, el archivo vuelve a su estado anterior.
    """
    anterior = store.obtener(nombre)
    store.reemplazar(nombre, perfil)
    try:
        if clave is not None:
            secrets.guardar_clave(perfil.name, clave)
            if perfil.name != nombre:
                secrets.borrar_clave(nombre)
        elif perfil.name != nombre:
            secrets.renombrar_clave(nombre, perfil.name)
    except SecretStoreError:
        store.reemplazar(perfil.name, anterior)
        raise


def eliminar_perfil(store: ProfileStore, nombre: str) -> None:
    """Elimina el perfil y su clave. Sin backend de keyring no puede haber clave que borrar."""
    store.eliminar(nombre)
    try:
        secrets.borrar_clave(nombre)
    except SecretStoreError as error:
        if error.motivo is not MotivoSecreto.SIN_BACKEND:
            raise
