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
| `timeout` | int | `180` | Segundos de lectura por petición. La conexión TCP/TLS tiene un límite fijo de 10 s |
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
- Un solo login por perfil en cada ejecución. **Sin reintentos automáticos.** Cada `Sesion` admite un único intento: un segundo `login()` falla sin enviar nada.
- Ninguna petición sigue redirecciones (`allow_redirects=False`): requests reenviaría las cabeceras `username`, `password` y `authToken` al destino.
- Timeout `(10, perfil.timeout)`: 10 s para conectar, el timeout del perfil para leer.
- Nunca se registran cabeceras ni cuerpos de login en logs o excepciones.

---

## 7. Prueba de conexión (diagnóstico)

Se ejecuta al agregar o editar un perfil, al actualizar credenciales y con `p6 doctor`. Realiza **un** intento de login; el usuario debe saberlo, porque cuenta para el bloqueo de cuentas.

**Pasos:** DNS → TCP → TLS → `POST /login` → `GET /project/fields` → `GET` a una ruta canario inexistente (`/__p6cli_canary__`). El canario usa GET para respetar la regla de solo lectura; el servlet comodín responde 405 a GET, que también es distinto de 404. DNS, TCP y TLS se deducen del error de red del primer paso que falle, y ese error corta la secuencia.

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

**Resultado:** `DiagnosticReport` con `status`, `detalle` (datos no sensibles: mensaje de P6, código, content-type, fragmento), `causa_red` (cuando no hubo respuesta) y la lista de pasos observados (método, URL sin credenciales, código, content-type, tamaño y fragmento del cuerpo). El mensaje y la sugerencia al usuario los arma `cli/messages.py` a partir de `status` o `causa_red`. Un tiempo de lectura agotado se reporta como `UNKNOWN`.

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
    doc_name: str          # título exacto en la documentación de Oracle, ej. "Read Activities"
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

En la rama 24.x la documentación de Oracle marca `Filter` y `OrderBy` como opcionales. El cliente igual envía los valores neutros cuando quedan vacíos (P6 los acepta, confirmado en M4), para que la consulta enviada sea siempre explícita.

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

| key | doc_name (Oracle) | path | plantilla | grupo | large | doc_verified |
|---|---|---|---|---|---|---|
| `project` | Read Projects | `/project` | entity | Proyectos | no | sí |
| `eps` | Read EPS | `/eps` | entity | Proyectos | no | sí |
| `wbs` | Read WBS | `/wbs` | entity | Proyectos | sí | sí |
| `activity` | Read Activities | `/activity` | entity | Actividades | sí | sí |
| `relationship` | Read Relationship | `/relationship` | entity | Actividades | sí | sí |
| `activityCodeType` | Read ActivityCodeTypes | `/activityCodeType` | entity | Códigos | no | sí |
| `activityCode` | Read ActivityCodes | `/activityCode` | entity | Códigos | sí | sí |
| `activityCodeAssignment` | Read ActivityCodeAssignments | `/activityCodeAssignment` | entity | Códigos | sí | sí |
| `resource` | Read Resources | `/resource` | entity | Recursos | no | sí |
| `resourceAssignment` | Read ResourceAssignments | `/resourceAssignment` | entity | Recursos | sí | sí |
| `udfType` | Read UDFTypes | `/udfType` | entity | UDF | no | sí |
| `udfValue` | Read UDFValues | `/udfValue` | entity | UDF | sí | sí |
| `spread.activity` | ReadActivitySpread | `/spread/activitySpread` | spread (`ActivityObjectId`) | Series temporales | — | sí |
| `spread.resourceAssignment` | ReadResourceAssignmentSpread | `/spread/resourceAssignmentSpread` | spread (`ResourceAssignmentObjectId`) | Series temporales | — | sí |

Las 14 páginas de la rama 24.x se revisaron en M4: título, ruta (con mayúsculas) y parámetros coinciden con el catálogo.

El catálogo crece con el uso siguiendo la regla de `CLAUDE.md` ("Agregar un endpoint al catálogo").

