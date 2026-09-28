"""Exportación a CSV y JSON (§13) y lectura de ObjectId desde un archivo exportado (§11.2)."""

import codecs
import csv
import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from p6cli.core import catalog
from p6cli.core.errors import MotivoUso, UsageError
from p6cli.core.export import (
    Formato,
    escribir_csv,
    escribir_json,
    filas_spread_largo,
    formato_de_ruta,
    leer_ids,
    nombre_archivo,
)
from tests.conftest import leer_fixture


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


# --- Exportación (§13) ---------------------------------------------------------------

AHORA = datetime(2026, 9, 28, 10, 15, 0)
SPREAD = catalog.obtener("spread.activity")
RESPUESTA_SPREAD = json.loads(leer_fixture("activity_spread_ok.json"))


def test_csv_con_bom_coma_y_columnas_en_el_orden_de_fields(tmp_path: Path) -> None:
    filas = [{"Name": "Diseño", "ObjectId": 4835, "Id": "A1"}]

    escrita = escribir_csv(tmp_path / "actividades.csv", filas, ["ObjectId", "Id", "Name"])

    assert escrita == tmp_path / "actividades.csv"
    crudo = escrita.read_bytes()
    assert crudo.startswith(codecs.BOM_UTF8)
    assert crudo.decode("utf-8-sig") == "ObjectId,Id,Name\r\n4835,A1,Diseño\r\n"


def test_csv_valores_nulos_anidados_numeros_y_saltos_de_linea(tmp_path: Path) -> None:
    filas = [
        {
            "Nulo": None,
            "Anidado": {"Tipo": "Fase", "Valor": "Diseño"},
            "Unidades": 40.0,
            "Activo": True,
            "Nota": "línea 1\nlínea 2",
        }
    ]
    columnas = ["Nulo", "Anidado", "Unidades", "Activo", "Nota"]

    escrita = escribir_csv(tmp_path / "valores.csv", filas, columnas)

    with escrita.open(encoding="utf-8-sig", newline="") as archivo:
        leidas = list(csv.reader(archivo))
    assert leidas[1] == [
        "",
        '{"Tipo": "Fase", "Valor": "Diseño"}',
        "40.0",
        "true",
        "línea 1\nlínea 2",
    ]


def test_csv_ignora_claves_extra_y_deja_vacias_las_que_faltan(tmp_path: Path) -> None:
    filas = [{"ObjectId": 1, "Extra": "x"}, {"Id": "A2"}]

    escrita = escribir_csv(tmp_path / "parcial.csv", filas, ["ObjectId", "Id"])

    assert escrita.read_bytes().decode("utf-8-sig") == "ObjectId,Id\r\n1,\r\n,A2\r\n"


def test_el_csv_exportado_sirve_como_origen_de_ids(tmp_path: Path) -> None:
    filas = [{"ObjectId": 4835, "Name": "Uno"}, {"ObjectId": 4845, "Name": "Dos, con coma"}]

    escrita = escribir_csv(tmp_path / "ids.csv", filas, ["Name", "ObjectId"])

    assert leer_ids(escrita) == (4835, 4845)


def test_json_completo_con_indentacion_y_tildes_sin_bom(tmp_path: Path) -> None:
    datos = [{"ObjectId": 1, "Name": "Construcción"}, {"ObjectId": 2, "Codigos": [1, 2]}]

    escrita = escribir_json(tmp_path / "proyectos.json", datos)

    crudo = escrita.read_bytes()
    assert not crudo.startswith(codecs.BOM_UTF8)
    assert crudo.decode("utf-8") == json.dumps(datos, indent=2, ensure_ascii=False) + "\n"
    assert "Construcción" in crudo.decode("utf-8")


def test_nunca_sobrescribe_agrega_sufijo(tmp_path: Path) -> None:
    ruta = tmp_path / "informe.csv"
    ruta.write_text("original", encoding="utf-8")

    segunda = escribir_csv(ruta, [{"A": 1}], ["A"])
    tercera = escribir_csv(ruta, [{"A": 2}], ["A"])

    assert segunda == tmp_path / "informe_2.csv"
    assert tercera == tmp_path / "informe_3.csv"
    assert ruta.read_text(encoding="utf-8") == "original"
    assert segunda.read_bytes().decode("utf-8-sig") == "A\r\n1\r\n"


def test_crea_las_carpetas_que_faltan(tmp_path: Path) -> None:
    escrita = escribir_json(tmp_path / "exports" / "sub" / "datos.json", [])

    assert escrita.read_text(encoding="utf-8") == "[]\n"


@pytest.mark.parametrize(
    ("nombre", "formato"),
    [("datos.csv", Formato.CSV), ("DATOS.JSON", Formato.JSON), ("a.b.json", Formato.JSON)],
)
def test_formato_segun_la_extension(nombre: str, formato: Formato) -> None:
    assert formato_de_ruta(Path(nombre)) is formato


