# Plan de desarrollo — v1

Cada hito cabe en una sesión de Claude Code. Se trabajan en orden: cada uno se apoya en el anterior.

**Cómo iniciar un hito:** en Claude Code, `/hito M2`. Claude lee la documentación, propone un plan y espera tu aprobación. Al terminar: revisas, apruebas el commit y marcas el siguiente.

**Cómo cerrar un hito:** tests en verde, `ruff` y `mypy` limpios, criterios marcados aquí, commit.

---

## Estado

| Hito | Nombre | Estado |
|---|---|---|
| M0 | Preparación del repositorio | ⬜ |
| M1 | Esqueleto y calidad | ✅ |
| M2 | Perfiles, secretos y URLs | ✅ |
| M3 | Autenticación y diagnóstico | ✅ |
| M4 | Catálogo, cliente y comandos básicos | ✅ |
| M5 | Flujo interactivo | ✅ |
| M6 | Lecturas masivas y spread | ⬜ |
| M7 | Exportación | ⬜ |
| M8 | Modo automatización | ⬜ |
| M9 | Portafolio y release v1.0.0 | ⬜ |

---

## M0 — Preparación del repositorio (lo haces tú)

- [ ] Verificar Python 3.11 o superior: `py --version`.
- [ ] Crear la carpeta del proyecto **fuera de OneDrive** (ej. `C:\dev\p6-eppm-rest-cli`).
- [ ] Copiar el contenido del zip respetando la estructura (`docs/`, `.claude/`).
- [ ] `git init`, primer commit: `docs: add project specification and plan`.
- [ ] Crear el repositorio en GitHub **como privado** y conectarlo. Pasarlo a público solo después de confirmar con la empresa que puedes publicarlo.
- [ ] **Verificar las reglas de permisos de Claude Code:**
  1. Crear un `.env` de prueba con contenido falso (`FAKE_SECRET=123`). Está en `.gitignore`.
  2. Abrir Claude Code en la carpeta y ejecutar `/permissions`: deben aparecer las reglas `deny`.
  3. Pedirle que lea `.env`: debe negarse por la regla.
  4. Borrar el `.env` de prueba.

  Si en el paso 3 lo lee, las reglas no se están aplicando en tu versión: no guardes nada sensible en la carpeta del proyecto hasta resolverlo.

**Practica de Claude Code:** instalación, `/permissions`, cómo se carga `CLAUDE.md`.

---

## M1 — Esqueleto y calidad

Especificación: §3, §17.

- [x] `pyproject.toml` con layout `src/`, dependencias de §17 y extra `[dev]`.
- [x] Paquete `p6cli` con `__version__`, `__main__.py` y estructura de carpetas de §3 (módulos vacíos con docstring).
- [x] Comando `p6 --version` funcionando tras `pip install -e ".[dev]"`.
- [x] Configuración de `ruff`, `mypy` (strict en `core`) y `pytest` en `pyproject.toml`.
- [x] `.pre-commit-config.yaml` con ruff y **gitleaks** (escaneo de secretos).
- [x] GitHub Actions: lint, tipos y tests en cada push, en Windows y Ubuntu, más gitleaks.
- [x] Un test que verifique la versión.

**Decisiones tomadas antes de iniciar** (detalle en `ESPECIFICACION.md` §18):

- Backend de build `hatchling`, versión única en `src/p6cli/__init__.py`.
- Versión inicial `0.1.0`.
- Python 3.14+: `requires-python = ">=3.14"`, ruff/mypy apuntando a 3.14 y CI con 3.14 en Windows y Ubuntu.
- `p6` sin argumentos muestra un aviso en español (salida 0) hasta M5.
- `p6 --version` se verifica en tests con `CliRunner`; la prueba del comando instalado la haces tú a mano (Claude no ejecuta `p6`).

**Practica de Claude Code:** modo plan, revisar un plan antes de aprobarlo, commits por paso.

---

## M2 — Perfiles, secretos y URLs

Especificación: §4, §5.

