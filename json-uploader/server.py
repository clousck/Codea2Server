"""Servidor de CODEA 2: recibe los JSON de sesión del visor y los muestra en un panel."""

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlsplit

from flask import (Flask, Response, abort, flash, redirect, render_template, request,
                   send_from_directory, session, url_for)
from flask.sessions import SecureCookieSessionInterface
from werkzeug.utils import secure_filename

from codea2 import exports, metrics, sheet, stats, tables
from codea2.dataset import Dataset
from codea2.model import DIFFICULTIES, SCENARIOS, ZONE, Filters
from codea2.store import ALLOWED_EXTENSIONS, Store

app = Flask(__name__)

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/data/uploads")
API_KEY = os.environ.get("UPLOAD_API_KEY", "cambia-esto-por-algo-random")

# Sin contraseña propia, el panel se abre con la clave de subida: los datos de los niños
# no quedan a la vista de cualquiera por un despliegue sin configurar.
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD") or API_KEY
# Con DASHBOARD_PUBLIC=1 se puede mirar y descargar sin entrar; editar sigue pidiendo contraseña
DASHBOARD_PUBLIC = os.environ.get("DASHBOARD_PUBLIC", "").strip().lower() in ("1", "true", "si", "sí")

store = Store(UPLOAD_DIR)
dataset = Dataset(store)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("codea2")

# La clave de la cookie sale de la contraseña: cambiarla cierra todas las sesiones abiertas
app.secret_key = os.environ.get("SECRET_KEY") or hashlib.sha256(
    f"codea2-panel:{DASHBOARD_PASSWORD}".encode()).hexdigest()
