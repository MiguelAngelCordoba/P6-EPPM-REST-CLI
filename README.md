# p6-eppm-rest-cli

Cliente de terminal, de **solo lectura**, para la API REST de Oracle Primavera P6 EPPM (validado contra la rama 24.x).

Guarda varios ambientes de P6, los elige con menús de flechas, diagnostica por qué falla una conexión y consulta endpoints GET, mostrando los resultados en tabla o exportándolos a CSV y JSON.

## Características

- **Varios ambientes** (perfiles) con un predeterminado; la contraseña vive en el almacén de credenciales del sistema operativo (keyring), nunca en archivos.
- **Diagnóstico de conexión** (`p6 doctor`) que distingue DNS, puerto, certificado, ruta equivocada, interfaz web en lugar de API, servlet comodín, DatabaseName inválido y credencial rechazada.
- **Catálogo de endpoints** agrupado (proyectos, actividades, códigos, recursos, UDF y series temporales), con el nombre y la ruta de la documentación de Oracle.
- **Consultas** con `Fields`, `Filter` y `OrderBy`, y ayuda en la terminal (`?` en los formularios, `p6 syntax`).
- **Lecturas masivas por lotes** de ObjectId, con barra de progreso y pausa entre lotes.
- **Series temporales** del servicio Spread, en tabla por período.
- **Exportación** a CSV (UTF-8 con BOM, listo para Excel y Power BI) y JSON; nunca sobrescribe un archivo.
- **Dos modos de uso:** menús interactivos (`p6`) o comandos con flags (`p6 get ...`).

## Requisitos

- Python 3.14 o superior.
- Windows o Linux (la CI prueba ambos).
- Un P6 EPPM con **P6 EPPM Web Services** publicado (normalmente en `{host}/p6ws`) y un usuario con acceso a Web Services.

## Instalación

El paquete no está publicado en PyPI: se instala desde el código.

**Windows (PowerShell)**

```powershell
git clone https://github.com/MiguelAngelCordoba/P6-EPPM-REST-CLI.git
cd P6-EPPM-REST-CLI
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install .
.venv\Scripts\activate
p6 --version
```

**Linux**

```bash
git clone https://github.com/MiguelAngelCordoba/P6-EPPM-REST-CLI.git
cd P6-EPPM-REST-CLI
python3.14 -m venv .venv
.venv/bin/python -m pip install .
source .venv/bin/activate
p6 --version
```

```
p6cli 1.0.0
```

## Primeros pasos

1. **Agregar un ambiente.** El asistente pide nombre, la URL de Web Services (se puede pegar tal cual, incluso con `/restapi/login?...`), DatabaseName, usuario, clave (oculta) y cómo validar el certificado TLS. Al final prueba la conexión, con un único intento de login.

   ```
   p6 profiles add
   ```

2. **Probar la conexión** cuando algo falle:

   ```
   p6 doctor demo
   ```

   ```
   Probando conexión con «demo» (se hará un intento de login)...
   ┌────────────────────────────────────────────── Diagnóstico · OK ───────────────────────────────────────────────┐
   │ Conectado.                                                                                                    │
   └───────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
   ┌────────┬────────────────────────────────────────┬────────┬──────────────────┬───────┬─────────────────────────┐
   │ Método │ URL                                    │ Código │ Content-Type     │ Bytes │ Inicio del cuerpo       │
   ├────────┼────────────────────────────────────────┼────────┼──────────────────┼───────┼─────────────────────────┤
   │ POST   │ https://localhost:7001/p6ws/restapi/lo │ 200    │ application/json │ 3     │ {}                      │
   │        │ gin?DatabaseName=orcl                  │        │                  │       │                         │
   │ GET    │ https://localhost:7001/p6ws/restapi/pr │ 200    │ application/json │ 44    │ ObjectId,Id,Name,Status │
   │        │ oject/fields?DatabaseName=orcl         │        │                  │       │ ,StartDate,FinishDate   │
   │ GET    │ https://localhost:7001/p6ws/restapi/__ │ 404    │                  │ 0     │                         │
   │        │ p6cli_canary__?DatabaseName=orcl       │        │                  │       │                         │
   └────────┴────────────────────────────────────────┴────────┴──────────────────┴───────┴─────────────────────────┘
   ```

   Los tres pasos juntos prueban que es la API real: el login devuelve JSON, `/project/fields` responde y una ruta inventada da 404.

3. **Abrir los menús:**

   ```
   p6
   ```

