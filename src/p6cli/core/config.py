"""Rutas de configuración y modo por variables de entorno."""

import os
from pathlib import Path

import platformdirs

VARIABLE_DIR_CONFIG = "P6CLI_CONFIG_DIR"
ARCHIVO_PERFILES = "profiles.toml"


def directorio_config() -> Path:
    """Directorio de configuración del usuario.

    Usa ``P6CLI_CONFIG_DIR`` si está definida y no vacía; si no, el directorio de
    configuración estándar del sistema operativo. Se evalúa en cada llamada.
    """
    valor = os.environ.get(VARIABLE_DIR_CONFIG, "").strip()
    if valor:
        return Path(valor).expanduser()
    return Path(platformdirs.user_config_dir("p6cli", appauthor=False, roaming=True))


def ruta_perfiles() -> Path:
    """Ruta del archivo ``profiles.toml``."""
    return directorio_config() / ARCHIVO_PERFILES
