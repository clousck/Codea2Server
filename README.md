# Codea2Server

Servidor de datos de **CODEA 2**, el escape room educativo en VR de Yachay Tech. Hace dos cosas:

1. **Recibe** el JSON de cada sesión que sube el visor (`POST /upload`).
2. **Muestra** esas sesiones en un panel web: resumen, detalle de cada partida, análisis por
   escenario y todo tabulado para descargar en Excel, CSV o JSON.

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

**La contraseña del panel es, por defecto, la clave de subida.** Esa clave viaja dentro del
APK, así que conviene poner una `DASHBOARD_PASSWORD` propia: con ella, la clave del visor solo
sirve para subir y no para leer.

## El panel

| Página | Qué hay |
|---|---|
| **Resumen** | Sesiones, cuántas completaron los cuatro escenarios, duración, tiempo por escenario (un punto por sesión), sesiones por día y descriptivos |
| **Sesiones** | Una fila por partida, ordenable y con buscador. Desde aquí se excluye una sesión del análisis |
| **Detalle de una sesión** | Línea de tiempo, cada intento, selección y colocación con su hora, avisos de integridad, nota y JSON original |
| **Escenarios** | Lo que pasó dentro de cada reto: intentos hasta completar, secuencias probadas, qué opción se marcó en cada módulo, repeticiones según la ficha, qué ficha se puso en cada hueco |
| **Datos** | Las tablas, con vista previa, diccionario de columnas y descarga |
| **Archivos** | Lo que hay en `uploads/` y su estado. Subida a mano de los JSON sacados del visor por cable |

Los filtros de arriba (fechas, dificultad, PIN) valen para todo lo que hay debajo **y para las
descargas**. En PIN se pueden poner varios, comodines y descartes: `0101 02* -0000`.

**Excluir no borra.** Una sesión excluida (una prueba interna, un duplicado) sigue en
`uploads/`, pero deja de contar en el resumen, en los escenarios y en las descargas.

## Las tablas

Todas llevan `file`, `pin`, `sessionId` y `difficulty`. `file` es la clave que las une.

| Tabla | Una fila por… |
|---|---|
| `sesiones` | sesión, con el resumen de los cuatro escenarios en columnas `e1_`…`e4_` |
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
| `nombre_distinto` | El archivo no se llama `{pin}_{sessionId}.json` |
| `duplicada` | Otro archivo trae la misma sesión: cuenta doble mientras no se excluya una |
| `pin_repetido` | Mismo PIN y contador que otro archivo, pero otra hora de inicio: dos visores |
| `sin_cierre` | La run no se cerró (`endedUtc` vacío) |
| `evento_antes` | Un evento anterior al inicio de su escenario: el reto se abrió tarde y `totalSeconds` se queda corto |
| `tiempo_distinto` | `totalSeconds` y el reloj difieren en más de 2 s |
| `sin_tipo` | Intento del escenario 3 sin `itemType` |
| `contador` | Un contador no coincide con lo que hay en su lista |
| `agarres` | Se soltó más de lo que se agarró: agarres atribuidos a otro escenario |
| `no_iniciado`, `sin_completar`, `eventos_sin_inicio`, `sin_eventos`, `sin_resuelto`, `resuelto_sin_completar`, `sin_registro`, `sin_inicio` | Un escenario cuyo estado no cuadra con sus eventos o con los escenarios siguientes |

## La subida

El contrato con el visor no cambió:

```
POST /upload        cabecera X-API-Key, multipart con el campo "file"
  200 {"status": "ok", "saved_as": "0101_5.json"}
  400 {"error": "..."}      401 sin clave o con una clave mala
GET  /health        200 {"status": "alive"}
```

Se guarda con el nombre que manda el visor, `{pin}_{sessionId}.json`. Dos cosas nuevas, para no
perder datos nunca:

- **Otra sesión con el mismo nombre no se pisa.** `sessionId` es un contador de cada visor: dos
  visores con el mismo PIN pueden mandar el mismo nombre. Si lo guardado es otra sesión (otro
  `startedUtc`), la nueva se guarda como `0101_5-2.json` y el panel avisa.
- **Resubir la misma sesión conserva la versión anterior** en `uploads/.versiones/`.

Dentro de `uploads/` el panel solo escribe eso y `.codea2-panel.json` (sesiones excluidas y notas).

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
  codea2/stats.py         descriptivos y datos de los gráficos
  codea2/exports.py       CSV, JSON, Excel y ZIP
  templates/, static/     el panel (sin dependencias externas ni CDN)
  tests/                  pruebas
JSON Samples/             sesiones de ejemplo; las usan las pruebas
uploads/                  los JSON subidos (volumen del contenedor)
```
