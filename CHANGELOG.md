# Registro de cambios

Todos los cambios relevantes de este proyecto se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [versionado semántico](https://semver.org/lang/es/).

## [1.0.0] - 2026-09-28

Primera versión estable. Cliente de terminal, de solo lectura, para la API REST de Oracle Primavera P6 EPPM, validado contra la rama 24.x.

### Agregado

**Perfiles y secretos**

- Varios ambientes de P6 en `profiles.toml`, con perfil predeterminado y escritura atómica: `p6 profiles list | add | edit | remove | default`.
- Contraseñas en el keyring del sistema operativo, siempre enmascaradas como `••••••••`; sin flag de contraseña.
- Normalización de la URL pegada por el usuario (host y contexto), con aviso si es la interfaz web o HTTP sin cifrado.
- Validación TLS configurable por perfil: sí, no o CA propia (`.pem`).

**Autenticación y diagnóstico**

- Login con Username Token Profile, un único intento por sesión, sin reintentos ni redirecciones, y logout al salir o al cambiar de ambiente.
- `p6 doctor`: prueba de conexión (login, `/project/fields` y canario) que distingue red, TLS, ruta no publicada, interfaz web, servlet comodín, DatabaseName inválido y credencial rechazada.
- Prueba de conexión al agregar o editar un perfil, con las opciones corregir, guardar de todas formas o cancelar.

**Catálogo y consultas**

- Catálogo de 14 endpoints verificados contra la documentación de Oracle 24.x, agrupados en proyectos, actividades, códigos, recursos, UDF y series temporales: `p6 endpoints`.
- `p6 get` con `Fields`, `Filter` y `OrderBy`; `p6 fields` para ver los campos válidos; `p6 syntax` con guías de sintaxis.
- Guardarraíles: filtro obligatorio (o `--allow-unfiltered`) en endpoints grandes y validación del largo de la URL antes de enviar.
- Errores de P6 con su mensaje y una pista por código HTTP; códigos de salida `0`, `1`, `2`, `3` y `130`.

**Lecturas masivas y spread**

- `p6 get-all`: sondeo de ObjectId y lotes por rango, con pausa entre lotes y barra de progreso.
- `p6 spread` para `spread.activity` y `spread.resourceAssignment`, con IDs escritos o leídos de un CSV/JSON, y tabla por período.

**Exportación**

- CSV (UTF-8 con BOM, coma) y JSON con `--output` o desde el menú; spread en CSV de formato largo para Power BI.
- Nombre por defecto con marca de tiempo; nunca se sobrescribe un archivo (sufijos `_2`, `_3`…).

**Flujo interactivo**

- `p6` sin argumentos abre menús con flechas: elegir ambiente, credenciales, endpoint, formulario con ayuda `?`, confirmación con el comando equivalente y resultados.
- Tras cada consulta: ver la tabla o el JSON completos, exportar, nueva consulta, otro endpoint o cambiar de ambiente.

**Calidad**

- Tests con HTTP simulado, keyring en memoria y configuración temporal; `ruff`, `mypy` estricto, pre-commit con gitleaks y CI en Windows y Ubuntu.

### No incluido

- Operaciones de escritura en P6, OAuth e interfaz gráfica.
- Modo por variables de entorno para credenciales: se descartó durante el desarrollo, porque el programa es de uso manual y el keyring es más seguro.

[1.0.0]: https://github.com/MiguelAngelCordoba/P6-EPPM-REST-CLI/releases/tag/v1.0.0
