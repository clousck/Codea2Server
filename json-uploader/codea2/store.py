"""Carpeta de subidas: lectura tolerante de los JSON, guardado y estado del panel."""

import filecmp
import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass

# .csv se mantiene para no rechazar lo ya recogido con la versión anterior
ALLOWED_EXTENSIONS = (".json", ".csv")

# Todo lo que el panel escribe por su cuenta empieza por punto: secure_filename quita
# los puntos iniciales, así que una subida nunca puede pisarlo.
STATE_FILE = ".codea2-panel.json"
VERSIONS_DIR = ".versiones"


@dataclass(frozen=True)
class StoredFile:
    name: str
    size: int
    mtime: float
    status: str  # ok | repaired | invalid | not_run | other
    detail: str
    data: dict | None

    @property
    def id(self):
        return os.path.splitext(self.name)[0]

    @property
    def is_run(self):
        return self.data is not None


def repair_truncated(text):
    """Recupera un JSON cortado a mitad cerrando las estructuras que quedaron abiertas.

    Pasa cuando la app se cierra mientras escribe o cuando el archivo se copia incompleto.
    Devuelve None si el texto no está cortado: entonces el error es otro y no se inventa nada.
    """
    stack = []
    cuts = []  # (posición donde se puede cortar, estructuras abiertas en ese punto)
    in_string = escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
            cuts.append((i + 1, "".join(stack)))
        elif ch in "}]":
            if not stack:
                return None
            stack.pop()
            cuts.append((i + 1, "".join(stack)))
        elif ch == ",":
            cuts.append((i, "".join(stack)))
    if not stack:
        return None

    # Primero el texto entero; si no cierra, se va soltando el último elemento a medias
    candidates = [] if in_string else [(len(text), "".join(stack))]
    candidates += reversed(cuts[-40:])
    for end, opened in candidates:
        closers = "".join("}" if ch == "{" else "]" for ch in reversed(opened))
        try:
            return json.loads(text[:end].rstrip() + closers)
        except ValueError:
            continue
    return None


def looks_like_run(data):
    return isinstance(data, dict) and ("pin" in data or any(k.startswith("escenario") for k in data))


def parse_run_text(text):
    """Devuelve (datos, estado, detalle) de un JSON de sesión."""
    if not text.strip():
        return None, "invalid", "Archivo vacío"
    status, detail = "ok", ""
    try:
        data = json.loads(text)
    except ValueError as error:
        data = repair_truncated(text)
        if data is None:
            return None, "invalid", f"JSON inválido: {error}"
        status, detail = "repaired", "JSON cortado: se recuperó cerrando las estructuras abiertas"
    if not looks_like_run(data):
        return None, "not_run", "JSON válido, pero sin forma de sesión (ni pin ni escenarios)"
    return data, status, detail


