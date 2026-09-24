"""Todos los textos visibles para el usuario, en español."""

from enum import StrEnum

from p6cli.core.diagnostics import EstadoDiagnostico
from p6cli.core.errors import MotivoAuth, MotivoConfig, MotivoHTTP, MotivoPerfil, MotivoSecreto

AYUDA_APP = "Cliente de terminal, de solo lectura, para la API REST de Oracle Primavera P6 EPPM."
AYUDA_VERSION = "Muestra la versión y termina."

VERSION = "p6cli {version}"

AVISO_SIN_MENUS = (
    "El modo interactivo aún no está disponible. Usa `p6 --help` para ver las opciones."
)

# --- Perfiles: ayuda de comandos ---------------------------------------------

AYUDA_PERFILES = "Administra los ambientes de P6 guardados (perfiles)."
AYUDA_PERFILES_LIST = "Lista los perfiles guardados (la clave se muestra enmascarada)."
AYUDA_PERFILES_ADD = "Asistente para agregar un perfil (la clave se pide oculta)."
AYUDA_PERFILES_EDIT = "Edita un perfil; Enter conserva cada valor actual."
AYUDA_PERFILES_REMOVE = "Elimina un perfil y su clave guardada."
AYUDA_PERFILES_DEFAULT = "Marca un perfil como predeterminado."
AYUDA_ARG_NOMBRE = "Nombre del perfil."
AYUDA_YES = "No pide confirmación."

# --- Perfiles: asistente -----------------------------------------------------

PEDIR_NOMBRE = "Nombre del ambiente (ej. cliente-prod)"
PEDIR_URL = "URL de P6 Web Services (pega la URL completa)"
URL_NORMALIZADA = "  → Host: {host} · Contexto: {context}"
CONFIRMAR_URL = "¿Correcto?"
PEDIR_DATABASE = "DatabaseName"
PEDIR_USUARIO = "Usuario"
PEDIR_CLAVE = "Clave (oculta)"
PEDIR_CLAVE_EDITAR = "Clave (oculta; Enter para conservar la actual)"
PEDIR_TLS = "¿Validar el certificado TLS? (y = sí · n = no · ca = usar CA propia .pem)"
PEDIR_CA = "Ruta al archivo .pem de la CA"
AVISO_EDITAR = "Presiona Enter en cada campo para conservar su valor actual."

DATO_OBLIGATORIO = "Este dato es obligatorio."
CLAVE_VACIA = "La clave no puede estar vacía."
OPCION_TLS_INVALIDA = "Responde y, n o ca."
CA_NO_EXISTE = "No se encontró el archivo: {ruta}"

ADVERTENCIA_SIN_CIFRADO = (
    "Atención: la URL usa http://, sin cifrado. La clave viajará en texto plano."
)
ADVERTENCIA_TLS_DESACTIVADO = (
    "Atención: no se validará el certificado. No lo uses contra ambientes productivos."
)

# Confirmaciones sí/no: estándar en inglés, solo se acepta y o n (mayúscula o minúscula).
SUFIJO_CONFIRMAR_SI = " (Y/n)"
SUFIJO_CONFIRMAR_NO = " (y/N)"
RESPUESTA_SI = "y"
RESPUESTA_NO = "n"
RESPUESTA_SI_NO_INVALIDA = "Responde y o n."

# Opciones aceptadas en la pregunta de TLS.
TLS_SI = "y"
TLS_NO = "n"
TLS_CA = "ca"

PERFIL_GUARDADO = "Perfil «{nombre}» guardado."
PERFIL_GUARDADO_PREDETERMINADO = "Perfil «{nombre}» guardado como predeterminado."
PERFIL_ACTUALIZADO = "Perfil «{nombre}» actualizado."

# --- Perfiles: eliminar y predeterminado ---------------------------------------

CONFIRMAR_ELIMINAR = "¿Eliminar el perfil «{nombre}» y su clave guardada?"
CANCELADO = "Cancelado."
PERFIL_ELIMINADO = "Perfil «{nombre}» eliminado, junto con su clave."
SIN_PREDETERMINADO = "Ya no hay perfil predeterminado. Marca uno con `p6 profiles default NOMBRE`."
PREDETERMINADO_MARCADO = "«{nombre}» es ahora el perfil predeterminado."

# --- Perfiles: listado ----------------------------------------------------------

