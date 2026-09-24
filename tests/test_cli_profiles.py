"""Comandos ``p6 profiles ...`` (especificación §12, sin prueba de conexión hasta M3)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from p6cli.cli import messages
from p6cli.cli.app import app
from p6cli.core import profiles, secrets
from p6cli.core.profiles import Profile, ProfileStore

CLAVE = "ClaveDePrueba1"
MASCARA = "••••••••"

runner = CliRunner()


@pytest.fixture(autouse=True)
def terminal_ancha(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evita que rich recorte columnas en la salida capturada."""
    monkeypatch.setenv("COLUMNS", "200")


def invocar(*argumentos: str, entrada: str | None = None) -> Result:
    return runner.invoke(app, ["profiles", *argumentos], input=entrada)


def respuestas(*lineas: str) -> str:
    return "".join(f"{linea}\n" for linea in lineas)


def perfil(nombre: str = "demo", **cambios: object) -> Profile:
    datos: dict[str, object] = {
        "host": "https://localhost:7001",
        "database_name": "orcl",
        "username": "admin",
        **cambios,
    }
    return Profile.desde_toml(nombre, datos)


def crear(nombre: str = "demo", clave: str | None = CLAVE, **cambios: object) -> None:
    store = ProfileStore()
    if clave is None:
        store.agregar(perfil(nombre, **cambios))
    else:
        profiles.crear_perfil(store, perfil(nombre, **cambios), clave)


# Respuestas de un alta completa: nombre, URL, confirmación, DatabaseName, usuario, clave, TLS.
ALTA_DEMO = respuestas(
    "demo", "https://localhost:7001/p6ws/restapi", "", "orcl", "admin", CLAVE, ""
)


# --- list -------------------------------------------------------------------


def test_list_sin_perfiles() -> None:
    resultado = invocar("list")

    assert resultado.exit_code == 0
    assert messages.SIN_PERFILES in resultado.output


def test_list_muestra_perfiles_con_clave_enmascarada() -> None:
    crear("demo")
    crear("otro", host="https://p6ws.example.com", database_name="P6EPPM")

    resultado = invocar("list")

    assert resultado.exit_code == 0
    assert "demo" in resultado.output
    assert "p6ws.example.com" in resultado.output
    assert "P6EPPM" in resultado.output
    assert resultado.output.count(MASCARA) == 2
    assert CLAVE not in resultado.output


def test_list_muestra_el_modo_tls() -> None:
    crear("validado")
    crear("sin-validar", verify_ssl=False)
    crear("con-ca", verify_ssl="C:/certs/ca.pem")

    resultado = invocar("list")

    lineas = resultado.output.splitlines()
    assert messages.TLS_VALIDADO in next(linea for linea in lineas if " validado " in linea)
    assert messages.TLS_SIN_VALIDAR in next(linea for linea in lineas if " sin-validar " in linea)
    assert messages.TLS_CA_PROPIA in next(linea for linea in lineas if " con-ca " in linea)


def test_list_marca_el_predeterminado() -> None:
    crear("demo")
    crear("otro")

    resultado = invocar("list")

    linea_demo = next(linea for linea in resultado.output.splitlines() if " demo " in linea)
    linea_otro = next(linea for linea in resultado.output.splitlines() if " otro " in linea)
    assert messages.MARCA_PREDETERMINADO in linea_demo
    assert messages.MARCA_PREDETERMINADO not in linea_otro


def test_list_perfil_sin_clave() -> None:
    crear("demo", clave=None)

    resultado = invocar("list")

    assert messages.CLAVE_AUSENTE in resultado.output
    assert MASCARA not in resultado.output


def test_list_sin_backend_no_falla(keyring_sin_backend: None) -> None:
    ProfileStore().agregar(perfil())

    resultado = invocar("list")

    assert resultado.exit_code == 0
    assert messages.CLAVE_KEYRING_NO_DISPONIBLE in resultado.output


