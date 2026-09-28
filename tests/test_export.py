"""Lectura de ObjectId desde un archivo exportado (§11.2, origen «Desde un archivo»)."""

import json
from pathlib import Path

import pytest

from p6cli.core.errors import MotivoUso, UsageError
from p6cli.core.export import leer_ids


def escribir(ruta: Path, contenido: str, codificacion: str = "utf-8") -> Path:
    ruta.write_text(contenido, encoding=codificacion, newline="")
    return ruta


def test_csv_con_comas(tmp_path: Path) -> None:
    ruta = escribir(
        tmp_path / "actividades.csv", "Id,ObjectId,Name\r\nA1,4835,Uno\r\nA2,4845,Dos\r\n"
    )

    assert leer_ids(ruta) == (4835, 4845)


def test_csv_de_excel_con_punto_y_coma_y_bom(tmp_path: Path) -> None:
    contenido = "ObjectId;Name\r\n4835;Diseño\r\n4845;Construcción\r\n4835;Repetida\r\n"
    ruta = escribir(tmp_path / "actividades.CSV", contenido, "utf-8-sig")

    assert leer_ids(ruta) == (4835, 4845)


def test_csv_de_una_sola_columna(tmp_path: Path) -> None:
    ruta = escribir(tmp_path / "ids.csv", "ObjectId\n4835\n\n4845\n")

    assert leer_ids(ruta) == (4835, 4845)


def test_json_lista_de_objetos(tmp_path: Path) -> None:
    datos = [{"ObjectId": 4835, "Id": "A1"}, {"ObjectId": "4845", "Id": "A2"}]
    ruta = escribir(tmp_path / "actividades.json", json.dumps(datos))

    assert leer_ids(ruta) == (4835, 4845)


@pytest.mark.parametrize(
    ("nombre", "contenido"),
    [
        ("sin_columna.csv", "Id,Name\nA1,Uno\n"),
        ("sin_columna.json", '[{"Id": "A1"}]'),
        ("no_es_lista.json", '{"ObjectId": 4835}'),
    ],
)
def test_sin_columna_objectid(tmp_path: Path, nombre: str, contenido: str) -> None:
    ruta = escribir(tmp_path / nombre, contenido)

    with pytest.raises(UsageError) as capturado:
        leer_ids(ruta)

    assert capturado.value.motivo is MotivoUso.ARCHIVO_IDS_SIN_COLUMNA
    assert capturado.value.datos["columna"] == "ObjectId"


def test_extension_no_soportada(tmp_path: Path) -> None:
    ruta = escribir(tmp_path / "ids.xlsx", "ObjectId\n1\n")

    with pytest.raises(UsageError) as capturado:
        leer_ids(ruta)

    assert capturado.value.motivo is MotivoUso.ARCHIVO_IDS_EXTENSION


def test_archivo_inexistente(tmp_path: Path) -> None:
    with pytest.raises(UsageError) as capturado:
        leer_ids(tmp_path / "no_existe.csv")

    assert capturado.value.motivo is MotivoUso.ARCHIVO_IDS_ILEGIBLE
    assert capturado.value.datos["tipo"] == "FileNotFoundError"
    assert capturado.value.__context__ is None


def test_json_invalido_no_repite_el_contenido(tmp_path: Path) -> None:
    ruta = escribir(tmp_path / "roto.json", '[{"ObjectId": 4835, "Nota": "dato-privado"')

    with pytest.raises(UsageError) as capturado:
        leer_ids(ruta)

    assert capturado.value.motivo is MotivoUso.ARCHIVO_IDS_ILEGIBLE
    assert "dato-privado" not in str(capturado.value)


@pytest.mark.parametrize(
    ("nombre", "contenido"),
    [
        ("decimal.csv", "ObjectId\n4835\n1.5\n"),
        ("decimal.json", '[{"ObjectId": 4835}, {"ObjectId": 1.5}]'),
        ("booleano.json", '[{"ObjectId": true}]'),
        ("nulo.json", '[{"ObjectId": null}]'),
    ],
)
def test_valores_invalidos(tmp_path: Path, nombre: str, contenido: str) -> None:
    ruta = escribir(tmp_path / nombre, contenido)

    with pytest.raises(UsageError) as capturado:
        leer_ids(ruta)

    assert capturado.value.motivo is MotivoUso.ID_INVALIDO


def test_archivo_sin_ids(tmp_path: Path) -> None:
    ruta = escribir(tmp_path / "vacio.json", "[]")

    with pytest.raises(UsageError) as capturado:
        leer_ids(ruta)

    assert capturado.value.motivo is MotivoUso.IDS_VACIOS