app.config.update(
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    SESSION_COOKIE_NAME="codea2_panel",
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True


class _SessionInterface(SecureCookieSessionInterface):
    def get_cookie_secure(self, app):
        # Por el túnel la cookie viaja solo por HTTPS; en la red local, por http://raspberrypi, también sirve
        return request.is_secure


app.session_interface = _SessionInterface()


# ── Subida desde el visor ─────────────────────────────────────────────────────

def _same(given, expected):
    """Comparación en tiempo constante. Un valor vacío nunca coincide con nada."""
    if not given or not expected:
        return False
    return hmac.compare_digest(given.encode(), expected.encode())


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _same(request.headers.get("X-API-Key"), API_KEY):
            abort(401, description="invalid or missing API key")
        return f(*args, **kwargs)
    return decorated


def _save(file):
    """Valida y guarda un archivo subido. Devuelve (nombre guardado, error)."""
    # secure_filename neutraliza rutas tipo ../../ en el nombre que llega del cliente
    filename = secure_filename(file.filename or "")
    if not filename:
        return None, "empty filename"
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        return None, "must be .json or .csv"
    saved_as = store.save_upload(filename, file)
    log.info("subida %s guardada como %s desde %s", filename, saved_as, request.remote_addr)
    return saved_as, None


@app.route('/upload', methods=['POST'])
@require_api_key
def upload_telemetry():
    if 'file' not in request.files:
        return {"error": "no file field"}, 400

    saved_as, error = _save(request.files['file'])
    if error:
        return {"error": error}, 400
    return {"status": "ok", "saved_as": saved_as}, 200


@app.route('/health', methods=['GET'])
def health():
    return {"status": "alive"}, 200


# ── Acceso al panel ───────────────────────────────────────────────────────────

_FAILED_LOGINS = {}
_MAX_FAILURES, _LOCKOUT = 8, 600


def _logged_in():
    if session.get("auth"):
        return True
    # Para descargar desde un script: autenticación básica, con cualquier usuario
    basic = request.authorization
    return bool(basic and basic.password and _same(basic.password, DASHBOARD_PASSWORD))


def _deny():
    if "text/html" in request.headers.get("Accept", "") and not request.authorization:
        # Tras entrar se vuelve a donde se iba; a un formulario enviado no se puede volver
        back = request.full_path.rstrip("?") if request.method == "GET" else None
        return redirect(url_for("login", next=back))
    return Response("Hace falta la contraseña del panel.\n", 401,
                    {"WWW-Authenticate": 'Basic realm="CODEA 2"', "Content-Type": "text/plain; charset=utf-8"})


def viewer(view):
    """Páginas y descargas de solo lectura."""
    @wraps(view)
    def decorated(*args, **kwargs):
        if DASHBOARD_PUBLIC or _logged_in():
            return view(*args, **kwargs)
        return _deny()
    return decorated


def editor(view):
    """Lo que cambia algo: excluir sesiones, notas, subir archivos. Siempre con contraseña."""
    @wraps(view)
    def decorated(*args, **kwargs):
        if not session.get("auth"):
            return _deny()
        if not _same(request.form.get("csrf") or request.headers.get("X-CSRF-Token"), session.get("csrf")):
            abort(400, description="Formulario caducado: recarga la página y vuelve a intentarlo.")
        return view(*args, **kwargs)
    return decorated


def _csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def _safe_next(target):
    """Solo rutas de este mismo sitio: nunca redirigir a donde diga un enlace ajeno."""
    parts = urlsplit(target or "")
    if parts.scheme or parts.netloc or not parts.path.startswith("/") or parts.path.startswith("//"):
        return url_for("metricas")
    return target


@app.route("/login", methods=["GET", "POST"])
def login():
    target = _safe_next(request.values.get("next"))
    if session.get("auth"):
        return redirect(target)

    error = None
    if request.method == "POST":
        now = time.time()
        if len(_FAILED_LOGINS) > 2000:
            _FAILED_LOGINS.clear()
        failures = [t for t in _FAILED_LOGINS.get(request.remote_addr, []) if now - t < _LOCKOUT]
        if len(failures) >= _MAX_FAILURES:
            error = "Demasiados intentos. Espera unos minutos."
        elif _same(request.form.get("password"), DASHBOARD_PASSWORD):
            _FAILED_LOGINS.pop(request.remote_addr, None)
            session.clear()
            session["auth"] = True
            session.permanent = True
            return redirect(target)
        else:
            _FAILED_LOGINS[request.remote_addr] = failures + [now]
            log.warning("contraseña incorrecta desde %s", request.remote_addr)
            error = "Contraseña incorrecta."
    return render_template("login.html", error=error, target=target), 401 if error else 200


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Páginas ───────────────────────────────────────────────────────────────────

def _scope():
    """El recorte de la URL y las sesiones que deja: lo que comparten páginas y descargas."""
    filters = Filters.from_args(request.args)
    matching = filters.apply(dataset.runs(), with_excluded=True)
    included = [r for r in matching if not r.left_out]
    return {
        "filters": filters,
        "matching": matching,
        "runs": included,
        "excluded_count": len(matching) - len(included),
    }


@app.route("/")
@viewer
def metricas():
    scope = _scope()
    filters, runs = scope["filters"], scope["runs"]
    if filters.difficulty is None:
        # Las dificultades no se mezclan: sin elegir, se entra por la que más sesiones tiene
        counts = [sum(1 for r in runs if r.difficulty == d) for d in DIFFICULTIES]
        busiest = list(DIFFICULTIES)[counts.index(max(counts))]
        return redirect(url_for("metricas", **filters.query(difficulty=busiest)))
    return render_template(
        "metricas.html", **scope,
        summaries=[metrics.scenario_summary(runs, number) for number in SCENARIOS],
        sheet=sheet,
        legacy_count=sum(1 for r in scope["matching"] if r.legacy and not r.excluded and r.left_out),
    )


@app.route("/exploracion")
@viewer
def resumen():
    scope = _scope()
    runs = scope["runs"]
    return render_template(
        "resumen.html", **scope,
        headline=stats.headline(runs),
        cards=stats.scenario_cards(runs),
        strip=stats.time_strip(runs),
        days=stats.sessions_per_day(runs),
        descriptives=stats.descriptives(runs),
    )


@app.route("/sesiones")
@viewer
def sesiones():
    scope = _scope()
    return render_template("sesiones.html", **scope, rows=list(reversed(scope["matching"])))


@app.route("/sesiones/<run_id>")
@viewer
def sesion(run_id):
    runs = dataset.runs()
    run = next((r for r in runs if r.id == run_id), None)
    if run is None:
        abort(404, description="No hay ninguna sesión con ese nombre.")
    index = runs.index(run)
    return render_template(
        "sesion.html", run=run, sheet=sheet,
        measures={n: metrics.scenario_metrics(run, n) for n in run.scenarios},
        previous=runs[index - 1] if index else None,
        following=runs[index + 1] if index + 1 < len(runs) else None,
        timeline=stats.timeline(run),
        details={n: stats.scenario_detail(s) for n, s in run.scenarios.items()},
        tries={n: stats.tries_detail(s) for n, s in run.scenarios.items()},
        raw=json.dumps(run.raw, ensure_ascii=False, indent=2),
    )


@app.route("/sesiones/<run_id>/estado", methods=["POST"])
@editor
def sesion_estado(run_id):
    run = dataset.get(run_id)
    if run is None:
        abort(404)
    # El formulario manda un "0" oculto y, si la casilla está marcada, un "1" detrás: vale el último
    excluded = request.form.getlist("excluded")
    store.set_state(run.file.name,
                    excluded=excluded[-1] == "1" if excluded else None,
                    note=request.form.get("note"),
                    **sheet.from_form(request.form))
    if request.headers.get("X-Requested-With") == "fetch":
        return {"status": "ok"}
    target = request.form.get("next")
    return redirect(_safe_next(target) if target else url_for("sesion", run_id=run_id))


@app.route("/escenarios")
@viewer
def escenarios():
    scope = _scope()
    return render_template("escenarios.html", **scope, sections=stats.scenario_sections(scope["runs"]))


@app.route("/datos")
@viewer
def datos():
    scope = _scope()
    runs = scope["matching"] if scope["filters"].with_excluded else scope["runs"]
    return render_template("datos.html", **scope, tables=tables.build_tables(runs), preview=25,
                           cell=exports.plain)


@app.route("/archivos")
@viewer
def archivos():
    files = sorted(store.files(), key=lambda f: f.mtime, reverse=True)
    return render_template("archivos.html", files=files, total_size=sum(f.size for f in files))


@app.route("/archivos/subir", methods=["POST"])
@editor
def archivos_subir():
    saved = 0
    for file in request.files.getlist("files"):
        if not file.filename:
            continue
        saved_as, error = _save(file)
        if error:
            flash(f"{file.filename}: solo se aceptan archivos .json o .csv.", "error")
        else:
            saved += 1
            if saved_as != secure_filename(file.filename):
                flash(f"{file.filename} se guardó como {saved_as}: ya había otra sesión con ese nombre.", "info")
    if saved:
        flash(f"{saved} archivo(s) guardado(s).", "ok")
    return redirect(url_for("archivos"))


@app.route("/archivos/<name>")
@viewer
def archivo(name):
    if name not in {f.name for f in store.files()}:
        abort(404)
    return send_from_directory(store.directory, name, as_attachment=True, max_age=0)


# ── Descargas ─────────────────────────────────────────────────────────────────

def _export_tables():
    filters = Filters.from_args(request.args)
    return tables.build_tables(filters.apply(dataset.runs()))


def _download(body, mimetype, filename):
    stamp = datetime.now(ZONE).strftime("%Y%m%d")
    name, ext = os.path.splitext(filename)
    return Response(body, mimetype=mimetype, headers={
        "Content-Disposition": f'attachment; filename="{name}_{stamp}{ext}"'})


_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@app.route("/exportar/<name>.<fmt>")
@viewer
def exportar(name, fmt):
    table = next((t for t in _export_tables() if t.name == name), None)
    if table is None:
        abort(404, description="No existe esa tabla.")
    if fmt == "csv":
        return _download(exports.to_csv(table), "text/csv", f"codea2_{name}.csv")
    if fmt == "json":
        return _download(exports.to_json(table), "application/json", f"codea2_{name}.json")
    if fmt == "xlsx":
        return _download(exports.to_xlsx([table]), _XLSX, f"codea2_{name}.xlsx")
    abort(404, description="Formatos disponibles: csv, json y xlsx.")


@app.route("/exportar/todo.xlsx")
@viewer
def exportar_libro():
    return _download(exports.to_xlsx(_export_tables()), _XLSX, "codea2_datos.xlsx")


@app.route("/exportar/todo-csv.zip")
@viewer
def exportar_csv():
    return _download(exports.csv_zip(_export_tables()), "application/zip", "codea2_csv.zip")


@app.route("/exportar/originales.zip")
@viewer
def exportar_originales():
    return _download(exports.originals_zip(store), "application/zip", "codea2_json_originales.zip")


# ── Plantillas ────────────────────────────────────────────────────────────────

def _local(moment):
    if isinstance(moment, (int, float)):
        return datetime.fromtimestamp(moment, ZONE)
    return moment.astimezone(ZONE) if moment.tzinfo else moment


@app.template_filter("clock")
def fmt_clock(seconds):
    """Segundos como m:ss, o h:mm:ss si pasa de la hora."""
    if seconds is None:
        return "—"
    minutes, rest = divmod(int(round(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{rest:02d}" if hours else f"{minutes}:{rest:02d}"


@app.template_filter("num")
def fmt_num(value, decimals=1):
    """Número con coma decimal."""
    if value is None:
        return "—"
    return f"{value:,.{decimals}f}".replace(",", "\u202f").replace(".", ",")


@app.template_filter("secs")
def fmt_secs(value):
    return "—" if value is None else f"{fmt_num(value)}\u00a0s"


@app.template_filter("pct")
def fmt_pct(ratio):
    return "—" if ratio is None else f"{ratio * 100:.0f}\u00a0%"


@app.template_filter("css")
def fmt_css(ratio):
    """Fracción 0–1 como porcentaje para una propiedad CSS."""
    return f"{max(ratio or 0, 0) * 100:.3f}%"


@app.template_filter("dt")
def fmt_dt(moment, pattern="%d/%m/%Y %H:%M"):
    """Fecha y hora en la zona local."""
    return "—" if moment is None else _local(moment).strftime(pattern)


@app.template_filter("day")
def fmt_day(day, pattern="%d/%m/%Y"):
    return "—" if day is None else day.strftime(pattern)


@app.template_filter("size")
def fmt_size(size):
    return f"{fmt_num(size / 1024)}\u00a0kB" if size >= 1024 else f"{size}\u00a0B"


def _asset_version():
    """Cambia con cada despliegue: el navegador y Cloudflare no sirven un CSS viejo tras un git pull."""
    digest = hashlib.sha256()
    folder = app.static_folder
    for name in sorted(os.listdir(folder)):
        with open(os.path.join(folder, name), "rb") as handle:
            digest.update(handle.read())
    return digest.hexdigest()[:10]


ASSET_VERSION = _asset_version()


@app.context_processor
def _template_globals():
    return {
        "csrf_token": _csrf_token,
        "asset": lambda name: url_for("static", filename=name, v=ASSET_VERSION),
        "can_edit": bool(session.get("auth")),
        "is_public": DASHBOARD_PUBLIC,
        "SCENARIOS": SCENARIOS,
        "DIFFICULTIES": DIFFICULTIES,
        "COUNTER_LABELS": tables.COUNTER_LABELS,
        "COUNTER_DOCS": tables.COUNTER_DOCS,
        "TITLES": metrics.TITLES,
        "zone_name": getattr(ZONE, "key", None) or str(ZONE),
        # El recorte viaja en la URL: las páginas sin recorte propio lo conservan en los enlaces
        "filters": Filters.from_args(request.args),
    }


@app.errorhandler(404)
@app.errorhandler(400)
@app.errorhandler(413)
def _error_page(error):
    if "text/html" not in request.headers.get("Accept", ""):
        return {"error": error.description}, error.code
    return render_template("error.html", error=error), error.code


@app.after_request
def _finish(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    if request.endpoint == "static":
        return response
    response.headers.setdefault("Cache-Control", "no-store")
    # El healthcheck del contenedor llama cada pocos segundos: no se registra
    if not (request.path == "/health" and request.remote_addr in ("127.0.0.1", "::1")):
        log.info("%s %s %s %s", request.remote_addr, request.method, request.path, response.status_code)
    return response


@app.route("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


if __name__ == '__main__':
    port = int(os.environ.get("PORT", "8080"))
    try:
        from waitress import serve
    except ImportError:
        app.run(host='0.0.0.0', port=port)
    else:
        log.info("CODEA 2 escuchando en el puerto %s · subidas en %s", port, UPLOAD_DIR)
        # El túnel de Cloudflare llega por HTTP y dice en cabeceras quién pidió qué y si fue por HTTPS
        serve(app, host='0.0.0.0', port=port, threads=8, trusted_proxy="*",
              trusted_proxy_headers="x-forwarded-for x-forwarded-proto x-forwarded-host")
