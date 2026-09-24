# CLAUDE.md — p6-eppm-rest-cli

Cliente de terminal, de **solo lectura**, para la API REST de Oracle Primavera P6 EPPM (validado contra la rama 24.x). Guarda varios ambientes de P6, permite elegir uno con menús de flechas y consultar endpoints GET, mostrando resultados en la terminal o exportándolos a CSV/JSON.

Proyecto personal de portafolio, desarrollado hito por hito con Claude Code.

## Documentos de referencia

Lee lo que corresponda **antes** de proponer un plan:

| Documento | Contenido |
|---|---|
| `docs/ESPECIFICACION.md` | Qué hace el programa: flujos, perfiles, parámetros, catálogo, errores. Fuente de verdad del comportamiento |
| `docs/PLAN.md` | Hitos de la v1, criterios de aceptación y estado |
| `docs/APRENDIZAJES.md` | Comportamiento real de la API de P6 y sus trampas. Obligatorio antes de tocar autenticación, diagnóstico o manejo de errores |

Para endpoints y nombres de campos, la fuente de verdad es la documentación oficial de Oracle (rama 24.x):
https://docs.oracle.com/cd/F88966_01/English/Integration_Documentation/rest_api/toc.htm

## Reglas no negociables

1. **Solo lectura.** El cliente solo emite GET contra endpoints de datos. Los únicos POST permitidos son `/login` y `/logout`. Nunca PUT, PATCH, DELETE ni POST de datos, aunque un endpoint lo permita.
2. **Nunca contactes un P6 real.** No ejecutes `p6` ni `python -m p6cli` directamente: usarían credenciales reales guardadas en el keyring del usuario. Todo se prueba con `pytest` contra HTTP simulado. Las pruebas contra P6 reales las hace el usuario a mano.
3. **Nunca toques secretos.** No leas, imprimas, registres en logs ni incluyas en excepciones contraseñas, valores `authToken` ni cabeceras de autenticación. No leas `.env`, `.env.*` ni el directorio de configuración del usuario. En la interfaz la contraseña siempre se muestra enmascarada (`••••••••`).
4. **Nada de datos de clientes en el repositorio.** Ni hostnames reales, ni usuarios, ni `DatabaseName` reales, ni IDs de proyecto, ni respuestas capturadas de instancias reales. En ejemplos, docs y tests usa los valores de muestra de Oracle (`https://localhost:7001`, `DatabaseName=orcl`, usuario `admin`) o dominios `example.com`.
5. **Nunca reintentes un login fallido automáticamente.** P6 puede bloquear la cuenta. Un login fallido se reporta y el control vuelve al usuario.
6. **No agregues dependencias** fuera de las listadas en `docs/ESPECIFICACION.md` §17 sin preguntar.

## Arquitectura

```
src/p6cli/
├── core/   # librería: sin print, sin prompts, sin importar rich/questionary/typer
└── cli/    # interfaz: menús (questionary), comandos con flags (typer), render (rich)
```

- `core` nunca importa de `cli`. Devuelve datos o lanza excepciones tipadas; `cli` decide cómo mostrarlos.
- El progreso de operaciones largas se comunica desde `core` mediante callbacks, nunca imprimiendo.
- Todos los textos visibles al usuario viven en `cli/messages.py`, en español. Las descripciones del catálogo también van en español.
- Detalle de módulos en `docs/ESPECIFICACION.md` §3.

## Convenciones

- Python 3.14+, layout `src/`, empaquetado con `pyproject.toml`.
- **Identificadores, comentarios, docstrings y mensajes de commit en español.** Documentación (`docs/`, `README.md`, este archivo) en español. Textos de interfaz en español tambien.
- Type hints en todo el código; `mypy --strict` sobre `src/p6cli/core`.
- `ruff` para lint y formato.
- Commits con Conventional Commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`.

## Entorno virtual

- El proyecto usa un entorno virtual en `p6env/` (ignorado por git). Todo se instala y ejecuta dentro de él.
- **Nunca uses `pip`, `python` ni `pytest` a secas.** Usa siempre el intérprete del entorno por ruta explícita:
  - Windows: `p6env/Scripts/python -m pip install ...`, `p6env/Scripts/python -m pytest`
  - Linux/macOS: `p6env/bin/python -m ...`
- Nunca instales paquetes fuera de `p6env`, ni con `--user`, ni globales.
- Si `p6env` no existe, no lo crees por tu cuenta: avísame.

## Comandos

```bash
pip install -e ".[dev]"                    # instalar en modo desarrollo
pytest                                     # tests, siempre sin red
ruff check . && ruff format --check .      # lint y formato
mypy src                                   # tipos
```

## Forma de trabajo

- **Un hito por sesión.** Cuando el usuario indique un hito (comando `/hito M3`), lee su sección en `docs/PLAN.md`, propón un plan concreto (archivos, funciones, tests) y **espera aprobación** antes de escribir código.
- No amplíes el alcance. Si el hito requiere una decisión no documentada, pregunta.
- Cada cambio de comportamiento lleva su test. Los tests nunca usan red real: HTTP simulado con `responses`, keyring en memoria, directorio de configuración temporal vía `P6CLI_CONFIG_DIR`.
- **Definición de terminado de un hito:** tests en verde, `ruff` y `mypy` sin errores, criterios de aceptación cumplidos, casilla marcada en `docs/PLAN.md` y un mensaje de commit propuesto. El commit lo aprueba el usuario.

## Agregar un endpoint al catálogo

1. Abre su página en la documentación de Oracle (rama 24.x).
2. Si pide `Fields`, `Filter` y `OrderBy` → plantilla `entity`.
3. Si pide otros parámetros → plantilla `spread` o `custom`, declarando cada parámetro con su tipo.
4. Marca `doc_verified=True` solo si la página se revisó.
5. Si puede devolver decenas de miles de filas, márcalo `large=True`.
