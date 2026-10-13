# Codea2Server

Servidor de datos de **CODEA 2**, el escape room educativo en VR de Yachay Tech. Hace dos cosas:

1. **Recibe** el JSON de cada sesión que sube el visor (`POST /upload`).
2. **Muestra** esas sesiones en un panel web centrado en las métricas del estudio (dos comunes
   y tres por escenario), con la ficha de cada sesión y todo tabulado para descargar.

Corre en Docker en la Raspberry Pi, detrás del túnel de Cloudflare:
**<https://codea2.penginexr.com>**

## Actualizar la Raspberry Pi

```bash
cd ~/Services/JSONServer      # la carpeta de este repositorio en la Pi
git pull
docker compose up -d --build
```

Eso es todo. El contenedor se sigue llamando `json-uploader` y los datos siguen en `./uploads`.

```bash
curl http://localhost:26332/health     # {"status":"alive"}
docker logs -f json-uploader           # cada petición, cada subida y los errores
```

### Solo la primera vez: de `csv.penginexr.com:8090` a `codea2.penginexr.com:26332`

El puerto del host cambió de 8090 a **26332** (CODEA en un teclado de teléfono: C=2 O=6 D=3 E=3
A=2), así que el túnel hay que apuntarlo al puerto nuevo. Sin este paso Cloudflare da 502.

1. **Cloudflare** → Zero Trust → Networks → Tunnels → el túnel de la Pi → *Public Hostname*:
   - Añadir `codea2.penginexr.com` → servicio `HTTP` → `raspberrypi:26332`.
   - Mientras quede algún visor con el APK anterior, dejar `csv.penginexr.com` y cambiarle el
     servicio a `raspberrypi:26332`. Si no, esos visores no pueden subir (el JSON no se pierde:
     se queda en el visor y se puede subir a mano desde el panel).
2. **Unity** → `JSONUploader`: la URL pasa a `https://codea2.penginexr.com/upload`. Recompilar el APK.
3. Comprobar desde fuera: `curl https://codea2.penginexr.com/health`.

## Configuración

Sin tocar nada funciona con los valores de `docker-compose.yml`. Para cambiarlos, copia
`.env.example` a `.env` (no se sube al repositorio) y vuelve a lanzar `docker compose up -d`.

| Variable | Por defecto | Para qué |
|---|---|---|
| `UPLOAD_API_KEY` | la del compose | Clave con la que sube el visor (`X-API-Key`). La misma que lleva `JSONUploader.cs` |
| `DASHBOARD_PASSWORD` | la clave de subida | Contraseña del panel |
| `DASHBOARD_PUBLIC` | vacío | `1` deja ver y descargar sin contraseña. Editar sigue pidiéndola |
| `DASHBOARD_TZ` | `America/Guayaquil` | Zona horaria en la que se muestran las horas |
| `ANALYZE_OLD_FORMAT` | vacío | `1` mete en el análisis las sesiones con el JSON anterior al 06/10/2026 |

**La contraseña del panel es, por defecto, la clave de subida.** Esa clave viaja dentro del
APK, así que conviene poner una `DASHBOARD_PASSWORD` propia: con ella, la clave del visor solo
sirve para subir y no para leer.

## El panel

| Página | Qué hay |
|---|---|
| **Métricas** | La página principal. Por escenario: MC1 logro final, MC2 tiempo registrado y sus tres métricas (E1A–E4C), siempre con numerador, denominador y exclusiones. Una sola dificultad cada vez. Al final, la evidencia de pilares de las fichas |
| **Sesiones** | Una fila por partida, ordenable y con buscador. Desde aquí se excluye una sesión del análisis |
| **Detalle de una sesión** | Sus métricas, línea de tiempo, cada intento, selección y colocación con su hora, avisos de integridad, **ficha de sesión** y JSON original |
| **Datos** | Las tablas, con vista previa, diccionario de columnas y descarga |
| **Archivos** | Lo que hay en `uploads/` y su estado. Subida a mano de los JSON sacados del visor por cable |
| **Exploración** | Lo que no es métrica del estudio pero ayuda a preparar preguntas: tiempos sesión a sesión, secuencias probadas, qué opción se marcó en cada módulo, qué ficha se puso en cada hueco |

Los filtros de arriba (fechas, dificultad, PIN) valen para todo lo que hay debajo **y para las
descargas**. En PIN se pueden poner varios, comodines y descartes: `0101 02* -0000`.

### Las métricas

Siguen el documento «Métricas por escenario de CODEA2» (09/10/2026). Las reglas están en
`codea2/metrics.py`:

- La unidad es una sesión en un escenario; las dificultades no se mezclan.
- Lo que no se puede calcular queda **sin dato**, nunca en cero (K de quien no resuelve, un
  porcentaje con denominador cero).
