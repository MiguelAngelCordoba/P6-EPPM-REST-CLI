# Especificación funcional y técnica — v1

> Fuente de verdad del comportamiento del programa. Si algo no está aquí ni en `PLAN.md`, se pregunta antes de implementarlo.

---

## 1. Objetivo y alcance

`p6cli` es un cliente de terminal, de solo lectura, para la API REST de Oracle Primavera P6 EPPM. Sirve para explorar endpoints, ver datos en la terminal y exportarlos, contra cualquier instalación de P6, en nube u on-premise.

**En alcance (v1)**

- Guardar varios ambientes (perfiles) y elegir uno con menús de flechas.
- Contraseñas en el almacén de credenciales del sistema operativo (keyring).
- Prueba de conexión con diagnóstico que explica la causa de un fallo.
- Consultas GET con parámetros escritos por el usuario.
- Lecturas masivas por lotes y series temporales (servicio Spread).
- Resultados en tabla; exportación a CSV y JSON.
- Las mismas operaciones como comandos con flags, para automatización.

**Fuera de alcance (v1)**

- Cualquier operación de escritura en P6.
- OAuth (solo aplica a instancias hospedadas en Oracle Cloud Infrastructure).
- Interfaz gráfica, caché, carga a bases de datos, consultas guardadas como plantillas.

---

## 2. Conceptos de P6 necesarios

- **P6 EPPM Web Services**: módulo de P6 que expone la API. Vive en un contexto web, normalmente `/p6ws`; la base de la API es `{host}/{contexto}/restapi`. No confundir con la interfaz web de P6 (`/p6`).
- **DatabaseName**: alias de la instancia de base de datos configurado en P6. Cada instalación tiene el suyo. `orcl` es solo el valor de ejemplo de la documentación de Oracle.
- **ObjectId**: identificador numérico interno de cada objeto. Base de los filtros y de la paginación simulada.
- **Plantilla `entity`**: la mayoría de lecturas (`GET /activity`, `/project`, `/wbs`...) reciben `Fields`, `Filter` y `OrderBy`.
- **Spread**: series temporales ya calculadas (unidades, costos, valor ganado) por período. Exige listas explícitas de ObjectId.

El comportamiento real observado está en `APRENDIZAJES.md`.

---

## 3. Arquitectura

```
p6-eppm-rest-cli/
├── src/p6cli/
│   ├── __init__.py            # __version__
│   ├── __main__.py            # permite python -m p6cli
│   ├── core/
│   │   ├── config.py          # rutas de configuración y modo por variables de entorno
│   │   ├── profiles.py        # modelo Profile y ProfileStore (TOML)
│   │   ├── secrets.py         # envoltorio de keyring
│   │   ├── urls.py            # normalización de la URL pegada por el usuario
│   │   ├── session.py         # sesión HTTP autenticada: login, logout, cabeceras
│   │   ├── diagnostics.py     # prueba de conexión y clasificación de fallos
│   │   ├── catalog.py         # endpoints, plantillas, especificación de parámetros
│   │   ├── client.py          # GET genérico, lecturas por lotes, spread
│   │   ├── export.py          # escritura de CSV y JSON
│   │   └── errors.py          # jerarquía de excepciones y pistas por código HTTP
│   └── cli/
│       ├── app.py             # Typer: comandos con flags; sin argumentos abre los menús
│       ├── menus.py           # flujo interactivo
│       ├── forms.py           # formularios de parámetros
│       ├── prompter.py        # interfaz delgada sobre questionary, inyectable en tests
│       ├── render.py          # tablas, paneles y progreso con rich
│       └── messages.py        # todos los textos visibles, en español
├── tests/
├── docs/
├── .claude/
├── pyproject.toml
├── env.example
├── .gitignore
├── CLAUDE.md
└── README.md
```

**Reglas de capas**

