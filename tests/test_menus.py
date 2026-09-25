"""Flujo interactivo (§10): transiciones con un Prompter guionizado y HTTP simulado."""

import json

import keyring
import pytest
import responses

from p6cli import __version__
from p6cli.cli import menus, messages
from p6cli.cli.forms import Confirmacion, Decision, ModoTLS
from p6cli.cli.menus import Accion
from p6cli.core import catalog, profiles, secrets
from p6cli.core.profiles import Profile, ProfileStore
from p6cli.core.session import Sesion
from tests.conftest import (
    BASE,
    LOGIN_OK,
    LOGIN_RECHAZADO,
    KeyringBloqueado,
    Simulada,
    leer_fixture,
    registrar_p6,
)
from tests.guion import Pregunta, PrompterGuion, confirmar, elegir, escribir, oculta

CLAVE = "ClaveDePrueba1"
BASE_OTRO = "https://p6ws.example.com/p6ws/restapi"
FILTRO = "ProjectObjectId:eq:1234"
ACTIVIDADES = Simulada(200, "activity_ok.json")
FILAS_ACTIVIDADES = len(json.loads(leer_fixture("activity_ok.json")))
PROYECTO = catalog.obtener("project")
ACTIVIDAD = catalog.obtener("activity")

EJECUTAR = elegir(Confirmacion.EJECUTAR)
CONTINUAR = elegir(Accion.CONTINUAR)
SALIR = elegir(Accion.SALIR)


@pytest.fixture(autouse=True)
def terminal_ancha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "300")


def crear(nombre: str = "demo", clave: str | None = CLAVE, **cambios: object) -> Profile:
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
    return perfil


def crear_otro() -> Profile:
    return crear("otro", host="https://p6ws.example.com", database_name="P6EPPM")


def ejecutar(*respuestas: tuple[str, object]) -> PrompterGuion:
    guion = PrompterGuion(*respuestas)
    menus.ejecutar(guion)
    assert guion.terminado, f"Quedaron respuestas sin usar: {guion.respuestas}"
    return guion


def llenar(fields: str, filtro: str = "", orden: str = "") -> list[tuple[str, object]]:
    return [escribir(fields), escribir(filtro), escribir(orden)]


def llamadas_a(simulado: responses.RequestsMock, metodo: str, url: str) -> int:
    return sum(
        1
        for llamada in simulado.calls
        if llamada.request.method == metodo and str(llamada.request.url).split("?")[0] == url
    )


def json_simulado(datos: object, codigo: int = 200) -> Simulada:
    return Simulada(codigo, cuerpo=json.dumps(datos), content_type="application/json")


# --- Inicio (§10.1) -----------------------------------------------------------------


