"""Envoltorio de keyring (especificación §4.3)."""

from collections.abc import Callable

import keyring
import pytest

from p6cli.core import secrets
from p6cli.core.errors import MotivoSecreto, SecretStoreError
from tests.conftest import KeyringBloqueado, KeyringMemoria

CLAVE = "ClaveDePrueba1"


def test_guardar_usa_servicio_p6cli_y_nombre_del_perfil(keyring_memoria: KeyringMemoria) -> None:
    secrets.guardar_clave("demo", CLAVE)

    assert keyring_memoria.claves == {("p6cli", "demo"): CLAVE}
    assert secrets.leer_clave("demo") == CLAVE


def test_leer_inexistente_devuelve_none() -> None:
    assert secrets.leer_clave("demo") is None


def test_borrar_elimina_la_clave() -> None:
    secrets.guardar_clave("demo", CLAVE)

    secrets.borrar_clave("demo")

    assert secrets.leer_clave("demo") is None


def test_borrar_inexistente_no_falla() -> None:
    secrets.borrar_clave("demo")


def test_renombrar_copia_y_borra_la_anterior(keyring_memoria: KeyringMemoria) -> None:
    secrets.guardar_clave("demo", CLAVE)

    secrets.renombrar_clave("demo", "nuevo")

    assert keyring_memoria.claves == {("p6cli", "nuevo"): CLAVE}


def test_renombrar_sin_clave_no_hace_nada(keyring_memoria: KeyringMemoria) -> None:
    secrets.renombrar_clave("demo", "nuevo")

    assert keyring_memoria.claves == {}


def test_otro_error_de_keyring() -> None:
    keyring.set_keyring(KeyringBloqueado())

    with pytest.raises(SecretStoreError) as error:
        secrets.guardar_clave("demo", CLAVE)

    assert error.value.motivo is MotivoSecreto.ERROR_KEYRING
    assert error.value.datos == {"tipo": "KeyringLocked"}
    assert error.value.__cause__ is None
    assert CLAVE not in str(error.value)


@pytest.mark.usefixtures("keyring_sin_backend")
@pytest.mark.parametrize(
    "operacion",
    [
        pytest.param(lambda: secrets.guardar_clave("demo", CLAVE), id="guardar"),
        pytest.param(lambda: secrets.leer_clave("demo"), id="leer"),
        pytest.param(lambda: secrets.borrar_clave("demo"), id="borrar"),
        pytest.param(lambda: secrets.renombrar_clave("demo", "nuevo"), id="renombrar"),
    ],
)
def test_sin_backend_error_claro(operacion: Callable[[], object]) -> None:
    with pytest.raises(SecretStoreError) as error:
        operacion()

    assert error.value.motivo is MotivoSecreto.SIN_BACKEND
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__
    assert CLAVE not in str(error.value)