- `core` no imprime, no pregunta y no importa `rich`, `questionary` ni `typer`.
- `core` comunica progreso con callbacks (`on_progress(done: int, total: int)`).
- `cli` traduce excepciones de `core` a mensajes de `messages.py`.
- `cli/prompter.py` define un protocolo `Prompter` (select, checkbox, text, password, confirm). La implementación real usa questionary; los tests inyectan una con respuestas guionizadas.

---

## 4. Perfiles y secretos

### 4.1 Modelo

| Campo | Tipo | Por defecto | Notas |
|---|---|---|---|
| `name` | str | — | Identidad del perfil. Patrón `^[a-z0-9][a-z0-9-]{0,31}$`. `env` está reservado (§15) |
| `host` | str | — | Esquema + host + puerto opcional, sin ruta. Ej. `https://localhost:7001` |
| `context` | str | `p6ws` | Contexto web de Web Services |
| `database_name` | str | — | Alias de la instancia |
| `username` | str | — | |
| `verify_ssl` | bool \| str | `true` | `true`, `false` o ruta a un `.pem` de CA propia |
| `timeout` | int | `180` | Segundos por petición |
| `id_chunk_size` | int | `200` | ObjectId por lote en lecturas masivas y spread |
| `throttle_seconds` | float | `0.5` | Pausa entre lotes consecutivos |

La contraseña **no** es parte del modelo persistido.

### 4.2 Almacenamiento

- Archivo `profiles.toml` en el directorio de configuración del usuario:
  - Si existe la variable `P6CLI_CONFIG_DIR`, se usa esa ruta (tests y usos avanzados).
  - Si no: `platformdirs.user_config_dir("p6cli", appauthor=False, roaming=True)`. En Windows queda en `%APPDATA%\p6cli\`.
- Lectura con `tomllib`, escritura con `tomli-w`. Escritura atómica (archivo temporal + reemplazo).
- El primer perfil creado queda como predeterminado.

```toml
default = "demo"

[profiles.demo]
host = "https://localhost:7001"
context = "p6ws"
database_name = "orcl"
username = "admin"
verify_ssl = true
timeout = 180
id_chunk_size = 200
throttle_seconds = 0.5
```

### 4.3 Secretos

- Servicio keyring: `p6cli`. Usuario keyring: el `name` del perfil.
- Operaciones: guardar, leer, borrar, renombrar (copiar a la nueva clave y borrar la anterior).
- Eliminar un perfil elimina también su secreto.
- Si no hay backend de keyring disponible, error claro sugiriendo el modo por variables de entorno (§15).
- La contraseña se muestra siempre como `••••••••`, sin revelar su longitud.

---

## 5. Normalización de URL

El usuario pega la URL tal como la tenga. `core/urls.py` extrae `host` y `context`:

| Entrada | host | context | Nota |
|---|---|---|---|
| `https://p6ws.example.com/p6ws/` | `https://p6ws.example.com` | `p6ws` | |
| `https://p6ws.example.com/p6ws/restapi` | `https://p6ws.example.com` | `p6ws` | se descarta `restapi` |
| `https://localhost:7001/p6ws/restapi/login?DatabaseName=orcl` | `https://localhost:7001` | `p6ws` | se descartan endpoint y query |
| `https://p6ws.example.com` | `https://p6ws.example.com` | `p6ws` | contexto por defecto |
| `p6ws.example.com/p6ws` | `https://p6ws.example.com` | `p6ws` | se asume `https` |
| `http://p6ws.example.com/p6ws` | `http://p6ws.example.com` | `p6ws` | se acepta con advertencia: sin cifrado |
| `https://p6.example.com/p6/action/login` | — | — | **advertencia**: parece la interfaz web, no Web Services |

La normalización siempre se muestra al usuario para confirmar antes de guardar.

---

## 6. Autenticación

Esquema: **Username Token Profile** (autenticación HTTP estándar de P6).