def test_inicio_muestra_banner_y_perfiles_con_el_predeterminado_preseleccionado(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = crear()
    crear_otro()

    guion = ejecutar(SALIR)

    assert f"P6 EPPM REST CLI  v{__version__} — solo lectura" in capsys.readouterr().out
    inicio = guion.preguntas[0]
    assert inicio.mensaje == messages.PREGUNTA_AMBIENTE
    assert inicio.por_defecto == demo
    titulos = inicio.titulos()
    assert titulos[0] == "demo   localhost:7001     orcl     (predeterminado)"
    assert titulos[1] == "otro   p6ws.example.com   P6EPPM"
    assert titulos[-3:] == [
        messages.OPCION_AGREGAR,
        messages.OPCION_ADMINISTRAR,
        messages.OPCION_SALIR,
    ]
    assert len(http_simulado.calls) == 0


def test_sin_perfiles_da_la_bienvenida_y_abre_el_asistente_una_sola_vez(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    registrar_p6(http_simulado, login=LOGIN_RECHAZADO)

    guion = ejecutar(
        *alta("demo", "https://localhost:7001/p6ws"),
        elegir(Decision.CANCELAR),
        elegir(Accion.ADMINISTRAR),
        SALIR,
    )

    salida = capsys.readouterr().out
    assert messages.BIENVENIDA in salida
    assert messages.SIN_PERFILES_MENU in salida
    # Tras cancelar, el inicio solo ofrece agregar, administrar y salir.
    assert guion.de_tipo("select")[-1].elegibles() == [
        Accion.AGREGAR,
        Accion.ADMINISTRAR,
        Accion.SALIR,
    ]
    assert ProfileStore().listar() == []


def alta(nombre: str, url: str) -> list[tuple[str, object]]:
    return [
        escribir(nombre),
        escribir(url),
        confirmar(True),
        escribir("orcl"),
        escribir("admin"),
        oculta(CLAVE),
        elegir(ModoTLS.VALIDAR),
    ]


def test_agregar_desde_el_inicio_guarda_perfil_y_clave(
    http_simulado: responses.RequestsMock,
) -> None:
    crear()
    registrar_p6(http_simulado, base=BASE_OTRO)

    guion = ejecutar(elegir(Accion.AGREGAR), *alta("otro", "https://p6ws.example.com/p6ws"), SALIR)

    assert [p.name for p in ProfileStore().listar()] == ["demo", "otro"]
    assert secrets.leer_clave("otro") == CLAVE
    assert "otro   p6ws.example.com" in guion.preguntas[-1].titulos()[1]


# --- Credenciales (§10.2) -------------------------------------------------------------


def test_pantalla_de_credenciales_enmascara_la_clave_y_volver_regresa_al_inicio(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = crear()

    guion = ejecutar(elegir(demo), elegir(Accion.VOLVER), SALIR)

    salida = capsys.readouterr()
    assert "Ambiente : demo   (https://localhost:7001/p6ws · orcl)" in salida.out
    assert "Usuario  : admin" in salida.out
    assert "Clave    : ••••••••" in salida.out
    assert messages.CLAVE_NO_GUARDADA not in salida.out
    assert CLAVE not in salida.out + salida.err
    assert guion.preguntas[1].elegibles() == [Accion.CONTINUAR, Accion.ACTUALIZAR, Accion.VOLVER]
    assert guion.preguntas[2].mensaje == messages.PREGUNTA_AMBIENTE
    assert len(http_simulado.calls) == 0


def test_sin_clave_guardada_la_pide_antes_y_no_la_guarda(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = crear(clave=None)
    registrar_p6(http_simulado)

    guion = ejecutar(elegir(demo), oculta(CLAVE), CONTINUAR, SALIR)

    salida = capsys.readouterr().out
    assert messages.AVISO_CLAVE_SESION.format(nombre="demo") in salida
    assert messages.CLAVE_NO_GUARDADA in salida
    assert guion.preguntas[1].mensaje == messages.PEDIR_CLAVE_TEMPORAL
    assert http_simulado.calls[0].request.headers["password"] == CLAVE
    assert secrets.leer_clave("demo") is None


def test_continuar_hace_un_solo_login_con_diagnostico_y_salir_hace_logout(
    http_simulado: responses.RequestsMock,
) -> None:
    demo = crear()
    registrar_p6(http_simulado)

    guion = ejecutar(elegir(demo), CONTINUAR, SALIR)

    assert llamadas_a(http_simulado, "POST", f"{BASE}/login") == 1
    assert llamadas_a(http_simulado, "GET", f"{BASE}/project/fields") == 1
    assert llamadas_a(http_simulado, "GET", f"{BASE}/__p6cli_canary__") == 1
    assert llamadas_a(http_simulado, "POST", f"{BASE}/logout") == 1
    assert guion.preguntas[-1].mensaje == messages.PREGUNTA_ENDPOINT


def test_login_fallido_muestra_diagnostico_y_no_reintenta(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = crear()
    registrar_p6(http_simulado, login=LOGIN_RECHAZADO)

    guion = ejecutar(elegir(demo), CONTINUAR, elegir(Accion.VOLVER), SALIR)

    assert "CREDENTIALS_REJECTED" in capsys.readouterr().out
    fallo = guion.preguntas[2]
    assert fallo.mensaje == messages.PREGUNTA_LOGIN_FALLIDO
    assert fallo.elegibles() == [Accion.ACTUALIZAR, Accion.VOLVER]
    assert fallo.titulos() == [messages.OPCION_ACTUALIZAR, messages.OPCION_VOLVER_INICIO]
    assert llamadas_a(http_simulado, "POST", f"{BASE}/login") == 1
    assert llamadas_a(http_simulado, "POST", f"{BASE}/logout") == 0


def test_actualizar_tras_un_fallo_guarda_y_sigue_con_la_misma_sesion(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = crear()
    registrar_p6(http_simulado, login=LOGIN_RECHAZADO)
    registrar_p6(http_simulado, login=LOGIN_OK)

    guion = ejecutar(
        elegir(demo),
        CONTINUAR,
        elegir(Accion.ACTUALIZAR),
        escribir("otro-usuario"),
        oculta("ClaveNueva2"),
        SALIR,
    )

    usuario = guion.de_tipo("text")[0]
    assert (usuario.mensaje, usuario.por_defecto) == (messages.PEDIR_USUARIO, "admin")
    assert ProfileStore().obtener("demo").username == "otro-usuario"
    assert secrets.leer_clave("demo") == "ClaveNueva2"
    logins = [c.request for c in http_simulado.calls if c.request.method == "POST"]
    assert [r.headers.get("username") for r in logins] == ["admin", "otro-usuario", None]
    assert llamadas_a(http_simulado, "POST", f"{BASE}/logout") == 1
    salida = capsys.readouterr()
    assert messages.CREDENCIALES_GUARDADAS.format(nombre="demo") in salida.out
    assert "ClaveNueva2" not in salida.out + salida.err
    assert guion.preguntas[-1].mensaje == messages.PREGUNTA_ENDPOINT


def test_actualizar_con_exito_no_repite_el_login(http_simulado: responses.RequestsMock) -> None:
    demo = crear()
    registrar_p6(http_simulado)

    ejecutar(
        elegir(demo), elegir(Accion.ACTUALIZAR), escribir("admin"), oculta("ClaveNueva2"), SALIR
    )

    assert llamadas_a(http_simulado, "POST", f"{BASE}/login") == 1
    assert secrets.leer_clave("demo") == "ClaveNueva2"


def test_actualizar_fallido_no_guarda(http_simulado: responses.RequestsMock) -> None:
    demo = crear()
    registrar_p6(http_simulado, login=LOGIN_RECHAZADO)

    ejecutar(
        elegir(demo),
        elegir(Accion.ACTUALIZAR),
        escribir("otro-usuario"),
        oculta("ClaveMala"),
        elegir(Accion.VOLVER),
        SALIR,
    )

    assert ProfileStore().obtener("demo") == demo
    assert secrets.leer_clave("demo") == CLAVE


def test_keyring_no_disponible_en_credenciales_vuelve_al_inicio(
    keyring_sin_backend: None, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = crear(clave=None)

    ejecutar(elegir(demo), SALIR)

    assert "No hay un almacén de credenciales" in capsys.readouterr().err


# --- Endpoints, consulta y resultados (§10.5 a §10.7) --------------------------------


def test_menu_de_endpoints_agrupado_con_spread_deshabilitado(
    http_simulado: responses.RequestsMock,
) -> None:
    demo = crear()
    registrar_p6(http_simulado)

    guion = ejecutar(elegir(demo), CONTINUAR, SALIR)

    menu = guion.preguntas[-1]
    grupos = [t for t in menu.titulos() if t.startswith("── ")]
    assert grupos == [f"── {grupo} ──" for grupo in catalog.grupos()]
    assert [e.key for e in menu.deshabilitadas()] == [
        "spread.activity",
        "spread.resourceAssignment",
    ]
    assert menu.elegibles()[-2:] == [Accion.CAMBIAR_AMBIENTE, Accion.SALIR]
    assert "activity" in menu.titulos()[menu.titulos().index("── Actividades ──") + 1]


def test_consulta_completa_muestra_resultados_y_nueva_consulta_conserva_los_parametros(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = crear()
    registrar_p6(http_simulado)
    http_simulado.add(ACTIVIDADES.respuesta("GET", f"{BASE}/activity"))

    guion = ejecutar(
        elegir(demo),
        CONTINUAR,
        elegir(ACTIVIDAD),
        *llenar("ObjectId,Id,Name", FILTRO),
        EJECUTAR,
        elegir(Accion.NUEVA_CONSULTA),
        *llenar("ObjectId,Id", FILTRO),
        EJECUTAR,
        elegir(Accion.OTRO_ENDPOINT),
        SALIR,
    )

    salida = capsys.readouterr()
    assert f"activity · {FILAS_ACTIVIDADES} filas ·" in salida.out
    assert "A1010" in salida.out
    resultados = [p for p in guion.preguntas if p.mensaje == messages.PREGUNTA_SIGUIENTE]
    assert resultados[0].deshabilitadas() == [Accion.EXPORTAR_CSV, Accion.EXPORTAR_JSON]
    textos = guion.de_tipo("text")
    assert [t.por_defecto for t in textos[3:]] == ["ObjectId,Id,Name", FILTRO, ""]
    assert guion.preguntas[-1].mensaje == messages.PREGUNTA_ENDPOINT
    assert llamadas_a(http_simulado, "GET", f"{BASE}/activity") == 2
    assert llamadas_a(http_simulado, "POST", f"{BASE}/login") == 1
    assert llamadas_a(http_simulado, "POST", f"{BASE}/logout") == 1
    assert CLAVE not in salida.out + salida.err
    for pregunta in guion.preguntas:
        assert CLAVE not in f"{pregunta.mensaje} {pregunta.por_defecto}"


def test_tabla_muestra_25_filas_con_aviso_del_menu(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = crear()
    registrar_p6(http_simulado)
    filas = [{"ObjectId": numero} for numero in range(30)]
    http_simulado.add(json_simulado(filas).respuesta("GET", f"{BASE}/project"))

    ejecutar(elegir(demo), CONTINUAR, elegir(PROYECTO), *llenar("ObjectId"), EJECUTAR, SALIR)

    salida = capsys.readouterr().out
    assert "Mostrando 25 de 30 filas." in salida
    assert "--max-rows" not in salida


# ObjectId 1001 a 1030: la tabla inicial solo muestra hasta 1025.
TREINTA_FILAS = [{"ObjectId": 1001 + numero, "Id": f"P{numero}"} for numero in range(30)]


def consultar_proyectos(
    http_simulado: responses.RequestsMock, filas: list[dict[str, object]]
) -> list[tuple[str, object]]:
    """Registra P6 y devuelve el guion hasta la tabla de resultados de ``project``."""
    demo = crear()
    registrar_p6(http_simulado)
    http_simulado.add(json_simulado(filas).respuesta("GET", f"{BASE}/project"))
    return [elegir(demo), CONTINUAR, elegir(PROYECTO), *llenar("ObjectId,Id"), EJECUTAR]


def menus_siguiente(guion: PrompterGuion) -> list[Pregunta]:
    return [p for p in guion.preguntas if p.mensaje == messages.PREGUNTA_SIGUIENTE]


def test_ver_la_tabla_completa_muestra_todas_las_filas_y_vuelve_al_menu(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    inicio = consultar_proyectos(http_simulado, TREINTA_FILAS)

    guion = ejecutar(*inicio, elegir(Accion.VER_TABLA), SALIR)

    resultados = menus_siguiente(guion)
    assert len(resultados) == 2
    assert resultados[0].titulos()[:4] == [
        "Ver la tabla completa (30 filas)",
        messages.OPCION_VER_JSON,
        messages.OPCION_EXPORTAR_CSV,
        messages.OPCION_EXPORTAR_JSON,
    ]
    salida = capsys.readouterr().out
    assert salida.count("1025") == 2
    assert salida.count("1030") == 1
    assert llamadas_a(http_simulado, "GET", f"{BASE}/project") == 1


def test_ver_el_json_completo_sin_recortes_y_vuelve_al_menu(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    nombre_largo = "Proyecto de ejemplo con un nombre muy largo que supera el límite de la celda"
    filas: list[dict[str, object]] = [
        {"ObjectId": 1001, "Id": "P1", "Name": nombre_largo},
        {"ObjectId": 1002, "Id": "P2", "Codigos": [{"Tipo": "Fase", "Valor": "Diseño"}]},
    ]
    inicio = consultar_proyectos(http_simulado, filas)

    guion = ejecutar(*inicio, elegir(Accion.VER_JSON), SALIR)

    resultados = menus_siguiente(guion)
    # Con 25 filas o menos la tabla ya está completa: solo se ofrece el JSON.
    assert Accion.VER_TABLA not in resultados[0].elegibles()
    assert resultados[0].elegibles()[0] is Accion.VER_JSON
    assert len(resultados) == 2
    salida = capsys.readouterr().out
    assert f'"Name": "{nombre_largo}"' in salida
    assert '"Valor": "Diseño"' in salida
    assert llamadas_a(http_simulado, "GET", f"{BASE}/project") == 1


def test_sin_filas_no_se_ofrece_la_salida_completa(
    http_simulado: responses.RequestsMock,
) -> None:
    inicio = consultar_proyectos(http_simulado, [])

    guion = ejecutar(*inicio, SALIR)

    opciones = menus_siguiente(guion)[0].elegibles()
    assert Accion.VER_TABLA not in opciones
    assert Accion.VER_JSON not in opciones


def test_salida_completa_grande_pide_confirmacion_por_defecto_no(
    http_simulado: responses.RequestsMock,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(menus, "FILAS_AVISO_SALIDA_COMPLETA", 29)
    inicio = consultar_proyectos(http_simulado, TREINTA_FILAS)

    guion = ejecutar(
        *inicio,
        elegir(Accion.VER_TABLA),
        confirmar(False),
        elegir(Accion.VER_JSON),
        confirmar(True),
        SALIR,
    )

    confirmaciones = guion.de_tipo("confirm")
    assert confirmaciones[0].mensaje == messages.CONFIRMAR_SALIDA_COMPLETA.format(filas="30")
    assert confirmaciones[0].por_defecto is False
    salida = capsys.readouterr().out
    # Con No no se imprimió la tabla; con Sí se imprimió el JSON.
    assert salida.count("1030") == 1
    assert '"ObjectId": 1030' in salida
    assert len(menus_siguiente(guion)) == 3


def test_ver_tabla_y_json_seguidos_sin_repetir_la_consulta(
    http_simulado: responses.RequestsMock,
) -> None:
    inicio = consultar_proyectos(http_simulado, TREINTA_FILAS)

    guion = ejecutar(
        *inicio,
        elegir(Accion.VER_TABLA),
        elegir(Accion.VER_JSON),
        elegir(Accion.OTRO_ENDPOINT),
        SALIR,
    )

    assert len(menus_siguiente(guion)) == 3
    assert guion.preguntas[-1].mensaje == messages.PREGUNTA_ENDPOINT
    assert llamadas_a(http_simulado, "GET", f"{BASE}/project") == 1
    assert llamadas_a(http_simulado, "POST", f"{BASE}/login") == 1


def test_error_de_p6_muestra_pista_y_el_formulario_reaparece_con_lo_escrito(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = crear()
    registrar_p6(http_simulado)
    rechazo = json_simulado({"message": "Foo is not a valid field."}, codigo=400)
    http_simulado.add(rechazo.respuesta("GET", f"{BASE}/activity"))

    guion = ejecutar(
        elegir(demo),
        CONTINUAR,
        elegir(ACTIVIDAD),
        *llenar("Foo", FILTRO, "Id"),
        EJECUTAR,
        *llenar("ObjectId", FILTRO, "Id"),
        elegir(Confirmacion.CANCELAR),
        SALIR,
    )

    error = capsys.readouterr().err
    assert "P6 respondió 400" in error
    assert "Foo is not a valid field." in error
    assert "Revisa nombres en Fields" in error
    assert [t.por_defecto for t in guion.de_tipo("text")[3:]] == ["Foo", FILTRO, "Id"]
    assert llamadas_a(http_simulado, "GET", f"{BASE}/activity") == 1


def test_cancelar_en_la_confirmacion_vuelve_al_menu_de_endpoints(
    http_simulado: responses.RequestsMock,
) -> None:
    demo = crear()
    registrar_p6(http_simulado)

    guion = ejecutar(
        elegir(demo),
        CONTINUAR,
        elegir(PROYECTO),
        *llenar("ObjectId"),
        elegir(Confirmacion.CANCELAR),
        SALIR,
    )

    assert guion.preguntas[-1].mensaje == messages.PREGUNTA_ENDPOINT
    assert llamadas_a(http_simulado, "GET", f"{BASE}/project") == 0


def test_cambiar_ambiente_hace_logout_y_el_otro_perfil_usa_su_base(
    http_simulado: responses.RequestsMock,
) -> None:
    demo = crear()
    otro = crear_otro()
    registrar_p6(http_simulado)
    registrar_p6(http_simulado, base=BASE_OTRO)

    guion = ejecutar(
        elegir(demo),
        CONTINUAR,
        elegir(Accion.CAMBIAR_AMBIENTE),
        elegir(otro),
        CONTINUAR,
        SALIR,
    )

    assert guion.preguntas[3].mensaje == messages.PREGUNTA_AMBIENTE
    posts = [
        str(c.request.url).split("?")[0] for c in http_simulado.calls if c.request.method == "POST"
    ]
    assert posts == [
        f"{BASE}/login",
        f"{BASE}/logout",
        f"{BASE_OTRO}/login",
        f"{BASE_OTRO}/logout",
    ]


def test_cambiar_ambiente_desde_resultados_hace_logout(
    http_simulado: responses.RequestsMock,
) -> None:
    demo = crear()
    registrar_p6(http_simulado)
    http_simulado.add(json_simulado([]).respuesta("GET", f"{BASE}/project"))

    guion = ejecutar(
        elegir(demo),
        CONTINUAR,
        elegir(PROYECTO),
        *llenar("ObjectId"),
        EJECUTAR,
        elegir(Accion.CAMBIAR_AMBIENTE),
        SALIR,
    )

    assert guion.preguntas[-1].mensaje == messages.PREGUNTA_AMBIENTE
    assert llamadas_a(http_simulado, "POST", f"{BASE}/logout") == 1


class Interrumpe(PrompterGuion):
    """Simula Ctrl+C en la primera pregunta de texto."""

    def text(self, mensaje: str, por_defecto: str = "") -> str:
        raise KeyboardInterrupt


def test_ctrl_c_a_mitad_de_consulta_hace_logout(http_simulado: responses.RequestsMock) -> None:
    demo = crear()
    registrar_p6(http_simulado)
    guion = Interrumpe(elegir(demo), CONTINUAR, elegir(PROYECTO))

    with pytest.raises(KeyboardInterrupt):
        menus.ejecutar(guion)

    assert llamadas_a(http_simulado, "POST", f"{BASE}/logout") == 1


# --- Administrar ambientes (§10.4) ----------------------------------------------------


def administrar(
    perfil: Profile, accion: Accion, *resto: tuple[str, object]
) -> list[tuple[str, object]]:
    return [elegir(Accion.ADMINISTRAR), elegir(perfil), elegir(accion), *resto]


def test_administrar_ofrece_las_acciones_de_la_especificacion() -> None:
    demo = crear()

    guion = ejecutar(*administrar(demo, Accion.VOLVER), elegir(Accion.VOLVER), SALIR)

    assert guion.preguntas[2].elegibles() == [
        Accion.EDITAR,
        Accion.PROBAR,
        Accion.PREDETERMINADO,
        Accion.ELIMINAR,
        Accion.VOLVER,
    ]


def test_administrar_editar_usa_el_asistente_con_los_valores_actuales(
    http_simulado: responses.RequestsMock,
) -> None:
    demo = crear()
    registrar_p6(http_simulado)

    guion = ejecutar(
        *administrar(
            demo,
            Accion.EDITAR,
            escribir("demo"),
            escribir("https://localhost:7001/p6ws"),
            confirmar(True),
            escribir("P6EPPM"),
            escribir("admin"),
            oculta(""),
            elegir(ModoTLS.VALIDAR),
        ),
        elegir(Accion.VOLVER),
        SALIR,
    )

    textos = guion.de_tipo("text")
    assert [t.por_defecto for t in textos] == [
        "demo",
        "https://localhost:7001/p6ws",
        "orcl",
        "admin",
    ]
    assert ProfileStore().obtener("demo").database_name == "P6EPPM"
    assert secrets.leer_clave("demo") == CLAVE


def test_administrar_probar_sin_clave_la_pide_y_no_la_guarda(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = crear(clave=None)
    registrar_p6(http_simulado)

    ejecutar(
        *administrar(demo, Accion.PROBAR, oculta(CLAVE)),
        elegir(Accion.VOLVER),
        SALIR,
    )

    salida = capsys.readouterr().out
    assert messages.AVISO_CLAVE_PRUEBA_MENU.format(nombre="demo") in salida
    assert "Diagnóstico · OK" in salida
    assert secrets.leer_clave("demo") is None
    assert llamadas_a(http_simulado, "POST", f"{BASE}/logout") == 1


def test_administrar_marcar_predeterminado() -> None:
    crear()
    otro = crear_otro()

    ejecutar(*administrar(otro, Accion.PREDETERMINADO), elegir(Accion.VOLVER), SALIR)

    assert ProfileStore().predeterminado() == "otro"


def test_administrar_eliminar_por_defecto_no_elimina() -> None:
    demo = crear()

    guion = ejecutar(
        *administrar(demo, Accion.ELIMINAR, confirmar(False)), elegir(Accion.VOLVER), SALIR
    )

    confirmacion = guion.de_tipo("confirm")[0]
    assert confirmacion.mensaje == messages.CONFIRMAR_ELIMINAR.format(nombre="demo")
    assert confirmacion.por_defecto is False
    assert ProfileStore().obtener("demo") == demo


def test_administrar_eliminar_borra_perfil_y_clave(capsys: pytest.CaptureFixture[str]) -> None:
    demo = crear()
    crear_otro()

    ejecutar(*administrar(demo, Accion.ELIMINAR, confirmar(True)), elegir(Accion.VOLVER), SALIR)

    assert [p.name for p in ProfileStore().listar()] == ["otro"]
    assert secrets.leer_clave("demo") is None
    assert messages.SIN_PREDETERMINADO_MENU in capsys.readouterr().out


def test_administrar_error_de_keyring_se_muestra_y_vuelve_al_menu(
    capsys: pytest.CaptureFixture[str],
) -> None:
    demo = crear()
    crear_otro()
    keyring.set_keyring(KeyringBloqueado())

    guion = ejecutar(
        *administrar(demo, Accion.ELIMINAR, confirmar(True)), elegir(Accion.VOLVER), SALIR
    )

    assert "El almacén de credenciales del sistema falló (KeyringLocked)" in capsys.readouterr().err
    assert guion.preguntas[-2].mensaje == messages.PREGUNTA_ADMINISTRAR


# --- Errores durante el flujo ---------------------------------------------------------


def test_error_al_guardar_un_perfil_nuevo_vuelve_al_inicio(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    keyring.set_keyring(KeyringBloqueado())
    registrar_p6(http_simulado)

    guion = ejecutar(*alta("demo", "https://localhost:7001/p6ws"), SALIR)

    assert "El almacén de credenciales del sistema falló (KeyringLocked)" in capsys.readouterr().err
    assert guion.preguntas[-1].mensaje == messages.PREGUNTA_AMBIENTE
    assert ProfileStore().listar() == []


def test_clave_no_codificable_no_envia_nada_y_ofrece_actualizar(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = crear(clave="Clave€")
    registrar_p6(http_simulado)

    guion = ejecutar(elegir(demo), CONTINUAR, elegir(Accion.VOLVER), SALIR)

    assert "no se pueden enviar en una cabecera HTTP" in capsys.readouterr().err
    assert guion.preguntas[2].mensaje == messages.PREGUNTA_LOGIN_FALLIDO
    assert len(http_simulado.calls) == 0


def test_ctrl_c_durante_la_prueba_de_conexion_cierra_la_sesion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    demo = crear()
    cerradas: list[Sesion] = []
    cerrar_original = Sesion.cerrar

    def cerrar(sesion: Sesion) -> None:
        cerradas.append(sesion)
        cerrar_original(sesion)

    def interrumpir(_: Sesion) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(Sesion, "cerrar", cerrar)
    monkeypatch.setattr(menus, "diagnosticar", interrumpir)

    with pytest.raises(KeyboardInterrupt):
        menus.ejecutar(PrompterGuion(elegir(demo), CONTINUAR))

    assert len(cerradas) == 1


def test_actualizar_con_error_al_guardar_sigue_conectado_sin_cambiar_el_perfil(
    http_simulado: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    demo = crear()
    keyring.set_keyring(KeyringBloqueado())
    registrar_p6(http_simulado)

    guion = ejecutar(
        elegir(demo),
        oculta(CLAVE),
        elegir(Accion.ACTUALIZAR),
        escribir("otro-usuario"),
        oculta("ClaveNueva2"),
        SALIR,
    )

    assert "El almacén de credenciales del sistema falló (KeyringLocked)" in capsys.readouterr().err
    assert ProfileStore().obtener("demo") == demo
    assert guion.preguntas[-1].mensaje == messages.PREGUNTA_ENDPOINT
    assert llamadas_a(http_simulado, "POST", f"{BASE}/logout") == 1
