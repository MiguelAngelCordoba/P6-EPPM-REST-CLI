"""Todos los textos visibles para el usuario, en español."""

from dataclasses import dataclass
from enum import StrEnum

from p6cli.core.diagnostics import EstadoDiagnostico
from p6cli.core.errors import (
    MotivoAuth,
    MotivoConfig,
    MotivoGuardarrail,
    MotivoHTTP,
    MotivoPerfil,
    MotivoSecreto,
    MotivoUso,
)

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
PEDIR_CLAVE_TEMPORAL = "Clave (oculta; no se guardará)"
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

# --- Catálogo y consultas (§8, §12, §13) -----------------------------------------

AYUDA_ENDPOINTS = "Lista el catálogo de endpoints."
AYUDA_OPCION_GRUPO = "Muestra solo los endpoints de ese grupo."
AYUDA_FIELDS = "Lista los campos válidos de un endpoint, consultando P6 en vivo."
AYUDA_GET = "Lectura simple de un endpoint (una sola petición)."
AYUDA_ARG_ENDPOINT = "Clave del endpoint (ver `p6 endpoints`)."
AYUDA_OPCION_ENV = "Perfil a usar (por defecto, el predeterminado)."
AYUDA_OPCION_FIELDS = "Campos separados por comas, p. ej. ObjectId,Id,Name."
AYUDA_OPCION_FILTER = (
    "Filtro de P6, p. ej. ProjectObjectId:eq:1234. Vacío envía ObjectId:gte:0. "
    "Guía: p6 syntax filter"
)
AYUDA_OPCION_ORDER_BY = "Orden «Campo asc|desc». Vacío envía ObjectId asc. Guía: p6 syntax order-by"
AYUDA_OPCION_ALLOW_UNFILTERED = "Permite consultar sin filtro un endpoint grande."
AYUDA_OPCION_MAX_ROWS = (
    "Filas que muestra la tabla (0 = todas). No reduce lo que se pide a P6: la API no pagina."
)
AYUDA_OPCION_JSON = "Imprime la respuesta completa como JSON, sin tabla."

GRUPO_INEXISTENTE = "No existe el grupo «{grupo}». Grupos: {grupos}."
COLUMNA_NUMERO = "#"
# Columnas del catálogo en inglés por decisión del usuario: coinciden con la documentación.
COLUMNA_TASKS = "Tasks"
COLUMNA_NAME = "Name"
COLUMNA_RUTA = "Ruta"
TITULO_GRUPO = "── {grupo} ──"
COLUMNA_GRANDE = "Grande"
COLUMNA_VERIFICADO = "Verificado"
MARCA_SI = "sí"

TITULO_CAMPOS = "Campos de {endpoint} ({cantidad})"

AVISO_CLAVE_NO_GUARDADA_CONSULTA = (
    "El perfil «{nombre}» no tiene clave guardada. La que escribas se usará solo para esta "
    "consulta; para guardarla usa `p6 profiles edit {nombre}`."
)

# Encabezado de resultados: «activity · 1.284 filas · 3,2 s».
ENCABEZADO_RESULTADOS = "{endpoint} · {filas} {unidad} · {segundos} s"
UNIDAD_FILA = "fila"
UNIDAD_FILAS = "filas"
SIN_RESULTADOS = "Sin resultados."
AVISO_FILAS_MOSTRADAS = (
    "Mostrando {mostradas} de {total} filas. Usa --max-rows 0 para verlas todas o --json "
    "para la respuesta completa."
)

# Pistas por código HTTP (§14).
PISTAS_HTTP: dict[int, str] = {
    400: (
        "Revisa nombres en Fields, sintaxis de Filter (:eq: :gt: :lt: :gte: :lte: :like: "
        ":and: :or:) y OrderBy (Campo asc|desc). Guía: p6 syntax filter"
    ),
    401: (
        "Credencial inválida, sesión expirada, DatabaseName incorrecto o sin privilegio sobre "
        "el objeto."
    ),
    403: "Autenticado pero sin autorización para esta operación.",
    404: ("Ruta inexistente o sin acceso al objeto: P6 enmascara la falta de permisos como 404."),
    405: "Método no permitido. Si ocurre en un GET documentado, esa ruta no es la API REST.",
    500: (
        "Error del servidor. En lecturas grandes: filtro demasiado amplio (memoria o timeout). "
        "En el login: ejecuta `p6 doctor`."
    ),
    503: "Servidor sobrecargado o en mantenimiento. Reintenta más tarde.",
}
PISTA = "Pista: {pista}"

SUGERENCIA_DOCTOR = "Para el diagnóstico completo: p6 doctor {perfil}"

# --- Guías de sintaxis: p6 syntax [TEMA] -----------------------------------------
# Contenido tomado de la documentación oficial de Oracle (rama 24.x): Entity Filtering,
# Ordering y las páginas de cada endpoint. Los ejemplos usan valores de muestra de Oracle.


