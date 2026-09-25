"""Interfaz delgada sobre questionary, inyectable en tests.

``Prompter`` es el protocolo con el que menús y formularios hacen preguntas (§3). Hay dos
implementaciones:

- ``PrompterQuestionary``: listas con flechas, para el flujo interactivo.
- ``PrompterTexto``: preguntas de texto con ``typer.prompt``, para los comandos con flags.
  Funciona con entrada redirigida; cada opción de una lista se elige por su tecla.

La clave se pide siempre sin eco: ni siquiera se revela su longitud. Ctrl+C interrumpe la
pregunta con ``KeyboardInterrupt`` (questionary) o ``typer.Abort`` (typer).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import questionary
import typer

from p6cli.cli import messages


@dataclass(frozen=True)
class Opcion[T]:
    """Una opción de una lista.

    ``tecla`` es el atajo con que se elige en ``PrompterTexto``. ``deshabilitada`` es el
    motivo que se muestra junto a una opción que no se puede elegir.
    """

    titulo: str
    valor: T
    tecla: str | None = None
    deshabilitada: str | None = None


@dataclass(frozen=True)
class Separador:
    """Línea no elegible de una lista: un título de grupo o una raya."""

    titulo: str = messages.LINEA_SEPARADOR


class Prompter(Protocol):
    """Preguntas al usuario. Los tests inyectan una implementación con respuestas fijas."""

    def select[T](
        self,
        mensaje: str,
        opciones: Sequence[Opcion[T] | Separador],
        por_defecto: T | None = None,
    ) -> T:
        """Una opción de la lista; ``por_defecto`` es el valor preseleccionado."""
        ...

    def checkbox[T](
        self, mensaje: str, opciones: Sequence[Opcion[T]], marcados: Sequence[T] = ()
    ) -> list[T]:
        """Varias opciones de la lista; ``marcados`` son los valores marcados al inicio."""
        ...

    def text(self, mensaje: str, por_defecto: str = "") -> str:
        """Texto libre; ``por_defecto`` aparece ya escrito (o se toma con Enter)."""
        ...

    def password(self, mensaje: str) -> str:
        """Texto oculto, sin eco."""
        ...

    def confirm(self, mensaje: str, por_defecto: bool) -> bool:
        """Sí/no con el estándar ``(Y/n)``: solo se acepta y o n."""
        ...


def enumerar(textos: Sequence[str]) -> str:
    """«y, n o ca»."""
    if len(textos) <= 1:
        return "".join(textos)
    return f"{', '.join(textos[:-1])}{messages.CONJUNCION_O}{textos[-1]}"


def pedir_oculto(mensaje: str, *, err: bool = False) -> str:
    """Entrada oculta sin eco. Enter sin escribir devuelve un texto vacío."""
    return str(typer.prompt(mensaje, default="", show_default=False, hide_input=True, err=err))


class PrompterQuestionary:
    """Listas con flechas (questionary).

    ``terminal`` recibe ``input`` y ``output`` de prompt_toolkit; solo los tests lo usan.
    Las preguntas usan ``unsafe_ask``: Ctrl+C lanza ``KeyboardInterrupt`` en lugar de
    devolver ``None``.
    """

    def __init__(self, **terminal: Any) -> None:
        self._terminal = terminal

    def select[T](
        self,
        mensaje: str,
        opciones: Sequence[Opcion[T] | Separador],
        por_defecto: T | None = None,
    ) -> T:
        # El valor de cada opción es su posición: la respuesta no depende de cómo se
        # comparen los valores.
        eleccion: list[questionary.Choice] = []
        por_indice: dict[int, Opcion[T]] = {}
        defecto: questionary.Choice | None = None
        for indice, opcion in enumerate(opciones):
            if isinstance(opcion, Separador):
                eleccion.append(questionary.Separator(opcion.titulo))
                continue
            choice = questionary.Choice(opcion.titulo, value=indice, disabled=opcion.deshabilitada)
            if por_defecto is not None and opcion.valor == por_defecto:
                defecto = choice
            eleccion.append(choice)
            por_indice[indice] = opcion
        pregunta = questionary.select(mensaje, eleccion, default=defecto, **self._terminal)
        elegida: int = pregunta.unsafe_ask()
        return por_indice[elegida].valor

    def checkbox[T](
        self, mensaje: str, opciones: Sequence[Opcion[T]], marcados: Sequence[T] = ()
    ) -> list[T]:
        eleccion = [
            questionary.Choice(
                opcion.titulo,
                value=indice,
                disabled=opcion.deshabilitada,
                checked=opcion.valor in marcados,
            )
            for indice, opcion in enumerate(opciones)
        ]
        indices = questionary.checkbox(mensaje, eleccion, **self._terminal).unsafe_ask()
        return [opciones[indice].valor for indice in indices]

    def text(self, mensaje: str, por_defecto: str = "") -> str:
        return str(questionary.text(mensaje, default=por_defecto, **self._terminal).unsafe_ask())

    def password(self, mensaje: str) -> str:
        # questionary.password muestra un * por carácter y revelaría la longitud de la clave.
        return pedir_oculto(mensaje)

    def confirm(self, mensaje: str, por_defecto: bool) -> bool:
        # questionary muestra (Y/n) o (y/N) y solo acepta y o n.
        return bool(
            questionary.confirm(mensaje, default=por_defecto, **self._terminal).unsafe_ask()
        )


class PrompterTexto:
    """Preguntas de texto con ``typer.prompt``, para los comandos con flags.

    ``err`` escribe las preguntas en stderr, para dejar stdout limpio (p. ej. con ``--json``).
    """

    def __init__(self, *, err: bool = False) -> None:
        self._err = err

    def _elegibles[T](self, opciones: Sequence[Opcion[T] | Separador]) -> dict[str, Opcion[T]]:
        """Opciones elegibles por su tecla. Toda opción elegible debe tener una."""
        por_tecla: dict[str, Opcion[T]] = {}
        for opcion in opciones:
            if isinstance(opcion, Separador) or opcion.deshabilitada is not None:
                continue
            if opcion.tecla is None:
                raise ValueError(f"La opción «{opcion.titulo}» no tiene tecla.")
            por_tecla[opcion.tecla] = opcion
        return por_tecla

    def _preguntar(self, mensaje: str, por_tecla: dict[str, Opcion[Any]], defecto: str) -> str:
        teclas = messages.SEPARADOR_OPCIONES.join(
            messages.OPCION_CON_TECLA.format(tecla=tecla, titulo=opcion.titulo)
            for tecla, opcion in por_tecla.items()
        )
        respuesta = typer.prompt(
            f"{mensaje} ({teclas})",
            default=defecto or None,
            show_default=bool(defecto),
            err=self._err,
        )
        return str(respuesta).strip().lower()

    def _invalida(self, teclas: Sequence[str]) -> None:
        typer.echo(messages.RESPUESTA_OPCION_INVALIDA.format(opciones=enumerar(teclas)), err=True)

    def select[T](
        self,
        mensaje: str,
        opciones: Sequence[Opcion[T] | Separador],
        por_defecto: T | None = None,
    ) -> T:
        por_tecla = self._elegibles(opciones)
        defecto = next(
            (t for t, o in por_tecla.items() if por_defecto is not None and o.valor == por_defecto),
            "",
        )
        while True:
            respuesta = self._preguntar(mensaje, dict(por_tecla), defecto)
            if respuesta in por_tecla:
                return por_tecla[respuesta].valor
            self._invalida(list(por_tecla))

    def checkbox[T](
        self, mensaje: str, opciones: Sequence[Opcion[T]], marcados: Sequence[T] = ()
    ) -> list[T]:
        por_tecla = self._elegibles(opciones)
        defecto = ",".join(t for t, o in por_tecla.items() if o.valor in marcados)
        while True:
            respuesta = self._preguntar(mensaje, dict(por_tecla), defecto)
            teclas = [tecla.strip() for tecla in respuesta.split(",") if tecla.strip()]
            if all(tecla in por_tecla for tecla in teclas):
                # En el orden de la lista, como questionary.
                return [opcion.valor for tecla, opcion in por_tecla.items() if tecla in teclas]
            self._invalida(list(por_tecla))

    def text(self, mensaje: str, por_defecto: str = "") -> str:
        # Sin valor por defecto, Enter vuelve a preguntar.
        respuesta = typer.prompt(
            mensaje, default=por_defecto or None, show_default=bool(por_defecto), err=self._err
        )
        return str(respuesta)

    def password(self, mensaje: str) -> str:
        return pedir_oculto(mensaje, err=self._err)

    def confirm(self, mensaje: str, por_defecto: bool) -> bool:
        sufijo = messages.SUFIJO_CONFIRMAR_SI if por_defecto else messages.SUFIJO_CONFIRMAR_NO
        while True:
            respuesta = typer.prompt(
                mensaje + sufijo, default="", show_default=False, err=self._err
            )
            respuesta = str(respuesta).strip().lower()
            if not respuesta:
                return por_defecto
            if respuesta == messages.RESPUESTA_SI:
                return True
            if respuesta == messages.RESPUESTA_NO:
                return False
            typer.echo(messages.RESPUESTA_SI_NO_INVALIDA, err=True)
