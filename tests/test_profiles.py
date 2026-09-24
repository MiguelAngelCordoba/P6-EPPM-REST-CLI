"""Modelo Profile, ProfileStore y orquestación perfil + clave (especificación §4)."""

import os
import tomllib
from dataclasses import replace
from pathlib import Path

import keyring
import pytest

from p6cli.core import profiles, secrets
from p6cli.core.errors import (
    ConfigError,
    MotivoConfig,
    MotivoPerfil,
    MotivoSecreto,
    ProfileError,
    SecretStoreError,
)
from p6cli.core.profiles import Profile, ProfileStore
from tests.conftest import KeyringBloqueado, KeyringMemoria

CLAVE = "ClaveDePrueba1"

EJEMPLO_TOML = """\
default = "demo"

[profiles.demo]
host = "https://localhost:7001"
context = "p6ws"
database_name = "orcl"
username = "admin"
verify_ssl = true
timeout = 180
id_chunk_size = 200
throttle_seconds = 0.5
"""


def perfil(nombre: str = "demo", **cambios: object) -> Profile:
    base = Profile(
        name=nombre, host="https://localhost:7001", database_name="orcl", username="admin"
    )
    return replace(base, **cambios)


@pytest.fixture
def store(dir_config: Path) -> ProfileStore:
    return ProfileStore()


# --- Nombre -----------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["demo", "a", "cliente-prod", "0x", "a" * 32])
def test_nombres_validos(nombre: str) -> None:
    profiles.validar_nombre(nombre)


@pytest.mark.parametrize(
    "nombre", ["", "Demo", "-demo", "a" * 33, "demo_1", "demo prod", "demó", "demo\n"]
)
def test_nombres_invalidos(nombre: str) -> None:
    with pytest.raises(ProfileError) as error:
        profiles.validar_nombre(nombre)

    assert error.value.motivo is MotivoPerfil.NOMBRE_INVALIDO


def test_env_esta_reservado() -> None:
    with pytest.raises(ProfileError) as error:
        profiles.validar_nombre("env")

    assert error.value.motivo is MotivoPerfil.NOMBRE_RESERVADO


# --- Modelo -----------------------------------------------------------------


def test_valores_por_defecto() -> None:
    p = perfil()

    assert p.context == "p6ws"
    assert p.verify_ssl is True
    assert p.timeout == 180
    assert p.id_chunk_size == 200
    assert p.throttle_seconds == 0.5


def test_el_modelo_valida_el_nombre() -> None:
    with pytest.raises(ProfileError) as error:
        perfil("Demo")

    assert error.value.motivo is MotivoPerfil.NOMBRE_INVALIDO


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("host", "https://localhost:7001/p6ws"),
        ("host", "localhost:7001"),
        ("host", "ftp://localhost"),
        ("host", ""),
        ("context", ""),
        ("context", "p6ws/restapi"),
        ("database_name", ""),
        ("database_name", "   "),
        ("username", ""),
        ("verify_ssl", ""),
        ("verify_ssl", 1),
        ("timeout", 0),
        ("timeout", -5),
        ("timeout", True),
        ("timeout", 1.5),
        ("id_chunk_size", 0),
        ("id_chunk_size", "200"),
        ("throttle_seconds", -0.1),
        ("throttle_seconds", False),
        ("throttle_seconds", "0.5"),
    ],
)
def test_campos_invalidos(campo: str, valor: object) -> None:
    with pytest.raises(ProfileError) as error:
        perfil(**{campo: valor})

    assert error.value.motivo is MotivoPerfil.CAMPO_INVALIDO
    assert error.value.datos["campo"] == campo


def test_throttle_entero_se_acepta() -> None:
    assert perfil(throttle_seconds=0).throttle_seconds == 0


# --- ProfileStore -----------------------------------------------------------


def test_store_vacio(store: ProfileStore) -> None:
    assert store.listar() == []
    assert store.predeterminado() is None


def test_ruta_por_defecto_en_directorio_de_config(dir_config: Path) -> None:
    assert ProfileStore().ruta == dir_config / "profiles.toml"


def test_el_primero_queda_predeterminado(store: ProfileStore) -> None:
    store.agregar(perfil("demo"))
    store.agregar(perfil("otro"))

    assert store.predeterminado() == "demo"
    assert [p.name for p in store.listar()] == ["demo", "otro"]