- **MC1** excluye del denominador los escenarios no iniciados, los que quedan sin cierre
  confirmado y las interrupciones técnicas. El *motivo de cierre* de la ficha decide los dudosos.
  Una sala que agota sus 5 minutos (`timedOut`, desde el 12/10/2026) es un resultado final:
  cuenta como no completada, y la tarjeta dice cuántas hubo.
- **MC2** solo usa el tiempo de escenarios completados cuyo cronómetro no tiene avisos
  (`evento_antes`, `evento_despues`, `tiempo_distinto`).
- Los porcentajes son el promedio de los porcentajes de cada sesión; el global (suma de F entre
  suma de N) se muestra al lado.
- En el escenario 3 no hay tasa de fallos: `solved = false` es una pasada intermedia.
- El documento se escribió con el formato de JSON anterior. Con el actual, E1C son choques y
  usos inválidos, y F ya no se contrasta con `wrongSelections` ni `wrongPlacements`.

### La ficha de sesión

Lo que el estudio necesita y el visor no sabe. Se rellena en la página de cada sesión: código
de participante, momento (inicial o final), ayuda recibida, motivo de cierre, versión del juego
y los dos criterios de cada pilar (1, 0 o NO) con su evidencia. Se guarda en
`uploads/.codea2-panel.json` y sale en las tablas `sesiones` y `analisis`.

**Excluir no borra.** Una sesión excluida (una prueba interna, un duplicado) sigue en
`uploads/`, pero deja de contar en el resumen, en los escenarios y en las descargas.

## Las tablas

Todas llevan `file`, `pin`, `deviceId`, `sessionId` y `difficulty`. `file` es la clave que las une.

| Tabla | Una fila por… |
|---|---|
| `analisis` | sesión y escenario, con las métricas del estudio (G, tiempo validado, N, F, K, primer acierto, cambios del plan) y por qué se excluye lo excluido. **La tabla para el estudio** |
| `sesiones` | sesión, con el resumen de los cuatro escenarios en columnas `e1_`…`e4_` y la ficha |
| `escenarios` | sesión y escenario (lo mismo, en formato largo) |
| `intentos` | pulsación de ejecutar en los escenarios 1 y 3 |
| `bloques` | bloque de cada secuencia, para analizar el orden |
| `selecciones` | opción pulsada en el escenario 2, incluidas las que se quitan |
| `colocaciones` | ficha encajada en un hueco en el escenario 4 |
| `eventos` | evento de la sesión, de cualquier escenario, en orden cronológico |
| `avisos` | aviso de integridad |
| `diccionario` | columna de cada tabla, con lo que mide |

- Los nombres de columna son los del JSON cuando el dato sale tal cual (`failedAttempts`,
  `wrongSelections`…), para cruzarlos con `VARIABLES_TELEMETRIA.md`.
- Las banderas van como 0/1; lo que no aplica a una fila queda **vacío**, nunca a cero.
- Los tiempos van en segundos, redondeados a milésimas.
- `pin` es texto. Para Excel, descargar el **.xlsx**: al abrir un CSV, Excel convierte `0101` en `101`.
- Si un APK nuevo añade campos al JSON, aparecen solos al final de su tabla.
- `timedOut` (la sala agotó su tiempo y la historia siguió) existe desde el 12/10/2026; en los
  JSON anteriores queda vacío.
- **Conviven dos formatos de JSON** (el del visor cambió el 06/10/2026) y las tablas los juntan.
  Lo que un formato no trae queda vacío: `deviceId`, `totalSeconds` de la sesión,
  `blocksConnected`, `blockResets`, `errorInvalidUse` y el `durationSeconds` de selecciones y
  colocaciones solo existen en el nuevo; `blocksReleased`, `chipsReleased` y las deselecciones,
  solo en el anterior. `wrongSelections` y `wrongPlacements` ya no vienen en el JSON: se cuentan
  de la lista, así que la columna está completa en los dos.

Para descargar desde un script, autenticación básica con la contraseña del panel:

```python
import io, requests, pandas as pd
r = requests.get("https://codea2.penginexr.com/exportar/sesiones.csv", auth=("codea", "CONTRASEÑA"))
sesiones = pd.read_csv(io.BytesIO(r.content), dtype={"pin": str})
```

Rutas: `/exportar/<tabla>.csv|json|xlsx`, `/exportar/todo.xlsx`, `/exportar/todo-csv.zip` y
`/exportar/originales.zip` (los archivos de `uploads/` tal cual, como copia de seguridad).
Admiten los filtros en la URL: `?desde=2026-10-01&hasta=2026-10-31&dif=1&pin=01*`.

## Avisos de integridad

Esta telemetría no falla reventando: falla saliendo a cero. El panel marca lo que huele a dato
mal capturado, sesión por sesión. Son avisos, no errores: un cero puede ser legítimo.