- `authToken` = base64 de `usuario:contraseña`.
- **Login:** `POST {base}/login?DatabaseName={db}` con cabeceras `username`, `password`, `authToken` y `Accept: */*`. Éxito = 200. La sesión HTTP conserva las cookies que devuelva el servidor.
- **Cada GET:** cabeceras `authToken` y `Accept: application/json`; query param `DatabaseName` siempre presente.
- **Logout:** `POST {base}/logout` al salir o al cambiar de ambiente. Sus fallos se ignoran.
- Un solo login por perfil en cada ejecución. **Sin reintentos automáticos.**
- Nunca se registran cabeceras ni cuerpos de login en logs o excepciones.

---

## 7. Prueba de conexión (diagnóstico)

Se ejecuta al agregar o editar un perfil, al actualizar credenciales y con `p6 doctor`. Realiza **un** intento de login; el usuario debe saberlo, porque cuenta para el bloqueo de cuentas.

**Pasos:** DNS → TCP → TLS → `POST /login` → `GET /project/fields` → `POST` a una ruta canario inexistente (`/__p6cli_canary__`).

**Clasificación** (se evalúa en este orden):

| # | Evidencia | Estado | Mensaje al usuario |
|---|---|---|---|
| 1 | El nombre no resuelve | `NETWORK` | El host no resuelve. ¿Estás en la red o VPN correcta? |
| 2 | No hay conexión TCP | `NETWORK` | Puerto cerrado o filtrado |
| 3 | Error de certificado | `TLS` | Certificado no confiable. Configura la CA del perfil |
| 4 | El canario responde distinto de 404 | `CATCH_ALL` | Esa ruta responde a cualquier petición (p. ej. P6 Professional Cloud Connect). No es la API REST |
| 5 | Login 404 con HTML | `ROUTE_NOT_FOUND` | Web Services no está publicado en ese host/contexto. Prueba el host dedicado (p. ej. `p6ws.<dominio>`) |
| 6 | Login con HTML y redirección a `/p6/action/login` | `UI_NOT_API` | Esa URL es la interfaz web de P6, no Web Services |
| 7 | Login 401 JSON con `Invalid database name` | `INVALID_DATABASE` | El DatabaseName no existe en esa instancia |
| 8 | Login 500 | `CREDENTIALS_REJECTED` | Credencial rechazada, cuenta bloqueada o sin acceso a Web Services. No se reintentará |
| 9 | Login 401 JSON con otro mensaje | `AUTH_FAILED` | Autenticación rechazada: `<mensaje de P6>` |
| 10 | Login 200 JSON + `/project/fields` 200 JSON + canario 404 | `OK` | Conectado |
| — | Cualquier otro caso | `UNKNOWN` | Código, content-type y primeros 200 caracteres del cuerpo |

`GET /project/fields` con 200 **no** prueba autenticación: responde aun con DatabaseName inválido. El éxito exige las tres condiciones de la fila 10.

**Resultado:** `DiagnosticReport` con `status`, `message`, `suggestion` y la lista de pasos observados (método, URL sin credenciales, código, content-type, tamaño y fragmento del cuerpo).

---

## 8. Catálogo de endpoints

### 8.1 Modelo

```python
class ParamKind(Enum):
    FIELDS = "fields"      # lista separada por comas
    FILTER = "filter"      # expresión de filtro de P6, texto libre
    ORDER = "order"        # "Campo asc|desc"
    ENUM = "enum"          # una opción de una lista
    DATE = "date"          # AAAA-MM-DD
    BOOL = "bool"
    ID_LIST = "id_list"    # lista de ObjectId

@dataclass(frozen=True)
class ParamSpec:
    name: str              # nombre exacto del query param en P6
    kind: ParamKind
    required: bool
    default: str | None = None
    choices: tuple[str, ...] = ()
    help: str = ""

@dataclass(frozen=True)
class Endpoint:
    key: str               # clave estable, ej. "activity", "spread.activity"
    path: str              # ruta relativa a {base}, ej. "/activity"
    group: str             # agrupación en el menú
    template: str          # "entity" | "spread" | "custom"
    description: str       # en español
    large: bool = False
    doc_verified: bool = False
    params: tuple[ParamSpec, ...] = ()   # solo para spread/custom
```

