"""Envoltorio de keyring para las contraseñas de los perfiles.

Servicio keyring ``p6cli``; usuario keyring = nombre del perfil. Los errores de keyring
se traducen a ``SecretStoreError`` sin encadenar la excepción original, para que nada
que pudiera contener la clave llegue a un mensaje o a un traceback.
"""

import keyring
from keyring.errors import KeyringError, NoKeyringError, PasswordDeleteError

from p6cli.core.errors import MotivoSecreto, SecretStoreError

SERVICIO_KEYRING = "p6cli"


def _traducir(error: KeyringError) -> SecretStoreError:
    if isinstance(error, NoKeyringError):
        return SecretStoreError(MotivoSecreto.SIN_BACKEND)
    return SecretStoreError(MotivoSecreto.ERROR_KEYRING, tipo=type(error).__name__)


def guardar_clave(perfil: str, clave: str) -> None:
    """Guarda (o reemplaza) la clave del perfil."""
    try:
        keyring.set_password(SERVICIO_KEYRING, perfil, clave)
    except KeyringError as error:
        raise _traducir(error) from None


def leer_clave(perfil: str) -> str | None:
    """Devuelve la clave del perfil, o ``None`` si no hay una guardada."""
    try:
        return keyring.get_password(SERVICIO_KEYRING, perfil)
    except KeyringError as error:
        raise _traducir(error) from None


def borrar_clave(perfil: str) -> None:
    """Borra la clave del perfil; no falla si no existe."""
    try:
        keyring.delete_password(SERVICIO_KEYRING, perfil)
    except PasswordDeleteError:
        pass
    except KeyringError as error:
        raise _traducir(error) from None


def renombrar_clave(anterior: str, nuevo: str) -> None:
    """Copia la clave a ``nuevo`` y borra la de ``anterior``; no hace nada si no hay clave."""
    clave = leer_clave(anterior)
    if clave is None:
        return
    guardar_clave(nuevo, clave)
    borrar_clave(anterior)