def test_list_archivo_invalido_sale_con_2(dir_config: Path) -> None:
    dir_config.mkdir(parents=True)
    (dir_config / "profiles.toml").write_text("[[[", encoding="utf-8")

    resultado = invocar("list")

    assert resultado.exit_code == 2
    assert "profiles.toml" in resultado.output


# --- add --------------------------------------------------------------------


def test_add_guarda_perfil_y_clave() -> None:
    resultado = invocar("add", entrada=ALTA_DEMO)

    assert resultado.exit_code == 0, resultado.output
    store = ProfileStore()
    assert store.obtener("demo") == perfil()
    assert store.predeterminado() == "demo"
    assert secrets.leer_clave("demo") == CLAVE
    assert "Host: https://localhost:7001 · Contexto: p6ws" in resultado.output
    assert "¿Correcto? (Y/n)" in resultado.output
    assert CLAVE not in resultado.output


def test_add_no_muestra_el_aviso_de_edicion() -> None:
    resultado = invocar("add", entrada=ALTA_DEMO)

    assert messages.AVISO_EDITAR not in resultado.output


def test_add_url_http_advierte() -> None:
    entrada = respuestas("demo", "http://p6ws.example.com/p6ws", "", "orcl", "admin", CLAVE, "")

    resultado = invocar("add", entrada=entrada)

    assert resultado.exit_code == 0
    assert messages.ADVERTENCIA_SIN_CIFRADO in resultado.output
    assert ProfileStore().obtener("demo").host == "http://p6ws.example.com"


def test_add_url_de_interfaz_web_repregunta() -> None:
    entrada = respuestas(
        "demo",
        "https://p6.example.com/p6/action/login",
        "https://p6ws.example.com/p6ws",
        "",
        "orcl",
        "admin",
        CLAVE,
        "",
    )

    resultado = invocar("add", entrada=entrada)

    assert resultado.exit_code == 0
    assert "interfaz web" in resultado.output
    assert ProfileStore().obtener("demo").host == "https://p6ws.example.com"


def test_add_normalizacion_rechazada_repregunta() -> None:
    entrada = respuestas(
        "demo",
        "https://p6ws.example.com/otro",
        "n",
        "https://p6ws.example.com/p6ws",
        "",
        "orcl",
        "admin",
        CLAVE,
        "",
    )

    resultado = invocar("add", entrada=entrada)

    assert resultado.exit_code == 0
    assert ProfileStore().obtener("demo").context == "p6ws"


def test_add_nombre_invalido_repregunta() -> None:
    entrada = "Demo\n" + ALTA_DEMO

    resultado = invocar("add", entrada=entrada)

    assert resultado.exit_code == 0
    assert "no válido" in resultado.output
    assert [p.name for p in ProfileStore().listar()] == ["demo"]


def test_add_nombre_existente_repregunta() -> None:
    crear("demo")
    entrada = respuestas(
        "demo", "otro", "https://localhost:7001/p6ws", "", "orcl", "admin", CLAVE, ""
    )

    resultado = invocar("add", entrada=entrada)

    assert resultado.exit_code == 0
    assert "Ya existe" in resultado.output
    assert [p.name for p in ProfileStore().listar()] == ["demo", "otro"]


def test_add_datos_vacios_repreguntan() -> None:
    entrada = respuestas(
        "demo", "https://localhost:7001/p6ws", "", "   ", "orcl", "  ", "admin", "", CLAVE, ""
    )

    resultado = invocar("add", entrada=entrada)

    assert resultado.exit_code == 0
    assert messages.DATO_OBLIGATORIO in resultado.output
    assert messages.CLAVE_VACIA in resultado.output
    assert ProfileStore().obtener("demo") == perfil()


def test_add_tls_desactivado() -> None:
    entrada = respuestas("demo", "https://localhost:7001/p6ws", "", "orcl", "admin", CLAVE, "n")

    resultado = invocar("add", entrada=entrada)

    assert resultado.exit_code == 0
    assert messages.ADVERTENCIA_TLS_DESACTIVADO in resultado.output
    assert ProfileStore().obtener("demo").verify_ssl is False