- [x] `core/urls.py`: normalización con todos los casos de la tabla §5 como tests.
- [x] `core/profiles.py`: `Profile`, validación de nombre, `ProfileStore` con lectura/escritura TOML atómica y perfil predeterminado.
- [x] `core/secrets.py`: guardar, leer, borrar y renombrar en keyring; error claro sin backend.
- [x] `core/config.py`: resolución del directorio de configuración con `P6CLI_CONFIG_DIR`.
- [x] Comandos: `p6 profiles list | add | edit | remove | default` (sin prueba de conexión todavía).
- [x] Contraseña enmascarada en todo listado.
- [x] Tests con keyring en memoria y directorio temporal.

**Decisiones tomadas antes de iniciar** (detalle en `ESPECIFICACION.md` §18):

- El asistente de `add`/`edit` usa `typer.prompt`; el `Prompter` sigue en M5.
- `edit NAME` repite el asistente con los valores actuales por defecto, con un único aviso inicial de que Enter conserva cada valor; permite renombrar (mueve la clave).
- Confirmaciones siempre `(Y/n)` / `(y/N)`, solo `y` o `n` (ajuste pedido tras la prueba manual).
- Al eliminar el perfil predeterminado no se promueve otro: queda sin predeterminado.
- `timeout`, `id_chunk_size` y `throttle_seconds` no se piden en ningún comando: se editan en `profiles.toml` y se validan al leerlo.

**Practica de Claude Code:** pedir los tests primero y luego la implementación (TDD guiado).

---

## M3 — Autenticación y diagnóstico

Especificación: §6, §7. Leer `APRENDIZAJES.md` completo antes de empezar.

- [x] `core/session.py`: login, cabeceras, cookies, logout; sin reintentos; sin secretos en logs ni excepciones.
- [x] `core/diagnostics.py`: pasos y clasificación de §7 en el orden exacto.
- [x] Fixtures en `tests/fixtures/` para cada caso de §16, y un test por cada estado de la tabla §7.
- [x] Comando `p6 doctor [NAME]` con reporte legible.
- [x] `p6 profiles add` y `edit` ejecutan la prueba de conexión y ofrecen corregir, guardar de todas formas o cancelar.

**Decisiones tomadas antes de iniciar** (detalle en `ESPECIFICACION.md` §18):

- El canario se consulta con **GET**, no con POST: los únicos POST permitidos son `/login` y `/logout`.
- Si la prueba de conexión falla en `add`/`edit`: `c` corregir · `g` guardar de todas formas · `x` cancelar (por defecto `c`).
- Timeout `(10, perfil.timeout)`: 10 s fijos para conectar y el timeout del perfil para leer.
- `p6 doctor` sin clave guardada la pide oculta, la usa solo para esa prueba y no la guarda.
- `DiagnosticReport` no guarda textos; ninguna petición sigue redirecciones; un único intento de login por `Sesion`; DNS, TCP y TLS se deducen de la excepción de requests.
- `tests/fixtures/project_fields.json` tiene una estructura ilustrativa: el formato real de `/fields` se confirma en M4.

**Validación manual (tú):** `p6 doctor` contra tu instancia de pruebas y contra la productiva. Anota en `APRENDIZAJES.md` cualquier comportamiento nuevo, **anonimizado**.

**Practica de Claude Code:** crear tu primer comando personalizado propio en `.claude/commands/` (por ejemplo, uno que corra lint, tipos y tests y resuma los resultados).

---

## M4 — Catálogo, cliente y comandos básicos

Especificación: §8, §9, §12, §13 (tabla y JSON en pantalla), §14.

- [x] `core/catalog.py`: modelos, plantillas `entity`/`spread`/`custom` y catálogo inicial §8.3.
- [x] `core/client.py`: `get`, `fields`, guardarraíl `large`, completado de Filter/OrderBy, validación de content-type y de longitud de URL.
- [x] `core/errors.py`: jerarquía y pistas §14.
- [x] Comandos: `p6 endpoints`, `p6 fields`, `p6 get` con `--json`, `--max-rows`, `--allow-unfiltered`.
- [x] Códigos de salida §12.