@pytest.mark.parametrize("nombre", ["datos.xlsx", "datos", "datos.csv.bak"])
def test_extension_de_salida_no_soportada(nombre: str) -> None:
    with pytest.raises(UsageError) as capturado:
        formato_de_ruta(Path(nombre))

    assert capturado.value.motivo is MotivoUso.EXTENSION_SALIDA
    assert capturado.value.datos["extensiones"] == ".csv o .json"


def test_nombre_de_archivo_con_marca_de_tiempo() -> None:
    assert nombre_archivo("demo", "activity", Formato.CSV, AHORA) == (
        "demo_activity_20260928-101500.csv"
    )
    assert nombre_archivo("demo", "spread.activity", Formato.JSON, AHORA) == (
        "demo_spread.activity_20260928-101500.json"
    )


def test_error_de_escritura_sin_contexto(tmp_path: Path) -> None:
    (tmp_path / "archivo").write_text("", encoding="utf-8")
    ruta = tmp_path / "archivo" / "datos.csv"

    with pytest.raises(UsageError) as capturado:
        escribir_csv(ruta, [{"A": 1}], ["A"])

    assert capturado.value.motivo is MotivoUso.ARCHIVO_SALIDA_NO_ESCRIBIBLE
    assert capturado.value.datos["ruta"] == str(ruta)
    assert capturado.value.__context__ is None


def test_fallo_a_mitad_borra_el_archivo_parcial(tmp_path: Path) -> None:
    def filas_rotas() -> Iterator[dict[str, object]]:
        yield {"A": 1}
        raise OSError("disco lleno")

    with pytest.raises(UsageError) as capturado:
        escribir_csv(tmp_path / "datos.csv", filas_rotas(), ["A"])

    assert capturado.value.motivo is MotivoUso.ARCHIVO_SALIDA_NO_ESCRIBIBLE
    assert capturado.value.datos["tipo"] == "OSError"
    assert "disco lleno" not in str(capturado.value)
    assert capturado.value.__context__ is None
    assert list(tmp_path.iterdir()) == []


def test_interrupcion_a_mitad_borra_el_archivo_parcial_y_se_propaga(tmp_path: Path) -> None:
    def filas_interrumpidas() -> Iterator[dict[str, object]]:
        yield {"A": 1}
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        escribir_csv(tmp_path / "datos.csv", filas_interrumpidas(), ["A"])

    assert list(tmp_path.iterdir()) == []


def test_spread_en_formato_largo_con_acumulado() -> None:
    resultado = filas_spread_largo(RESPUESTA_SPREAD, SPREAD, ["PlannedLaborUnits"])

    assert resultado is not None
    columnas, filas = resultado
    assert columnas == [
        "ActivityObjectId",
        "StartDate",
        "EndDate",
        "SpreadField",
        "Valor",
        "Acumulado",
    ]
    assert [list(fila.values()) for fila in filas] == [
        [4835, "2026-01-05T00:00:00", "2026-01-11T23:59:59", "PlannedLaborUnits", 40.0, 40.0],
        [4835, "2026-01-12T00:00:00", "2026-01-18T23:59:59", "PlannedLaborUnits", 32.0, 72.0],
        [4845, "2026-01-12T00:00:00", "2026-01-18T23:59:59", "PlannedLaborUnits", 16.0, 16.0],
    ]
    assert all(list(fila) == columnas for fila in filas)


def test_spread_largo_una_fila_por_campo_en_su_orden_y_sin_acumulado() -> None:
    periodo = {"StartDate": "S1", "EndDate": "E1", "ActualLaborUnits": 2.0, "PlannedLaborUnits": 5}
    respuesta = [{"ActivityObjectId": 4835, "Period": [periodo]}]

    resultado = filas_spread_largo(respuesta, SPREAD, ["PlannedLaborUnits", "ActualLaborUnits"])

    assert resultado is not None
    assert [(f["SpreadField"], f["Valor"], f["Acumulado"]) for f in resultado[1]] == [
        ("PlannedLaborUnits", 5, None),
        ("ActualLaborUnits", 2.0, None),
    ]


def test_spread_largo_forma_inesperada_o_respuesta_vacia() -> None:
    assert filas_spread_largo([{"Otra": "forma"}], SPREAD, ["PlannedLaborUnits"]) is None
    vacia = filas_spread_largo([], SPREAD, ["PlannedLaborUnits"])
    assert vacia is not None
    assert vacia[1] == []


def test_spread_largo_a_csv(tmp_path: Path) -> None:
    resultado = filas_spread_largo(RESPUESTA_SPREAD, SPREAD, ["PlannedLaborUnits"])
    assert resultado is not None
    columnas, filas = resultado

    escrita = escribir_csv(tmp_path / "spread.csv", filas, columnas)

    lineas = escrita.read_text(encoding="utf-8-sig").splitlines()
    assert lineas[0] == "ActivityObjectId,StartDate,EndDate,SpreadField,Valor,Acumulado"
    assert lineas[1] == "4835,2026-01-05T00:00:00,2026-01-11T23:59:59,PlannedLaborUnits,40.0,40.0"
    assert len(lineas) == 4