SIN_PERFILES = "No hay perfiles guardados. Agrega uno con `p6 profiles add`."
COLUMNA_NOMBRE = "Nombre"
COLUMNA_URL = "URL"
COLUMNA_DATABASE = "DatabaseName"
COLUMNA_USUARIO = "Usuario"
COLUMNA_CLAVE = "Clave"
COLUMNA_TLS = "TLS"
COLUMNA_PREDETERMINADO = "Predeterminado"
MARCA_PREDETERMINADO = "sí"
TLS_VALIDADO = "validado"
TLS_SIN_VALIDAR = "sin validar"
TLS_CA_PROPIA = "CA propia"

# La clave nunca se muestra ni se revela su longitud.
CLAVE_ENMASCARADA = "••••••••"
CLAVE_AUSENTE = "(sin clave)"
CLAVE_KEYRING_NO_DISPONIBLE = "(keyring no disponible)"

# --- Prueba de conexión y diagnóstico (§7) ----------------------------------------

AYUDA_DOCTOR = (
    "Prueba la conexión de un perfil y explica la causa de un fallo (hace un intento de login)."
)
AYUDA_ARG_NOMBRE_DOCTOR = "Nombre del perfil (por defecto, el predeterminado)."

PROBANDO_CONEXION = "Probando conexión con «{nombre}» (se hará un intento de login)..."
ESPERANDO_RESPUESTA = "Esperando respuesta de P6..."
CONEXION_EXITOSA = "Conexión exitosa."

AVISO_CLAVE_NO_GUARDADA = (
    "El perfil «{nombre}» no tiene clave guardada. La que escribas se usará solo para esta "
    "prueba; para guardarla usa `p6 profiles edit {nombre}`."
)
PEDIR_CLAVE_DOCTOR = "Clave (oculta; no se guardará)"
CLAVE_REQUERIDA_PRUEBA = "El perfil no tiene clave guardada: escríbela para probar la conexión."

# Opciones cuando la prueba de conexión falla al agregar o editar un perfil.
PREGUNTA_FALLO_CONEXION = (
    "¿Qué hacemos? (c = corregir datos · g = guardar de todas formas · x = cancelar)"
)
OPCION_CORREGIR = "c"
OPCION_GUARDAR = "g"
OPCION_CANCELAR = "x"
OPCION_FALLO_INVALIDA = "Responde c, g o x."

TITULO_DIAGNOSTICO = "Diagnóstico · {estado}"
COLUMNA_METODO = "Método"
COLUMNA_CODIGO = "Código"
COLUMNA_CONTENT_TYPE = "Content-Type"
COLUMNA_TAMANO = "Bytes"
COLUMNA_FRAGMENTO = "Inicio del cuerpo"
SIN_CODIGO = "—"

# (mensaje, sugerencia) por estado. Se completan con ``DiagnosticReport.detalle``.
DIAGNOSTICO: dict[EstadoDiagnostico, tuple[str, str]] = {
    EstadoDiagnostico.CATCH_ALL: (
        "Esa ruta responde a cualquier petición (p. ej. P6 Professional Cloud Connect). "
        "No es la API REST.",
        "Cambia de host o de contexto: prueba el host dedicado de Web Services "
        "(p. ej. p6ws.<dominio>).",
    ),
    EstadoDiagnostico.ROUTE_NOT_FOUND: (
        "Web Services no está publicado en ese host/contexto.",
        "Prueba el host dedicado (p. ej. p6ws.<dominio>).",
    ),
    EstadoDiagnostico.UI_NOT_API: (
        "Esa URL es la interfaz web de P6, no Web Services.",
        "Usa la URL de Web Services, p. ej. https://p6ws.<dominio>/p6ws.",
    ),
    EstadoDiagnostico.INVALID_DATABASE: (
        "El DatabaseName no existe en esa instancia.",
        "Pide el alias correcto al administrador de P6.",
    ),
    EstadoDiagnostico.CREDENTIALS_REJECTED: (
        "Credencial rechazada, cuenta bloqueada o sin acceso a Web Services. No se reintentará.",
        "Verifica la clave entrando a la interfaz web y pide al administrador que revise la "
        "cuenta. Cada intento cuenta para el bloqueo.",
    ),
    EstadoDiagnostico.AUTH_FAILED: (
        "Autenticación rechazada: {mensaje_p6}",
        "Revisa el usuario y la clave.",
    ),
    EstadoDiagnostico.OK: ("Conectado.", ""),
    EstadoDiagnostico.UNKNOWN: (
        "Respuesta no reconocida en {metodo} {url}: código {codigo}, "
        "content-type «{content_type}».",
        "Inicio del cuerpo: {fragmento}",
    ),
}