def _read_run(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    # El visor escribe con BOM
    return parse_run_text(raw.decode("utf-8-sig", errors="replace"))


class Store:
    def __init__(self, directory):
        self.directory = directory
        os.makedirs(directory, exist_ok=True)
        self._lock = threading.RLock()
        self._cache = {}
        self._state = (None, {})

    # ── Lectura ──────────────────────────────────────────────────────────────

    def files(self):
        """Todos los archivos subidos. Cada uno se lee una sola vez mientras no cambie."""
        found = []
        with self._lock:
            with os.scandir(self.directory) as entries:
                for entry in entries:
                    if entry.name.startswith(".") or not entry.is_file():
                        continue
                    stat = entry.stat()
                    signature = (stat.st_mtime_ns, stat.st_size)
                    cached = self._cache.get(entry.name)
                    if cached is None or cached[0] != signature:
                        cached = (signature, self._load(entry.path, entry.name, stat))
                        self._cache[entry.name] = cached
                    found.append(cached[1])
            for name in set(self._cache) - {f.name for f in found}:
                del self._cache[name]
        return sorted(found, key=lambda f: f.name)

    def _load(self, path, name, stat):
        if not name.lower().endswith(".json"):
            return StoredFile(name, stat.st_size, stat.st_mtime, "other",
                              "No es JSON: se conserva, pero el panel no lo lee", None)
        try:
            data, status, detail = _read_run(path)
        except OSError as error:
            data, status, detail = None, "invalid", f"No se pudo leer: {error}"
        return StoredFile(name, stat.st_size, stat.st_mtime, status, detail, data)

    def path(self, name):
        return os.path.join(self.directory, name)

    # ── Subidas ──────────────────────────────────────────────────────────────

    def save_upload(self, filename, upload):
        """Guarda una subida y devuelve el nombre con el que quedó.

        Normalmente es el que manda el visor, {pin}_{sessionId}.json. El sessionId es un
        contador de cada visor, así que dos visores con el mismo PIN pueden mandar el
        mismo nombre: si lo que hay guardado es otra sesión, la nueva se guarda aparte
        con un sufijo en vez de pisarla.
        """
        handle, temp = tempfile.mkstemp(dir=self.directory, prefix=".subiendo-", suffix=".tmp")
        os.close(handle)
        try:
            upload.save(temp)
            os.chmod(temp, 0o644)  # mkstemp crea con 600 y el archivo no se podría leer fuera del contenedor
            with self._lock:
                name = self._free_name(filename, temp)
                target = self.path(name)
                if os.path.exists(target):
                    if filecmp.cmp(temp, target, shallow=False):
                        return name
                    self._keep_version(name)
                os.replace(temp, target)
            return name
        finally:
            if os.path.exists(temp):
                os.remove(temp)

    def _free_name(self, filename, temp):
        """El nombre pedido, o el primero con sufijo que no pise una sesión distinta."""
        stem, ext = os.path.splitext(filename)
        incoming = _run_start(temp) if ext.lower() == ".json" else None
        candidate = filename
        for suffix in range(2, 100):
            stored = self.path(candidate)
            if incoming is None or not os.path.exists(stored):
                return candidate
            existing = _run_start(stored)
            if existing is None or existing == incoming:
                return candidate
            candidate = f"{stem}-{suffix}{ext}"
        return filename

    def _keep_version(self, name):
        """Una resubida con otro contenido no borra la anterior: queda en .versiones/."""
        try:
            versions = self.path(VERSIONS_DIR)
            os.makedirs(versions, exist_ok=True)
            stem, ext = os.path.splitext(name)
            stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(os.path.getmtime(self.path(name))))
            backup = os.path.join(versions, f"{stem}.{stamp}{ext}")
            copy = 2
            while os.path.exists(backup):
                backup = os.path.join(versions, f"{stem}.{stamp}-{copy}{ext}")
                copy += 1
            os.replace(self.path(name), backup)
        except OSError:
            # Sin respaldo no se rechaza la subida: lo que llega del visor es lo más reciente
            pass

    # ── Estado del panel: sesiones excluidas, notas, fichas y las listas de personas ──

    def _document(self):
        """El archivo de estado entero: {"sessions", "supervisors", "students"}."""
        path = self.path(STATE_FILE)
        try:
            mtime = os.stat(path).st_mtime_ns
        except OSError:
            return {}
        with self._lock:
            if self._state[0] != mtime:
                try:
                    with open(path, encoding="utf-8") as handle:
                        document = json.load(handle)
                except (OSError, ValueError):
                    document = {}
                self._state = (mtime, document if isinstance(document, dict) else {})
            return self._state[1]

    def state(self):
        sessions = self._document().get("sessions", {})
        return sessions if isinstance(sessions, dict) else {}

    def supervisors(self):
        """{"07": "Mateo", …}: el código son los dos primeros dígitos del PIN."""
        found = self._document().get("supervisors", {})
        return {str(k): str(v) for k, v in found.items()} if isinstance(found, dict) else {}

    def students(self):
        """{"0701": {"name": "Ana", "supervisor": "07", "retired": False}, …}, por código."""
        found = self._document().get("students", {})
        if not isinstance(found, dict):
            return {}
        return {str(code): {"name": str(v.get("name") or ""), "supervisor": str(v.get("supervisor") or ""),
                            "retired": bool(v.get("retired"))}
                for code, v in sorted(found.items()) if isinstance(v, dict)}

    def _write(self, change):
        """Aplica change(documento) y lo guarda de golpe: o queda entero o no se escribe."""
        with self._lock:
            document = json.loads(json.dumps(self._document()))  # copia: lo cacheado no se toca
            change(document)
            handle, temp = tempfile.mkstemp(dir=self.directory, prefix=".subiendo-", suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump(document, out, ensure_ascii=False, indent=2)
            os.chmod(temp, 0o644)
            path = self.path(STATE_FILE)
            os.replace(temp, path)
            # Se deja ya en memoria: dos escrituras seguidas pueden compartir marca de tiempo
            self._state = (os.stat(path).st_mtime_ns, document)

    def set_state(self, name, **fields):
        """Cambia lo que se pase del estado de una sesión; lo que vaya en None no se toca."""
        def change(document):
            sessions = document.get("sessions")
            sessions = {k: v for k, v in sessions.items() if isinstance(v, dict)} if isinstance(sessions, dict) else {}
            entry = sessions.get(name, {})
            for key, value in fields.items():
                if value is not None:
                    entry[key] = value.strip() if isinstance(value, str) else value
            entry = {key: value for key, value in entry.items() if value}
            if entry:
                sessions[name] = entry
            else:
                sessions.pop(name, None)
            document["sessions"] = sessions
        self._write(change)

    def set_supervisor(self, code, name):
        """Añade, renombra o (con name vacío) quita un supervisor."""
        def change(document):
            found = document.get("supervisors")
            found = dict(found) if isinstance(found, dict) else {}
            if name:
                found[code] = name
            else:
                found.pop(code, None)
            document["supervisors"] = dict(sorted(found.items()))
        self._write(change)

    def add_students(self, supervisor, lines):
        """Da de alta una línea por estudiante con el supervisor indicado.

        Una línea es un nombre, que recibe el siguiente código libre del bloque del supervisor
        (07 → 0701, 0702…, siempre detrás del más alto ya dado), o «0701 Nombre» para respetar un
        código ya numerado. Los códigos no se reutilizan: un estudiante que se va queda retirado.
        Devuelve (añadidos [(código, nombre)], errores [texto]). Si hay algún error no se guarda nada.
        """
        added, errors = [], []

        def change(document):
            found = document.get("students")
            found = dict(found) if isinstance(found, dict) else {}
            block = [int(code[2:]) for code in found if code.startswith(supervisor) and code[2:].isdigit()]
            following = max(block + [0]) + 1
            for number, line in enumerate(lines, start=1):
                line = " ".join(line.split())
                if not line:
                    continue
                head, _, rest = line.partition(" ")
                if len(head) == 4 and head.isdigit() and rest:
                    code, name = head, rest
                    if head.startswith(supervisor):
                        # Los nombres sueltos siguen detrás de los códigos ya escritos, también en esta tanda
                        following = max(following, int(head[2:]) + 1)
                else:
                    if following > 99:
                        errors.append(f"Línea {number} ({line}): el bloque {supervisor} ya no tiene códigos libres "
                                      "(llega a 99). Usa otro bloque para el resto.")
                        continue
                    code, name = f"{supervisor}{following:02d}", line
                    following += 1
                name = name[:80]
                if code in found:
                    errors.append(f"Línea {number} ({line}): el código {code} ya es de {found[code].get('name')}.")
                    continue
                found[code] = {"name": name, "supervisor": supervisor}
                added.append((code, name))
            if not errors:
                document["students"] = dict(sorted(found.items()))
        self._write(change)
        if errors:
            added.clear()
        return added, errors

    def set_student(self, code, name=None, supervisor=None, retired=None):
        """Cambia el nombre, el supervisor o si está retirado; lo que vaya en None no se toca."""
        def change(document):
            found = document.get("students")
            found = dict(found) if isinstance(found, dict) else {}
            entry = dict(found.get(code) or {})
            if not entry:
                return
            if name:
                entry["name"] = name[:80]
            if supervisor:
                entry["supervisor"] = supervisor
            if retired is not None:
                if retired:
                    entry["retired"] = True
                else:
                    entry.pop("retired", None)
            found[code] = entry
            document["students"] = found
        self._write(change)


def _run_start(path):
    """startedUtc de una sesión guardada, o None si no se puede saber."""
    try:
        data, _, _ = _read_run(path)
    except OSError:
        return None
    start = data.get("startedUtc") if data else None
    return start if isinstance(start, str) and start else None
