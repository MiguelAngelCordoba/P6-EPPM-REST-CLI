"""Implementaciones de ``Prompter``: questionary (menús) y texto con typer (comandos)."""

from collections.abc import Iterator
from typing import Any

import pytest
import typer
from prompt_toolkit.input import PipeInput, create_pipe_input
from prompt_toolkit.output import DummyOutput

from p6cli.cli.prompter import (
    Opcion,
    PrompterQuestionary,
    PrompterTexto,
    Separador,
    enumerar,
)

ABAJO = "\x1b[B"
ENTER = "\r"
ESPACIO = " "
CTRL_C = "\x03"

OPCIONES: list[Opcion[int] | Separador] = [
    Opcion("uno", 1),
    Separador("── grupo ──"),
    Opcion("dos", 2, deshabilitada="próximamente"),
    Opcion("tres", 3),
]


@pytest.fixture
def entrada() -> Iterator[PipeInput]:
    with create_pipe_input() as tuberia:
        yield tuberia


@pytest.fixture
def menus(entrada: PipeInput) -> PrompterQuestionary:
    return PrompterQuestionary(input=entrada, output=DummyOutput())


# --- PrompterQuestionary --------------------------------------------------------


def test_select_devuelve_el_valor_elegido(entrada: PipeInput, menus: PrompterQuestionary) -> None:
    entrada.send_text(ENTER)

    assert menus.select("¿Cuál?", OPCIONES) == 1


def test_select_salta_separadores_y_deshabilitadas(
    entrada: PipeInput, menus: PrompterQuestionary
) -> None:
    entrada.send_text(ABAJO + ENTER)

    assert menus.select("¿Cuál?", OPCIONES) == 3


def test_select_preselecciona_el_valor_por_defecto(
    entrada: PipeInput, menus: PrompterQuestionary
) -> None:
    entrada.send_text(ENTER)

    assert menus.select("¿Cuál?", OPCIONES, por_defecto=3) == 3


def test_select_con_valores_repetidos_respeta_la_posicion(
    entrada: PipeInput, menus: PrompterQuestionary
) -> None:
    # Dos títulos distintos con valores iguales: se devuelve el valor de la posición elegida.
    entrada.send_text(ABAJO + ENTER)

    assert menus.select("¿Cuál?", [Opcion("a", "x"), Opcion("b", "x")]) == "x"


def test_checkbox_devuelve_los_marcados(entrada: PipeInput, menus: PrompterQuestionary) -> None:
    entrada.send_text(ESPACIO + ABAJO + ESPACIO + ENTER)
    opciones = [Opcion("uno", 1), Opcion("dos", 2), Opcion("tres", 3)]

    assert menus.checkbox("¿Cuáles?", opciones) == [1, 2]


def test_checkbox_respeta_los_marcados_iniciales(
    entrada: PipeInput, menus: PrompterQuestionary
) -> None:
    entrada.send_text(ENTER)
    opciones = [Opcion("uno", 1), Opcion("dos", 2), Opcion("tres", 3)]

    assert menus.checkbox("¿Cuáles?", opciones, marcados=[3]) == [3]


def test_text_ofrece_el_valor_por_defecto_editable(
    entrada: PipeInput, menus: PrompterQuestionary
) -> None:
    entrada.send_text(",Name" + ENTER)

    assert menus.text("Fields", "ObjectId") == "ObjectId,Name"


@pytest.mark.parametrize(("teclas", "esperado"), [("y", True), ("n", False), ("N", False)])
def test_confirm_acepta_y_o_n(
    entrada: PipeInput, menus: PrompterQuestionary, teclas: str, esperado: bool
) -> None:
    entrada.send_text(teclas)

    assert menus.confirm("¿Seguro?", por_defecto=not esperado) is esperado


def test_confirm_ignora_otras_teclas(entrada: PipeInput, menus: PrompterQuestionary) -> None:
    # «s» (sí) no es una respuesta válida: se ignora y cuenta la n.
    entrada.send_text("sn")

    assert menus.confirm("¿Seguro?", por_defecto=True) is False