**Operaciones auxiliares** (no son entradas del catálogo): `GET {path}/fields` lista los campos válidos de cualquier endpoint `entity`. Responde 200 con Content-Type JSON, pero el cuerpo es texto plano separado por comas (ver `APRENDIZAJES.md` §6).

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
  → Host: https://p6ws.example.com · Contexto: p6ws   ¿Correcto? (Y/n)
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
 ❯ Ver la tabla completa (1.284 filas)
   Ver el JSON completo
   Exportar a CSV
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
Consulta la documentación de Oracle o escribe ? en cualquier campo para ver ayuda aquí mismo.

(Obligatorio) Fields  : 
(Opcional)    Filter  : 
(Opcional)    OrderBy : 
```

**Reglas**

1. **Sin valores preseleccionados.** El usuario escribe lo que necesita, con la documentación de Oracle a mano.
2. **Fields vacío** → mensaje *"Se necesita al menos un campo en Fields."* y el formulario reaparece conservando lo escrito en Filter y OrderBy.
3. **`?` en cualquier campo** muestra su ayuda y vuelve a pedir ese mismo campo, conservando lo ya escrito:
   - **Fields** → lista los campos válidos consultando `{path}/fields` en vivo, en columnas.
   - **Filter** → la guía de `p6 syntax filter`; **OrderBy** → la guía de `p6 syntax order-by`. Sin red. Al final se avisa que en el formulario el valor va sin comillas dobles alrededor.
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
| `p6 endpoints [--group G]` | Lista el catálogo con el nombre y la ruta de la documentación de Oracle |
| `p6 syntax [TEMA]` | Guía de sintaxis de `filter`, `order-by` o `fields`; sin tema lista los temas |
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
| Asistente de `p6 profiles add`/`edit` con `typer.prompt` | El `Prompter` es alcance de M5 |
| Confirmaciones sí/no siempre con el estándar en inglés `(Y/n)` / `(y/N)`: solo se acepta `y` o `n` (mayúscula o minúscula), nunca `s`, `si`, `yes` ni `no`. La pregunta de TLS usa `y` · `n` · `ca` | Estándar de terminal; una sola respuesta válida por opción no deja margen al error |
| Los textos del programa van en español; los mensajes técnicos estándar de las librerías (p. ej. `Aborted!` de Typer al pulsar Ctrl+C) se dejan en inglés y no se traducen | Son convenciones reconocibles de la terminal |
| `p6 profiles edit NAME` repite el asistente con los valores actuales por defecto y muestra al inicio un único aviso: Enter conserva el valor actual. Permite renombrar (la clave se mueve en el keyring) | Una sola forma de capturar datos; renombrar no obliga a reescribir la clave |
| Al eliminar el perfil predeterminado, queda sin predeterminado; si el almacén queda vacío, el próximo perfil creado vuelve a serlo | Nunca se promueve en silencio un ambiente (quizá productivo) a predeterminado |
| `timeout`, `id_chunk_size` y `throttle_seconds` solo se editan en `profiles.toml`; se validan al leerlo y `edit` los conserva | Son ajustes avanzados; el asistente se mantiene corto como en §10.3 |
| Campos desconocidos en `profiles.toml` son error; un `default` que apunta a un perfil inexistente se ignora | Un error de tipeo (`timout`) no debe pasar en silencio; un `default` huérfano no bloquea el uso |
| Las excepciones de `core` llevan un `motivo` (enum) y datos no sensibles; `cli/messages.py` los traduce a texto. `ConfigError`, `ProfileError` y `SecretStoreError` salen con código 2 | Los textos viven en un solo lugar y `core` no conoce la interfaz |
| URL con usuario o clave incrustados (`https://u:c@host`) se rechaza sin repetirla en el error; la URL de la interfaz web (`/p6/...`) se rechaza y se vuelve a pedir | Evita filtrar secretos y guardar una URL que no es la API |
| `verify_ssl` con CA propia: el asistente exige que el `.pem` exista y guarda la ruta absoluta; el archivo no se lee | La ruta sigue sirviendo desde cualquier directorio de trabajo |
| `profiles list` muestra `••••••••` si hay clave, `(sin clave)` si no, y `(keyring no disponible)` sin fallar si no hay backend | El listado siempre funciona y nunca revela la clave ni su longitud |
| Crear un perfil guarda la clave antes que el TOML y la revierte si falla el archivo; editar revierte el TOML si falla el keyring | Archivo y keyring no quedan desincronizados |
| El canario del diagnóstico se consulta con GET, no con POST | Los únicos POST permitidos son `/login` y `/logout` (regla de solo lectura); el comodín responde 405 a GET, así que se sigue detectando |
| Si la prueba de conexión falla en `profiles add`/`edit`: `c` corregir · `g` guardar de todas formas · `x` cancelar (por defecto `c`); otra respuesta repregunta | Mismo estilo que la pregunta de TLS mientras no exista el `Prompter` (M5). Corregir reabre el asistente con lo escrito; Enter conserva la clave |
| Timeout `(10, perfil.timeout)`: conexión fija de 10 s, lectura con el timeout del perfil | Con un puerto filtrado, el diagnóstico no espera los 180 s de lectura |
| `p6 doctor` sin clave guardada la pide oculta, la usa solo para esa prueba y no la guarda | El diagnóstico no modifica el keyring; para guardarla está `p6 profiles edit` |
| `DiagnosticReport` no guarda textos: `status`, `detalle` y `causa_red`; mensaje y sugerencia viven en `cli/messages.py` | Misma regla que los `motivo` de las excepciones: `core` no conoce la interfaz |
| Ninguna petición de `Sesion` sigue redirecciones | requests solo quita `Authorization` al redirigir; reenviaría `username`, `password` y `authToken`. Además se ve el 302 hacia `/p6/action/login` |
| Un único intento de login por instancia de `Sesion`; `diagnosticar(sesion)` usa ese intento y deja la sesión autenticada si el estado es OK | "Sin reintentos" queda garantizado por diseño, y M5 puede diagnosticar un login fallido sin volver a intentarlo |
| DNS, TCP y TLS se deducen de la excepción de requests (`SSLError`, `socket.gaierror` en la cadena de causas, `ConnectionError`/`ConnectTimeout`), sin sondeos de socket aparte | Un sondeo propio fallaría detrás de un proxy corporativo que requests sí atraviesa |
| `p6 doctor` hace logout al final si el login fue exitoso; el logout no aparece en los pasos | No deja sesiones abiertas en el servidor |
| Salida de `p6 doctor`: `0` si OK, `1` con cualquier otro estado, `2` con errores de perfil, configuración o keyring | Códigos de §12 |
| Los errores de red se lanzan como `P6HTTPError` fuera del `except`, sin `__cause__` ni `__context__` | La excepción de requests guarda la petición con sus cabeceras |
| `Endpoint.template` es un `StrEnum` (`Plantilla`) con los valores `entity`, `spread` y `custom` | Mismo valor de texto que §8.1, con verificación de tipos |
| `Cliente` hace el login en la primera petición; parámetros, guardarraíl y largo de URL se validan antes. En `p6 get` la validación ocurre incluso antes de pedir la clave | Un error de uso nunca gasta el único intento de login ni pide datos de más |
| `Sesion` rechaza con `UsageError`, sin enviar nada, cualquier verbo distinto de GET salvo `POST /login` y `POST /logout` | Defensa en profundidad de la regla de solo lectura |
| `P6HTTPError` lleva `codigo`, `metodo`, `url` y `mensaje_p6` (máx. 500 caracteres); el texto de la pista por código vive en `cli/messages.py` (`PISTAS_HTTP`). Un código sin pista en §14 se muestra sin ella | `core` no conoce textos de interfaz |
| Un 200 JSON de `get` debe ser una lista de objetos; si no, `P6HTTPError` `FORMATO_INESPERADO` | No se muestra como datos algo que no lo es |
| `fields` lee el cuerpo como texto: si es JSON válido acepta una lista de textos o un texto con comas; si no, lo trata como texto plano con comas. Cada nombre debe cumplir `^[A-Za-z][A-Za-z0-9_]*$`; si no, `FORMATO_INESPERADO` | P6 real responde 200 con Content-Type JSON y cuerpo en texto plano separado por comas (validación manual de M4), aunque Oracle declara `string` |
| `get` y `fields` solo admiten endpoints `entity`; un spread sale con 2 y sugiere `p6 spread` | Spread tiene su propio comando (M6) |
| Un login fallido en `get` o `fields` se clasifica con las filas 5–9 de §7 (`clasificar_login`), sin peticiones extra; se muestran mensaje y sugerencia del diagnóstico y `p6 doctor NAME`. Salida 1 | Explica la causa sin gastar otro intento de login |
| `get` y `fields` sin clave guardada la piden oculta, la usan solo en esa ejecución y no la guardan. El aviso y la pregunta van a stderr | Mismo criterio que `p6 doctor`; stdout queda limpio para `--json` |
| `--max-rows N` limita solo las filas de la tabla (25 por defecto, `0` = todas, negativo es error de uso); `--json` imprime siempre la lista completa, solo el JSON en stdout (indentación 2, `ensure_ascii=False`) | Recortar en el cliente no reduce la carga de P6; el JSON completo se puede redirigir o pasar a `jq` |
| Celdas de la tabla: nulos vacíos, valores no texto como JSON, caracteres de control como espacio, recorte a 40 caracteres con `…`. Encabezado `activity · 1.284 filas · 3,2 s` | Formato numérico en español y tabla estable |
| `p6 endpoints` muestra el catálogo agrupado con títulos de grupo, en columnas `#`, `Tasks` (clave para `p6 get`), `Name` (título en Oracle), `Ruta`, `Grande` y `Verificado`. Tasks, Name y Ruta nunca se recortan. `--group` no distingue mayúsculas y un grupo inexistente sale con 2 listando los válidos | Misma agrupación que el menú de §10.5; el nombre y la ruta sirven para buscar la operación en la documentación |
| Los encabezados `Tasks` y `Name` de `p6 endpoints` van en inglés | Decisión del usuario: coinciden con la documentación de Oracle. Excepción a los textos en español |
| `Endpoint.doc_name` guarda el título exacto de la página de Oracle; las 14 entradas del catálogo quedan con `doc_verified=True` | Se revisaron las 14 páginas de la rama 24.x en M4 |
| `p6 syntax [TEMA]` muestra guías de `filter`, `order-by` y `fields` armadas solo con la documentación oficial (Entity Filtering, Ordering), con ejemplos de valores de muestra y la URL de referencia. Tema desconocido sale con 2. No toca red ni perfiles. `--filter`, `--order-by` y la pista del 400 remiten a la guía | Pedido del usuario tras la validación manual: consultar la sintaxis sin salir de la terminal |
| `--fields ObjectId, Id, Name` sin comillas no se une: la terminal parte los argumentos en cada espacio, y con comillas ya funciona | Decisión del usuario: es comportamiento de la terminal, no del programa |
| Ctrl+C, también dentro de una pregunta (`Abort` de Typer), sale con 130 y el mensaje estándar `Aborted!` en todos los comandos | Código de §12; Typer por sí solo sale con 1 al abortar una pregunta |
| `normalizar_campos` distingue `CAMPOS_VACIOS` («Se necesita al menos un campo en Fields.») de `PARAMETRO_REQUERIDO` | Mensaje de §11.1, regla 2, reutilizable en M5 |
| El asistente de perfiles vive en `cli/forms.py` sobre el `Prompter`. Los menús usan `PrompterQuestionary` (listas con flechas); `p6 profiles add/edit` usan `PrompterTexto` (`typer.prompt`), donde cada opción se elige por su tecla (`y · n · ca`, `c · g · x`), Enter toma la opción por defecto y otra respuesta repregunta con «Responde …» | Una sola lógica para los dos modos; los comandos siguen funcionando con entrada redirigida |
| `Prompter` usa `Opcion(titulo, valor, tecla, deshabilitada)` y `Separador(titulo)`. `PrompterQuestionary` pregunta con `unsafe_ask`: Ctrl+C lanza `KeyboardInterrupt` y sale con 130 y `Aborted!` | Una opción se identifica por su posición, no por cómo se comparan los valores; Ctrl+C no se confunde con una respuesta vacía |
| La clave se pide sin eco también en los menús (`typer.prompt(hide_input=True)`), no con `questionary.password` | `questionary.password` muestra un `*` por carácter y revelaría la longitud (§4.3) |
| Las opciones de hitos posteriores se ven deshabilitadas con «(próximamente)»: endpoints spread (M6) y Exportar a CSV/JSON (M7) | El flujo ya tiene la forma final de §10 sin ofrecer algo que no funciona |
| «Continuar» (§10.2) ejecuta `diagnosticar(sesion)`: login, `/project/fields` y canario, con el único intento de login de la sesión. Si da OK, esa sesión atiende todas las consultas del ambiente; si no, se muestra el diagnóstico y solo se ofrece *Actualizar credenciales* o *Volver al inicio* | Explica la causa de un fallo con §7 sin gastar un segundo intento |
| En §10.2, si el perfil no tiene clave guardada, se pide oculta, se usa solo en esa sesión y no se guarda; la pantalla muestra `•••••••• (no guardada)` | Mismo criterio que `doctor`, `get` y `fields`; para guardarla está «Actualizar credenciales» |
| «Actualizar credenciales» pide usuario (actual por defecto) y clave, y diagnostica con una sesión nueva. Si da OK, guarda ambos y sigue al menú de endpoints con esa misma sesión; si falla, no guarda nada. Si solo falla el keyring al guardar, se avisa y se sigue conectado | Un login por decisión del usuario, nunca dos |
| La sesión de cada ambiente vive en un `with`: el logout ocurre al cambiar de ambiente, al salir y también ante Ctrl+C | §6: logout al salir o al cambiar de ambiente, sin excepciones |
| Sin perfiles al abrir, la bienvenida y el asistente aparecen una sola vez; si se cancela, se muestra el menú de inicio | Evita un bucle entre la bienvenida y el asistente |
| En el formulario `entity` todo se valida antes de la confirmación (Fields, largo de URL y confirmación sin filtro en endpoints `large`, por defecto No). Cualquier error al ejecutar (no solo el 400) muestra mensaje y pista, y el formulario reaparece con lo escrito. «Cancelar» vuelve al menú de endpoints | Regla 7 de §11.1 aplicada a todo error de la consulta |
| El comando equivalente (§11.3) es `p6 get KEY --env PERFIL --fields "..."`, con `--filter` y `--order-by` solo si se escribieron y `--allow-unfiltered` si se confirmó sin filtro; los valores van entre comillas dobles | Repite exactamente la consulta enviada en modo flags |
| En los menús, la tabla muestra 25 filas con el aviso «Mostrando 25 de N filas.», sin mencionar `--max-rows` ni `--json` | Esas opciones son del modo flags; la exportación llega en M7 |
| `?` funciona en los tres campos del formulario `entity`: Fields lista los campos válidos; Filter y OrderBy muestran la guía de `p6 syntax` más el aviso de escribir el valor sin comillas dobles alrededor. Luego se vuelve a pedir el mismo campo. La cabecera dice «Consulta la documentación de Oracle o escribe ? en cualquier campo para ver ayuda aquí mismo.» | Pedido del usuario tras la validación manual: `?` en Filter u OrderBy se enviaba a P6 y la consulta fallaba; la documentación de Oracle y la ayuda en la terminal son caminos alternativos, no ambos obligatorios. Los ejemplos de las guías son de línea de comandos, donde sí se usan comillas |
| «¿Qué sigue?» ofrece «Ver la tabla completa (N filas)», solo con más de 25 filas, y «Ver el JSON completo», con al menos una fila. Usan las filas ya recibidas, sin consultar de nuevo a P6, y luego vuelve el mismo menú. La tabla completa sigue recortando celdas a 40 caracteres; el JSON va completo (indentación 2, sin escapar tildes), como `p6 get --json`. Con más de 500 filas se pide confirmar, por defecto No | Pedido del usuario tras la validación manual: ver la salida completa sin exportar. Con miles de filas la terminal tarda, el inicio se pierde al desplazarse y un Ctrl+C a mitad cierra el programa |
