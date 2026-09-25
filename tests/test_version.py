"""Versión del paquete y comportamiento mínimo del comando ``p6``."""

import runpy
import sys
from importlib.metadata import version

import pytest
import typer
from typer.testing import CliRunner

import p6cli
from p6cli.cli import menus, messages
from p6cli.cli.app import app
from p6cli.cli.prompter import Prompter, PrompterQuestionary

runner = CliRunner()


def test_version_coincide_con_metadatos() -> None:
    assert version("p6cli") == p6cli.__version__


def test_opcion_version_muestra_version() -> None:
    resultado = runner.invoke(app, ["--version"])

    assert resultado.exit_code == 0
    assert resultado.output == f"p6cli {p6cli.__version__}\n"


def test_sin_argumentos_abre_los_menus(monkeypatch: pytest.MonkeyPatch) -> None:
    recibidos: list[Prompter] = []
    monkeypatch.setattr(menus, "ejecutar", recibidos.append)

    resultado = runner.invoke(app, [])

    assert resultado.exit_code == 0
    assert len(recibidos) == 1
    assert isinstance(recibidos[0], PrompterQuestionary)


@pytest.mark.parametrize("interrupcion", [KeyboardInterrupt, typer.Abort])
def test_ctrl_c_en_los_menus_sale_con_130(
    monkeypatch: pytest.MonkeyPatch, interrupcion: type[BaseException]
) -> None:
    def interrumpir(_: Prompter) -> None:
        raise interrupcion

    monkeypatch.setattr(menus, "ejecutar", interrumpir)

    resultado = runner.invoke(app, [])

    assert resultado.exit_code == 130
    assert messages.ABORTADO in resultado.output


def test_ejecucion_como_modulo_muestra_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["p6", "--version"])

    with pytest.raises(SystemExit) as salida:
        runpy.run_module("p6cli", run_name="__main__")

    assert salida.value.code == 0
    assert capsys.readouterr().out == f"p6cli {p6cli.__version__}\n"