**Decisiones tomadas antes de iniciar** (detalle en `ESPECIFICACION.md` §18):

- `--max-rows N` limita solo las filas de la tabla (25 por defecto, `0` = todas); `--json` imprime siempre la lista completa.
- `get` y `fields` sin clave guardada la piden oculta, la usan solo en esa ejecución y no la guardan (como `doctor`).
- Un login fallido en `get`/`fields` se clasifica con las filas 5–9 de §7, sin peticiones extra, y sugiere `p6 doctor NAME`. Salida 1.
- Toda la validación (parámetros, guardarraíl, largo de URL) ocurre antes de pedir la clave y de hacer login.
- `/fields` se acepta como lista JSON o como texto separado por comas, hasta confirmar el formato real.
- Ctrl+C (también dentro de una pregunta) sale con 130 y `Aborted!`.

**Validación manual (tú)** — no hay instancia de pruebas: se hace contra productivo, solo con lecturas acotadas.

- [x] `p6 get project --fields ObjectId,Id,Name`, filtros, `--max-rows`, `--order-by` y `--json`.
- [x] `p6 fields project` → reveló que `/fields` es texto plano con comas, no JSON válido (corregido).
- [x] Filtro sin resultados → `200 []`. Campo inexistente → 400 `<Campo> is not a valid field.`
- [ ] Repetir `p6 fields project`, `p6 endpoints` y `p6 syntax filter` tras los ajustes.

**Ajustes tras la validación manual** (detalle en `ESPECIFICACION.md` §18):

- `/fields` se lee como texto plano separado por comas (también acepta JSON).
- `p6 endpoints` muestra `Tasks` (clave) y `Name` (título en Oracle) con la ruta exacta; las 14 páginas se revisaron y quedan `doc_verified`.
- Nuevo `p6 syntax [TEMA]`: guías de `filter`, `order-by` y `fields` desde la documentación oficial.
- `--fields` con espacios sin comillas no se une: lo parte la terminal.

**Practica de Claude Code:** configurar un hook que ejecute `ruff format` y `ruff check` después de cada edición.

---

## M5 — Flujo interactivo

Especificación: §10, §11.

- [x] `cli/prompter.py`: protocolo `Prompter` e implementación con questionary.
- [x] `cli/messages.py`: todos los textos de §10 y §11.
- [x] `cli/menus.py`: inicio, credenciales, agregar, administrar, elegir endpoint, resultados y siguiente paso.
- [x] `cli/forms.py`: formulario `entity` con las 7 reglas de §11.1 y la confirmación §11.3 con el comando equivalente.
- [x] Logout al cambiar de ambiente y al salir.
- [x] Tests de transiciones con `Prompter` guionizado.

**Decisiones tomadas antes de iniciar** (detalle en `ESPECIFICACION.md` §18):

- El asistente de perfiles pasa a `cli/forms.py` sobre el `Prompter`. Los menús usan `PrompterQuestionary` (listas con flechas); `p6 profiles add/edit` usan `PrompterTexto` (`typer.prompt`), con las mismas teclas `y · n · ca` y `c · g · x`.
- Spread (M6) y Exportar a CSV/JSON (M7) aparecen deshabilitados con «(próximamente)».
- Si el perfil no tiene clave guardada, se pide oculta, se usa solo en esa sesión y no se guarda; para guardarla está «Actualizar credenciales».
- «Continuar» ejecuta la prueba de conexión completa (§7) con el único intento de login de la sesión; si da OK, esa sesión atiende todas las consultas del ambiente.
- «Actualizar credenciales» prueba con una sesión nueva; si da OK guarda usuario y clave y sigue con esa misma sesión, sin un segundo login.
- La clave se pide sin eco (no con `questionary.password`, que muestra un `*` por carácter).
- Cualquier error al ejecutar la consulta (no solo el 400) muestra mensaje y pista, y el formulario reaparece con lo escrito.