La identidad es `key`. El número visible en listados es un índice derivado del orden; nunca se persiste.

### 8.2 Plantillas

**`entity`**

| Param | Tipo | Requerido | Comportamiento si se deja vacío |
|---|---|---|---|
| `Fields` | FIELDS | sí | No se permite |
| `Filter` | FILTER | no | El cliente envía `ObjectId:gte:0` |
| `OrderBy` | ORDER | no | El cliente envía `ObjectId asc` |

La documentación de Oracle marca `Filter` y `OrderBy` como obligatorios; en la interfaz son opcionales porque el cliente los completa.

**`spread`**

| Param | Tipo | Requerido | Por defecto |
|---|---|---|---|
| `<id param>` (ej. `ActivityObjectId`) | ID_LIST | sí | — |
| `SpreadField` | FIELDS | sí | — |
| `PeriodType` | ENUM: Hour, Day, Week, Month, Quarter, Year, FinancialPeriod | sí | `Week` |
| `StartDate` | DATE | no | — |
| `EndDate` | DATE | no | — |
| `IncludeCumulative` | BOOL | no | `true` |

Formato de fecha enviado: `AAAA-MM-DDT00:00:00`. Se confirma contra una instancia real en el hito M6.

**`custom`**: el endpoint declara sus `params` explícitamente.

### 8.3 Catálogo inicial

| key | path | plantilla | grupo | large | doc_verified |
|---|---|---|---|---|---|
| `project` | `/project` | entity | Proyectos | no | no |
| `eps` | `/eps` | entity | Proyectos | no | no |
| `wbs` | `/wbs` | entity | Proyectos | sí | no |
| `activity` | `/activity` | entity | Actividades | sí | **sí** |
| `relationship` | `/relationship` | entity | Actividades | sí | no |
| `activityCodeType` | `/activityCodeType` | entity | Códigos | no | no |
| `activityCode` | `/activityCode` | entity | Códigos | sí | no |
| `activityCodeAssignment` | `/activityCodeAssignment` | entity | Códigos | sí | no |
| `resource` | `/resource` | entity | Recursos | no | no |
| `resourceAssignment` | `/resourceAssignment` | entity | Recursos | sí | no |
| `udfType` | `/udfType` | entity | UDF | no | no |
| `udfValue` | `/udfValue` | entity | UDF | sí | no |
| `spread.activity` | `/spread/activitySpread` | spread (`ActivityObjectId`) | Series temporales | — | **sí** |
| `spread.resourceAssignment` | `/spread/resourceAssignmentSpread` | spread (`ResourceAssignmentObjectId`) | Series temporales | — | **sí** |

El catálogo crece con el uso siguiendo la regla de `CLAUDE.md` ("Agregar un endpoint al catálogo").

**Operaciones auxiliares** (no son entradas del catálogo): `GET {path}/fields` lista los campos válidos de cualquier endpoint `entity`.

---

## 9. Cliente HTTP y guardarraíles

- **Solo GET.** Cualquier otro verbo lanza `UsageError`, salvo el login y el logout de `session.py`.
- **`get(endpoint, params, allow_unfiltered=False)`**
  - Valida parámetros requeridos según la plantilla.
  - Completa `Filter` y `OrderBy` vacíos (§8.2) y agrega `DatabaseName`.
  - Si la URL resultante supera 7000 caracteres → `UsageError` (reducir campos o tamaño de lote).
  - Respuesta ≠ 200 → `P6HTTPError` con pista (§14).
  - Respuesta 200 cuyo `Content-Type` no sea JSON → `P6HTTPError` explicando que probablemente un proxy devolvió la interfaz web o la sesión expiró.
