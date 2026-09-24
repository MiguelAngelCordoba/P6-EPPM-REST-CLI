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
| M2 | Perfiles, secretos y URLs | ⬜ |
| M3 | Autenticación y diagnóstico | ⬜ |
| M4 | Catálogo, cliente y comandos básicos | ⬜ |
| M5 | Flujo interactivo | ⬜ |
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

- [ ] `core/urls.py`: normalización con todos los casos de la tabla §5 como tests.
- [ ] `core/profiles.py`: `Profile`, validación de nombre, `ProfileStore` con lectura/escritura TOML atómica y perfil predeterminado.
- [ ] `core/secrets.py`: guardar, leer, borrar y renombrar en keyring; error claro sin backend.
- [ ] `core/config.py`: resolución del directorio de configuración con `P6CLI_CONFIG_DIR`.
- [ ] Comandos: `p6 profiles list | add | edit | remove | default` (sin prueba de conexión todavía).
- [ ] Contraseña enmascarada en todo listado.
- [ ] Tests con keyring en memoria y directorio temporal.

**Practica de Claude Code:** pedir los tests primero y luego la implementación (TDD guiado).

---

## M3 — Autenticación y diagnóstico

Especificación: §6, §7. Leer `APRENDIZAJES.md` completo antes de empezar.

- [ ] `core/session.py`: login, cabeceras, cookies, logout; sin reintentos; sin secretos en logs ni excepciones.
- [ ] `core/diagnostics.py`: pasos y clasificación de §7 en el orden exacto.
- [ ] Fixtures en `tests/fixtures/` para cada caso de §16, y un test por cada estado de la tabla §7.
- [ ] Comando `p6 doctor [NAME]` con reporte legible.
- [ ] `p6 profiles add` y `edit` ejecutan la prueba de conexión y ofrecen corregir, guardar de todas formas o cancelar.

**Validación manual (tú):** `p6 doctor` contra tu instancia de pruebas y contra la productiva. Anota en `APRENDIZAJES.md` cualquier comportamiento nuevo, **anonimizado**.

**Practica de Claude Code:** crear tu primer comando personalizado propio en `.claude/commands/` (por ejemplo, uno que corra lint, tipos y tests y resuma los resultados).

---

## M4 — Catálogo, cliente y comandos básicos

Especificación: §8, §9, §12, §13 (tabla y JSON en pantalla), §14.

- [ ] `core/catalog.py`: modelos, plantillas `entity`/`spread`/`custom` y catálogo inicial §8.3.
- [ ] `core/client.py`: `get`, `fields`, guardarraíl `large`, completado de Filter/OrderBy, validación de content-type y de longitud de URL.
- [ ] `core/errors.py`: jerarquía y pistas §14.
- [ ] Comandos: `p6 endpoints`, `p6 fields`, `p6 get` con `--json`, `--max-rows`, `--allow-unfiltered`.
- [ ] Códigos de salida §12.

**Validación manual (tú):** `p6 get project --fields ObjectId,Id,Name` contra tu instancia de pruebas.

**Practica de Claude Code:** configurar un hook que ejecute `ruff format` y `ruff check` después de cada edición.

---

## M5 — Flujo interactivo

Especificación: §10, §11.

- [ ] `cli/prompter.py`: protocolo `Prompter` e implementación con questionary.
- [ ] `cli/messages.py`: todos los textos de §10 y §11.
- [ ] `cli/menus.py`: inicio, credenciales, agregar, administrar, elegir endpoint, resultados y siguiente paso.
- [ ] `cli/forms.py`: formulario `entity` con las 7 reglas de §11.1 y la confirmación §11.3 con el comando equivalente.
- [ ] Logout al cambiar de ambiente y al salir.
- [ ] Tests de transiciones con `Prompter` guionizado.

**Validación manual (tú):** recorrer el flujo completo contra tu instancia de pruebas.

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
