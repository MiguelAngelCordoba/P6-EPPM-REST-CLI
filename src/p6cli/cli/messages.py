"""Todos los textos visibles para el usuario, en español."""

from enum import StrEnum

from p6cli.core.errors import MotivoConfig, MotivoPerfil, MotivoSecreto

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
    MotivoSecreto.SIN_BACKEND: (
        "No hay un almacén de credenciales (keyring) disponible en este sistema. "
        "Usa el modo por variables de entorno: define P6CLI_HOST, P6CLI_DATABASE_NAME, "
        "P6CLI_USERNAME y P6CLI_PASSWORD (ver env.example) y ejecuta con --env env."
    ),
    MotivoSecreto.ERROR_KEYRING: "El almacén de credenciales del sistema falló ({tipo}).",
}
