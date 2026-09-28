"""Escritura de resultados en CSV y JSON; lectura de ObjectId desde un archivo exportado.

La exportación (§13) nunca sobrescribe: si el archivo existe se agrega un sufijo (``_2``,
``_3``…) y se devuelve la ruta realmente escrita. El CSV va en UTF-8 con BOM, delimitado por
coma; el JSON, completo, con indentación 2 y sin escapar tildes.

``leer_ids`` es el origen «Desde un archivo exportado» del formulario spread (§11.2) y de
``p6 spread --ids-from``: un CSV o un JSON con una columna ``ObjectId``.
"""

import contextlib
import csv
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, TextIO

from p6cli.core.catalog import END_DATE, START_DATE, Endpoint, ids_unicos
from p6cli.core.client import Fila, filas_por_periodo
from p6cli.core.errors import MotivoUso, UsageError

COLUMNA_IDS = "ObjectId"
EXTENSIONES_IDS = (".csv", ".json")
# Excel en español guarda los CSV con punto y coma.
_DELIMITADORES = ",;"


class Formato(StrEnum):
    """Formatos de exportación; el valor es la extensión del archivo."""

    CSV = "csv"
    JSON = "json"


# Carpeta por defecto en el menú (§13), dentro del directorio de trabajo.
CARPETA_EXPORTACION = Path("exports")
# BOM en el CSV para que Excel en Windows muestre bien las tildes.
_CODIFICACION = {Formato.CSV: "utf-8-sig", Formato.JSON: "utf-8"}

# Columnas propias del spread en formato largo; las demás son las de la respuesta de P6.
COLUMNA_CAMPO = "SpreadField"
COLUMNA_VALOR = "Valor"
COLUMNA_ACUMULADO = "Acumulado"


# --- Exportación -----------------------------------------------------------------


def formato_de_ruta(ruta: Path) -> Formato:
    """Formato según la extensión (``.csv`` o ``.json``, sin distinguir mayúsculas)."""
    try:
        return Formato(ruta.suffix.lower().removeprefix("."))
    except ValueError:
        extensiones = " o ".join(f".{formato}" for formato in Formato)
        raise UsageError(
            MotivoUso.EXTENSION_SALIDA, ruta=str(ruta), extensiones=extensiones
        ) from None


def nombre_archivo(perfil: str, endpoint: str, formato: Formato, ahora: datetime) -> str:
    """``{perfil}_{endpoint}_{AAAAMMDD-HHMMSS}.{ext}``; la carpeta la elige el usuario."""
    return f"{perfil}_{endpoint}_{ahora:%Y%m%d-%H%M%S}.{formato}"


def escribir_csv(ruta: Path, filas: Iterable[Mapping[str, Any]], columnas: Sequence[str]) -> Path:
    """Escribe las filas con las columnas en el orden dado; devuelve la ruta escrita.

    Las claves que no están en ``columnas`` se ignoran y las que faltan quedan vacías.
    """

    def volcar(archivo: TextIO) -> None:
        escritor = csv.writer(archivo)
        escritor.writerow(columnas)
        escritor.writerows(
            [_texto_csv(fila.get(columna)) for columna in columnas] for fila in filas
        )

    return _escribir(ruta, _CODIFICACION[Formato.CSV], volcar)


def escribir_json(ruta: Path, datos: Sequence[Any]) -> Path:
    """Escribe la lista completa como JSON; devuelve la ruta escrita."""
    texto = json.dumps(list(datos), indent=2, ensure_ascii=False) + "\n"
    return _escribir(ruta, _CODIFICACION[Formato.JSON], lambda archivo: archivo.write(texto))


def filas_spread_largo(
    respuesta: Sequence[Fila], endpoint: Endpoint, campos: Sequence[str]
) -> tuple[list[str], list[Fila]] | None:
    """Spread en formato largo: una fila por objeto, período y campo pedido.

    Columnas: el ObjectId del objeto, StartDate y EndDate del período, ``SpreadField``,
    ``Valor`` y ``Acumulado`` (vacío si la respuesta no trae ``Cumulative<campo>``). Devuelve
    ``None`` si la respuesta no tiene la forma documentada por Oracle.
    """
    tabla = filas_por_periodo(respuesta, endpoint, campos)
    if tabla is None:
        return None
    columnas_periodo, filas_periodo = tabla
    nombre_ids = columnas_periodo[0]
    columnas = [nombre_ids, START_DATE, END_DATE, COLUMNA_CAMPO, COLUMNA_VALOR, COLUMNA_ACUMULADO]
    filas = [
        {
            nombre_ids: fila[nombre_ids],
            START_DATE: fila[START_DATE],
            END_DATE: fila[END_DATE],
            COLUMNA_CAMPO: campo,
            COLUMNA_VALOR: fila[campo],
            COLUMNA_ACUMULADO: fila.get(f"Cumulative{campo}"),
        }
        for fila in filas_periodo
        for campo in campos
    ]
    return columnas, filas


def _texto_csv(valor: Any) -> str:
    """Nulo vacío, texto tal cual y cualquier otro valor como JSON (``40.0``, ``true``)."""
    if valor is None:
        return ""
    if isinstance(valor, str):
        return valor
    return json.dumps(valor, ensure_ascii=False)


def _escribir(ruta: Path, codificacion: str, volcar: Callable[[TextIO], object]) -> Path:
    """Crea las carpetas que falten y escribe en una ruta libre; nunca sobrescribe.

    Un fallo borra el archivo a medio escribir. El error se lanza fuera del ``except``, sin
    la excepción original.
    """
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        destino, archivo = _abrir_libre(ruta, codificacion)
    except OSError as error:
        fallo = UsageError(
            MotivoUso.ARCHIVO_SALIDA_NO_ESCRIBIBLE, ruta=str(ruta), tipo=type(error).__name__
        )
    else:
        try:
            with archivo:
                volcar(archivo)
        except OSError as error:
            fallo = UsageError(
                MotivoUso.ARCHIVO_SALIDA_NO_ESCRIBIBLE,
                ruta=str(destino),
                tipo=type(error).__name__,
            )
            _borrar(destino)
        except BaseException:
            _borrar(destino)
            raise
        else:
            return destino
    raise fallo


def _abrir_libre(ruta: Path, codificacion: str) -> tuple[Path, TextIO]:
    """Abre ``ruta`` o, si existe, ``<nombre>_2``, ``_3``… en modo exclusivo.

    El modo ``x`` falla si el archivo existe: no hay carrera entre comprobar y escribir.
    """
    candidata = ruta
    numero = 1
    while True:
        try:
            return candidata, candidata.open("x", encoding=codificacion, newline="")
        except FileExistsError:
            numero += 1
            candidata = ruta.with_name(f"{ruta.stem}_{numero}{ruta.suffix}")


def _borrar(ruta: Path) -> None:
    with contextlib.suppress(OSError):
        ruta.unlink(missing_ok=True)


# --- Lectura de ObjectId ---------------------------------------------------------


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
