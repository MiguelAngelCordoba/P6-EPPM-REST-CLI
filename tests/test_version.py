"""Versión del paquete y comportamiento mínimo del comando ``p6``."""

import runpy
import sys
from importlib.metadata import version

import pytest
from typer.testing import CliRunner

import p6cli
from p6cli.cli import messages
from p6cli.cli.app import app

runner = CliRunner()


def test_version_coincide_con_metadatos() -> None:
    assert version("p6cli") == p6cli.__version__


def test_opcion_version_muestra_version() -> None:
    resultado = runner.invoke(app, ["--version"])

    assert resultado.exit_code == 0
    assert resultado.output == f"p6cli {p6cli.__version__}\n"


def test_sin_argumentos_muestra_aviso() -> None:
    resultado = runner.invoke(app, [])

    assert resultado.exit_code == 0
    assert messages.AVISO_SIN_MENUS in resultado.output


def test_ejecucion_como_modulo_muestra_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["p6", "--version"])

    with pytest.raises(SystemExit) as salida:
        runpy.run_module("p6cli", run_name="__main__")

    assert salida.value.code == 0
    assert capsys.readouterr().out == f"p6cli {p6cli.__version__}\n"