def test_add_tls_acepta_y_en_mayuscula() -> None:
    entrada = respuestas("demo", "https://localhost:7001/p6ws", "", "orcl", "admin", CLAVE, "Y")

    resultado = invocar("add", entrada=entrada)

    assert resultado.exit_code == 0
    assert ProfileStore().obtener("demo").verify_ssl is True


@pytest.mark.parametrize("invalida", ["tal vez", "si", "s", "yes", "no"])
def test_add_tls_opcion_invalida_repregunta(invalida: str) -> None:
    entrada = respuestas(
        "demo", "https://localhost:7001/p6ws", "", "orcl", "admin", CLAVE, invalida, "y"
    )

    resultado = invocar("add", entrada=entrada)

    assert resultado.exit_code == 0
    assert messages.OPCION_TLS_INVALIDA in resultado.output
    assert ProfileStore().obtener("demo").verify_ssl is True


def test_add_tls_con_ca_propia(tmp_path: Path) -> None:
    ca = tmp_path / "ca.pem"
    ca.write_text("no es un certificado real", encoding="utf-8")
    inexistente = tmp_path / "no-existe.pem"
    entrada = respuestas(
        "demo",
        "https://localhost:7001/p6ws",
        "",
        "orcl",
        "admin",
        CLAVE,
        "ca",
        str(inexistente),
        str(ca),
    )

    resultado = invocar("add", entrada=entrada)

    assert resultado.exit_code == 0
    assert "No se encontró el archivo" in resultado.output
    assert ProfileStore().obtener("demo").verify_ssl == str(ca.resolve())


def test_add_sin_backend_sale_con_2_y_no_guarda(keyring_sin_backend: None) -> None:
    resultado = invocar("add", entrada=ALTA_DEMO)

    assert resultado.exit_code == 2
    assert "P6CLI_" in resultado.output
    assert ProfileStore().listar() == []


def test_add_no_acepta_flag_de_clave() -> None:
    resultado = invocar("add", "--password", CLAVE)

    assert resultado.exit_code == 2
    assert ProfileStore().listar() == []


def test_add_segundo_perfil_no_es_predeterminado() -> None:
    crear("demo")
    entrada = respuestas("otro", "https://localhost:7001/p6ws", "", "orcl", "admin", CLAVE, "")

    resultado = invocar("add", entrada=entrada)

    assert resultado.exit_code == 0
    assert ProfileStore().predeterminado() == "demo"


# --- edit -------------------------------------------------------------------

CONSERVAR_TODO = respuestas("", "", "", "", "", "", "")


def test_edit_avisa_una_vez_que_enter_conserva() -> None:
    crear("demo")

    resultado = invocar("edit", "demo", entrada=CONSERVAR_TODO)

    assert resultado.exit_code == 0
    assert resultado.output.count(messages.AVISO_EDITAR) == 1
    assert resultado.output.startswith(messages.AVISO_EDITAR)


def test_edit_enter_en_todo_conserva() -> None:
    crear("demo", verify_ssl=False)

    resultado = invocar("edit", "demo", entrada=CONSERVAR_TODO)

    assert resultado.exit_code == 0, resultado.output
    assert ProfileStore().obtener("demo") == perfil(verify_ssl=False)
    assert secrets.leer_clave("demo") == CLAVE
    assert CLAVE not in resultado.output


def test_edit_conserva_campos_avanzados() -> None:
    crear("demo", timeout=60, id_chunk_size=50, throttle_seconds=1.0)

    resultado = invocar("edit", "demo", entrada=CONSERVAR_TODO)

    assert resultado.exit_code == 0
    editado = ProfileStore().obtener("demo")
    assert (editado.timeout, editado.id_chunk_size, editado.throttle_seconds) == (60, 50, 1.0)


def test_edit_renombra_y_mueve_clave_y_predeterminado() -> None:
    crear("demo")
    crear("otro")

    resultado = invocar("edit", "demo", entrada=respuestas("nuevo", "", "", "", "", "", ""))

    assert resultado.exit_code == 0
    store = ProfileStore()
    assert [p.name for p in store.listar()] == ["nuevo", "otro"]
    assert store.predeterminado() == "nuevo"
    assert secrets.leer_clave("nuevo") == CLAVE
    assert secrets.leer_clave("demo") is None