@pytest.mark.parametrize("por_defecto", [True, False])
def test_confirm_enter_toma_el_defecto(
    entrada: PipeInput, menus: PrompterQuestionary, por_defecto: bool
) -> None:
    entrada.send_text(ENTER)

    assert menus.confirm("¿Seguro?", por_defecto=por_defecto) is por_defecto


@pytest.mark.parametrize("pregunta", ["select", "text", "confirm"])
def test_ctrl_c_lanza_keyboard_interrupt(
    entrada: PipeInput, menus: PrompterQuestionary, pregunta: str
) -> None:
    entrada.send_text(CTRL_C)

    with pytest.raises(KeyboardInterrupt):
        if pregunta == "select":
            menus.select("¿Cuál?", OPCIONES)
        elif pregunta == "text":
            menus.text("Fields")
        else:
            menus.confirm("¿Seguro?", por_defecto=True)


def test_password_sin_eco(monkeypatch: pytest.MonkeyPatch) -> None:
    llamadas: list[dict[str, Any]] = []

    def prompt(texto: str, **opciones: Any) -> str:
        llamadas.append({"texto": texto, **opciones})
        return "secreta"

    monkeypatch.setattr(typer, "prompt", prompt)

    assert PrompterQuestionary().password("Clave") == "secreta"
    assert llamadas[0]["hide_input"] is True


# --- PrompterTexto ----------------------------------------------------------------


class PromptFalso:
    """Sustituye ``typer.prompt``: responde en orden y registra el texto de cada pregunta."""

    def __init__(self, *respuestas: str) -> None:
        self.respuestas = list(respuestas)
        self.textos: list[str] = []

    def __call__(self, texto: str, default: str | None = None, **_: Any) -> str:
        self.textos.append(texto)
        respuesta = self.respuestas.pop(0)
        return respuesta if respuesta or default is None else default


def falso(monkeypatch: pytest.MonkeyPatch, *respuestas: str) -> PromptFalso:
    prompt = PromptFalso(*respuestas)
    monkeypatch.setattr(typer, "prompt", prompt)
    return prompt


TECLAS = [
    Opcion("Sí", "si", tecla="y"),
    Opcion("Más tarde", "luego", tecla="t", deshabilitada="próximamente"),
    Opcion("No", "no", tecla="n"),
]


def test_texto_select_muestra_las_teclas_elegibles(monkeypatch: pytest.MonkeyPatch) -> None:
    prompt = falso(monkeypatch, "n")

    assert PrompterTexto().select("¿Validar?", TECLAS) == "no"
    assert prompt.textos == ["¿Validar? (y = Sí · n = No)"]


def test_texto_select_enter_toma_el_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    falso(monkeypatch, "")

    assert PrompterTexto().select("¿Validar?", TECLAS, por_defecto="no") == "no"


def test_texto_select_rechaza_deshabilitadas_y_repregunta(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    falso(monkeypatch, "t", "Y")

    assert PrompterTexto().select("¿Validar?", TECLAS) == "si"
    assert "Responde y o n." in capsys.readouterr().err


def test_texto_select_exige_teclas() -> None:
    with pytest.raises(ValueError, match="no tiene tecla"):
        PrompterTexto().select("¿Cuál?", [Opcion("uno", 1)])


def test_texto_checkbox_por_teclas(monkeypatch: pytest.MonkeyPatch) -> None:
    falso(monkeypatch, "n, y, n")

    assert PrompterTexto().checkbox("¿Cuáles?", TECLAS) == ["si", "no"]


def test_texto_checkbox_enter_conserva_los_marcados(monkeypatch: pytest.MonkeyPatch) -> None:
    falso(monkeypatch, "")

    assert PrompterTexto().checkbox("¿Cuáles?", TECLAS, marcados=["no"]) == ["no"]


def test_texto_checkbox_tecla_invalida_repregunta(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    falso(monkeypatch, "y,z", "y")

    assert PrompterTexto().checkbox("¿Cuáles?", TECLAS) == ["si"]
    assert "Responde y o n." in capsys.readouterr().err


@pytest.mark.parametrize(
    ("textos", "esperado"),
    [([], ""), (["y"], "y"), (["y", "n"], "y o n"), (["y", "n", "ca"], "y, n o ca")],
)
def test_enumerar(textos: list[str], esperado: str) -> None:
    assert enumerar(textos) == esperado