def test_agregar_duplicado(store: ProfileStore) -> None:
    store.agregar(perfil())

    with pytest.raises(ProfileError) as error:
        store.agregar(perfil())

    assert error.value.motivo is MotivoPerfil.YA_EXISTE


def test_archivo_coincide_con_el_ejemplo(store: ProfileStore) -> None:
    store.agregar(perfil())

    escrito = tomllib.loads(store.ruta.read_text(encoding="utf-8"))

    assert escrito == tomllib.loads(EJEMPLO_TOML)


def test_lee_el_ejemplo(store: ProfileStore) -> None:
    store.ruta.parent.mkdir(parents=True)
    store.ruta.write_text(EJEMPLO_TOML, encoding="utf-8")

    assert store.listar() == [perfil()]
    assert store.predeterminado() == "demo"


def test_verify_ssl_como_ruta_se_conserva(store: ProfileStore) -> None:
    store.agregar(perfil(verify_ssl="C:/certs/ca.pem"))

    assert store.obtener("demo").verify_ssl == "C:/certs/ca.pem"


@pytest.mark.parametrize("operacion", ["obtener", "eliminar", "marcar_predeterminado"])
def test_inexistente(store: ProfileStore, operacion: str) -> None:
    with pytest.raises(ProfileError) as error:
        getattr(store, operacion)("nada")

    assert error.value.motivo is MotivoPerfil.NO_EXISTE


def test_marcar_predeterminado(store: ProfileStore) -> None:
    store.agregar(perfil("demo"))
    store.agregar(perfil("otro"))

    store.marcar_predeterminado("otro")

    assert store.predeterminado() == "otro"


def test_reemplazar_sin_renombrar(store: ProfileStore) -> None:
    store.agregar(perfil())

    store.reemplazar("demo", perfil(database_name="otra"))

    assert store.obtener("demo").database_name == "otra"


def test_reemplazar_con_renombre_mueve_el_predeterminado(store: ProfileStore) -> None:
    store.agregar(perfil("demo"))
    store.agregar(perfil("otro"))

    store.reemplazar("demo", perfil("nuevo"))

    assert [p.name for p in store.listar()] == ["nuevo", "otro"]
    assert store.predeterminado() == "nuevo"


def test_reemplazar_renombre_a_nombre_existente(store: ProfileStore) -> None:
    store.agregar(perfil("demo"))
    store.agregar(perfil("otro"))

    with pytest.raises(ProfileError) as error:
        store.reemplazar("demo", perfil("otro"))

    assert error.value.motivo is MotivoPerfil.YA_EXISTE


def test_reemplazar_inexistente(store: ProfileStore) -> None:
    with pytest.raises(ProfileError) as error:
        store.reemplazar("nada", perfil())

    assert error.value.motivo is MotivoPerfil.NO_EXISTE


def test_eliminar_predeterminado_deja_sin_predeterminado(store: ProfileStore) -> None:
    store.agregar(perfil("demo"))
    store.agregar(perfil("otro"))

    store.eliminar("demo")

    assert store.predeterminado() is None
    assert "default" not in tomllib.loads(store.ruta.read_text(encoding="utf-8"))


def test_eliminar_no_predeterminado_lo_conserva(store: ProfileStore) -> None:
    store.agregar(perfil("demo"))
    store.agregar(perfil("otro"))

    store.eliminar("otro")

    assert store.predeterminado() == "demo"


def test_sin_predeterminado_el_siguiente_no_lo_toma(store: ProfileStore) -> None:
    store.agregar(perfil("demo"))
    store.agregar(perfil("otro"))
    store.eliminar("demo")

    store.agregar(perfil("tercero"))

    assert store.predeterminado() is None


def test_almacen_vacio_el_siguiente_vuelve_a_ser_predeterminado(store: ProfileStore) -> None:
    store.agregar(perfil("demo"))
    store.eliminar("demo")

    store.agregar(perfil("otro"))

    assert store.predeterminado() == "otro"