@dataclass(frozen=True)
class GuiaSintaxis:
    """Guía de un tema: introducción, tabla de referencia, notas y ejemplos."""

    titulo: str
    resumen: str
    intro: tuple[str, ...]
    columnas: tuple[str, ...]
    filas: tuple[tuple[str, ...], ...]
    notas: tuple[str, ...]
    ejemplos: tuple[str, ...]
    referencia: str


AYUDA_SYNTAX = "Guías de sintaxis de Filter, OrderBy y Fields, según la documentación de Oracle."
AYUDA_ARG_TEMA = "Tema de la guía: filter, order-by o fields. Sin tema, lista los temas."
TITULO_TEMAS = "Guías disponibles (p6 syntax TEMA):"
TEMA_INEXISTENTE = "No existe la guía «{tema}». Temas: {temas}."
TITULO_NOTAS = "Tener en cuenta"
TITULO_EJEMPLOS = "Ejemplos"
TITULO_REFERENCIA = "Documentación oficial: {url}"

_DOC_ORACLE = "https://docs.oracle.com/cd/F88966_01/English/Integration_Documentation/rest_api"

GUIAS_SINTAXIS: dict[str, GuiaSintaxis] = {
    "filter": GuiaSintaxis(
        titulo="--filter: qué registros traer",
        resumen="Operadores, comillas y cómo combinar condiciones.",
        intro=(
            "Cada condición tiene la forma Campo:operador:valor, p. ej. ObjectId:eq:1001.",
            "Los números van sin comillas. Los textos y las fechas van entre comillas simples: "
            "Status:eq:'Not Started' · CreateDate:gte:'2021-04-20'.",
        ),
        columnas=("Operador", "Significado", "Ejemplo"),
        filas=(
            (":eq:", "Igual a", "ObjectId:eq:1001"),
            ("!=", "Distinto de (se escribe sin dos puntos)", "ObjectId!=1001"),
            (":gt:", "Mayor que (números y fechas)", "ObjectId:gt:88578"),
            (":gte:", "Mayor o igual que (números y fechas)", "ObjectId:gte:88578"),
            (":lt:", "Menor que (números y fechas)", "ObjectId:lt:88578"),
            (":lte:", "Menor o igual que (números y fechas)", "ObjectId:lte:88578"),
            (":like:", "Patrón de texto con % (texto y enum)", "Name :like: 'act%'"),
            ("IN(...)", "Está en la lista", "ObjectId IN(1,2)"),
            (
                ":and:",
                "Se cumplen todas las condiciones",
                "ObjectId:eq:88577 :and: Name :like: 'Ensure%'",
            ),
            (":or:", "Se cumple al menos una", "ObjectId:eq:88577 :or: ObjectId:eq:88578"),
        ),
        notas=(
            "Con :like:, % reemplaza cualquier texto: 'act%' empieza con act, '%act' termina "
            "con act y '%act%' contiene act.",
            "La API no admite paréntesis: no mezcles :and: con :or: en el mismo filtro, porque "
            "no se garantiza el orden en que se evalúan.",
            "En la terminal, escribe el filtro completo entre comillas dobles.",
            "En cmd, %texto% se reemplaza si existe una variable de entorno con ese nombre; si "
            "pasa, usa PowerShell.",
            "Los nombres de campo válidos de cada endpoint se ven con p6 fields ENDPOINT.",
            "Si no escribes --filter, se envía ObjectId:gte:0 (todos los registros). Los "
            "endpoints marcados como Grande en p6 endpoints exigen --filter o --allow-unfiltered.",
        ),
        ejemplos=(
            'p6 get activity --fields ObjectId,Id,Name --filter "ProjectObjectId:eq:1234"',
            'p6 get activity --fields ObjectId,Name,Status --filter "ProjectObjectId:eq:1234 '
            ":and: Status:eq:'Not Started'\"",
            "p6 get project --fields ObjectId,Id,Name --filter \"Name :like: '%act%'\"",
            'p6 get project --fields ObjectId,Id,Name --filter "ObjectId IN(1001,1002)"',
            "p6 get project --fields ObjectId,Id,CreateDate "
            "--filter \"CreateDate:gte:'2021-04-20'\"",
        ),
        referencia=f"{_DOC_ORACLE}/D99716.html",
    ),
    "order-by": GuiaSintaxis(
        titulo="--order-by: en qué orden traer los registros",
        resumen="Orden ascendente o descendente por uno o varios campos.",
        intro=(
            "Se escribe el campo y, opcionalmente, asc o desc. Sin asc ni desc, el orden es "
            "ascendente.",
        ),
        columnas=("Forma", "Significado", "Ejemplo"),
        filas=(
            ("Campo", "Ascendente", "Id"),
            ("Campo desc", "Descendente", "Id desc"),
            ("Campo1,Campo2", "Por Campo1 y, si empatan, por Campo2", "OBSName,Id"),
            ("Campo1 asc,Campo2 desc", "Cada campo con su propio orden", "OBSName asc,Id desc"),
        ),
        notas=(
            "Si no escribes --order-by, se envía ObjectId asc.",
            "No se puede ordenar por propiedades con varios valores ni por propiedades de "
            "objetos anidados.",
            "Si el orden tiene espacios, escríbelo entre comillas dobles.",
        ),
        ejemplos=(
            'p6 get project --fields ObjectId,Id,Name --order-by "Name desc"',
            'p6 get project --fields ObjectId,Id,Name --order-by "Id asc,Name desc"',
        ),
        referencia=f"{_DOC_ORACLE}/D100086.html",
    ),
    "fields": GuiaSintaxis(
        titulo="--fields: qué columnas traer",
        resumen="Cómo escribir la lista de campos y cómo ver los válidos.",
        intro=(
            "Lista de campos separados por comas. La tabla muestra las columnas en ese mismo "
            "orden.",
        ),
        columnas=("Regla", "Ejemplo"),
        filas=(
            ("Separados por comas", "ObjectId,Id,Name"),
            ("Espacios y repetidos se limpian solos", '"ObjectId, Id, Name, Id"'),
            ("Con espacios, entre comillas dobles", '--fields "ObjectId, Id, Name"'),
            ("Letras, dígitos y _, empezando por letra", "ObjectId · Udf_1"),
        ),
        notas=(
            "Los campos válidos de cada endpoint se ven con p6 fields ENDPOINT.",
            "Pide solo los campos que necesites: menos campos es menos carga para P6.",
        ),
        ejemplos=(
            "p6 fields activity",
            'p6 get activity --fields "ObjectId, Id, Name" --filter "ProjectObjectId:eq:1234"',
        ),
        referencia=f"{_DOC_ORACLE}/op-activity-fields-get.html",
    ),
}