Los perfiles se guardan en `profiles.toml` dentro del directorio de configuración del usuario (`%APPDATA%\p6cli\` en Windows); la variable `P6CLI_CONFIG_DIR` permite cambiarlo.

```
p6 profiles list
```

```
┌────────┬───────────────────────────────┬──────────────┬─────────┬─────────────┬──────────┬────────────────┐
│ Nombre │ URL                           │ DatabaseName │ Usuario │ Clave       │ TLS      │ Predeterminado │
├────────┼───────────────────────────────┼──────────────┼─────────┼─────────────┼──────────┼────────────────┤
│ demo   │ https://localhost:7001/p6ws   │ orcl         │ admin   │ ••••••••    │ validado │ sí             │
│ otro   │ https://p6ws.example.com/p6ws │ otra_db      │ admin   │ (sin clave) │ validado │                │
└────────┴───────────────────────────────┴──────────────┴─────────┴─────────────┴──────────┴────────────────┘
```

## Uso interactivo

`p6` sin argumentos abre un flujo guiado con listas que se recorren con flechas: elegir ambiente, confirmar credenciales, elegir endpoint, llenar el formulario, confirmar y ver resultados.

```
P6 EPPM REST CLI  v1.0.0 — solo lectura

? ¿Qué ambiente quieres consultar?
 ❯ demo   localhost:7001     orcl      (predeterminado)
   otro   p6ws.example.com   otra_db
   ─────────────
   + Agregar ambiente
   ⚙ Administrar ambientes
   Salir
```

El formulario de un endpoint no trae valores preseleccionados: se escribe lo que se necesita, con la documentación de Oracle a mano o escribiendo `?` en cualquier campo (Fields lista los campos válidos; Filter y OrderBy muestran la guía de sintaxis). Antes de ejecutar se muestra el comando equivalente, para repetir la consulta con flags:

```
GET /activity
  Fields  : ObjectId, Id, Name, Status
  Filter  : ProjectObjectId:eq:4501
  OrderBy : ObjectId asc   (por defecto)
  Equivale a: p6 get activity --env demo --fields "ObjectId,Id,Name,Status" --filter "ProjectObjectId:eq:4501"

? ¿Ejecutar?
 ❯ Ejecutar
   Editar
   Cancelar
```

Después de cada consulta:

```
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

## Uso con comandos

Con argumentos, `p6` ejecuta directo, sin menús. `--env` es opcional si hay un perfil predeterminado. **No existe ningún flag para la contraseña:** si el perfil no tiene clave guardada, se pide oculta y no se guarda.

| Comando | Descripción |
|---|---|
| `p6` | Abre el flujo interactivo |
| `p6 --version` | Versión |
| `p6 profiles list \| add \| edit NAME \| remove NAME \| default NAME` | Administra los perfiles |
| `p6 doctor [NAME]` | Prueba de conexión con diagnóstico |
| `p6 endpoints [--group G]` | Catálogo, con el nombre y la ruta de la documentación de Oracle |
| `p6 syntax [TEMA]` | Guía de sintaxis de `filter`, `order-by` o `fields` |
| `p6 fields ENDPOINT` | Campos válidos de un endpoint, consultando P6 |
| `p6 get ENDPOINT --fields F [--filter X] [--order-by Y]` | Lectura simple |
| `p6 get-all ENDPOINT --fields F --filter X [--chunk N]` | Lectura masiva por lotes |
| `p6 spread ENDPOINT (--ids 1,2,3 \| --ids-from ARCHIVO) --spread-fields F [--period Week] [--start D] [--end D]` | Series temporales |

`get`, `get-all` y `spread` aceptan además `--env NAME`, `--max-rows N` (filas de la tabla; `0` = todas), `--json` y `--output ARCHIVO`. `p6 COMANDO --help` muestra todas las opciones.

### Lectura simple

```
p6 get project --fields ObjectId,Id,Name,Status --filter "Status:eq:'Active'"
```

```
project · 2 filas · 0,4 s
┌──────────┬─────────┬───────────────────────────────┬────────┐
│ ObjectId │ Id      │ Name                          │ Status │
├──────────┼─────────┼───────────────────────────────┼────────┤
│ 4501     │ EC00501 │ Ampliación de planta — fase 1 │ Active │
│ 4502     │ EC00502 │ Subestación eléctrica norte   │ Active │
└──────────┴─────────┴───────────────────────────────┴────────┘
```

Con `--json`, stdout lleva solo el JSON, listo para redirigir o pasar a `jq`:

```
p6 get project --fields ObjectId,Id,Name --filter "Id:eq:'EC00501'" --json
```

```json
[
  {
    "ObjectId": 4501,
    "Id": "EC00501",
    "Name": "Ampliación de planta — fase 1"
  }
]
```

Si P6 rechaza la consulta, se muestran su mensaje y una pista (salida 1):

```
P6 respondió 400 a GET https://localhost:7001/p6ws/restapi/project?Fields=ObjectId%2CNombre&...
Mensaje de P6: Nombre is not a valid field.
Pista: Revisa nombres en Fields, sintaxis de Filter (:eq: :gt: :lt: :gte: :lte: :like: :and: :or:) y OrderBy (Campo asc|desc). Guía: p6 syntax filter
```

### Lectura masiva

`get-all` primero pide los ObjectId que cumplen el filtro y luego trae los campos en lotes por rango de ObjectId (`id_chunk_size` del perfil o `--chunk`), con una pausa entre lotes y barra de progreso. Exige `Filter`: sin él serían todos los registros de la instancia.

```
p6 get-all activity --fields ObjectId,Id,Name --filter "ProjectObjectId:eq:4501"
```

### Series temporales (Spread)

```
p6 spread spread.activity --ids 4835,4845 --spread-fields PlannedLaborUnits --start 2026-01-05 --end 2026-01-25
```

```
spread.activity · 2 objetos · 3 períodos · 0,6 s
┌──────────────────┬─────────────────────┬─────────────────────┬───────────────────┬─────────────────────────────┐
│ ActivityObjectId │ StartDate           │ EndDate             │ PlannedLaborUnits │ CumulativePlannedLaborUnits │
├──────────────────┼─────────────────────┼─────────────────────┼───────────────────┼─────────────────────────────┤
│ 4835             │ 2026-01-05T00:00:00 │ 2026-01-11T23:59:59 │ 40.0              │ 40.0                        │
│ 4835             │ 2026-01-12T00:00:00 │ 2026-01-18T23:59:59 │ 32.0              │ 72.0                        │
│ 4845             │ 2026-01-12T00:00:00 │ 2026-01-18T23:59:59 │ 16.0              │ 16.0                        │
└──────────────────┴─────────────────────┴─────────────────────┴───────────────────┴─────────────────────────────┘
```

Los ObjectId también pueden salir de un CSV o JSON exportado antes (`--ids-from exports/actividades.csv`), con una columna `ObjectId`.

## Exportación

`--output` define el formato por la extensión (`.csv` o `.json`) y reemplaza la tabla en pantalla. En los menús, *Exportar a CSV/JSON* propone `exports\{perfil}_{endpoint}_{AAAAMMDD-HHMMSS}.{ext}` en el directorio de trabajo.

```
p6 get project --fields ObjectId,Id,Name --filter "Status:eq:'Active'" --output exports/proyectos.csv
```

```
project · 2 filas · 0,4 s
Exportado a exports\proyectos.csv (2 filas).
```

- **CSV:** UTF-8 con BOM, delimitado por coma, columnas en el orden de `Fields`. En Excel en español se abre con *Datos > Desde texto/CSV* (el doble clic espera `;`). Power BI y pandas lo leen sin configurar nada.
- **Spread en CSV:** formato largo, una fila por objeto × período × campo (`ActivityObjectId, StartDate, EndDate, SpreadField, Valor, Acumulado`), cómodo para Power BI.
- **JSON:** la lista completa, con indentación 2 y sin escapar tildes.
- **Nunca se sobrescribe:** si el archivo existe se escribe `proyectos_2.csv`, `_3`… y se informa la ruta real.

La carpeta `exports/` está en `.gitignore`: los datos exportados pueden ser de un cliente.

## Códigos de salida

| Código | Significado |
|---|---|
| `0` | Éxito |
| `1` | Error de P6 o HTTP (incluye un login fallido) |
| `2` | Error de uso o de configuración |
| `3` | Bloqueado por un guardarraíl (p. ej. consulta sin filtro sobre un endpoint grande) |
| `130` | Interrumpido con Ctrl+C |

## Seguridad

El programa está pensado para usarse contra instancias productivas, así que la seguridad está en el diseño y no depende de la buena voluntad del usuario:

- **Solo lectura.** Los únicos POST son `/login` y `/logout`. La sesión HTTP rechaza, sin enviar nada, cualquier otro verbo o ruta.
- **Claves en el keyring** del sistema operativo (Administrador de credenciales en Windows). No hay flag de contraseña ni variables de entorno con claves; en pantalla siempre se ve `••••••••`, sin revelar la longitud, y la clave se pide sin eco.
- **Un solo intento de login.** Un login fallido nunca se reintenta: P6 puede bloquear la cuenta. El diagnóstico reutiliza ese mismo intento para explicar la causa.
- **Sin redirecciones.** Ninguna petición sigue un redirect, porque requests reenviaría las cabeceras `username`, `password` y `authToken` al destino.
- **Sin secretos en errores.** Ninguna excepción ni mensaje lleva contraseñas, `authToken` ni cabeceras; los errores de red se relanzan sin la excepción original, que guarda la petición completa.
- **Sin falsos positivos.** Solo cuenta como API una respuesta JSON; un canario detecta servlets que responden a cualquier ruta. El detalle está en [APRENDIZAJES.md](docs/APRENDIZAJES.md).
- **Guardarraíles:** los endpoints que pueden devolver decenas de miles de filas exigen filtro (o confirmación explícita), y se valida el largo de la URL antes de enviar.
- **Repositorio:** gitleaks en pre-commit y en CI (sobre todo el historial); ejemplos y tests usan solo valores de muestra de Oracle (`localhost:7001`, `orcl`, `admin`) o `example.com`.

## Arquitectura

```
src/p6cli/
├── core/             # librería: sin print, sin prompts, sin rich/questionary/typer
│   ├── config.py     # directorio de configuración
│   ├── profiles.py   # Profile y ProfileStore (TOML, escritura atómica)
│   ├── secrets.py    # envoltorio de keyring
│   ├── urls.py       # normalización de la URL pegada por el usuario
│   ├── session.py    # login, cabeceras, logout; solo GET más /login y /logout
│   ├── diagnostics.py# prueba de conexión y clasificación de fallos
│   ├── catalog.py    # endpoints y plantillas entity / spread / custom
│   ├── client.py     # GET, lecturas por lotes, spread y guardarraíles
│   ├── export.py     # CSV y JSON
│   └── errors.py     # jerarquía de excepciones con motivos tipados
└── cli/              # interfaz
    ├── app.py        # comandos con flags (Typer); sin argumentos abre los menús
    ├── menus.py      # flujo interactivo
    ├── forms.py      # formularios de parámetros
    ├── prompter.py   # protocolo Prompter (questionary / typer.prompt / guion en tests)
    ├── render.py     # tablas, paneles y progreso (rich)
    └── messages.py   # todos los textos visibles, en español
```

- `core` nunca importa de `cli`: devuelve datos o lanza excepciones con un `motivo` y datos no sensibles; `cli` decide qué texto mostrar.
- El progreso de las lecturas largas sale de `core` por callbacks, no imprimiendo.
- Los menús dependen de un protocolo `Prompter`, así que los tests recorren el flujo completo con respuestas guionizadas.

## Decisiones de diseño

Algunas de las más relevantes; el registro completo está en [ESPECIFICACION.md §18](docs/ESPECIFICACION.md#18-registro-de-decisiones).

| Decisión | Motivo |
|---|---|
| Solo lectura | Uso exploratorio contra instancias productivas |
| Fields sin preselección | Lo que se consulta depende de la necesidad; `?` ayuda sin salir del formulario |
| `/fields` leído como texto con comas | P6 real responde con Content-Type JSON y cuerpo en texto plano, aunque Oracle documenta otra cosa |
| Lotes por rango de ObjectId en `get-all` | La API no pagina; el rango sobre IDs ya filtrados evita respuestas gigantes |
| CSV con coma y BOM | Power BI y pandas lo leen directo; Excel en español lo abre con *Desde texto/CSV* |
| Catálogo con `doc_verified` | Cada endpoint se revisa una vez contra la documentación de Oracle 24.x |
| Textos centralizados en `messages.py` | Toda la interfaz en español y en un solo archivo |

## Desarrollo

```bash
python -m pip install -e ".[dev]"
python -m pytest            # HTTP simulado con responses; nunca red real
python -m ruff check .
python -m ruff format --check .
python -m mypy              # strict
python -m pre_commit install
```

- Los tests nunca contactan un P6 real: HTTP simulado con `responses`, keyring en memoria y configuración en un directorio temporal (`P6CLI_CONFIG_DIR`).
- La CI (GitHub Actions) ejecuta lint, formato, tipos y tests en Windows y Ubuntu, más gitleaks.
- El proyecto se desarrolló hito por hito con [Claude Code](https://claude.com/claude-code), siguiendo el [plan](docs/PLAN.md) y la [especificación](docs/ESPECIFICACION.md). Las validaciones contra P6 real las hizo el autor a mano, solo con lecturas acotadas.

## Documentación

- [Especificación](docs/ESPECIFICACION.md): comportamiento completo y registro de decisiones.
- [Plan de desarrollo](docs/PLAN.md): hitos, criterios de aceptación y validaciones manuales.
- [Aprendizajes sobre la API de P6](docs/APRENDIZAJES.md): comportamiento real de la API y sus trampas.
- [Registro de cambios](CHANGELOG.md).
- [Documentación oficial de la API REST de P6 EPPM 24.x](https://docs.oracle.com/cd/F88966_01/English/Integration_Documentation/rest_api/toc.htm).

## Aviso

Proyecto personal e independiente, **sin afiliación, patrocinio ni respaldo de Oracle**. Oracle, Primavera y P6 son marcas registradas de Oracle Corporation y/o sus filiales. Los datos de los ejemplos son ficticios.

## Licencia

Sin licencia de uso: todos los derechos reservados. El código se puede leer, pero no reutilizar sin permiso del autor.