def test_escritura_atomica(store: ProfileStore, monkeypatch: pytest.MonkeyPatch) -> None:
    store.agregar(perfil("demo"))
    original = store.ruta.read_bytes()

    def reemplazo_fallido(origen: object, destino: object) -> None:
        raise OSError("disco lleno")

    monkeypatch.setattr(os, "replace", reemplazo_fallido)

    with pytest.raises(OSError):
        store.agregar(perfil("otro"))

    assert store.ruta.read_bytes() == original
    assert list(store.ruta.parent.iterdir()) == [store.ruta]


def test_toml_corrupto(store: ProfileStore) -> None:
    store.ruta.parent.mkdir(parents=True)
    store.ruta.write_text("default = \n[[[", encoding="utf-8")

    with pytest.raises(ConfigError) as error:
        store.listar()

    assert error.value.motivo is MotivoConfig.ARCHIVO_INVALIDO


@pytest.mark.parametrize(
    "contenido",
    [
        'default = 1\n[profiles.demo]\nhost = "https://localhost:7001"',
        'profiles = "no-es-tabla"',
        "[profiles]\ndemo = 1",
    ],
)
def test_estructura_invalida(store: ProfileStore, contenido: str) -> None:
    store.ruta.parent.mkdir(parents=True)
    store.ruta.write_text(contenido, encoding="utf-8")

    with pytest.raises(ConfigError) as error:
        store.listar()

    assert error.value.motivo is MotivoConfig.ARCHIVO_INVALIDO


@pytest.mark.parametrize(
    ("reemplazo", "campo"),
    [
        ('timeout = "mucho"', "timeout"),
        ('username = ""', "username"),
    ],
)
def test_campo_invalido_en_archivo(store: ProfileStore, reemplazo: str, campo: str) -> None:
    clave = reemplazo.split(" ")[0]
    lineas = [
        reemplazo if linea.startswith(f"{clave} ") else linea for linea in EJEMPLO_TOML.splitlines()
    ]
    store.ruta.parent.mkdir(parents=True)
    store.ruta.write_text("\n".join(lineas), encoding="utf-8")

    with pytest.raises(ProfileError) as error:
        store.listar()

    assert error.value.motivo is MotivoPerfil.CAMPO_INVALIDO
    assert error.value.datos["campo"] == campo


def test_campo_faltante_en_archivo(store: ProfileStore) -> None:
    store.ruta.parent.mkdir(parents=True)
    store.ruta.write_text(EJEMPLO_TOML.replace('username = "admin"\n', ""), encoding="utf-8")

    with pytest.raises(ProfileError) as error:
        store.listar()

    assert error.value.motivo is MotivoPerfil.CAMPO_INVALIDO
    assert error.value.datos["campo"] == "username"


def test_campo_desconocido_en_archivo(store: ProfileStore) -> None:
    store.ruta.parent.mkdir(parents=True)
    store.ruta.write_text(EJEMPLO_TOML + "timout = 30\n", encoding="utf-8")

    with pytest.raises(ProfileError) as error:
        store.listar()

    assert error.value.datos["campo"] == "timout"


def test_predeterminado_inexistente_se_ignora(store: ProfileStore) -> None:
    store.ruta.parent.mkdir(parents=True)
    store.ruta.write_text(EJEMPLO_TOML.replace('default = "demo"', 'default = "nada"'), "utf-8")

    assert store.predeterminado() is None


def test_nombre_invalido_en_archivo(store: ProfileStore) -> None:
    store.ruta.parent.mkdir(parents=True)
    store.ruta.write_text(EJEMPLO_TOML.replace("profiles.demo", "profiles.Demo"), "utf-8")

    with pytest.raises(ProfileError) as error:
        store.listar()

    assert error.value.motivo is MotivoPerfil.NOMBRE_INVALIDO


# --- Orquestación perfil + clave ---------------------------------------------


def test_crear_perfil_guarda_perfil_y_clave(store: ProfileStore) -> None:
    profiles.crear_perfil(store, perfil(), CLAVE)

    assert store.obtener("demo") == perfil()
    assert secrets.leer_clave("demo") == CLAVE
    assert CLAVE not in store.ruta.read_text(encoding="utf-8")


def test_crear_perfil_duplicado_no_toca_la_clave(store: ProfileStore) -> None:
    profiles.crear_perfil(store, perfil(), CLAVE)

    with pytest.raises(ProfileError):
        profiles.crear_perfil(store, perfil(), "OtraClave")

    assert secrets.leer_clave("demo") == CLAVE