- **Guardarraíl:** endpoint `large` con `Filter` vacío → `GuardrailError`, salvo `allow_unfiltered=True`. El menú pide confirmación; en flags se usa `--allow-unfiltered`.
- **`get_all(endpoint, params)`** — la API no tiene paginación:
  1. Exige `Filter` (mismo guardarraíl).
  2. Si el filtro contiene `:or:` → `UsageError`: la documentación no define paréntesis y la precedencia al agregar rangos no está garantizada.
  3. Pide solo `ObjectId` con el filtro del usuario.
  4. Ordena los IDs, los agrupa en lotes de `id_chunk_size` y pide cada lote con `<filtro> :and: ObjectId:gte:<primero> :and: ObjectId:lte:<último>`.
  5. Pausa `throttle_seconds` entre lotes y notifica progreso por callback.
- **`get_spread(endpoint, ids, params)`**: trocea `ids` en lotes de `id_chunk_size`, con la misma pausa y el mismo callback.
- **`fields(endpoint)`**: `GET {path}/fields`.

---

## 10. Flujo interactivo

`p6` sin argumentos abre este flujo. Todas las listas se navegan con flechas.

### 10.1 Inicio

```
P6 EPPM REST CLI  v1.0 — solo lectura

? ¿Qué ambiente quieres consultar?
 ❯ demo         localhost:7001        orcl      (predeterminado)
   otro         p6ws.example.com      P6EPPM
   ─────────────
   + Agregar ambiente
   ⚙ Administrar ambientes
   Salir
```

Sin perfiles guardados, se va directo a "Agregar ambiente" con un mensaje de bienvenida.

### 10.2 Credenciales

```
Ambiente : demo   (https://localhost:7001/p6ws · orcl)
Usuario  : admin
Clave    : ••••••••

? ¿Cómo continuamos?
 ❯ Continuar con estas credenciales
   Actualizar credenciales
   Volver
```

- **Actualizar credenciales:** usuario (valor actual por defecto) y clave oculta. Se prueba la conexión; si pasa, se guardan.
- Si el perfil no tiene clave en el keyring, se pide antes de mostrar esta pantalla.
- **Login fallido:** se muestra el diagnóstico (§7) y las opciones *Actualizar credenciales* o *Volver al inicio*. Nunca se reintenta solo.

### 10.3 Agregar ambiente

```
Nombre del ambiente (ej. cliente-prod): 
URL de P6 Web Services (pega la URL completa): 
  → Host: https://p6ws.example.com · Contexto: p6ws   ¿Correcto? (S/n)
DatabaseName: 
Usuario: 
Clave: (oculta)
? ¿Validar el certificado TLS?  Sí · No · Usar CA propia (.pem)

Probando conexión (se hará un intento de login)...
```

- Éxito → se guarda el perfil y la clave.
- Fallo → diagnóstico y opciones: *Corregir datos* (vuelve al formulario con los valores cargados) · *Guardar de todas formas* · *Cancelar*.

### 10.4 Administrar ambientes

Lista de perfiles → acciones: *Editar* · *Probar conexión* · *Marcar como predeterminado* · *Eliminar* (con confirmación; borra también la clave) · *Volver*.

### 10.5 Elegir endpoint

```
? ¿Qué quieres consultar?
   ── Proyectos ──
 ❯ project                     Proyectos
   wbs                         Estructura WBS
   ── Actividades ──
   activity                    Actividades
   ...
   ── Series temporales ──
   spread.activity             Spread por actividad
   ─────────────
   Cambiar ambiente
   Salir
```

### 10.6 Formulario, confirmación y ejecución

Ver §11. Tras la confirmación se ejecuta con indicador de progreso y tiempo transcurrido.

### 10.7 Resultados y siguiente paso

```
activity · 1.284 filas · 3,2 s
[tabla con las primeras 25 filas]

? ¿Qué sigue?
 ❯ Exportar a CSV
   Exportar a JSON
   Nueva consulta en este endpoint (conserva los parámetros)
   Otro endpoint
   Cambiar ambiente
   Salir
```

---

## 11. Formularios de parámetros

