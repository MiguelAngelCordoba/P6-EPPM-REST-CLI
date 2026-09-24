"""Aislamiento común: keyring en memoria y directorio de configuración temporal.

Las fixtures automáticas garantizan que ningún test toque el keyring ni la
configuración reales del usuario.
"""

from collections.abc import Iterator
from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.backends import fail
from keyring.errors import KeyringLocked, PasswordDeleteError


class KeyringMemoria(KeyringBackend):
    """Backend de keyring que guarda las claves en un diccionario."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.claves: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.claves.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.claves[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        try:
            del self.claves[(service, username)]
        except KeyError:
            raise PasswordDeleteError("no existe") from None


@pytest.fixture(autouse=True)
def keyring_memoria() -> Iterator[KeyringMemoria]:
    """Sustituye el keyring del sistema por uno en memoria durante cada test."""
    anterior = keyring.get_keyring()
    memoria = KeyringMemoria()
    keyring.set_keyring(memoria)
    yield memoria
    keyring.set_keyring(anterior)


@pytest.fixture(autouse=True)
def dir_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Apunta ``P6CLI_CONFIG_DIR`` a un directorio temporal."""
    ruta = tmp_path / "config"
    monkeypatch.setenv("P6CLI_CONFIG_DIR", str(ruta))
    return ruta


@pytest.fixture
def keyring_sin_backend() -> None:
    """Simula un sistema sin backend de keyring disponible."""
    keyring.set_keyring(fail.Keyring())


class KeyringBloqueado(KeyringMemoria):
    """Keyring en memoria cuyas escrituras y borrados fallan (p. ej. almacén bloqueado)."""

    def set_password(self, service: str, username: str, password: str) -> None:
        raise KeyringLocked("bloqueado")

    def delete_password(self, service: str, username: str) -> None:
        raise KeyringLocked("bloqueado")
