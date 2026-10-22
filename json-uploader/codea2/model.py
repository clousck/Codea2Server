"""Modelo de una sesión: normaliza el JSON que emite el visor.

JsonUtility siempre escribe todos los campos, pero aquí no se da por hecho: un APK
antiguo, un archivo cortado o una subida a mitad de partida dejan campos sin venir.
"""

import fnmatch
import math
import os
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .store import StoredFile


def _local_zone():
    try:
        return ZoneInfo(os.environ.get("DASHBOARD_TZ", "America/Guayaquil"))
    except Exception:
        # Sin base de zonas horarias: Ecuador continental no tiene horario de verano
        return timezone(timedelta(hours=-5), "UTC-5")


ZONE = _local_zone()

DIFFICULTIES = {1: "Básica", 2: "Intermedia"}

# Las sesiones con el formato anterior al 06/10/2026 son pruebas internas con el cronómetro
# sin validar: se guardan y se pueden ver, pero no entran en el análisis salvo que se pida.
INCLUDE_LEGACY = os.environ.get("ANALYZE_OLD_FORMAT", "").strip() == "1"


@dataclass(frozen=True)
class ScenarioMeta:
    number: int
    name: str  # pilar que trabaja
    events_key: str  # lista de eventos dentro del registro
    events_label: str
    counters: tuple  # contadores del registro, en el orden del JSON
    error_key: str  # el contador que mejor resume los errores del escenario
    error_label: str
    tries_key: str = ""  # segunda lista: los Probar del escenario 2 (desde el 22/10/2026)
    tries_label: str = ""

    @property
    def key(self):
        return f"escenario{self.number}"

    @property
    def short(self):
        return f"E{self.number}"


# El formato cambió el 06/10/2026 y en uploads/ conviven los dos. Cada escenario lista primero
# sus contadores de hoy y después los que solo traen los JSON anteriores; el que un archivo
# no trae queda vacío. wrongSelections y wrongPlacements ya no vienen: se cuentan de la lista.
_LEGACY = ("blocksReleased", "errorIncompleteSequence")

# En el escenario 3 los intentos fallidos casi no ocurren por diseño (solo falla la pasada
# que no clasifica nada): lo que distingue a un niño de otro son los comandos inválidos.
SCENARIOS = {
    1: ScenarioMeta(1, "Secuencialidad", "attempts", "Intentos",
                    ("failedAttempts", "blocksGrabbed", "blocksConnected", "blockResets",
                     "errorCollisionBot", "errorInvalidUse", *_LEGACY, "errorInvalidCommand"),
                    "failedAttempts", "intentos fallidos"),
    2: ScenarioMeta(2, "Condicionales", "selections", "Selecciones", ("failedAttempts", "wrongSelections"),
                    "wrongSelections", "selecciones incorrectas", "attempts", "Pruebas"),
    3: ScenarioMeta(3, "Bucles", "attempts", "Ejecuciones",
                    ("failedAttempts", "blocksGrabbed", "blocksConnected", "errorInvalidCommand",
                     *_LEGACY, "errorCollisionBot"),
                    "errorInvalidCommand", "comandos inválidos"),
    4: ScenarioMeta(4, "Patrones", "placements", "Colocaciones",
                    ("wrongPlacements", "chipsGrabbed", "chipsReleased"),
                    "wrongPlacements", "colocaciones incorrectas"),
}

_ISO = re.compile(r"^(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d)(?:\.(\d+))?(Z|[+-]\d\d:?\d\d)?$")


def parse_utc(value):
    """Marca de tiempo del visor ('2026-09-30T15:15:47.1021390Z', siete decimales) a datetime UTC."""
    if not isinstance(value, str):
        return None
    match = _ISO.match(value.strip())
    if not match:
        return None
    year, month, day, hour, minute, second, fraction, offset = match.groups()
    micro = int((fraction or "").ljust(6, "0")[:6])
    # Una fecha por defecto (año 1) no es una marca de tiempo, y no se puede pasar a hora local
    if int(year) < 1970:
        return None
    try:
        moment = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second),
                          micro, tzinfo=timezone.utc)
    except ValueError:
        return None
    if offset and offset != "Z":
        digits = offset[1:].replace(":", "")
        delta = timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
        moment = moment - delta if offset[0] == "+" else moment + delta
    return moment


def as_flag(value):
    """Las banderas llegan como true/false (started, completed) o como 0/1 (solved, correct...)."""
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true")
    return bool(value)


