"""Escritura de resultados en CSV y JSON; lectura de ObjectId desde un archivo exportado.

``leer_ids`` es el origen «Desde un archivo exportado» del formulario spread (§11.2) y de
``p6 spread --ids-from``: un CSV o un JSON con una columna ``ObjectId``.
"""

import csv
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from p6cli.core.catalog import ids_unicos
from p6cli.core.errors import MotivoUso, UsageError

COLUMNA_IDS = "ObjectId"
EXTENSIONES_IDS = (".csv", ".json")
# Excel en español guarda los CSV con punto y coma.
_DELIMITADORES = ",;"


def leer_ids(ruta: Path) -> tuple[int, ...]:
    """ObjectId de la columna ``ObjectId`` de un CSV o JSON, sin repetir y en su orden.

    El CSV se lee con ``utf-8-sig`` (con o sin BOM) y con ``,`` o ``;`` como delimitador.
    El JSON debe ser una lista de objetos. Los errores nunca incluyen el contenido del
    archivo.
    """
    extension = ruta.suffix.lower()
    if extension not in EXTENSIONES_IDS:
        raise UsageError(
            MotivoUso.ARCHIVO_IDS_EXTENSION,
            ruta=str(ruta),
            extensiones=", ".join(EXTENSIONES_IDS),
        )
    try:
        texto = ruta.read_text(encoding="utf-8-sig")
        valores = _valores_csv(texto) if extension == ".csv" else _valores_json(texto)
    except (OSError, UnicodeDecodeError, csv.Error, json.JSONDecodeError) as error:
        fallo = UsageError(
            MotivoUso.ARCHIVO_IDS_ILEGIBLE, ruta=str(ruta), tipo=type(error).__name__
        )
    else:
        if valores is None:
            raise UsageError(MotivoUso.ARCHIVO_IDS_SIN_COLUMNA, ruta=str(ruta), columna=COLUMNA_IDS)
        return ids_unicos(valores)
    # Se lanza fuera del except: el mensaje de la excepción original podría citar el archivo.
    raise fallo


def _valores_csv(texto: str) -> list[str] | None:
    """Valores de la columna ``ObjectId``; ``None`` si el encabezado no la tiene."""
    lineas = texto.splitlines()
    try:
        dialecto: Any = csv.Sniffer().sniff(lineas[0] if lineas else "", _DELIMITADORES)
    except csv.Error:
        # Una sola columna no tiene delimitador que detectar.
        dialecto = csv.excel
    lector = csv.reader(lineas, dialecto)
    encabezado = [nombre.strip() for nombre in next(lector, [])]
    if COLUMNA_IDS not in encabezado:
        return None
    indice = encabezado.index(COLUMNA_IDS)
    return [fila[indice] for fila in lector if len(fila) > indice]


def _valores_json(texto: str) -> list[str] | None:
    """Valores de ``ObjectId`` de una lista de objetos; ``None`` si no tiene esa forma."""
    datos: Any = json.loads(texto)
    if not isinstance(datos, list) or not all(
        isinstance(fila, dict) and COLUMNA_IDS in fila for fila in datos
    ):
        return None
    return _como_texto(fila[COLUMNA_IDS] for fila in datos)


def _como_texto(valores: Iterable[Any]) -> list[str]:
    """Cada valor como texto, para validarlo igual que un ID escrito (1.5 o true no pasan)."""
    return [valor if isinstance(valor, str) else json.dumps(valor) for valor in valores]