# (mensaje, sugerencia) cuando no hubo respuesta (filas 1 a 3 de §7 y tiempo agotado).
DIAGNOSTICO_RED: dict[MotivoHTTP, tuple[str, str]] = {
    MotivoHTTP.SIN_RESOLUCION: (
        "El host no resuelve.",
        "¿Estás en la red o VPN correcta?",
    ),
    MotivoHTTP.SIN_CONEXION: (
        "Puerto cerrado o filtrado.",
        "Revisa el host y el puerto, y que la red o la VPN permitan llegar a él.",
    ),
    MotivoHTTP.TLS: (
        "Certificado no confiable.",
        "Configura la CA del perfil (opción ca en `p6 profiles edit`).",
    ),
    MotivoHTTP.TIEMPO_AGOTADO: (
        "El servidor no respondió a tiempo.",
        "Revisa el estado del servidor o aumenta `timeout` en profiles.toml.",
    ),
}

# --- Errores por motivo ---------------------------------------------------------

ERRORES: dict[StrEnum, str] = {
    MotivoConfig.URL_VACIA: "La URL está vacía.",
    MotivoConfig.URL_ESQUEMA: "Esquema «{esquema}» no soportado: usa https://.",
    MotivoConfig.URL_CREDENCIALES: (
        "La URL no debe incluir usuario ni clave. Pégala sin ellos: la clave se pide aparte."
    ),
    MotivoConfig.URL_SIN_HOST: "La URL no tiene un host válido.",
    MotivoConfig.URL_INTERFAZ_WEB: (
        "Esa URL parece la interfaz web de P6 (/p6), no Web Services. "
        "Usa la URL de Web Services, p. ej. https://p6ws.<dominio>/p6ws."
    ),
    MotivoConfig.ARCHIVO_INVALIDO: (
        "El archivo de perfiles {ruta} no es un TOML válido. Corrígelo o muévelo para empezar "
        "de cero."
    ),
    MotivoPerfil.NOMBRE_INVALIDO: (
        "Nombre «{nombre}» no válido: usa minúsculas, dígitos y guiones, empieza con letra o "
        "dígito y no pases de 32 caracteres."
    ),
    MotivoPerfil.NOMBRE_RESERVADO: (
        "El nombre «{nombre}» está reservado para el modo por variables de entorno."
    ),
    MotivoPerfil.CAMPO_INVALIDO: "El perfil «{perfil}» tiene un valor no válido en «{campo}».",
    MotivoPerfil.NO_EXISTE: "No existe el perfil «{nombre}».",
    MotivoPerfil.YA_EXISTE: "Ya existe un perfil llamado «{nombre}».",
    MotivoPerfil.SIN_PREDETERMINADO: (
        "No hay perfil predeterminado. Indica el nombre del perfil o marca uno con "
        "`p6 profiles default NOMBRE`."
    ),
    MotivoAuth.LOGIN_YA_INTENTADO: (
        "Ya se hizo un intento de login con «{perfil}»; no se reintenta automáticamente."
    ),
    MotivoAuth.CLAVE_NO_CODIFICABLE: (
        "El usuario o la clave tienen caracteres que no se pueden enviar en una cabecera HTTP "
        "(fuera de Latin-1, saltos de línea o espacio inicial)."
    ),
    MotivoHTTP.SIN_RESOLUCION: "El host no resuelve ({metodo} {url}).",
    MotivoHTTP.SIN_CONEXION: "No hay conexión con el servidor ({metodo} {url}).",
    MotivoHTTP.TLS: "Certificado no confiable ({metodo} {url}).",
    MotivoHTTP.TIEMPO_AGOTADO: "El servidor no respondió a tiempo ({metodo} {url}).",
    MotivoSecreto.SIN_BACKEND: (
        "No hay un almacén de credenciales (keyring) disponible en este sistema. "
        "Usa el modo por variables de entorno: define P6CLI_HOST, P6CLI_DATABASE_NAME, "
        "P6CLI_USERNAME y P6CLI_PASSWORD (ver env.example) y ejecuta con --env env."
    ),
    MotivoSecreto.ERROR_KEYRING: "El almacén de credenciales del sistema falló ({tipo}).",
}
