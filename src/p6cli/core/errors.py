"""Jerarquía de excepciones y pistas por código HTTP.

Las excepciones llevan un ``motivo`` y datos no sensibles; los textos para el usuario los
arma la interfaz a partir de ellos (``cli/messages.py``). Ninguna excepción contiene
contraseñas ni valores de ``authToken``.
"""

from enum import StrEnum


class MotivoConfig(StrEnum):
    """Motivos de un error de configuración."""

    URL_VACIA = "url_vacia"
    URL_ESQUEMA = "url_esquema"
    URL_CREDENCIALES = "url_credenciales"
    URL_SIN_HOST = "url_sin_host"
    URL_INTERFAZ_WEB = "url_interfaz_web"
    ARCHIVO_INVALIDO = "archivo_invalido"


class MotivoPerfil(StrEnum):
    """Motivos de un error de perfil."""

    NOMBRE_INVALIDO = "nombre_invalido"
    NOMBRE_RESERVADO = "nombre_reservado"
    CAMPO_INVALIDO = "campo_invalido"
    NO_EXISTE = "no_existe"
    YA_EXISTE = "ya_existe"
    SIN_PREDETERMINADO = "sin_predeterminado"


class MotivoSecreto(StrEnum):
    """Motivos de un error del almacén de credenciales."""

    SIN_BACKEND = "sin_backend"
    ERROR_KEYRING = "error_keyring"


class MotivoAuth(StrEnum):
    """Motivos de un error de autenticación."""

    LOGIN_YA_INTENTADO = "login_ya_intentado"
    CLAVE_NO_CODIFICABLE = "clave_no_codificable"
    LOGIN_FALLIDO = "login_fallido"


class MotivoHTTP(StrEnum):
    """Motivos de un error de comunicación con P6."""

    SIN_RESOLUCION = "sin_resolucion"
    SIN_CONEXION = "sin_conexion"
    TLS = "tls"
    TIEMPO_AGOTADO = "tiempo_agotado"
    CODIGO_HTTP = "codigo_http"
    RESPUESTA_NO_JSON = "respuesta_no_json"
    FORMATO_INESPERADO = "formato_inesperado"


class MotivoUso(StrEnum):
    """Motivos de un error de uso: la consulta no se envía."""

    ENDPOINT_DESCONOCIDO = "endpoint_desconocido"
    PLANTILLA_NO_SOPORTADA = "plantilla_no_soportada"
    CAMPOS_VACIOS = "campos_vacios"
    PARAMETRO_REQUERIDO = "parametro_requerido"
    PARAMETRO_DESCONOCIDO = "parametro_desconocido"
    CAMPO_INVALIDO = "campo_invalido"
    URL_DEMASIADO_LARGA = "url_demasiado_larga"
    METODO_NO_PERMITIDO = "metodo_no_permitido"


class MotivoGuardarrail(StrEnum):
    """Motivos de un bloqueo por guardarraíl."""

    SIN_FILTRO = "sin_filtro"


class P6CliError(Exception):
    """Base de todos los errores del programa."""

    def __init__(self, motivo: StrEnum, **datos: str) -> None:
        self.motivo = motivo
        self.datos = datos
        detalle = ", ".join(f"{clave}={valor}" for clave, valor in datos.items())
        super().__init__(f"{motivo}: {detalle}" if detalle else str(motivo))


class ConfigError(P6CliError):
    """Configuración o URL inválida."""


class ProfileError(P6CliError):
    """Perfil inexistente, duplicado o con datos inválidos."""


class SecretStoreError(P6CliError):
    """Fallo del almacén de credenciales del sistema operativo."""


class AuthError(P6CliError):
    """Login no permitido o imposible de enviar."""


class P6HTTPError(P6CliError):
    """Fallo de comunicación con P6. Lleva método y URL, nunca cabeceras.

    Con ``CODIGO_HTTP`` lleva además ``codigo`` y ``mensaje_p6`` (fragmento del cuerpo); la
    pista por código la arma la interfaz.
    """


class GuardrailError(P6CliError):
    """Consulta bloqueada por un guardarraíl (p. ej. endpoint grande sin filtro)."""


class UsageError(P6CliError):
    """Uso inválido: parámetros, endpoint o verbo no permitido. No se envía nada."""