# Mensaje estándar de la librería al interrumpir: se deja en inglés a propósito.
ABORTADO = "Aborted!"

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
    MotivoAuth.LOGIN_FALLIDO: "Falló el login con «{perfil}» ({estado}). No se reintentará.",
    MotivoAuth.CLAVE_NO_CODIFICABLE: (
        "El usuario o la clave tienen caracteres que no se pueden enviar en una cabecera HTTP "
        "(fuera de Latin-1, saltos de línea o espacio inicial)."
    ),
    MotivoHTTP.SIN_RESOLUCION: "El host no resuelve ({metodo} {url}).",
    MotivoHTTP.SIN_CONEXION: "No hay conexión con el servidor ({metodo} {url}).",
    MotivoHTTP.TLS: "Certificado no confiable ({metodo} {url}).",
    MotivoHTTP.TIEMPO_AGOTADO: "El servidor no respondió a tiempo ({metodo} {url}).",
    MotivoHTTP.CODIGO_HTTP: "P6 respondió {codigo} a {metodo} {url}\nMensaje de P6: {mensaje_p6}",
    MotivoHTTP.RESPUESTA_NO_JSON: (
        "P6 respondió 200 pero no en JSON (content-type «{content_type}») a {metodo} {url}. "
        "Probablemente un proxy devolvió la interfaz web o la sesión expiró.\n"
        "Inicio del cuerpo: {fragmento}"
    ),
    MotivoHTTP.FORMATO_INESPERADO: (
        "La respuesta de {metodo} {url} no tiene el formato esperado.\n"
        "Inicio del cuerpo: {fragmento}"
    ),
    MotivoUso.ENDPOINT_DESCONOCIDO: (
        "No existe el endpoint «{endpoint}». Consulta la lista con `p6 endpoints`."
    ),
    MotivoUso.PLANTILLA_NO_SOPORTADA: (
        "«{endpoint}» no es un endpoint de lectura simple (plantilla entity). Las series "
        "temporales se consultan con `p6 spread`."
    ),
    MotivoUso.CAMPOS_VACIOS: "Se necesita al menos un campo en {parametro}.",
    MotivoUso.PARAMETRO_REQUERIDO: "Falta el parámetro obligatorio {parametro}.",
    MotivoUso.PARAMETRO_DESCONOCIDO: "El parámetro {parametro} no aplica a «{endpoint}».",
    MotivoUso.CAMPO_INVALIDO: (
        "Campo «{campo}» no válido en {parametro}: usa letras, dígitos y guion bajo, "
        "empezando por una letra."
    ),
    MotivoUso.URL_DEMASIADO_LARGA: (
        "La consulta genera una URL de {largo} caracteres (máximo {maximo}). Reduce los campos "
        "o el tamaño del lote."
    ),
    MotivoUso.METODO_NO_PERMITIDO: (
        "Operación {metodo} {ruta} bloqueada: el cliente es de solo lectura."
    ),
    MotivoGuardarrail.SIN_FILTRO: (
        "Sin filtro se traerán todos los registros de «{endpoint}» de la instancia. Agrega "
        "--filter o, si de verdad lo necesitas, --allow-unfiltered."
    ),
    MotivoSecreto.SIN_BACKEND: (
        "No hay un almacén de credenciales (keyring) disponible en este sistema. "
        "Usa el modo por variables de entorno: define P6CLI_HOST, P6CLI_DATABASE_NAME, "
        "P6CLI_USERNAME y P6CLI_PASSWORD (ver env.example) y ejecuta con --env env."
    ),
    MotivoSecreto.ERROR_KEYRING: "El almacén de credenciales del sistema falló ({tipo}).",
}