### 11.1 Plantilla `entity`

```
GET /activity — Actividades
Consulta la documentación de Oracle para nombres de campos y sintaxis de filtros.
Escribe ? en Fields para ver los campos válidos de este endpoint.

(Obligatorio) Fields  : 
(Opcional)    Filter  : 
(Opcional)    OrderBy : 
```

**Reglas**

1. **Sin valores preseleccionados.** El usuario escribe lo que necesita, con la documentación de Oracle a mano.
2. **Fields vacío** → mensaje *"Se necesita al menos un campo en Fields."* y el formulario reaparece conservando lo escrito en Filter y OrderBy.
3. **`?` en Fields** → lista los campos válidos consultando `{path}/fields` en vivo, en columnas, y vuelve a pedir Fields.
4. **Normalización de Fields:** separar por comas, quitar espacios, eliminar duplicados preservando el orden. Cada campo debe cumplir `^[A-Za-z][A-Za-z0-9_]*$`; si no, mensaje y el formulario reaparece.
5. **Filter y OrderBy** se envían tal cual los escribe el usuario.
6. **Filter vacío en un endpoint `large`** → confirmación: *"Sin filtro se traerán todos los registros de `<endpoint>` de la instancia. ¿Continuar?"* (por defecto: No).
7. **Si P6 rechaza la consulta** (400, campo inexistente, filtro mal escrito) → se muestra la pista y el mensaje de P6, y el formulario reaparece **con los valores escritos**, no vacío.

### 11.2 Plantilla `spread`

1. **Origen de los ObjectId:** *Escribirlos* (lista separada por comas) · *Desde un archivo exportado* (CSV o JSON con columna `ObjectId`) · *Desde una consulta* (se pide un Filter sobre la entidad base y se obtienen los IDs con `get_all`).
2. `(Obligatorio) SpreadField`, con la misma regla de campos vacíos que Fields.
3. `PeriodType` como lista de opciones, `Week` preseleccionado.
4. `(Opcional) StartDate` y `(Opcional) EndDate` en formato `AAAA-MM-DD`, validados.
5. `IncludeCumulative` Sí/No, por defecto Sí.

### 11.3 Confirmación

```
GET /activity
  Fields  : ObjectId, Id, Name, Status
  Filter  : ProjectObjectId:eq:1234
  OrderBy : ObjectId asc   (por defecto)
  Equivale a: p6 get activity --env demo --fields "ObjectId,Id,Name,Status" --filter "ProjectObjectId:eq:1234"

? ¿Ejecutar?
 ❯ Ejecutar
   Editar
   Cancelar
```

El comando equivalente permite repetir la consulta en modo flags.

---

## 12. Modo con flags

`p6` con argumentos ejecuta directo, sin menús. `--env` es opcional si hay perfil predeterminado. **Nunca existe un flag para la contraseña.**

| Comando | Descripción |
|---|---|
| `p6` | Abre el flujo interactivo |
| `p6 --version` | Versión |
| `p6 profiles list` | Lista perfiles (clave enmascarada) |
| `p6 profiles add` | Asistente para agregar perfil (clave oculta) |
| `p6 profiles edit NAME` | Edita un perfil |
| `p6 profiles remove NAME [--yes]` | Elimina perfil y clave |
| `p6 profiles default NAME` | Marca el predeterminado |
| `p6 doctor [NAME]` | Prueba de conexión con diagnóstico (§7) |
| `p6 endpoints [--group G]` | Lista el catálogo |
| `p6 fields ENDPOINT [--env NAME]` | Campos válidos de un endpoint |
| `p6 get ENDPOINT --fields F [--filter X] [--order-by Y] [--env NAME] [--allow-unfiltered] [--max-rows N] [--json] [--output ARCHIVO]` | Lectura simple |
| `p6 get-all ENDPOINT --fields F --filter X [--chunk N] [--env NAME] [--output ARCHIVO]` | Lectura masiva por lotes |
| `p6 spread ENDPOINT (--ids 1,2,3 \| --ids-from ARCHIVO) --spread-fields F [--period Week] [--start D] [--end D] [--no-cumulative] [--env NAME] [--output ARCHIVO]` | Series temporales |