def test_edit_cambia_datos_y_clave() -> None:
    crear("demo")
    entrada = respuestas("", "https://p6ws.example.com/p6ws", "", "P6EPPM", "", "ClaveNueva2", "")

    resultado = invocar("edit", "demo", entrada=entrada)

    assert resultado.exit_code == 0
    editado = ProfileStore().obtener("demo")
    assert (editado.host, editado.database_name) == ("https://p6ws.example.com", "P6EPPM")
    assert secrets.leer_clave("demo") == "ClaveNueva2"
    assert "ClaveNueva2" not in resultado.output


def test_edit_con_ca_propia_la_ofrece_por_defecto(tmp_path: Path) -> None:
    ca = tmp_path / "ca.pem"
    ca.write_text("no es un certificado real", encoding="utf-8")
    crear("demo", verify_ssl=str(ca))

    resultado = invocar("edit", "demo", entrada=respuestas("", "", "", "", "", "", "", ""))

    assert resultado.exit_code == 0
    assert ProfileStore().obtener("demo").verify_ssl == str(ca.resolve())


def test_edit_inexistente_sale_con_2() -> None:
    resultado = invocar("edit", "nada")

    assert resultado.exit_code == 2
    assert "nada" in resultado.output


# --- remove -----------------------------------------------------------------


def test_remove_con_confirmacion() -> None:
    crear("demo")

    resultado = invocar("remove", "demo", entrada="y\n")

    assert resultado.exit_code == 0
    assert "(y/N)" in resultado.output
    assert ProfileStore().listar() == []
    assert secrets.leer_clave("demo") is None


def test_remove_acepta_y_en_mayuscula() -> None:
    crear("demo")

    resultado = invocar("remove", "demo", entrada="Y\n")

    assert resultado.exit_code == 0
    assert ProfileStore().listar() == []


@pytest.mark.parametrize("invalida", ["quizas", "s", "si", "sí", "yes", "no"])
def test_remove_solo_acepta_y_o_n(invalida: str) -> None:
    crear("demo")

    resultado = invocar("remove", "demo", entrada=f"{invalida}\nn\n")

    assert resultado.exit_code == 0
    assert messages.RESPUESTA_SI_NO_INVALIDA in resultado.output
    assert [p.name for p in ProfileStore().listar()] == ["demo"]


def test_remove_por_defecto_no_elimina() -> None:
    crear("demo")

    resultado = invocar("remove", "demo", entrada="\n")

    assert resultado.exit_code == 0
    assert messages.CANCELADO in resultado.output
    assert [p.name for p in ProfileStore().listar()] == ["demo"]
    assert secrets.leer_clave("demo") == CLAVE


def test_remove_con_yes_no_pregunta() -> None:
    crear("demo")
    crear("otro")

    resultado = invocar("remove", "otro", "--yes")

    assert resultado.exit_code == 0
    assert [p.name for p in ProfileStore().listar()] == ["demo"]
    assert secrets.leer_clave("otro") is None


def test_remove_predeterminado_avisa() -> None:
    crear("demo")
    crear("otro")

    resultado = invocar("remove", "demo", "--yes")

    assert resultado.exit_code == 0
    assert messages.SIN_PREDETERMINADO in resultado.output
    assert ProfileStore().predeterminado() is None


def test_remove_inexistente_sale_con_2() -> None:
    resultado = invocar("remove", "nada", "--yes")

    assert resultado.exit_code == 2


# --- default ----------------------------------------------------------------


def test_default_cambia_el_predeterminado() -> None:
    crear("demo")
    crear("otro")

    resultado = invocar("default", "otro")

    assert resultado.exit_code == 0
    assert ProfileStore().predeterminado() == "otro"


def test_default_inexistente_sale_con_2() -> None:
    resultado = invocar("default", "nada")

    assert resultado.exit_code == 2
    assert "nada" in resultado.output
