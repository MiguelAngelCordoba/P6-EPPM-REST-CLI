"""Comando ``p6 doctor [NAME]`` (especificación §7 y §12)."""

import pytest
import responses
from typer.testing import CliRunner, Result

from p6cli.cli import messages
from p6cli.cli.app import app
from p6cli.core import profiles, secrets
from p6cli.core.diagnostics import EstadoDiagnostico
from p6cli.core.profiles import Profile, ProfileStore
from p6cli.core.session import token_autenticacion
from tests.conftest import (
    LOGIN_DATABASE_INVALIDA,
    LOGIN_RECHAZADO,
    Simulada,
    error_dns,
    llamadas,
    registrar_p6,
)

CLAVE = "ClaveDePrueba1"
BASE_OTRO = "https://p6ws.example.com/p6ws/restapi"

runner = CliRunner()


@pytest.fixture(autouse=True)
def terminal_ancha(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evita que rich recorte o parta líneas en la salida capturada."""
    monkeypatch.setenv("COLUMNS", "300")


def doctor(*argumentos: str, entrada: str | None = None) -> Result:
    return runner.invoke(app, ["doctor", *argumentos], input=entrada)


def crear(nombre: str = "demo", clave: str | None = CLAVE, **cambios: object) -> None:
    datos: dict[str, object] = {
        "host": "https://localhost:7001",
        "database_name": "orcl",
        "username": "admin",
        **cambios,
    }
    perfil = Profile.desde_toml(nombre, datos)
    if clave is None:
        ProfileStore().agregar(perfil)
    else:
        profiles.crear_perfil(ProfileStore(), perfil, clave)


def test_ok_sale_con_0(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar_p6(http_simulado)

    resultado = doctor("demo")

    assert resultado.exit_code == 0, resultado.output
    assert "OK" in resultado.output
    assert messages.DIAGNOSTICO[EstadoDiagnostico.OK][0] in resultado.output
    assert "/project/fields" in resultado.output
    assert "__p6cli_canary__" in resultado.output


def test_avisa_del_intento_de_login(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar_p6(http_simulado)

    resultado = doctor("demo")

    assert messages.PROBANDO_CONEXION.format(nombre="demo") in resultado.output


def test_fallo_sale_con_1_con_mensaje_y_sugerencia(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar_p6(http_simulado, login=LOGIN_DATABASE_INVALIDA)

    resultado = doctor("demo")

    assert resultado.exit_code == 1
    mensaje, sugerencia = messages.DIAGNOSTICO[EstadoDiagnostico.INVALID_DATABASE]
    assert "INVALID_DATABASE" in resultado.output
    assert mensaje in resultado.output
    assert sugerencia in resultado.output


def test_error_de_red_sale_con_1(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar_p6(http_simulado, login=Simulada(error=error_dns()))

    resultado = doctor("demo")

    assert resultado.exit_code == 1
    assert "NETWORK" in resultado.output
    assert "El host no resuelve." in resultado.output


def test_credencial_rechazada_no_reintenta(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar_p6(http_simulado, login=LOGIN_RECHAZADO)

    resultado = doctor("demo")

    assert resultado.exit_code == 1
    assert "No se reintentará" in resultado.output
    assert llamadas(http_simulado, "POST", "/login") == 1


def test_sin_nombre_usa_el_predeterminado(http_simulado: responses.RequestsMock) -> None:
    crear("demo")
    crear("otro", host="https://p6ws.example.com")
    ProfileStore().marcar_predeterminado("otro")
    registrar_p6(http_simulado, base=BASE_OTRO)

    resultado = doctor()

    assert resultado.exit_code == 0, resultado.output
    assert messages.PROBANDO_CONEXION.format(nombre="otro") in resultado.output


def test_sin_nombre_ni_predeterminado_sale_con_2() -> None:
    resultado = doctor()

    assert resultado.exit_code == 2
    assert "No hay perfil predeterminado" in resultado.output


def test_perfil_inexistente_sale_con_2() -> None:
    resultado = doctor("nada")

    assert resultado.exit_code == 2
    assert "nada" in resultado.output


def test_sin_clave_la_pide_y_no_la_guarda(http_simulado: responses.RequestsMock) -> None:
    crear(clave=None)
    registrar_p6(http_simulado)

    resultado = doctor("demo", entrada=f"{CLAVE}\n")

    assert resultado.exit_code == 0, resultado.output
    assert messages.AVISO_CLAVE_NO_GUARDADA.format(nombre="demo") in resultado.output
    assert http_simulado.calls[0].request.headers["password"] == CLAVE
    assert secrets.leer_clave("demo") is None


def test_sin_backend_de_keyring_sale_con_2(keyring_sin_backend: None) -> None:
    ProfileStore().agregar(
        Profile.desde_toml(
            "demo", {"host": "https://localhost:7001", "database_name": "orcl", "username": "admin"}
        )
    )

    resultado = doctor("demo")

    assert resultado.exit_code == 2
    assert "P6CLI_" in resultado.output


@pytest.mark.parametrize(
    "login", [Simulada(200, "login_ok.json"), LOGIN_RECHAZADO], ids=["ok", "rechazo"]
)
def test_la_clave_nunca_aparece_en_la_salida(
    http_simulado: responses.RequestsMock, login: Simulada
) -> None:
    crear()
    registrar_p6(http_simulado, login=login)

    resultado = doctor("demo")

    assert CLAVE not in resultado.output
    assert token_autenticacion("admin", CLAVE) not in resultado.output


def test_el_cuerpo_no_se_interpreta_como_marcado(http_simulado: responses.RequestsMock) -> None:
    crear()
    registrar_p6(
        http_simulado, login=Simulada(200, cuerpo="[bold]hola[/bold]", content_type="text/html")
    )

    resultado = doctor("demo")

    assert resultado.exit_code == 1
    assert "[bold]hola[/bold]" in resultado.output