La extensión de `--output` (`.csv` o `.json`) define el formato.

**Códigos de salida:** `0` éxito · `1` error de P6 o HTTP · `2` error de uso o configuración · `3` bloqueado por guardarraíl · `130` interrumpido.

---

## 13. Salida y exportación

- **Tabla:** rich; columnas en el orden de `Fields`; primeras 25 filas (configurable); celdas truncadas a 40 caracteres; encabezado con conteo de filas y tiempo.
- **JSON en pantalla:** `--json`, con indentación.
- **CSV:** UTF-8 con BOM (`utf-8-sig`) para que Excel en Windows muestre bien las tildes; columnas en el orden de `Fields`; valores anidados serializados como JSON.
- **JSON a archivo:** lista completa, indentación 2, `ensure_ascii=False`.
- **Spread:** JSON tal como lo devuelve P6. CSV en formato largo (una fila por objeto × período × campo), útil para Power BI. La forma exacta de la respuesta se confirma en el hito M6 con una estructura de ejemplo anonimizada que aporta el usuario.
- **Ruta por defecto en el menú:** `./exports/{perfil}_{endpoint}_{AAAAMMDD-HHMMSS}.{ext}`. Se crea la carpeta si no existe. Nunca se sobrescribe: si el archivo existe se agrega un sufijo.

---

## 14. Errores

**Jerarquía:** `P6CliError` → `ConfigError`, `ProfileError`, `SecretStoreError`, `AuthError`, `P6HTTPError`, `GuardrailError`, `UsageError`.

`P6HTTPError` incluye código, método, URL **sin** cabeceras, fragmento del cuerpo (máx. 500 caracteres) y una pista:

| Código | Pista |
|---|---|
| 400 | Revisa nombres en Fields, sintaxis de Filter (`:eq: :gt: :lt: :gte: :lte: :like: :and: :or:`) y OrderBy (`Campo asc\|desc`) |
| 401 | Credencial inválida, sesión expirada, DatabaseName incorrecto o sin privilegio sobre el objeto |
| 403 | Autenticado pero sin autorización para esta operación |
| 404 | Ruta inexistente **o** sin acceso al objeto: P6 enmascara la falta de permisos como 404 |
| 405 | Método no permitido. Si ocurre en un GET documentado, esa ruta no es la API REST |
| 500 | Error del servidor. En lecturas grandes: filtro demasiado amplio (memoria o timeout). En login: ver §7 |
| 503 | Servidor sobrecargado o en mantenimiento. Reintentar más tarde |

Ningún mensaje ni excepción contiene contraseñas ni valores de `authToken`.

---

## 15. Modo automatización por variables de entorno

Para ejecuciones sin perfiles guardados (tareas programadas, servidores). Se usa con `--env env`:

| Variable | Obligatoria | Equivale a |
|---|---|---|
| `P6CLI_HOST` | sí | `host` o URL completa (se normaliza, §5) |
| `P6CLI_CONTEXT` | no | `context` |
| `P6CLI_DATABASE_NAME` | sí | `database_name` |
| `P6CLI_USERNAME` | sí | `username` |
| `P6CLI_PASSWORD` | sí | contraseña |
| `P6CLI_VERIFY_SSL` | no | `verify_ssl` |
| `P6CLI_CONFIG_DIR` | no | directorio de configuración (§4.2) |

El programa **no** carga archivos `.env`; las variables las define el sistema o el orquestador. `env.example` documenta los nombres.

---

## 16. Estrategia de pruebas

