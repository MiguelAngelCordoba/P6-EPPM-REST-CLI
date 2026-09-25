"""``Prompter`` con respuestas guionizadas para probar menús y formularios.

Cada respuesta indica el tipo de pregunta que se espera. El guion falla (``AssertionError``)
si llega otra pregunta, si la opción elegida no existe o está deshabilitada, o si se acaba
el guion: un bucle inesperado nunca cuelga un test.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from p6cli.cli.prompter import Opcion, Separador


@dataclass(frozen=True)
class Pregunta:
    """Una pregunta hecha durante el test, con lo que ofrecía."""

    tipo: str
    mensaje: str
    por_defecto: Any = None
    opciones: tuple[Opcion[Any] | Separador, ...] = ()

    def elegibles(self) -> list[Any]:
        """Valores de las opciones que se pueden elegir."""
        return [o.valor for o in self.opciones if isinstance(o, Opcion) and o.deshabilitada is None]

    def deshabilitadas(self) -> list[Any]:
        return [
            o.valor for o in self.opciones if isinstance(o, Opcion) and o.deshabilitada is not None
        ]

    def titulos(self) -> list[str]:
        return [o.titulo for o in self.opciones]


def elegir(valor: object) -> tuple[str, object]:
    return ("select", valor)


def marcar(*valores: object) -> tuple[str, object]:
    return ("checkbox", list(valores))


def escribir(texto: str) -> tuple[str, object]:
    return ("text", texto)


def oculta(texto: str) -> tuple[str, object]:
    return ("password", texto)


def confirmar(respuesta: bool) -> tuple[str, object]:
    return ("confirm", respuesta)


class PrompterGuion:
    """Responde con el guion en orden y registra cada pregunta."""

    def __init__(self, *respuestas: tuple[str, object]) -> None:
        self.respuestas = list(respuestas)
        self.preguntas: list[Pregunta] = []

    @property
    def terminado(self) -> bool:
        return not self.respuestas

    def de_tipo(self, tipo: str) -> list[Pregunta]:
        return [p for p in self.preguntas if p.tipo == tipo]

    def _siguiente(self, pregunta: Pregunta) -> object:
        self.preguntas.append(pregunta)
        assert self.respuestas, f"Guion agotado en {pregunta.tipo}: {pregunta.mensaje!r}"
        tipo, respuesta = self.respuestas.pop(0)
        assert tipo == pregunta.tipo, (
            f"Se esperaba {tipo} y se preguntó {pregunta.tipo}: {pregunta.mensaje!r}"
        )
        return respuesta

    def select[T](
        self,
        mensaje: str,
        opciones: Sequence[Opcion[T] | Separador],
        por_defecto: T | None = None,
    ) -> T:
        pregunta = Pregunta("select", mensaje, por_defecto, tuple(opciones))
        respuesta = self._siguiente(pregunta)
        elegida = next(
            (o for o in opciones if isinstance(o, Opcion) and o.valor == respuesta), None
        )
        assert elegida is not None, f"{respuesta!r} no está entre las opciones de {mensaje!r}"
        assert elegida.deshabilitada is None, f"{respuesta!r} está deshabilitada"
        return elegida.valor

    def checkbox[T](
        self, mensaje: str, opciones: Sequence[Opcion[T]], marcados: Sequence[T] = ()
    ) -> list[T]:
        pregunta = Pregunta("checkbox", mensaje, list(marcados), tuple(opciones))
        respuesta = self._siguiente(pregunta)
        assert isinstance(respuesta, list)
        valores = [o.valor for o in opciones if o.deshabilitada is None]
        assert all(valor in valores for valor in respuesta)
        return [o.valor for o in opciones if o.valor in respuesta]

    def text(self, mensaje: str, por_defecto: str = "") -> str:
        respuesta = self._siguiente(Pregunta("text", mensaje, por_defecto))
        assert isinstance(respuesta, str)
        return respuesta

    def password(self, mensaje: str) -> str:
        respuesta = self._siguiente(Pregunta("password", mensaje))
        assert isinstance(respuesta, str)
        return respuesta

    def confirm(self, mensaje: str, por_defecto: bool) -> bool:
        respuesta = self._siguiente(Pregunta("confirm", mensaje, por_defecto))
        assert isinstance(respuesta, bool)
        return respuesta
