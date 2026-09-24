"""Normalización de la URL pegada por el usuario (especificación §5)."""

import pytest

from p6cli.core.errors import ConfigError, MotivoConfig
from p6cli.core.urls import AdvertenciaUrl, normalizar_url


@pytest.mark.parametrize(
    ("entrada", "host", "context"),
    [
        pytest.param(
            "https://p6ws.example.com/p6ws/", "https://p6ws.example.com", "p6ws", id="contexto"
        ),
        pytest.param(
            "https://p6ws.example.com/p6ws/restapi",
            "https://p6ws.example.com",
            "p6ws",
            id="descarta-restapi",
        ),
        pytest.param(
            "https://localhost:7001/p6ws/restapi/login?DatabaseName=orcl",
            "https://localhost:7001",
            "p6ws",
            id="descarta-endpoint-y-query",
        ),
        pytest.param(
            "https://p6ws.example.com",
            "https://p6ws.example.com",
            "p6ws",
            id="contexto-por-defecto",
        ),
        pytest.param("p6ws.example.com/p6ws", "https://p6ws.example.com", "p6ws", id="asume-https"),
        pytest.param(
            "http://p6ws.example.com/p6ws", "http://p6ws.example.com", "p6ws", id="acepta-http"
        ),
    ],
)
def test_casos_de_la_tabla(entrada: str, host: str, context: str) -> None:
    resultado = normalizar_url(entrada)

    assert (resultado.host, resultado.context) == (host, context)


def test_http_advierte_sin_cifrado() -> None:
    resultado = normalizar_url("http://p6ws.example.com/p6ws")

    assert resultado.advertencias == (AdvertenciaUrl.SIN_CIFRADO,)


def test_https_sin_advertencias() -> None:
    assert normalizar_url("https://p6ws.example.com/p6ws").advertencias == ()


@pytest.mark.parametrize(
    "entrada",
    ["https://p6.example.com/p6/action/login", "https://p6.example.com/p6/"],
)
def test_interfaz_web_se_rechaza(entrada: str) -> None:
    with pytest.raises(ConfigError) as error:
        normalizar_url(entrada)

    assert error.value.motivo is MotivoConfig.URL_INTERFAZ_WEB


def test_recorta_espacios() -> None:
    resultado = normalizar_url("  https://p6ws.example.com/p6ws/  \n")

    assert resultado.host == "https://p6ws.example.com"


def test_esquema_y_host_en_minusculas() -> None:
    resultado = normalizar_url("HTTPS://P6WS.Example.COM:7001/p6ws")

    assert resultado.host == "https://p6ws.example.com:7001"


def test_ipv6_conserva_corchetes_y_puerto() -> None:
    resultado = normalizar_url("https://[::1]:7001/p6ws")

    assert resultado.host == "https://[::1]:7001"


def test_contexto_no_estandar() -> None:
    resultado = normalizar_url("https://p6ws.example.com/otro-ws/restapi/project")

    assert resultado.context == "otro-ws"


def test_contexto_sin_restapi_toma_el_primer_segmento() -> None:
    resultado = normalizar_url("https://p6ws.example.com/p6ws/project")

    assert resultado.context == "p6ws"


@pytest.mark.parametrize(
    ("entrada", "motivo"),
    [
        pytest.param("", MotivoConfig.URL_VACIA, id="vacia"),
        pytest.param("   ", MotivoConfig.URL_VACIA, id="solo-espacios"),
        pytest.param("ftp://p6ws.example.com/p6ws", MotivoConfig.URL_ESQUEMA, id="ftp"),
        pytest.param("https:///p6ws", MotivoConfig.URL_SIN_HOST, id="sin-host"),
        pytest.param(
            "https://p6ws.example.com:puerto/p6ws", MotivoConfig.URL_SIN_HOST, id="puerto-invalido"
        ),
    ],
)
def test_entradas_invalidas(entrada: str, motivo: MotivoConfig) -> None:
    with pytest.raises(ConfigError) as error:
        normalizar_url(entrada)

    assert error.value.motivo is motivo


def test_credenciales_incrustadas_se_rechazan_sin_repetirlas() -> None:
    with pytest.raises(ConfigError) as error:
        normalizar_url("https://admin:ClaveSecreta1@p6ws.example.com/p6ws")

    assert error.value.motivo is MotivoConfig.URL_CREDENCIALES
    assert "ClaveSecreta1" not in str(error.value)
    assert "ClaveSecreta1" not in repr(error.value.datos)
    assert error.value.__cause__ is None
