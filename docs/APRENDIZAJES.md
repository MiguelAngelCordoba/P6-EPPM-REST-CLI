# Aprendizajes sobre la API REST de P6 EPPM

Lo que descubrimos conectándonos a instalaciones reales de P6 EPPM 24.x: una **on-premise** publicada a internet mediante un gateway, y una **en la nube**. Todo está anonimizado a propósito: este archivo es público.

Mucho de esto no está en la documentación de Oracle o está en ella de forma ambigua. Léelo antes de tocar autenticación, diagnóstico o manejo de errores.

---

## 1. Dónde vive la API

- La API es parte de **P6 EPPM Web Services**, un módulo aparte de la interfaz web.
- Contexto web: `/p6ws`. Base de la API: `{host}/p6ws/restapi`.
- La interfaz web vive en `/p6`. **`/p6/restapi` no es la API**, aunque a veces responda (ver §3).

## 2. El host dedicado: la trampa que más tiempo costó

Ambas instalaciones publican Web Services en un **host distinto al de la interfaz**:

| Qué | Patrón observado |
|---|---|
| Interfaz web | `https://p6.<dominio>/p6/` |
| Web Services | `https://p6ws.<dominio>/p6ws/` |

En el host de la interfaz, `/p6ws` responde 404: el proxy simplemente no publica esa ruta ahí. La documentación y los ejemplos de Oracle usan `localhost:7001`, así que no lo sugieren.

**Regla:** si `/p6ws` da 404 en el host de la interfaz, prueba el host análogo `p6ws.<dominio>` antes de concluir que la API no existe.

## 3. Falsos positivos: tres formas de parecer la API sin serlo

Delante de P6 suele haber un reverse proxy (en la instalación on-premise: un gateway en la nube → Apache/Oracle HTTP Server → WebLogic). Eso produce respuestas engañosas:

| Qué se observó | Qué era en realidad | Cómo reconocerlo |
|---|---|---|
| `404` con página HTML genérica, DTD HTML 2.0, "The requested URL was not found on this server" | El **Apache** delante de WebLogic respondiendo él mismo: la ruta no está enrutada | Es la página 404 por defecto de Apache. La petición nunca llegó a P6 |
| `401` con HTML cuyo cuerpo es `/p6/action/login?sessionExpired=true&DatabaseName=...` | El **filtro de login de la interfaz web** interceptando cualquier ruta bajo `/p6` | Content-Type HTML y redirección al login de la UI |
| `200` vacío a cualquier `POST` y `405 HTTP method GET is not supported by this URL` a `GET` | El **servlet de P6 Professional Cloud Connect**, mapeado con comodín | Responde igual a una ruta inventada. La API real sí admite `GET /{servicio}/fields` |

**Reglas que salieron de esto:**

- Solo cuenta como éxito una respuesta con `Content-Type` JSON.
- Enviar siempre una petición a una **ruta canario inventada**: la API real responde 404; si responde otra cosa, el contexto es un comodín y ninguno de sus 200 significa nada.
- Un 405 en un GET documentado significa que en esa ruta hay otra cosa.

## 4. DatabaseName

- Es el **alias de la instancia de base de datos configurado en P6**. Cada instalación tiene el suyo.
- `orcl` aparece en todos los ejemplos de Oracle junto a `localhost:7001` y `admin:admin`: son valores de muestra, no constantes. La plantilla de la documentación no lo pone entre `< >` como las demás variables, lo cual induce a error.
- Con un alias inválido, el login responde **`401` JSON `{"message":"Invalid database name passed."}`**. Es un error de aplicación limpio: confirma que llegaste a la API real.
- En la instalación on-premise, los alias válidos coincidían con los *service names* de Oracle de cada base (una por PDB). En la nube, el alias no se parecía al service name. Si el alias es desconocido, preguntar al administrador de P6 es más rápido que adivinar.

## 5. Credencial rechazada: el 500 que no dice nada

- Con un alias **válido** y una credencial **inválida**, el login no responde 401: responde **`500` con el cuerpo `Request failed.`**.
- Pasar de "Invalid database name" (401) a "Request failed." (500) significa que el alias es correcto y el problema está en la fase de autenticación: clave incorrecta, cuenta bloqueada, cuenta inexistente en esa instancia o sin acceso a Web Services.
- **Cada intento cuenta para el bloqueo de la cuenta.** Ante un 500 en el login: parar, verificar la credencial entrando a la interfaz web y pedir al administrador que revise la cuenta. Nunca reintentar en bucle.

## 6. `/fields` no prueba nada sobre la autenticación

`GET /project/fields` devolvió **200 JSON** (el mismo contenido byte por byte en ambas instalaciones) incluso con un DatabaseName inválido. Es un endpoint de metadatos: confirma que la ruta es la API, no que la credencial sirva. La autenticación solo se confirma con un login 200.

## 7. Autenticación