| Aviso | Qué significa |
|---|---|
| `json_cortado` | Al JSON le faltaba el final y se recuperó lo que había |
| `nombre_distinto` | El archivo no se llama `{pin}_{sessionId}_{deviceId}.json` (o `{pin}_{sessionId}.json` en el formato anterior) |
| `duplicada` | Otro archivo trae la misma sesión: cuenta doble mientras no se excluya una |
| `pin_repetido` | Mismo PIN, contador y visor que otro archivo, pero otra hora de inicio |
| `sin_cierre` | La run no se cerró (`endedUtc` vacío) |
| `evento_antes` | Un evento anterior al inicio de su escenario: el reto se abrió tarde y `totalSeconds` se queda corto |
| `tiempo_distinto` | `totalSeconds` y el reloj difieren en más de 2 s |
| `sin_tipo` | Intento del escenario 3 sin `itemType` |
| `agotado_y_completado` | Un escenario figura a la vez como completado y con el tiempo agotado |
| `contador` | Un contador no coincide con lo que hay en su lista |
| `agarres` | Se soltó más de lo que se agarró: agarres atribuidos a otro escenario |
| `no_iniciado`, `sin_completar`, `eventos_sin_inicio`, `sin_eventos`, `sin_resuelto`, `resuelto_sin_completar`, `sin_registro`, `sin_inicio` | Un escenario cuyo estado no cuadra con sus eventos o con los escenarios siguientes |

## La subida

El contrato con el visor no cambió:

```
POST /upload        cabecera X-API-Key, multipart con el campo "file"
  200 {"status": "ok", "saved_as": "0101_5_A1B2C.json"}
  400 {"error": "..."}      401 sin clave o con una clave mala
GET  /health        200 {"status": "alive"}
```

Se guarda con el nombre que manda el visor, `{pin}_{sessionId}_{deviceId}.json`. Dos
protecciones, para no perder datos nunca:

- **Otra sesión con el mismo nombre no se pisa.** El `deviceId` ya distingue a los visores, pero
  si aun así lo guardado es otra sesión (otro `startedUtc`), la nueva se guarda con sufijo
  (`0101_5_A1B2C-2.json`) y el panel avisa.
- **Resubir la misma sesión conserva la versión anterior** en `uploads/.versiones/`. El visor
  resube solo, con el mismo nombre, una sesión que subió a medias y luego siguió: lo que queda
  visible es siempre lo último.

Dentro de `uploads/` el panel solo escribe eso y `.codea2-panel.json` (sesiones excluidas y notas).

> **No quitar del repositorio los JSON de `uploads/` que ya están versionados.** Un
> `git rm --cached` haría que el siguiente `git pull` los borrase de la Pi. Los que lleguen
> después no hace falta añadirlos: la copia de seguridad se descarga desde el panel
> (*Archivos → Descargar todos*).

## Si algo falla

- **502 en Cloudflare con el servidor vivo:** el túnel no apunta a `raspberrypi:26332`, o falta
  la línea `ports` del compose. Si `raspberrypi` no se resuelve desde el contenedor de
  `cloudflared`, se arregla en *su* compose con `extra_hosts: ["raspberrypi:host-gateway"]`.
- **401 al subir:** `UPLOAD_API_KEY` no coincide con la del APK.
- **El panel no acepta la contraseña:** sin `DASHBOARD_PASSWORD`, es la clave de subida. Tras
  8 intentos fallidos hay que esperar 10 minutos.
- **Un error 500:** el motivo está en `docker logs -f json-uploader`.
- **Volver a la versión anterior** (solo subida, puerto 8090):
  `git checkout b7042da && docker compose up -d --build`, y para regresar, `git checkout main`.

## Desarrollo

```bash
cd json-uploader
python -m venv .venv && . .venv/bin/activate      # en Windows: .venv\Scripts\activate
pip install -r requirements.txt

UPLOAD_DIR=../uploads DASHBOARD_PASSWORD=dev python server.py      # http://localhost:8080
python -m unittest discover tests
```

```
docker-compose.yml        el servicio, el puerto y las variables
json-uploader/
  server.py               rutas: subida, acceso, páginas y descargas
  codea2/store.py         carpeta de subidas: lectura tolerante, guardado, estado del panel
  codea2/model.py         una sesión normalizada y los filtros
  codea2/checks.py        avisos de integridad
  codea2/tables.py        las tablas
  codea2/metrics.py       las métricas del estudio y la tabla de análisis
  codea2/sheet.py         la ficha de sesión
  codea2/stats.py         descriptivos y datos de los gráficos de Exploración
  codea2/exports.py       CSV, JSON, Excel y ZIP
  templates/, static/     el panel (sin dependencias externas ni CDN)
  tests/                  pruebas
JSON Samples/             sesiones de ejemplo con el formato actual; las usan las pruebas
                          (las del formato anterior están en json-uploader/tests/fixtures/)
uploads/                  los JSON subidos (volumen del contenedor)
```
