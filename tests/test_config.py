"""Resolución del directorio de configuración (especificación §4.2)."""

from pathlib import Path

import pytest

from p6cli.core import config


def test_usa_la_variable_de_entorno(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("P6CLI_CONFIG_DIR", str(tmp_path / "otra"))

    assert config.directorio_config() == tmp_path / "otra"


def test_variable_vacia_se_ignora(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("P6CLI_CONFIG_DIR", "")
    llamadas: list[tuple[str, object, object]] = []

    def falso_user_config_dir(nombre: str, appauthor: object, roaming: object) -> str:
        llamadas.append((nombre, appauthor, roaming))
        return "/falso/p6cli"

    monkeypatch.setattr(config.platformdirs, "user_config_dir", falso_user_config_dir)

    assert config.directorio_config() == Path("/falso/p6cli")
    assert llamadas == [("p6cli", False, True)]


def test_sin_variable_usa_platformdirs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("P6CLI_CONFIG_DIR")
    llamadas: list[tuple[str, object, object]] = []

    def falso_user_config_dir(nombre: str, appauthor: object, roaming: object) -> str:
        llamadas.append((nombre, appauthor, roaming))
        return "/falso/p6cli"

    monkeypatch.setattr(config.platformdirs, "user_config_dir", falso_user_config_dir)

    assert config.directorio_config() == Path("/falso/p6cli")
    assert llamadas == [("p6cli", False, True)]


def test_ruta_de_perfiles(dir_config: Path) -> None:
    assert config.ruta_perfiles() == dir_config / "profiles.toml"