@pytest.mark.usefixtures("keyring_sin_backend")
def test_crear_perfil_sin_backend_no_guarda_el_perfil(store: ProfileStore) -> None:
    with pytest.raises(SecretStoreError):
        profiles.crear_perfil(store, perfil(), CLAVE)

    assert not store.ruta.exists()


def test_crear_perfil_revierte_la_clave_si_falla_el_archivo(
    store: ProfileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reemplazo_fallido(origen: object, destino: object) -> None:
        raise OSError("disco lleno")

    monkeypatch.setattr(os, "replace", reemplazo_fallido)

    with pytest.raises(OSError):
        profiles.crear_perfil(store, perfil(), CLAVE)

    assert secrets.leer_clave("demo") is None


def test_editar_perfil_conserva_la_clave(store: ProfileStore) -> None:
    profiles.crear_perfil(store, perfil(), CLAVE)

    profiles.editar_perfil(store, "demo", perfil(username="otro"), None)

    assert store.obtener("demo").username == "otro"
    assert secrets.leer_clave("demo") == CLAVE


def test_editar_perfil_reemplaza_la_clave(store: ProfileStore) -> None:
    profiles.crear_perfil(store, perfil(), CLAVE)

    profiles.editar_perfil(store, "demo", perfil(), "ClaveNueva2")

    assert secrets.leer_clave("demo") == "ClaveNueva2"


def test_editar_perfil_con_renombre_mueve_la_clave(store: ProfileStore) -> None:
    profiles.crear_perfil(store, perfil(), CLAVE)

    profiles.editar_perfil(store, "demo", perfil("nuevo"), None)

    assert secrets.leer_clave("demo") is None
    assert secrets.leer_clave("nuevo") == CLAVE
    assert store.predeterminado() == "nuevo"


def test_editar_perfil_con_renombre_y_clave_nueva(store: ProfileStore) -> None:
    profiles.crear_perfil(store, perfil(), CLAVE)

    profiles.editar_perfil(store, "demo", perfil("nuevo"), "ClaveNueva2")

    assert secrets.leer_clave("demo") is None
    assert secrets.leer_clave("nuevo") == "ClaveNueva2"


def test_editar_perfil_renombre_a_existente_no_toca_claves(store: ProfileStore) -> None:
    profiles.crear_perfil(store, perfil("demo"), CLAVE)
    profiles.crear_perfil(store, perfil("otro"), "ClaveOtro")

    with pytest.raises(ProfileError):
        profiles.editar_perfil(store, "demo", perfil("otro"), None)

    assert secrets.leer_clave("demo") == CLAVE
    assert secrets.leer_clave("otro") == "ClaveOtro"


def test_editar_perfil_revierte_el_archivo_si_falla_el_keyring(
    store: ProfileStore, keyring_memoria: KeyringMemoria
) -> None:
    profiles.crear_perfil(store, perfil(), CLAVE)
    bloqueado = KeyringBloqueado()
    bloqueado.claves = keyring_memoria.claves
    keyring.set_keyring(bloqueado)

    with pytest.raises(SecretStoreError):
        profiles.editar_perfil(store, "demo", perfil("nuevo"), None)

    assert [p.name for p in store.listar()] == ["demo"]
    assert store.predeterminado() == "demo"
    assert secrets.leer_clave("demo") == CLAVE


@pytest.mark.usefixtures("keyring_sin_backend")
def test_eliminar_perfil_sin_backend_elimina_el_perfil(store: ProfileStore) -> None:
    store.agregar(perfil())

    profiles.eliminar_perfil(store, "demo")

    assert store.listar() == []


def test_eliminar_perfil_con_keyring_fallando_informa(store: ProfileStore) -> None:
    store.agregar(perfil())
    keyring.set_keyring(KeyringBloqueado())

    with pytest.raises(SecretStoreError) as error:
        profiles.eliminar_perfil(store, "demo")

    assert error.value.motivo is MotivoSecreto.ERROR_KEYRING


def test_eliminar_perfil_borra_la_clave(store: ProfileStore) -> None:
    profiles.crear_perfil(store, perfil(), CLAVE)

    profiles.eliminar_perfil(store, "demo")

    assert store.listar() == []
    assert secrets.leer_clave("demo") is None
