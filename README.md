# Codea2Server

Servidor de datos de **CODEA 2**, el escape room educativo en VR de Yachay Tech. Hace dos cosas:

1. **Recibe** el JSON de cada sesión que sube el visor (`POST /upload`).
2. **Muestra** esas sesiones en un panel web centrado en las métricas del estudio (dos comunes
   y tres por escenario), con la ficha de cada sesión y todo tabulado para descargar.

Todo corre en Docker; el equipo no necesita nada más instalado. Hay dos instalaciones:

- **La Raspberry Pi**, detrás del túnel de Cloudflare: **<https://codea2.penginexr.com>**
  (ver [Actualizar la Raspberry Pi](#actualizar-la-raspberry-pi)).
- **El servidor de Yachay**, con IP pública propia y sin Cloudflare: ver
  [Instalar en el servidor de Yachay](#instalar-en-el-servidor-de-yachay-ip-pública-sin-cloudflare).

## Instalar en el servidor de Yachay (IP pública, sin Cloudflare)

Una sola máquina hace todo: el servidor de Yachay tiene la IP pública, corre Docker, guarda los
datos y publica el panel y la subida de los visores.

```text
  Visores / navegador        internet        Servidor de Yachay (IP pública)
  https://DOMINIO/upload  ───────────────▶   puerto 443 (HTTPS) ─▶ contenedor json-uploader :26332
                                                                    datos en uploads/
```

En el servidor solo hace falta **Docker** (y Git para descargar y actualizar el código). Python,
el servidor y, si se quiere, el HTTPS van dentro de contenedores. Los comandos van para
**Linux** (lo habitual en un servidor) y, cuando cambian, también para **Windows**.

### 0. Preguntas para TI de Yachay (antes de empezar)

Con las respuestas se elige la opción del [paso 5](#5-publicarlo-en-internet). Se pueden copiar
tal cual en un correo:

**El servidor**

1. ¿Qué sistema operativo tiene (Ubuntu, Debian, Rocky, Windows Server…)? ¿Tendremos acceso de
   administrador (`sudo`) o lo instalan ustedes?
2. ¿Se puede instalar **Docker** con el plugin `docker compose`? ¿Ya lo tiene?
3. ¿El servidor ya publica **otras webs**? Si es así, ¿con qué servidor web (nginx, Apache,
   IIS, Caddy…) y quién lo administra? Entonces los puertos 80 y 443 ya están ocupados y lo
   nuestro se añade como un sitio más.
4. ¿Cuánto disco libre hay y se hacen **copias de seguridad** del servidor? (Los datos de CODEA 2
   ocupan poco: unos MB por cientos de sesiones.)

**La red**

5. ¿Cuál es la **IP pública** y es fija? ¿Está **directamente** en el servidor o delante hay un
   firewall de la universidad que reenvía puertos? Si lo hay, ¿qué puertos abren hacia el
   servidor? Lo ideal, **443 y 80** (TCP).
6. ¿Nos pueden dar un **dominio o subdominio** (por ejemplo `codea2.yachaytech.edu.ec`) con un
   registro DNS `A` hacia la IP pública? Sin dominio no hay certificado HTTPS normal.
7. Si ya tienen servidor web: ¿ponen ellos el **certificado HTTPS** del dominio (o usan Let's
   Encrypt)?

**Los visores (Meta Quest)**

8. ¿Desde qué red suben los visores? Si es la **wifi de la universidad**, ¿desde dentro se
   puede abrir el dominio o la IP pública? (Algunas redes no dejan entrar a la IP pública desde
   dentro; entonces el DNS interno tiene que resolver el dominio a la IP interna del servidor.)
9. ¿Esa wifi tiene portal cautivo, inspección HTTPS o bloqueo de puertos que afecte a los visores?

**El mantenimiento**

10. ¿A quién avisamos si el servidor se reinicia, cambia de configuración o deja de verse desde
    fuera?

### 1. Instalar Docker

**Linux** (Ubuntu o Debian; para otras distribuciones, <https://docs.docker.com/engine/install/>):

```bash
curl -fsSL https://get.docker.com | sudo sh    # Docker Engine y el plugin compose
sudo systemctl enable --now docker             # arranca con el servidor
sudo usermod -aG docker $USER                  # usar docker sin sudo (cerrar sesión y volver a entrar)
docker compose version
```

Docker arranca solo con el servidor y el contenedor (`restart: unless-stopped`) también: tras
un reinicio no hay que hacer nada.

**Windows** (10/11): **Docker Desktop** desde <https://www.docker.com/products/docker-desktop/>,
con *Use WSL 2*. Necesita la virtualización activada en la BIOS (Administrador de tareas →
Rendimiento → CPU: *Virtualización: Habilitado*); si pide WSL, `wsl --install` como
administrador y reiniciar. Docker Desktop **solo arranca cuando alguien inicia sesión**, así que:

- Docker Desktop → *Settings* → *General*: marcar **Start Docker Desktop when you sign in**.
- Inicio de sesión automático: Configuración → Cuentas → Opciones de inicio de sesión →
  desactivar *permitir solo el inicio de sesión de Windows Hello*; luego `Win + R` → `netplwiz`
  → desmarcar *Los usuarios deben escribir su nombre de usuario y contraseña*.
- Que no se suspenda (PowerShell como administrador):
  `powercfg /change standby-timeout-ac 0` y `powercfg /change hibernate-timeout-ac 0`.

> Docker Desktop no está soportado oficialmente en Windows Server, y es gratuito para uso
> educativo y organizaciones pequeñas; si la universidad lo usa a gran escala, que TI confirme la
> licencia. En un servidor, Linux da menos guerra.

### 2. Descargar el código

```bash
# Linux
sudo mkdir -p /opt/codea2 && sudo chown $USER /opt/codea2
cd /opt/codea2
git clone https://github.com/clousck/Codea2Server.git
cd Codea2Server
```

```powershell
# Windows (Git desde https://git-scm.com/download/win)
mkdir C:\CODEA2; cd C:\CODEA2
git clone https://github.com/clousck/Codea2Server.git
cd Codea2Server
```

Si el repositorio es privado, Git pedirá iniciar sesión en GitHub con una cuenta que tenga
acceso. En Windows, mejor una ruta fuera de OneDrive (puede bloquear archivos de `uploads/`).

### 3. Configurar

```bash
cp .env.example .env        # Windows: copy .env.example .env
nano .env                   # Windows: notepad .env
```

Lo mínimo:

```ini
UPLOAD_API_KEY=CodeaVR2YachayTech2026     # la que lleva el APK (JSONUploader.cs); si se cambia, recompilar el APK
DASHBOARD_PASSWORD=una-contraseña-larga    # la del panel; sin ella, el panel se abre con la clave del APK
```

Y lo que diga la opción elegida en el paso 5 (`CODEA2_DOMINIO`, `CODEA2_BIND`, `TRUSTED_PROXY`).
Las demás variables están en [Configuración](#configuración).

### 4. Arrancar y comprobar en el propio servidor

En la carpeta del repositorio:

```bash
docker compose up -d --build
docker ps                                       # json-uploader: Up … (healthy) al cabo de un minuto
curl http://localhost:26332/health              # {"status":"alive"}   (Windows: curl.exe)
```

Registros: `docker logs -f json-uploader`.

### 5. Publicarlo en internet

Elegir **una** opción según lo que haya respondido TI.

#### Opción A — El servidor ya tiene un servidor web (nginx, Apache, IIS…) en el 80/443

Lo más probable si el servidor «sirve para todo». CODEA 2 se añade como un sitio más, que
reenvía a `http://127.0.0.1:26332`. En el `.env`:

```ini
CODEA2_BIND=127.0.0.1      # el 26332 solo se ve desde el propio servidor: se entra por el servidor web
```

`docker compose up -d` para aplicarlo. Con nginx, el sitio queda así (con Apache o IIS es
equivalente; el certificado, el que ya usen):

```nginx
server {
    listen 443 ssl;
    server_name codea2.yachaytech.edu.ec;
    # ssl_certificate / ssl_certificate_key: los de la universidad, o los de certbot
    client_max_body_size 20m;
    proxy_read_timeout 120s;
    location / {
        proxy_pass http://127.0.0.1:26332;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server {
    listen 80;
    server_name codea2.yachaytech.edu.ec;
    return 301 https://$host$request_uri;
}
```

`sudo nginx -t && sudo systemctl reload nginx`. Sin certificado de la universidad, `certbot
--nginx -d codea2.yachaytech.edu.ec` lo saca de Let's Encrypt y lo renueva solo.

#### Opción B — Los puertos 80 y 443 están libres: HTTPS con Caddy en Docker

Si en el servidor no hay otro servidor web, Caddy (otro contenedor, `docker-compose.https.yml`)
atiende el 80 y el 443 y saca y renueva solo el certificado de Let's Encrypt. Hace falta el
dominio apuntando a la IP pública. En el `.env`:

```ini
CODEA2_DOMINIO=codea2.yachaytech.edu.ec    # el que haya dado TI
CODEA2_BIND=127.0.0.1                      # el 26332 deja de verse desde fuera: se entra por Caddy
```

Arrancar con los dos archivos:

```bash
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --build
docker logs -f codea2-caddy        # "certificate obtained successfully"
```

A partir de aquí, **todos** los `docker compose` de este servidor llevan los dos `-f`. Si en los
registros de Caddy sale un error de *challenge*, el 80 o el 443 no llega desde internet (firewall
del servidor o de la universidad) o el DNS aún no apunta a la IP.

#### Opción C — Solo IP pública, sin dominio (HTTP, último recurso)

Los visores suben directamente a `http://IP-PÚBLICA:26332/upload`. Funciona, pero **sin
cifrar**: la contraseña del panel y los datos de los niños viajan en claro. Solo para salir del
paso mientras llega el dominio.

- En el `.env`: `TRUSTED_PROXY=no` (sin proxy delante, las cabeceras `X-Forwarded-*` las
  escribiría el cliente) y `CODEA2_BIND` vacío. `docker compose up -d` para aplicarlo.
- Abrir el 26332 en el firewall de la universidad, si lo hay.
- En Unity hay que permitir HTTP sin cifrar (ver el [paso 7](#7-el-apk)).

#### Firewall del servidor

| Opción | Puertos de entrada |
|---|---|
| A y B | 80 y 443 (TCP). El 26332 no: con `CODEA2_BIND=127.0.0.1` ya no se ve desde fuera |
| C | 26332 (TCP) |

```bash
sudo ufw allow 80,443/tcp          # Linux con ufw (opción C: sudo ufw allow 26332/tcp)
```

```powershell
New-NetFirewallRule -DisplayName "CODEA2" -Direction Inbound -Protocol TCP -LocalPort 80,443 -Action Allow   # Windows (C: -LocalPort 26332)
```

> En Linux, **los puertos que publica Docker se saltan `ufw`**: un `ufw deny 26332` no lo cierra.
> Para que el 26332 no se vea desde fuera está `CODEA2_BIND=127.0.0.1`.

### Comprobar con /health, tramo a tramo

`/health` responde `{"status":"alive"}` sin contraseña y sin tocar los datos. Probarlo desde
cada punto del camino dice **dónde** se corta si algo falla. Ir en orden y no pasar al siguiente
hasta que el anterior responda. En Windows se escribe `curl.exe` (en PowerShell 5, `curl` a
secas es otra cosa); en Linux o macOS, `curl`.

| # | Desde | Comando | Si falla, el problema está en… |
|---|---|---|---|
| 1 | El servidor | `curl http://localhost:26332/health` | Docker: `docker ps`, `docker logs json-uploader` |
| 2 | El servidor, por su nombre público | A y B: `curl --resolve DOMINIO:443:127.0.0.1 https://DOMINIO/health` | El sitio de nginx/Apache/IIS (A) o Caddy (B): `docker logs codea2-caddy` |
| 3 | Internet (un móvil con datos, sin wifi) | A y B: `https://DOMINIO/health` · C: `http://IP-PÚBLICA:26332/health` | El DNS, el firewall del servidor o el de la universidad |
| 4 | La wifi de los visores | Lo mismo que el 3, en el navegador del Quest | La wifi: no deja salir, o no deja entrar a la IP pública desde dentro (pregunta 8) |

Después, **la clave del visor**, sin guardar nada (`URL` es la del tramo 3, sin `/health`):

```bash
curl -i -X POST URL/upload                                    # 401: falta la clave (bien)
curl -i -X POST URL/upload -H "X-API-Key: CLAVE-DEL-APK"      # 400 {"error":"no file field"}: la clave es correcta
```

Un 401 en la segunda significa que `UPLOAD_API_KEY` del `.env` no es la del APK. Luego, **una
subida de verdad** con una sesión de ejemplo del repositorio, desde su carpeta (aparece en el
panel con PIN `0101`; después, excluirla en *Sesiones*):

```bash
curl -X POST URL/upload -H "X-API-Key: CLAVE-DEL-APK" -F "file=@JSON Samples/0101_5_00000.json"
# {"saved_as":"0101_5_00000.json","status":"ok"}
```

Por último, el panel: abrir `URL` en el navegador y entrar con `DASHBOARD_PASSWORD`.

### 6. Traer los datos de la Raspberry Pi

El repositorio trae solo unos JSON de prueba. Para que el servidor nuevo tenga todas las
sesiones **y las fichas, notas y exclusiones**:

1. En el panel de la Pi: *Archivos → Descargar todos* (`/exportar/originales.zip`). El ZIP
   lleva los JSON y `.codea2-panel.json`.
2. Descomprimirlo **dentro** de la carpeta `uploads` del repositorio, reemplazando lo que haya
   (Linux: `unzip -o codea2_json_originales.zip -d uploads`).
3. `docker compose restart` (con los dos `-f` si es la opción B) y comprobar en *Sesiones*.

Si las dos instalaciones reciben subidas a la vez durante un tiempo, se puede repetir: los JSON
con el mismo nombre son la misma sesión. Pero la ficha (`.codea2-panel.json`) es un solo archivo:
**rellenar fichas en un único servidor** o se pisarán al copiar.

### 7. El APK

En el proyecto de Unity, el `JSONUploader` de las escenas **Juego** y **Setup**: la URL pasa a
`https://DOMINIO/upload` (o `http://IP-PÚBLICA:26332/upload` en la opción C) y la clave sigue
siendo `UPLOAD_API_KEY`. Recompilar e instalar en los visores.

- **Opción C (HTTP):** *Project Settings → Player → Android → Other Settings → Allow downloads
  over HTTP* → **Always allowed**. Sin eso, Android rechaza la subida antes de salir del visor.
- Los visores con el APK anterior siguen subiendo a la Pi mientras esta siga encendida.
- Lo que un visor ya subió a la Pi queda apuntado como subido y **no** se vuelve a mandar al
  servidor nuevo: esas sesiones llegan con el ZIP del [paso 6](#6-traer-los-datos-de-la-raspberry-pi).

### 8. Actualizar y copias de seguridad

```bash
cd /opt/codea2/Codea2Server        # Windows: cd C:\CODEA2\Codea2Server
git pull
docker compose up -d --build
# opción B: docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --build
```

Copia de seguridad: *Archivos → Descargar todos* desde el panel, o copiar la carpeta `uploads`
entera (incluidos los archivos que empiezan por punto). Si TI hace copias del servidor, que
incluyan esa carpeta.

> Con Docker Desktop en Windows, la IP que se ve en los registros y en el bloqueo de contraseñas
> es la interna de Docker, no la del cliente (en Linux, y en la opción A, sí se ve la real). En
> ese caso, tras 8 contraseñas mal puestas el panel queda bloqueado 10 minutos **para todos**.

## Actualizar la Raspberry Pi

```bash
cd ~/Git/Codea2Server        # la carpeta de este repositorio en la Pi
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
| `TRUSTED_PROXY` | `*` | De quién se aceptan las cabeceras `X-Forwarded-*`. `no` cuando el 26332 se publica directo a internet, sin proxy delante |
| `CODEA2_BIND` | vacío | `127.0.0.1` deja el 26332 solo para la propia máquina (cuando delante va Caddy) |
| `CODEA2_DOMINIO` | — | Solo con `docker-compose.https.yml`: el dominio para el que Caddy saca el certificado |

**La contraseña del panel es, por defecto, la clave de subida.** Esa clave viaja dentro del
APK, así que conviene poner una `DASHBOARD_PASSWORD` propia: con ella, la clave del visor solo
sirve para subir y no para leer.

## El panel

| Página | Qué hay |
|---|---|
| **Métricas** | La página principal. Por escenario: MC1 logro final, MC2 tiempo registrado y sus tres métricas (E1A–E4C), siempre con numerador, denominador y exclusiones, y el perfil de evidencias de los pilares de esa actividad (E1P–E4P). Una sola dificultad cada vez |
| **Sesiones** | Una fila por partida, ordenable y con buscador. Desde aquí se excluye una sesión del análisis |
| **Detalle de una sesión** | Sus métricas, línea de tiempo, cada intento (con su cercanía a la solución), selección, prueba y colocación con su hora, avisos de integridad, **ficha de sesión** y JSON original |
| **Datos** | Las tablas, con vista previa, diccionario de columnas y descarga |
| **Archivos** | Lo que hay en `uploads/` y su estado. Subida a mano de los JSON sacados del visor por cable |
| **Exploración** | Lo que no es métrica del estudio pero ayuda a preparar preguntas: tiempos sesión a sesión, secuencias probadas, cercanía a la solución intento a intento, qué opción se marcó y cuántas pruebas hizo falta en cada módulo, ajuste del bucle, qué ficha se puso en cada hueco |

Los filtros de arriba (fechas, dificultad, PIN) valen para todo lo que hay debajo **y para las
descargas**. En PIN se pueden poner varios, comodines y descartes: `0101 02* -0000`.

### Las métricas

Siguen el documento «Métricas por escenario de CODEA2» (19/10/2026). Las reglas están en
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
- El documento nombra campos del formato anterior. Con el actual (22/10/2026), E1C son choques y
  usos inválidos (la secuencia incompleta queda en `attempts`), E3C es `failedAttempts` y comandos
  inválidos, y F se cuenta de la lista porque `wrongSelections` y `wrongPlacements` ya no vienen.
- `solutionPercent` y las pruebas del escenario 2 no son métricas del documento: se enseñan como
  contexto: en el escenario 1, la tarjeta **E1S · Cercanía a la solución** (primer intento, media
  y mejor de los fallidos); en el 3, la cercanía del primer intento en E3A; en el 2, las pruebas
  fallidas en E2B.
- **E1I · Número y orden de instrucciones** compara cada secuencia del escenario 1 con la solución
  de su dificultad: instrucciones que faltan y que sobran (sin mirar el orden) y, de las que
  coinciden, cuántas están en el orden de la solución. Vale también para los JSON anteriores al
  22/10/2026. La clave copia `CodeaSolutions` de Unity y está en `codea2/solutions.py`: **si
  cambian los niveles del escenario 1, hay que actualizarla**. El aviso `clave_distinta` salta
  cuando el `solutionPercent` del visor no coincide con el de la clave. E1S usa también la cuenta
  del panel y no la del visor, que el 22/10/2026 tomaba «Avanzar» como «Avanzar 2».
- La duración de una sesión es su `totalSeconds`, que no cuenta el visor parado; el aviso
  `visor_parado` dice cuándo el reloj se fue más de un minuto por encima. Dos eventos idénticos
  con menos de 0,5 s (`duplicado_tecnico`) y las pruebas con nada marcado (`prueba_vacia`) se
  avisan pero siguen contando: el documento pide verificarlos antes de descartarlos. Un `-1` en
  `solutionPercent` o `remaining` es «sin dato», nunca un cero.
- **E1P–E4P** (perfil de evidencias de los pilares) salen de la ficha, no del JSON: por cada
  actividad, dos criterios por dimensión (D descomposición, TD toma de decisiones, PA pensamiento
  algorítmico, RP reconocimiento de patrones). P vale 0, 50 o 100 solo con los dos criterios
  evaluados; con un NO queda NC. Las dimensiones no se suman en una nota global. La toma de
  decisiones sustituye a la abstracción.

### La ficha de sesión

Lo que el estudio necesita y el visor no sabe. Se rellena en la página de cada sesión: código
de participante, momento (inicial o final), ayuda recibida, motivo de cierre, observador, versión
del juego y, por cada escenario, los dos criterios de cada dimensión (1, 0 o NO) con su evidencia,
según las matrices del documento. Se guarda en `uploads/.codea2-panel.json` y sale en las tablas
`sesiones`, `analisis` y `pilares`. Las valoraciones de la ficha anterior (una por sesión, con
abstracción) siguen guardadas pero no se usan: no se atribuyen a una actividad ni se convierten en
toma de decisiones.

**Excluir no borra.** Una sesión excluida (una prueba interna, un duplicado) sigue en
`uploads/`, pero deja de contar en el resumen, en los escenarios y en las descargas.

## Las tablas

Todas llevan `file`, `pin`, `deviceId`, `sessionId` y `difficulty`. `file` es la clave que las une.

| Tabla | Una fila por… |
|---|---|
| `analisis` | sesión y escenario, con las métricas del estudio (G, tiempo validado, N, F, K, primer acierto, cambios del plan, perfil de pilares) y por qué se excluye lo excluido. **La tabla para el estudio** |
| `pilares` | sesión, escenario y dimensión valorados en la ficha: C1, C2, C, E, P y evidencias (sección 7.7) |
| `sesiones` | sesión, con el resumen de los cuatro escenarios en columnas `e1_`…`e4_` y la ficha |
| `escenarios` | sesión y escenario (lo mismo, en formato largo) |
| `intentos` | pulsación de ejecutar en los escenarios 1 y 3, con `solutionPercent` y, en el 3, `remaining` |
| `bloques` | bloque de cada secuencia, para analizar el orden |
| `selecciones` | opción pulsada en el escenario 2, incluidas las que se quitan |
| `pruebas` | pulsación de Probar en el escenario 2, con lo marcado (desde el 22/10/2026) |
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
- **Windows: `docker` no se reconoce o no conecta** (`error during connect`, `pipe/docker_engine`):
  Docker Desktop no está abierto o aún está arrancando. Si no arranca: virtualización desactivada
  en la BIOS o WSL sin instalar (`wsl --install`, como administrador, y reiniciar).
- **Windows: tras reiniciar el servidor no responde:** nadie ha iniciado sesión (Docker Desktop
  no arranca sin sesión) o falta *Start Docker Desktop when you sign in*. Ver el
  [paso 1](#1-instalar-docker).
- **Linux: `permission denied` al usar `docker`:** falta cerrar sesión y volver a entrar tras el
  `usermod -aG docker`, o usar `sudo docker …`.
- **Funciona en `localhost` pero no desde fuera:** seguir la tabla de
  [Comprobar con /health](#comprobar-con-health-tramo-a-tramo); el primer tramo que falla dice
  dónde está el problema.
- **502 o 504 de nginx/Apache (opción A):** el servidor web no llega a `127.0.0.1:26332`: el
  contenedor está parado (`docker ps`) o el sitio apunta a otro puerto.
- **Opción B: el navegador avisa de certificado no válido:** Caddy aún no lo ha conseguido;
  `docker logs codea2-caddy` dice por qué (casi siempre, el 80 o el 443 no llegan desde fuera).
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
docker-compose.https.yml  Caddy con HTTPS, para el servidor de Yachay (opción B)
caddy/Caddyfile           su configuración
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