- **Username Token Profile** (lo que funcionó en ambas): cabecera `authToken` con base64 de `usuario:contraseña`, y login con `POST /login?DatabaseName=...` más cabeceras `username` y `password`.
- La plantilla de la documentación pone `DatabaseName` en **cada** llamada a un servicio, no solo en el login. El cliente lo envía siempre.
- **OAuth** solo aplica a instancias hospedadas en Oracle Cloud Infrastructure. En ambas instalaciones `/p6ws/oauth/token` **existe pero responde 500**: está desplegado sin configurar.
- Un modo "automático" que prueba token y cae a OAuth si falla es mala idea: el 500 de OAuth tapa el error real del login.

## 8. El contrato de las lecturas

- Las lecturas estándar (`GET /activity`, `/project`...) reciben `Fields`, `Filter` y `OrderBy`. La documentación marca los tres como obligatorios.
- Operadores de filtro: `:eq:` `:gt:` `:lt:` `:gte:` `:lte:` `!=` `:like:` (comodín `%`), combinados con `:and:` y `:or:`.
- La documentación **no define paréntesis**. Combinar un filtro con `:or:` y un rango adicional con `:and:` tiene precedencia no garantizada.
- Cada endpoint tiene `GET /{servicio}/fields` para descubrir los nombres de campo válidos de esa instancia.
- **No todos los GET siguen ese contrato:** los de spread piden otros parámetros (§10).

## 9. No hay paginación

- No existe `limit`, `offset` ni cursor en ningún GET.
- Oracle advierte explícitamente que las lecturas grandes pueden causar timeouts y falta de memoria en el servidor, y recomienda: perfil Admin Superuser, pocos campos, filtros estrechos y, para volúmenes masivos, exportar a XML.
- **Paginación simulada:** pedir primero solo `ObjectId` con el filtro, y luego traer los campos completos en lotes acotados con `ObjectId:gte:X :and: ObjectId:lte:Y`.
- Recortar resultados en el cliente no reduce la carga del servidor.

## 10. El servicio Spread

- Devuelve series temporales ya calculadas por período: unidades, costos, valor ganado, acumulados.
- **Live** (actividad, asignación de recurso): se calcula sobre los datos actuales, sin depender del job Summarizer.
- **Summarized** (EPS, proyecto, WBS, recursos y roles de proyecto): depende de la última corrida del Summarizer.
- Exige **listas explícitas de ObjectId** (`ActivityObjectId=1,2,3`). No acepta "todo el proyecto": hay que obtener los IDs antes y trocearlos, cuidando el largo de la URL.
- Parámetros: `PeriodType` (Hour, Day, Week, Month, Quarter, Year, FinancialPeriod), `StartDate`, `EndDate`, `IncludeCumulative`, `SpreadField`.

## 11. Permisos enmascarados

La API responde **401 o 404** cuando la cuenta no tiene autorización sobre el objeto. Un 404 puede significar "no existe" o "no tienes permiso". Si la ruta está confirmada por el diagnóstico y aparece un 404, revisar el perfil global y el acceso OBS de la cuenta.

## 12. La versión importa

- La documentación de Oracle tiene una rama por versión. Endpoints como `udfValue` o las variantes Zip del spread no existen en todas.
- Verificar la versión de la instancia y usar la rama correspondiente. Este proyecto usa la **24.x**.

## 13. Detalles prácticos

- **Certificados:** una instalación on-premise accedida por red interna puede usar una CA propia. Configurar el `.pem`; nunca desactivar la validación contra productivo.
- **Varios hostnames, una IP:** en la instalación on-premise, el host de Web Services y el de Cloud Connect resolvían a la misma IP pública: un gateway enrutando por nombre de host.
- **`python-dotenv`:** expande `$` como variable e interpreta `#` como comentario. Una contraseña con esos caracteres se corrompe sin aviso si no va entre comillas simples. Motivo adicional para no guardar contraseñas en `.env`.
- **curl en Windows:** en PowerShell, `curl` es un alias de `Invoke-WebRequest`; usar `curl.exe`.

---

## Tabla de diagnóstico rápido

| Síntoma en el login | Causa probable | Acción |
|---|---|---|
| 404 HTML de Apache | Web Services no publicado en ese host | Probar `p6ws.<dominio>` |
| 401 HTML con redirección a `/p6/action/login` | Es la interfaz web | Cambiar a la URL de Web Services |
| 200 vacío y el canario también 200 | Servlet comodín (Cloud Connect) | Cambiar de host o contexto |
| 401 JSON "Invalid database name passed." | Alias incorrecto | Pedir el alias al administrador |
| 500 "Request failed." | Credencial rechazada o cuenta sin acceso | **Parar.** Verificar en la interfaz web y con el administrador |
| 200 JSON | Conectado | — |

## Referencias oficiales (rama 24.x)

- Índice de la API: https://docs.oracle.com/cd/F88966_01/English/Integration_Documentation/rest_api/toc.htm
- Autenticación estándar: https://docs.oracle.com/cd/F88966_01/English/Integration_Documentation/rest_api/D99833.html
- Filtrado de entidades: https://docs.oracle.com/cd/F88966_01/English/Integration_Documentation/rest_api/D99716.html
- Uso de filtros: https://docs.oracle.com/cd/F88966_01/English/Integration_Documentation/rest_api/D102455.html
- Recomendaciones de rendimiento: https://docs.oracle.com/cd/F88966_01/English/Integration_Documentation/rest_api/D102457.html