- **Sin red real, nunca.** HTTP simulado con `responses`.
- **Respuestas de referencia** (anonimizadas, en `tests/fixtures/`) que reproducen los casos de `APRENDIZAJES.md`:
  - login 200 JSON;
  - login 401 JSON `{"message":"Invalid database name passed."}`;
  - login 500 con cuerpo `Request failed.`;
  - 404 HTML por defecto de Apache;
  - 401 HTML con redirección a `/p6/action/login?sessionExpired=true`;
  - comodín: 200 vacío a cualquier POST y 405 `HTTP method GET is not supported by this URL` a GET;
  - `/project/fields` 200 JSON.
- **Keyring en memoria:** backend de prueba configurado en `conftest.py`.
- **Configuración aislada:** `P6CLI_CONFIG_DIR` apuntando a un directorio temporal.
- **Comandos con flags:** `typer.testing.CliRunner`.
- **Menús:** `Prompter` con respuestas guionizadas; se prueban decisiones y transiciones, no el dibujo.
- Cobertura objetivo: `core` ≥ 90 %.

---

## 17. Dependencias

**Ejecución:** `requests`, `keyring`, `platformdirs`, `tomli-w`, `typer`, `questionary`, `rich`.

**Desarrollo:** `pytest`, `pytest-cov`, `responses`, `ruff`, `mypy`, `types-requests`, `pre-commit`.

**Build:** `hatchling` (backend de `pyproject.toml`; no es dependencia de ejecución).

---

## 18. Registro de decisiones

| Decisión | Motivo |
|---|---|
| Solo lectura (GET) | Uso exploratorio contra instancias productivas |
| Contraseñas en keyring, no en `.env` | Fuera de la carpeta del proyecto y de carpetas sincronizadas; ni git ni Claude Code pueden tocarlas |
| Terminal con menús + flags, sin GUI en v1 | Resultados más legibles en terminal; flags permiten automatizar y probar |
| Fields sin preselección | Lo que se consulta depende de la necesidad; se trabaja con la documentación de Oracle a mano; `?` como ayuda |
| Filter y OrderBy opcionales en la interfaz | El cliente completa valores neutros que satisfacen a la API |
| Catálogo con plantillas y `doc_verified` | Crece gradualmente; cada endpoint nuevo se revisa una vez contra la documentación |
| Sin reintentos de login | Riesgo de bloqueo de cuentas de servicio |
| Diagnóstico exige JSON + canario | Evita falsos positivos de proxies, interfaz web y servlets comodín |
| Textos de interfaz en español, centralizados | Uso personal; traducción futura en un solo archivo |
| Nombres: repo `p6-eppm-rest-cli`, paquete `p6cli`, comando `p6` | Descriptivos y cortos |
| Backend de build `hatchling`; versión única en `src/p6cli/__init__.py` (`[tool.hatch.version]`) | Configuración mínima para layout `src/`; la versión se define en un solo lugar |
| Versión inicial `0.1.0`; llega a `1.0.0` en M9. El banner de §10.1 muestra `__version__`, no un valor fijo | Refleja que la v1 está en desarrollo |
| Python 3.14+: `requires-python = ">=3.14"`, ruff (`target-version = "py314"`) y mypy (`python_version = "3.14"`); CI con 3.14 en Windows y Ubuntu | La CI solo prueba 3.14; declarar soporte para versiones anteriores prometería algo que no se prueba |
| Identificadores en español (ASCII, sin tildes ni ñ), salvo los nombres que esta especificación ya fija (archivos de §3, `Profile`, `ProfileStore`, `P6CliError`, `Prompter`, `get_all`, comandos, `__version__`) | Coherencia con la documentación sin reescribir lo ya especificado |
| mypy `strict` en todo `src` | mypy no admite `strict` por módulo; activarlo globalmente cubre `core`. Si `cli` lo necesita, se relaja solo `p6cli.cli.*` |
| `ruff format` no formatea `*.md` | Los bloques de código de la documentación conservan su alineación manual |
| `p6` sin argumentos muestra un aviso en español (desde `cli/messages.py`, salida 0) hasta que existan los menús en M5 | Evita un comportamiento a medias; el texto ya queda centralizado |