def is_selected(event):
    """Si la pulsación marcó la opción. Desde el 06/10/2026 solo se registran las que marcan."""
    return as_flag(event.get("selected", True))


def solution_percent(event):
    """solutionPercent de un intento (0 a 100), o None.

    Llega el 22/10/2026. -1 significa que el juego no tenía la solución cargada: no es un cero.
    """
    value = as_float(event.get("solutionPercent"))
    return value if value is not None and 0 <= value <= 100 else None


def remaining(event):
    """remaining de una ejecución del escenario 3, o None si no viene o vale -1."""
    value = as_int(event.get("remaining"))
    return value if value is not None and value >= 0 else None


def as_int(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value == int(value):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def as_float(value):
    """Un número del JSON, o None. JsonUtility puede escribir NaN o Infinity: tampoco sirven."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def seconds_between(start, end):
    if start is None or end is None:
        return None
    return (end - start).total_seconds()


@dataclass(frozen=True)
class Issue:
    """Aviso de integridad. `scenario` es None si afecta a la sesión entera."""
    code: str
    scenario: int | None
    message: str


@dataclass(frozen=True)
class Scenario:
    meta: ScenarioMeta
    raw: dict
    present: bool
    started: bool
    completed: bool
    total_seconds: float | None
    started_at: datetime | None
    ended_at: datetime | None
    events: tuple
    timed_out: bool = False  # la sala agotó sus 5 minutos y la historia siguió (desde el 12/10/2026)
    tries: tuple = ()  # los Probar del escenario 2; vacío en los demás y en los JSON anteriores al 22/10/2026
    difficulty: int | None = None  # la de la sesión: hace falta para comparar con la clave de soluciones

    @property
    def number(self):
        return self.meta.number

    @property
    def clock_seconds(self):
        """Tiempo de reloj entre inicio y fin. Difiere de totalSeconds si el visor estuvo en pausa."""
        return seconds_between(self.started_at, self.ended_at)

    def counter(self, key):
        if key not in self.raw and self.present:
            if key == "wrongSelections":
                return sum(1 for e in self.events if is_selected(e) and not as_flag(e.get("correct")))
            if key == "wrongPlacements":
                return sum(1 for e in self.events if not as_flag(e.get("correct")))
        return as_int(self.raw.get(key))

    @property
    def has_tries(self):
        """Si el JSON trae la lista de pruebas: los anteriores al 22/10/2026 no la tienen."""
        return bool(self.meta.tries_key) and isinstance(self.raw.get(self.meta.tries_key), list)

    @property
    def errors(self):
        return self.counter(self.meta.error_key)

    def offset(self, event):
        """Segundos desde el inicio del escenario hasta un evento."""
        return seconds_between(self.started_at, parse_utc(event.get("timestamp")))


@dataclass(frozen=True)
class Run:
    file: StoredFile
    pin: str
    device_id: str
    session_id: int | None
    difficulty: int | None
    started_at: datetime | None
    ended_at: datetime | None
    scenarios: dict
    excluded: bool = False
    note: str = ""
    issues: tuple = field(default_factory=tuple)
    sheet: dict = field(default_factory=dict)  # ficha de sesión, rellenada en el panel

    @property
    def legacy(self):
        """Formato anterior al 06/10/2026: el visor aún no mandaba su código."""
        return "deviceId" not in self.raw

    @property
    def left_out(self):
        return self.excluded or (self.legacy and not INCLUDE_LEGACY)

    @property
    def id(self):
        return self.file.id

    @property
    def raw(self):
        return self.file.data

    @property
    def expected_name(self):
        """El nombre con el que el visor sube esta sesión; lleva el visor desde el 06/10/2026."""
        parts = [self.pin, str(self.session_id)] + ([self.device_id] if self.device_id else [])
        return "_".join(parts) + ".json"

    @property
    def difficulty_label(self):
        return DIFFICULTIES.get(self.difficulty, "Desconocida")

    @property
    def local_start(self):
        return self.started_at.astimezone(ZONE) if self.started_at else None

    @property
    def local_date(self):
        return self.local_start.date() if self.started_at else None

    @property
    def seconds(self):
        """Duración de la sesión entera: incluye narración y traslados entre salas.

        Sin cierre, vale el totalSeconds de la raíz: el visor lo va actualizando en cada guardado.
        """
        clock = seconds_between(self.started_at, self.ended_at)
        return clock if clock is not None else as_float(self.raw.get("totalSeconds"))

    @property
    def challenge_seconds(self):
        totals = [s.total_seconds for s in self.scenarios.values() if s.started and s.total_seconds]
        return sum(totals) if totals else None

    @property
    def scenarios_started(self):
        return sum(1 for s in self.scenarios.values() if s.started)

    @property
    def scenarios_completed(self):
        return sum(1 for s in self.scenarios.values() if s.completed)

    @property
    def completed_all(self):
        return self.scenarios_completed == len(SCENARIOS)


def build_run(file):
    data = file.data
    scenarios = {}
    for meta in SCENARIOS.values():
        raw = data.get(meta.key)
        present = isinstance(raw, dict)
        raw = raw if present else {}
        events = raw.get(meta.events_key)
        tries = raw.get(meta.tries_key) if meta.tries_key else None
        scenarios[meta.number] = Scenario(
            meta=meta,
            raw=raw,
            present=present,
            started=as_flag(raw.get("started")),
            completed=as_flag(raw.get("completed")),
            total_seconds=as_float(raw.get("totalSeconds")),
            started_at=parse_utc(raw.get("startedUtc")),
            ended_at=parse_utc(raw.get("endedUtc")),
            events=tuple(e for e in events if isinstance(e, dict)) if isinstance(events, list) else (),
            timed_out=as_flag(raw.get("timedOut")),
            tries=tuple(e for e in tries if isinstance(e, dict)) if isinstance(tries, list) else (),
            difficulty=as_int(data.get("difficulty")),
        )
    pin = data.get("pin")
    return Run(
        file=file,
        pin="" if pin is None else str(pin),
        device_id=str(data.get("deviceId") or ""),
        session_id=as_int(data.get("sessionId")),
        difficulty=as_int(data.get("difficulty")),
        started_at=parse_utc(data.get("startedUtc")),
        ended_at=parse_utc(data.get("endedUtc")),
        scenarios=scenarios,
    )


def _parse_date(value):
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


@dataclass(frozen=True)
class Filters:
    """El recorte que comparten el panel y las descargas: viaja en la URL."""
    date_from: date | None = None
    date_to: date | None = None
    difficulty: int | None = None
    pin: str = ""
    with_excluded: bool = False

    @classmethod
    def from_args(cls, args):
        difficulty = as_int(args.get("dif", ""))
        return cls(
            date_from=_parse_date(args.get("desde")),
            date_to=_parse_date(args.get("hasta")),
            difficulty=difficulty if difficulty in DIFFICULTIES else None,
            pin=" ".join((args.get("pin") or "").replace(",", " ").split()),
            with_excluded=args.get("excluidas") == "1",
        )

    @property
    def active(self):
        return bool(self.date_from or self.date_to or self.difficulty or self.pin)

    def query(self, **changes):
        """Parámetros de URL de este recorte, para enlazar sin perderlo."""
        current = replace(self, **changes) if changes else self
        params = {
            "desde": current.date_from.isoformat() if current.date_from else None,
            "hasta": current.date_to.isoformat() if current.date_to else None,
            "dif": current.difficulty,
            "pin": current.pin or None,
            "excluidas": "1" if current.with_excluded else None,
        }
        return {k: v for k, v in params.items() if v is not None}

    def _pin_matches(self, pin):
        """'0101 01* -0000': exactos o con comodines; con guion delante, se descartan."""
        wanted = [t for t in self.pin.split() if not t.startswith("-")]
        unwanted = [t[1:] for t in self.pin.split() if t.startswith("-") and len(t) > 1]
        if any(fnmatch.fnmatchcase(pin, pattern) for pattern in unwanted):
            return False
        return not wanted or any(fnmatch.fnmatchcase(pin, pattern) for pattern in wanted)

    def matches(self, run):
        if self.difficulty and run.difficulty != self.difficulty:
            return False
        if self.date_from or self.date_to:
            day = run.local_date
            if day is None:
                return False
            if (self.date_from and day < self.date_from) or (self.date_to and day > self.date_to):
                return False
        return not self.pin or self._pin_matches(run.pin)

    def apply(self, runs, with_excluded=None):
        """Las sesiones del recorte. Las excluidas solo entran si se piden."""
        keep_excluded = self.with_excluded if with_excluded is None else with_excluded
        return [r for r in runs if self.matches(r) and (keep_excluded or not r.left_out)]
