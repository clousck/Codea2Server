# Codea2Server

Servidor de datos de **CODEA 2**, el escape room educativo en VR de Yachay Tech. Hace dos cosas:

1. **Recibe** el JSON de cada sesión que sube el visor (`POST /upload`).
2. **Muestra** esas sesiones en un panel web centrado en las métricas del estudio (dos comunes
   y tres por escenario), con la ficha de cada sesión y todo tabulado para descargar.

Todo corre en Docker; el equipo no necesita nada más instalado. Hay dos instalaciones:

- **La Raspberry Pi**, detrás del túnel de Cloudflare: **<https://codea2.penginexr.com>**
  (ver [Actualizar la Raspberry Pi](#actualizar-la-raspberry-pi)).
- **Una laptop con Windows en Yachay, publicada por el servidor de la universidad, sin
  Cloudflare**: ver [Instalar en un servidor nuevo](#instalar-en-un-servidor-nuevo-windows-sin-cloudflare).

## Instalar en un servidor nuevo (Windows, sin Cloudflare)

Intervienen **dos computadoras**:

```text
  Visores / navegador                Servidor de Yachay                  Laptop (Windows)
  -------------------   internet     ------------------   red interna   -------------------------
  https://dominio/... ─────────────▶ IP pública         ──────────────▶ Docker Desktop
                                     (proxy o reenvío                    contenedor json-uploader
                                      de puertos)                        puerto 26332, uploads/
```

- **La laptop** levanta el servicio con Docker y guarda los datos. Es la que se configura con
  este README. Lo único que se instala en ella es **Docker Desktop** (y, si se quiere, Git para
  actualizar con un comando).
- **El servidor de Yachay** tiene la IP pública y hace llegar las peticiones a la laptop. Lo
  administra TI de Yachay; aquí solo se dice qué tiene que hacer.

### 0. Preguntas para TI de Yachay (antes de empezar)

Con las respuestas se elige la opción del [paso 5](#5-publicarlo-a-través-del-servidor-de-yachay).
Se pueden copiar tal cual en un correo:

**Sobre el servidor de Yachay**

1. ¿Qué hace exactamente con nuestro tráfico? ¿Es un **servidor web con proxy inverso** (nginx,
   Apache, IIS, Caddy…) que puede publicar un sitio HTTPS y reenviarlo a otra máquina, o es un
   **firewall/router que solo reenvía puertos** (NAT)?
2. ¿Cuál es la **IP pública**? ¿Es fija?
3. ¿Nos pueden dar un **dominio o subdominio** (por ejemplo `codea2.yachaytech.edu.ec`) con un
   registro DNS `A` hacia esa IP pública?
4. Si es proxy: ¿ponen ellos el **certificado HTTPS** para ese dominio?
5. Si es reenvío de puertos: ¿pueden reenviar los puertos **80 y 443** (TCP) a la laptop? Si no,
   ¿qué puerto pueden reenviar hacia el **26332** de la laptop?
6. ¿El proxy puede enviar las cabeceras `X-Forwarded-For` y `X-Forwarded-Proto`, aceptar
   cuerpos de hasta **20 MB** y esperar al menos **60 s** por la respuesta (las descargas del
   panel tardan algo con muchos datos)?

**Sobre la laptop en su red**

7. ¿Dónde se conecta la laptop (cable o wifi, qué red/VLAN) y **el servidor de Yachay puede
   llegar a ella**? Hay que poder abrir `http://IP-de-la-laptop:26332` desde el servidor.
8. ¿Le pueden dar a la laptop una **IP interna fija** (reserva DHCP por su MAC)? Si cambia, el
   servidor de Yachay deja de encontrarla.
9. ¿Hay que **registrar la laptop** (MAC, inventario, antivirus obligatorio) para conectarla a
   esa red? ¿Hay algún bloqueo a que una máquina de usuario reciba conexiones entrantes?

**Sobre los visores (Meta Quest)**

10. ¿Desde qué red suben los visores? Si es la **wifi de la universidad**, ¿desde dentro se
    puede abrir el dominio o la IP pública? (Algunas redes no dejan entrar a la IP pública desde
    dentro; entonces hace falta que el DNS interno resuelva el dominio a la IP del servidor.)
11. ¿Esa wifi tiene portal cautivo, inspección HTTPS o bloqueo de puertos que afecte a los visores?

**Sobre el mantenimiento**

12. ¿Quién de TI se encarga si el servidor de Yachay se reinicia o cambia su configuración, y
    a quién avisamos si deja de verse desde fuera?

### 1. Preparar la laptop

1. **Virtualización activada** en la BIOS/UEFI (Intel VT-x o AMD-V). En el Administrador de
   tareas → Rendimiento → CPU tiene que poner *Virtualización: Habilitado*.
2. **Docker Desktop** desde <https://www.docker.com/products/docker-desktop/>, con la opción
   *Use WSL 2* marcada. Funciona en Windows Home y Pro. Si al terminar pide instalar o actualizar
   WSL, en PowerShell como administrador: `wsl --install` (o `wsl --update`) y reiniciar.
   > Docker Desktop es gratuito para uso educativo y organizaciones pequeñas; si la universidad
   > lo usa a gran escala, que TI confirme la licencia.
3. En Docker Desktop → *Settings* → *General*: marcar **Start Docker Desktop when you sign in
   to your computer**.
4. **Inicio de sesión automático.** Docker Desktop solo arranca cuando alguien inicia sesión en
   Windows; tras un corte de luz o una actualización, la laptop tiene que entrar sola:
   - Configuración → Cuentas → Opciones de inicio de sesión: desactivar *Para mejorar la
     seguridad, permitir solo el inicio de sesión de Windows Hello…*.
   - `Win + R` → `netplwiz` → desmarcar *Los usuarios deben escribir su nombre de usuario y
     contraseña…* → Aceptar y escribir la contraseña de la cuenta.
   - Conviene una cuenta local dedicada a esto y bloquear la pantalla (`Win + L`) al irse.
5. **Que no se duerma** (PowerShell como administrador):

   ```powershell
   powercfg /change standby-timeout-ac 0          # no suspender enchufada
   powercfg /change hibernate-timeout-ac 0
   powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0   # cerrar la tapa: nada
   powercfg /setactive SCHEME_CURRENT
   ```

   Y dejarla siempre enchufada, con cable de red mejor que wifi. En Windows Update → Opciones
   avanzadas, poner un *horario de actividad* amplio para que no se reinicie en plena sesión.

### 2. Descargar el código

Con **Git** (<https://git-scm.com/download/win>), que permite actualizar luego con `git pull`.
En PowerShell:

```powershell
mkdir C:\CODEA2
cd C:\CODEA2
git clone https://github.com/clousck/Codea2Server.git
cd Codea2Server
```

Si el repositorio es privado, Git pedirá iniciar sesión en GitHub con una cuenta que tenga
acceso. **Sin Git:** en GitHub, *Code → Download ZIP*, descomprimir en `C:\CODEA2\Codea2Server`
y, para actualizar, repetir la descarga **sin tocar** la carpeta `uploads` ni el `.env`.

> Mejor una ruta corta y fuera de OneDrive: si OneDrive sincroniza la carpeta, puede bloquear
> archivos de `uploads/` mientras el servidor escribe.

### 3. Configurar

```powershell
copy .env.example .env
notepad .env
```

Lo mínimo:

```ini
UPLOAD_API_KEY=CodeaVR2YachayTech2026     # la que lleva el APK (JSONUploader.cs); si se cambia, recompilar el APK
DASHBOARD_PASSWORD=una-contraseña-larga    # la del panel; sin ella, el panel se abre con la clave del APK
```

Y lo que diga la opción elegida en el paso 5 (`CODEA2_DOMINIO`, `CODEA2_BIND`, `TRUSTED_PROXY`).
Las demás variables están en [Configuración](#configuración).

### 4. Arrancar y comprobar en la propia laptop

Con Docker Desktop abierto (la ballena en la bandeja, en verde), en la carpeta del repositorio:

```powershell
docker compose up -d --build
docker ps                                    # json-uploader: Up … (healthy) al cabo de un minuto
curl.exe http://localhost:26332/health       # {"status":"alive"}
```

El panel queda en <http://localhost:26332>. La primera vez Windows puede preguntar si deja a
Docker usar la red: **permitir en redes privadas y públicas**. El contenedor tiene
`restart: unless-stopped`, así que vuelve solo cada vez que arranca Docker Desktop.

### 5. Publicarlo a través del servidor de Yachay

Elegir **una** opción según lo que haya respondido TI. En las tres, `IP-LAPTOP` es la IP interna
fija de la laptop (`ipconfig` → *Dirección IPv4*) e `IP-SERVIDOR`, la interna del servidor de Yachay.

#### Opción A — El servidor de Yachay es un proxy con HTTPS (la más sencilla)

TI publica `https://dominio` en su servidor y lo reenvía a `http://IP-LAPTOP:26332`. Con nginx,
por ejemplo (con IIS, Apache o Caddy es equivalente):

```nginx
server {
    listen 443 ssl;
    server_name codea2.yachaytech.edu.ec;
    # ssl_certificate / ssl_certificate_key: los de la universidad
    client_max_body_size 20m;
    proxy_read_timeout 120s;
    location / {
        proxy_pass http://IP-LAPTOP:26332;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

En la laptop, abrir el 26332 en el firewall de Windows **solo para el servidor de Yachay**
(PowerShell como administrador):

```powershell
New-NetFirewallRule -DisplayName "CODEA2 26332" -Direction Inbound -Protocol TCP -LocalPort 26332 -RemoteAddress IP-SERVIDOR -Action Allow
```

El `.env` no necesita nada más: `TRUSTED_PROXY` por defecto ya acepta las cabeceras del proxy.

#### Opción B — El servidor de Yachay reenvía los puertos 80 y 443: HTTPS con Caddy en la laptop

TI apunta el dominio a la IP pública y reenvía los puertos **80 y 443** TCP a `IP-LAPTOP`. El
certificado lo saca y lo renueva **Caddy**, otro contenedor en la laptop
(`docker-compose.https.yml`). En el `.env`:

```ini
CODEA2_DOMINIO=codea2.yachaytech.edu.ec    # el que haya dado TI
CODEA2_BIND=127.0.0.1                      # el 26332 deja de verse desde fuera: se entra por Caddy
```

Abrir 80 y 443 en el firewall de Windows y arrancar con los dos archivos:

```powershell
New-NetFirewallRule -DisplayName "CODEA2 HTTP/HTTPS" -Direction Inbound -Protocol TCP -LocalPort 80,443 -Action Allow
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --build
docker logs -f codea2-caddy        # "certificate obtained successfully"
```

A partir de aquí, **todos** los `docker compose` de esta laptop llevan los dos `-f`. Si en los
registros de Caddy sale un error de *challenge*, el puerto 80 o el 443 no llega desde internet a
la laptop (o el DNS aún no apunta a la IP): es cosa del reenvío del servidor de Yachay.

#### Opción C — Solo IP pública, sin dominio (HTTP, último recurso)

El servidor de Yachay reenvía un puerto de la IP pública (`PUERTO`) al 26332 de la laptop.
Funciona, pero **sin cifrar**: la contraseña del panel y los datos de los niños viajan en claro.
Solo para salir del paso mientras llega el dominio.

- En el `.env`: `TRUSTED_PROXY=no` (sin proxy delante, las cabeceras `X-Forwarded-*` las
  escribiría el cliente) y `docker compose up -d` para aplicarlo.
- Firewall de Windows: la regla del 26332 de la opción A, pero sin `-RemoteAddress`.
- En Unity hay que permitir HTTP sin cifrar (ver el [paso 7](#7-el-apk)) y la URL del visor queda
  `http://IP-PÚBLICA:PUERTO/upload`.

### Comprobar con /health, tramo a tramo

`/health` responde `{"status":"alive"}` sin contraseña y sin tocar los datos. Probarlo desde
cada punto del camino dice **dónde** se corta si algo falla. Ir en orden y no pasar al siguiente
hasta que el anterior responda. En Windows se escribe `curl.exe` (en PowerShell 5, `curl` a
secas es otra cosa); en Linux o macOS, `curl`.

| # | Desde | Comando | Si falla, el problema está en… |
|---|---|---|---|
| 1 | La laptop | `curl.exe http://localhost:26332/health` | Docker: `docker ps`, `docker logs json-uploader` |
| 2 | Otro equipo de la red de la laptop | `curl.exe http://IP-LAPTOP:26332/health` | El firewall de Windows de la laptop (con la opción B no responde a propósito: pasar al 3) |
| 3 | El servidor de Yachay | A y C: `curl http://IP-LAPTOP:26332/health` · B: `curl --resolve DOMINIO:443:IP-LAPTOP https://DOMINIO/health` | La red entre las dos máquinas, o la IP de la laptop cambió |
| 4 | Internet (un móvil con datos, sin wifi) | A y B: `https://DOMINIO/health` · C: `http://IP-PÚBLICA:PUERTO/health` | El proxy, el DNS o el reenvío de puertos del servidor de Yachay |
| 5 | La wifi de los visores | Lo mismo que el 4, en el navegador del Quest | La wifi: no deja salir, o no deja entrar a la IP pública desde dentro (pregunta 10) |

Después, **la clave del visor**, sin guardar nada (`URL` es la del tramo 4, sin `/health`):

```powershell
curl.exe -i -X POST URL/upload                                    # 401: falta la clave (bien)
curl.exe -i -X POST URL/upload -H "X-API-Key: CLAVE-DEL-APK"      # 400 {"error":"no file field"}: la clave es correcta
```

Un 401 en la segunda significa que `UPLOAD_API_KEY` del `.env` no es la del APK. Luego, **una
subida de verdad** con una sesión de ejemplo del repositorio, desde su carpeta (aparece en el
panel con PIN `0101`; después, excluirla en *Sesiones*):

```powershell
curl.exe -X POST URL/upload -H "X-API-Key: CLAVE-DEL-APK" -F "file=@JSON Samples/0101_5_00000.json"
# {"saved_as":"0101_5_00000.json","status":"ok"}
```

Por último, el panel: abrir `URL` en el navegador y entrar con `DASHBOARD_PASSWORD`.

### 6. Traer los datos de la Raspberry Pi

El repositorio trae solo unos JSON de prueba. Para que el servidor nuevo tenga todas las
sesiones **y las fichas, notas y exclusiones**:

1. En el panel de la Pi: *Archivos → Descargar todos* (`/exportar/originales.zip`). El ZIP
   lleva los JSON y `.codea2-panel.json`.
2. Descomprimirlo **dentro** de `C:\CODEA2\Codea2Server\uploads`, reemplazando lo que haya.
3. `docker compose restart` (con los dos `-f` si es la opción B) y comprobar en *Sesiones*.

Si las dos instalaciones reciben subidas a la vez durante un tiempo, se puede repetir: los JSON
con el mismo nombre son la misma sesión. Pero la ficha (`.codea2-panel.json`) es un solo archivo:
**rellenar fichas en un único servidor** o se pisarán al copiar.

### 7. El APK

En el proyecto de Unity, el `JSONUploader` de las escenas **Juego** y **Setup**: la URL pasa a
`https://DOMINIO/upload` (o la de la opción C) y la clave sigue siendo `UPLOAD_API_KEY`.
Recompilar e instalar en los visores.

- **Opción C (HTTP):** *Project Settings → Player → Android → Other Settings → Allow downloads
  over HTTP* → **Always allowed**. Sin eso, Android rechaza la subida antes de salir del visor.
- Los visores con el APK anterior siguen subiendo a la Pi mientras esta siga encendida.
- Lo que un visor ya subió a la Pi queda apuntado como subido y **no** se vuelve a mandar al
  servidor nuevo: esas sesiones llegan con el ZIP del [paso 6](#6-traer-los-datos-de-la-raspberry-pi).

### 8. Actualizar

```powershell
cd C:\CODEA2\Codea2Server
git pull
docker compose up -d --build
# opción B: docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --build
```

Registros: `docker logs -f json-uploader`. Copia de seguridad: *Archivos → Descargar todos*
desde el panel, o copiar la carpeta `uploads` entera (incluidos los archivos que empiezan por
punto).

> Con Docker Desktop en Windows y las opciones B o C, la IP que se ve en los registros y en el
> bloqueo de contraseñas es la interna de Docker, no la del cliente. Consecuencia: tras 8
> contraseñas mal puestas, el panel queda bloqueado 10 minutos **para todos**, no solo para quien
> se equivocó. Con la opción A sí se ve la IP real, porque la manda el proxy de TI.

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
  Docker Desktop no está abierto o aún está arrancando. Abrirlo y esperar a que la ballena esté
  en verde. Si no arranca: virtualización desactivada en la BIOS o WSL sin instalar
  (`wsl --install`, como administrador, y reiniciar).
- **Windows: tras reiniciar la laptop el servidor no responde:** nadie ha iniciado sesión
  (Docker Desktop no arranca sin sesión) o falta *Start Docker Desktop when you sign in*. Ver el
  [paso 1](#1-preparar-la-laptop).
- **Windows: funciona en `localhost` pero no desde fuera:** por orden, el firewall de Windows (la
  regla del paso 5), la IP interna de la laptop (¿ha cambiado? `ipconfig`) y el reenvío de
  puertos de TI. Desde otro equipo de la misma red, `http://IP-interna:26332/health` separa lo
  primero de lo último (con la opción B y `CODEA2_BIND=127.0.0.1` eso no responde: es lo esperado).
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
docker-compose.https.yml  Caddy con HTTPS, para un servidor sin túnel de Cloudflare
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