**Validación manual (tú)** — contra productivo, solo lecturas acotadas (no hay instancia de pruebas):

- [x] `p6` → elegir ambiente → Continuar → `project` con `?` en Fields → consulta filtrada → Nueva consulta → Cambiar ambiente → Salir.
- [x] Ctrl+C dentro de una lista y dentro de un texto: sale con `Aborted!`.
- [x] Revisar que las listas se ven bien en la terminal de Windows (separadores, opciones deshabilitadas, `⚙`).

**Ajustes tras la validación manual** (detalle en `ESPECIFICACION.md` §18):

- `?` funciona en Fields, Filter y OrderBy: Fields lista los campos válidos; Filter y OrderBy muestran la guía de `p6 syntax` con un aviso de comillas, y se vuelve a pedir el mismo campo.
- La cabecera del formulario deja claro que la documentación de Oracle y la ayuda con `?` son caminos alternativos.
- [x] Repetir `?` en Fields, Filter y OrderBy tras el ajuste.
- En «¿Qué sigue?» se agregan «Ver la tabla completa» y «Ver el JSON completo», sin consultar de nuevo a P6; con más de 500 filas se pide confirmar (por defecto No).
- [x] Probar «Ver la tabla completa» y «Ver el JSON completo» con una consulta de más de 25 filas.

**Practica de Claude Code:** pedir una revisión crítica del flujo contra la especificación antes de dar el hito por cerrado.

---

## M6 — Lecturas masivas y spread

Especificación: §8.2 (`spread`), §9 (`get_all`, `get_spread`), §11.2.

- [ ] `get_all` con sondeo de IDs, lotes por rango, rechazo de `:or:`, pausa y callback de progreso.
- [ ] `get_spread` con troceo de IDs.
- [ ] Formulario `spread` con los tres orígenes de ObjectId.
- [ ] Comandos `p6 get-all` y `p6 spread`.
- [ ] Barra de progreso en la interfaz.

**Validación manual (tú):** un spread semanal sobre pocas actividades de un proyecto pequeño. Confirmar el formato de fecha aceptado y compartir con Claude una **estructura de ejemplo anonimizada** de la respuesta para el hito M7.

**Practica de Claude Code:** crear un subagente revisor en `.claude/agents/` que audite los cambios contra las reglas de `CLAUDE.md`.

---

## M7 — Exportación

Especificación: §13.

- [ ] `core/export.py`: CSV (`utf-8-sig`) y JSON.
- [ ] Spread a CSV en formato largo según la estructura confirmada en M6.
- [ ] Ruta por defecto con marca de tiempo y sin sobrescritura.
- [ ] Opciones de exportación en el menú de resultados y `--output` en comandos.

---

## M8 — Modo automatización

Especificación: §15.

- [ ] Perfil efímero `env` a partir de variables `P6CLI_*`.
- [ ] `env.example` actualizado.
- [ ] Tests con variables simuladas.

---

## M9 — Portafolio y release v1.0.0

- [ ] `README.md` completo: qué es, instalación, uso con capturas o GIF **grabados contra el mock**, arquitectura, decisiones de diseño y seguridad.
- [ ] Aviso de que el proyecto no está afiliado a Oracle.
- [ ] `LICENSE` (MIT o Apache-2.0), después de confirmar con la empresa.
- [ ] `CHANGELOG.md`.
- [ ] Revisión final: ningún dato de clientes en el código, los docs **ni el historial de git**.
- [ ] Tag `v1.0.0` y release en GitHub.
- [ ] Pasar el repositorio a público.

---

## Después de la v1 (no iniciar sin decidirlo)

- Más endpoints en el catálogo, según necesidad.
- Consultas guardadas como plantillas reutilizables.
- Exportación a Excel o Parquet.
- Interfaz gráfica sobre la misma librería `core`.
- OAuth para instancias en Oracle Cloud.
- Uso de `core` como librería desde un extractor hacia base de datos (repositorio privado aparte).
