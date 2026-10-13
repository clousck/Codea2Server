"""Tabulación: las sesiones convertidas en tablas planas, una fila por observación.

Los nombres de columna son los del JSON siempre que el dato sale tal cual, para poder
cruzarlos con la documentación de variables del proyecto. Las banderas van todas como
0/1 y lo que no aplica a una fila se deja vacío, nunca a cero.
"""

from dataclasses import dataclass
from datetime import datetime

from . import sheet as ficha
from .model import SCENARIOS, ZONE, as_flag, as_float, as_int, is_selected, parse_utc, seconds_between

SEQUENCE_SEPARATOR = " > "


@dataclass(frozen=True)
class Column:
    name: str
    kind: str  # text | int | float | flag | utc | local | date
    description: str


@dataclass(frozen=True)
class Table:
    name: str
    title: str
    description: str
    columns: tuple
    rows: tuple


@dataclass(frozen=True)
class Event:
    """Algo que pasó en la sesión, con su hora."""
    at: datetime | None
    stamp: str
    scenario: int | None
    kind: str
    detail: str
    result: bool | None


_ZONE_NAME = getattr(ZONE, "key", None) or str(ZONE)

KEYS = (
    Column("file", "text", "Archivo JSON de la sesión. Es la clave que une todas las tablas"),
    Column("pin", "text", "PIN del participante. Es texto: conserva los ceros a la izquierda"),
    Column("deviceId", "text", "Código del visor (5 caracteres). Vacío en los JSON anteriores al 06/10/2026"),
    Column("sessionId", "int", "Contador de sesión del visor"),
    Column("difficulty", "int", "Dificultad de la sesión: 1 = básica, 2 = intermedia"),
)

COUNTER_DOCS = {
    "failedAttempts": "intentos fallidos que registró el juego",
    "blocksGrabbed": "veces que agarró un bloque",
    "blocksConnected": "veces que encajó un bloque en un hueco",
    "blockResets": "veces que pulsó el reinicio de bloques",
    "blocksReleased": "veces que soltó un bloque (solo en los JSON anteriores al 06/10/2026)",
    "errorCollisionBot": "errores de lógica por salirse de la rejilla o chocar",
    "errorInvalidUse": "errores de lógica por usar donde no hay nada",
    "errorIncompleteSequence": "errores de lógica por secuencia incompleta (solo en los JSON anteriores; siempre 0)",
    "errorInvalidCommand": "errores de lógica por comando inválido. En el escenario 1, solo en los JSON "
                           "anteriores, donde incluía el uso inválido",
    "wrongSelections": "opciones incorrectas que seleccionó. Si el JSON no lo trae, se cuenta de la lista",
    "wrongPlacements": "fichas colocadas en un hueco que no era el suyo. Si el JSON no lo trae, se cuenta de la lista",
    "chipsGrabbed": "veces que agarró una ficha",
    "chipsReleased": "veces que soltó una ficha (solo en los JSON anteriores al 06/10/2026)",
}

# Nombre corto de cada contador, para rótulos del panel
COUNTER_LABELS = {
    "failedAttempts": "Intentos fallidos",
    "blocksGrabbed": "Bloques agarrados",
    "blocksConnected": "Bloques conectados",
    "blockResets": "Reinicios de bloques",
    "blocksReleased": "Bloques soltados",
    "errorInvalidUse": "Usos inválidos",
    "errorCollisionBot": "Choques",
    "errorIncompleteSequence": "Secuencias incompletas",
    "errorInvalidCommand": "Comandos inválidos",
    "wrongSelections": "Selecciones incorrectas",
    "wrongPlacements": "Colocaciones incorrectas",
    "chipsGrabbed": "Fichas agarradas",
    "chipsReleased": "Fichas soltadas",
}

_SCENARIO_BASE = ("started", "completed", "timedOut", "totalSeconds", "startedUtc", "endedUtc")
_RUN_KNOWN = ("pin", "deviceId", "sessionId", "difficulty", "startedUtc", "endedUtc", "totalSeconds")
_ATTEMPT_KNOWN = ("difficulty", "sequence", "repetitions", "itemType", "solved", "durationSeconds", "timestamp")
_SELECTION_KNOWN = ("module", "option", "selected", "correct", "durationSeconds", "timestamp")
_PLACEMENT_KNOWN = ("socket", "chip", "correct", "durationSeconds", "timestamp")


def _keys(run):
    return {"file": run.file.name, "pin": run.pin, "deviceId": run.device_id, "sessionId": run.session_id,
            "difficulty": run.difficulty}


def _local(moment):
    """Hora local sin zona ni fracción de segundo: así Excel la entiende como fecha."""
    return moment.astimezone(ZONE).replace(tzinfo=None, microsecond=0) if moment else None


def _kind_of(value):
    if isinstance(value, bool):
        return "flag"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "text"


def _extra_columns(records, known):
    """Campos del JSON que este servidor no conoce: un APK más nuevo puede traerlos.

    Se exportan igual, al final de la tabla, en vez de perderse en silencio.
    """
    extras = {}
    for record in records:
        for key, value in record.items():
            if key in known or key in extras or isinstance(value, (dict, list)):
                continue
            extras[key] = Column(key, _kind_of(value), "Campo del JSON que este servidor aún no documenta")
    return tuple(extras.values())


def _with_extras(row, record, extras):
    for column in extras:
        row[column.name] = record.get(column.name)
    return row


def _sequence(event):
    blocks = event.get("sequence")
    return [str(b) for b in blocks] if isinstance(blocks, list) else []


# ── Sesiones: una fila por sesión ─────────────────────────────────────────────

def _session_columns():
    columns = [
        *KEYS,
        Column("difficultyLabel", "text", "Dificultad en palabras"),
        Column("startedUtc", "utc", "Inicio de la sesión (UTC), tal como viene en el JSON"),
        Column("endedUtc", "utc", "Fin de la sesión (UTC). Vacío si la run no se cerró"),
        Column("startedLocal", "local", f"Inicio de la sesión en hora local ({_ZONE_NAME})"),
        Column("date", "date", "Fecha local de la sesión"),
        Column("sessionSeconds", "float", "Segundos entre startedUtc y endedUtc. Incluye narración y traslados"),
        Column("totalSeconds", "float", "Duración de la sesión según el visor. Si no se cerró, llega hasta el "
                                        "último guardado. Vacío en los JSON anteriores al 06/10/2026"),
        Column("challengeSeconds", "float", "Suma de totalSeconds de los escenarios iniciados"),
        Column("scenariosStarted", "int", "Escenarios iniciados (0 a 4)"),
        Column("scenariosCompleted", "int", "Escenarios completados (0 a 4)"),
        Column("completedAll", "flag", "1 si completó los cuatro escenarios"),
    ]
    for meta in SCENARIOS.values():
        prefix, label = f"e{meta.number}_", f"Escenario {meta.number} ({meta.name})"
        columns += [
            Column(prefix + "started", "flag", f"{label}: 1 si llegó a iniciarse"),
            Column(prefix + "completed", "flag", f"{label}: 1 si se completó"),
            Column(prefix + "timedOut", "flag", f"{label}: 1 si la sala agotó su tiempo. Vacío en los JSON que no lo traen"),
            Column(prefix + "totalSeconds", "float", f"{label}: segundos que duró, según el juego"),
            Column(prefix + meta.events_key, "int", f"{label}: número de {meta.events_label.lower()}"),
        ]
        columns += [Column(prefix + c, "int", f"{label}: {COUNTER_DOCS[c]}") for c in meta.counters]
        if meta.events_key == "attempts":
            columns.append(Column(prefix + "thinkSeconds", "float",
                                  f"{label}: suma de durationSeconds, el tiempo pensando sin contar la ejecución"))
        if meta.events_key == "selections":
            columns.append(Column(prefix + "deselections", "int",
                                  f"{label}: opciones que quitó después de marcarlas"))
    return columns


_SESSION_TAIL = (
    Column("issues", "int", "Avisos de integridad de la sesión. El detalle está en la tabla avisos"),
    Column("excluded", "flag", "1 si la sesión está excluida del análisis en el panel"),
    Column("note", "text", "Nota escrita en el panel"),
    Column("participant", "text", "Ficha · Código de participante"),
    Column("moment", "text", "Ficha · Momento de evaluación: inicial o final"),
    Column("help", "text", "Ficha · Ayuda recibida: ninguna, verbal o directa"),
    Column("closure", "text", "Ficha · Motivo de cierre: completada, tiempo, abandono o tecnica"),
    Column("gameVersion", "text", "Ficha · Versión del juego"),
    *(Column(ficha.criterion(key, number), "text",
             f"Ficha · {name}, criterio {number}: 1 se cumple, 0 no se cumple, NO sin evidencia")
      for key, (name, _, _) in ficha.PILLARS.items() for number in (1, 2)),
    *(Column(f"p_{key}_pct", "int",
             f"Ficha · {name}: 0, 50 o 100 si se observaron los dos criterios. No es un porcentaje de dominio")
      for key, (name, _, _) in ficha.PILLARS.items()),
    Column("uploadedLocal", "local", "Fecha del archivo en el servidor (última subida), en hora local"),
)


def sessions_table(runs):
    extras = _extra_columns([r.raw for r in runs], _RUN_KNOWN)
    rows = []
    for run in runs:
        row = _keys(run)
        row.update({
            "difficultyLabel": run.difficulty_label,
            "startedUtc": run.raw.get("startedUtc"),
            "endedUtc": run.raw.get("endedUtc"),
            "startedLocal": _local(run.started_at),
            "date": run.local_date,
            "sessionSeconds": seconds_between(run.started_at, run.ended_at),
            "totalSeconds": as_float(run.raw.get("totalSeconds")),
            "challengeSeconds": run.challenge_seconds,
            "scenariosStarted": run.scenarios_started,
            "scenariosCompleted": run.scenarios_completed,
            "completedAll": run.completed_all,
        })
        for number, scenario in run.scenarios.items():
            prefix, meta = f"e{number}_", scenario.meta
            row[prefix + "started"] = scenario.started
            row[prefix + "completed"] = scenario.completed
            row[prefix + "timedOut"] = scenario.raw.get("timedOut")
            if not scenario.present:
                continue
            row[prefix + "totalSeconds"] = scenario.total_seconds
            row[prefix + meta.events_key] = len(scenario.events)
            for counter in meta.counters:
                row[prefix + counter] = scenario.counter(counter)
            if meta.events_key == "attempts":
                durations = [as_float(e.get("durationSeconds")) for e in scenario.events]
                row[prefix + "thinkSeconds"] = sum(d for d in durations if d is not None)
            if meta.events_key == "selections":
                row[prefix + "deselections"] = sum(1 for e in scenario.events if not is_selected(e))
        _with_extras(row, run.raw, extras)
        row.update({
            "issues": len(run.issues),
            "excluded": run.excluded,
            "note": run.note,
            **{key: run.sheet.get(key, "") for key in ("participant", "moment", "help", "closure", "gameVersion")},
            **{ficha.criterion(key, number): run.sheet.get(ficha.criterion(key, number), "")
               for key in ficha.PILLARS for number in (1, 2)},
            **{f"p_{key}_pct": ficha.pillar_score(run.sheet, key) for key in ficha.PILLARS},
            "uploadedLocal": _local(datetime.fromtimestamp(run.file.mtime, ZONE)),
        })
        rows.append(row)
    return Table(
        "sesiones", "Sesiones",
        "Una fila por sesión, con el resumen de los cuatro escenarios en columnas (e1_ a e4_).",
        (*_session_columns(), *extras, *_SESSION_TAIL), tuple(rows))


# ── Escenarios: una fila por sesión y escenario ───────────────────────────────

def scenarios_table(runs):
    counters = []
    for meta in SCENARIOS.values():
        counters += [c for c in meta.counters if c not in counters]
    records = [s.raw for r in runs for s in r.scenarios.values() if s.present]
    event_keys = {m.events_key for m in SCENARIOS.values()}
    extras = _extra_columns(records, {*_SCENARIO_BASE, *counters, *event_keys})

    columns = (
        *KEYS,
        Column("scenario", "int", "Número de escenario (1 a 4)"),
        Column("scenarioName", "text", "Pilar que trabaja el escenario"),
        Column("started", "flag", "1 si llegó a iniciarse"),
        Column("completed", "flag", "1 si se completó"),
        Column("timedOut", "flag", "1 si la sala agotó su tiempo y la historia pasó a la siguiente. "
                                   "Vacío en los JSON que no lo traen"),
        Column("totalSeconds", "float", "Segundos que duró, según el juego. Incluye la narración de la sala"),
        Column("startedUtc", "utc", "Inicio del escenario (UTC)"),
        Column("endedUtc", "utc", "Fin del escenario (UTC)"),
        Column("clockSeconds", "float", "Segundos de reloj entre startedUtc y endedUtc. "
                                        "Si supera a totalSeconds, el visor estuvo en pausa"),
        Column("eventCount", "int", "Intentos, selecciones o colocaciones registrados, según el escenario"),
        *(Column(c, "int", COUNTER_DOCS[c][0].upper() + COUNTER_DOCS[c][1:] + ". Vacío donde no aplica")
          for c in counters),
        *extras,
    )
    rows = []
    for run in runs:
        for number, scenario in run.scenarios.items():
            row = _keys(run)
            row.update({
                "scenario": number,
                "scenarioName": scenario.meta.name,
                "started": scenario.started,
                "completed": scenario.completed,
                "timedOut": scenario.raw.get("timedOut"),
            })
            if scenario.present:
                row.update({
                    "totalSeconds": scenario.total_seconds,
                    "startedUtc": scenario.raw.get("startedUtc"),
                    "endedUtc": scenario.raw.get("endedUtc"),
                    "clockSeconds": scenario.clock_seconds,
                    "eventCount": len(scenario.events),
                })
                for counter in scenario.meta.counters:
                    row[counter] = scenario.counter(counter)
                _with_extras(row, scenario.raw, extras)
            rows.append(row)
    return Table(
        "escenarios", "Escenarios",
        "Una fila por sesión y escenario: la misma información que sesiones, en formato largo.",
        columns, tuple(rows))


# ── Eventos de cada escenario ─────────────────────────────────────────────────

def _scenario_events(runs, events_key):
    for run in runs:
        for scenario in run.scenarios.values():
            if scenario.meta.events_key == events_key:
                for index, event in enumerate(scenario.events, start=1):
                    yield run, scenario, index, event


def attempts_table(runs):
    found = list(_scenario_events(runs, "attempts"))
    extras = _extra_columns([e for _, _, _, e in found], _ATTEMPT_KNOWN)
    columns = (
        *KEYS,
        Column("scenario", "int", "Escenario del intento: 1 (secuencialidad) o 3 (bucles)"),
        Column("scenarioName", "text", "Pilar que trabaja el escenario"),
        Column("attempt", "int", "Número de intento dentro del escenario, desde 1"),
        Column("attemptDifficulty", "int", "Dificultad que el juego anotó en el intento (solo en los JSON "
                                           "anteriores al 06/10/2026)"),
        Column("sequence", "text", f"Bloques del programa en orden, separados por '{SEQUENCE_SEPARATOR.strip()}'"),
        Column("sequenceLength", "int", "Número de bloques de la secuencia"),
        Column("repetitions", "int", "Repeticiones del bucle. Solo en el escenario 3"),
        Column("itemType", "text", "Ficha de tipo puesta (Barril o Caja). Solo en el escenario 3"),
        Column("solved", "flag", "1 si este intento completó el escenario. En el escenario 3 hacen falta "
                                 "varias pasadas, y solo la última lleva un 1"),
        Column("durationSeconds", "float", "Segundos pensando antes de ejecutar. No incluye la ejecución"),
        Column("timestamp", "utc", "Momento en que pulsó ejecutar (UTC)"),
        Column("secondsFromScenarioStart", "float", "Segundos desde el inicio del escenario"),
        *extras,
    )
    rows = []
    for run, scenario, index, event in found:
        blocks = _sequence(event)
        row = _keys(run)
        row.update({
            "scenario": scenario.number,
            "scenarioName": scenario.meta.name,
            "attempt": index,
            "attemptDifficulty": as_int(event.get("difficulty")),
            "sequence": SEQUENCE_SEPARATOR.join(blocks),
            "sequenceLength": len(blocks),
            "repetitions": as_int(event.get("repetitions")),
            "itemType": event.get("itemType"),
            "solved": as_flag(event.get("solved")),
            "durationSeconds": as_float(event.get("durationSeconds")),
            "timestamp": event.get("timestamp"),
            "secondsFromScenarioStart": scenario.offset(event),
        })
        rows.append(_with_extras(row, event, extras))
    return Table(
        "intentos", "Intentos",
        "Una fila por cada vez que pulsó ejecutar en los escenarios 1 y 3.",
        columns, tuple(rows))


def blocks_table(runs):
    columns = (
        *KEYS,
        Column("scenario", "int", "Escenario del intento: 1 o 3"),
        Column("attempt", "int", "Número de intento dentro del escenario"),
        Column("position", "int", "Posición del bloque en la secuencia, desde 1"),
        Column("block", "text", "Etiqueta del bloque"),
    )
    rows = []
    for run, scenario, index, event in _scenario_events(runs, "attempts"):
        for position, block in enumerate(_sequence(event), start=1):
            row = _keys(run)
            row.update({"scenario": scenario.number, "attempt": index, "position": position, "block": block})
            rows.append(row)
    return Table(
        "bloques", "Bloques",
        "Las secuencias de intentos desplegadas: una fila por bloque, para analizar el orden.",
        columns, tuple(rows))


def selections_table(runs):
    found = list(_scenario_events(runs, "selections"))
    extras = _extra_columns([e for _, _, _, e in found], _SELECTION_KNOWN)
    columns = (
        *KEYS,
        Column("order", "int", "Orden de la pulsación dentro del escenario, desde 1"),
        Column("module", "text", "Módulo averiado: motores, generadores o enfriamiento"),
        Column("option", "text", "Texto de la opción pulsada"),
        Column("selected", "flag", "1 si la marcó, 0 si la quitó. Desde el 06/10/2026 solo se registran las "
                                   "que marcan: siempre 1"),
        Column("correct", "flag", "1 si la opción es una de las correctas del módulo"),
        Column("durationSeconds", "float", "Segundos desde la selección anterior (o desde el inicio del "
                                           "escenario). Vacío en los JSON anteriores al 06/10/2026"),
        Column("timestamp", "utc", "Momento de la pulsación (UTC)"),
        Column("secondsFromScenarioStart", "float", "Segundos desde el inicio del escenario"),
        *extras,
    )
    rows = []
    for run, scenario, index, event in found:
        row = _keys(run)
        row.update({
            "order": index,
            "module": event.get("module"),
            "option": event.get("option"),
            "selected": is_selected(event),
            "correct": as_flag(event.get("correct")),
            "durationSeconds": as_float(event.get("durationSeconds")),
            "timestamp": event.get("timestamp"),
            "secondsFromScenarioStart": scenario.offset(event),
        })
        rows.append(_with_extras(row, event, extras))
    return Table(
        "selecciones", "Selecciones",
        "Una fila por cada pulsación de opción en el escenario 2, incluidas las que quitan una opción.",
        columns, tuple(rows))


def placements_table(runs):
    found = list(_scenario_events(runs, "placements"))
    extras = _extra_columns([e for _, _, _, e in found], _PLACEMENT_KNOWN)
    columns = (
        *KEYS,
        Column("order", "int", "Orden de la colocación dentro del escenario, desde 1"),
        Column("socket", "text", "Figura que esperaba el hueco"),
        Column("chip", "text", "Figura de la ficha colocada"),
        Column("correct", "flag", "1 si la ficha era la del hueco"),
        Column("durationSeconds", "float", "Segundos desde la colocación anterior (o desde el inicio del "
                                           "escenario). Vacío en los JSON anteriores al 06/10/2026"),
        Column("timestamp", "utc", "Momento de la colocación (UTC)"),
        Column("secondsFromScenarioStart", "float", "Segundos desde el inicio del escenario"),
        *extras,
    )
    rows = []
    for run, scenario, index, event in found:
        row = _keys(run)
        row.update({
            "order": index,
            "socket": event.get("socket"),
            "chip": event.get("chip"),
            "correct": as_flag(event.get("correct")),
            "durationSeconds": as_float(event.get("durationSeconds")),
            "timestamp": event.get("timestamp"),
            "secondsFromScenarioStart": scenario.offset(event),
        })
        rows.append(_with_extras(row, event, extras))
    return Table(
        "colocaciones", "Colocaciones",
        "Una fila por cada ficha encajada en un hueco en el escenario 4.",
        columns, tuple(rows))


# ── Línea de tiempo ───────────────────────────────────────────────────────────

def _describe_attempt(event):
    detail = SEQUENCE_SEPARATOR.join(_sequence(event)) or "(vacía)"
    repetitions = as_int(event.get("repetitions"))
    if repetitions is not None:
        detail += f" ×{repetitions}"
    if event.get("itemType"):
        detail += f" [{event['itemType']}]"
    return detail


def run_events(run):
    """Todo lo que pasó en la sesión, en orden cronológico."""
    events = []

    def add(stamp, scenario, kind, detail="", result=None):
        events.append(Event(parse_utc(stamp), stamp if isinstance(stamp, str) else "",
                            scenario, kind, detail, result))

    if run.started_at:
        add(run.raw.get("startedUtc"), None, "inicio_sesion")
    for number, scenario in run.scenarios.items():
        if scenario.started_at:
            add(scenario.raw.get("startedUtc"), number, "inicio_escenario", scenario.meta.name)
        for event in scenario.events:
            stamp = event.get("timestamp")
            if scenario.meta.events_key == "attempts":
                add(stamp, number, "intento", _describe_attempt(event), as_flag(event.get("solved")))
            elif scenario.meta.events_key == "selections":
                kind = "seleccion" if is_selected(event) else "deseleccion"
                add(stamp, number, kind, f"{event.get('module')}: {event.get('option')}",
                    as_flag(event.get("correct")))
            else:
                add(stamp, number, "colocacion", f"{event.get('chip')} → {event.get('socket')}",
                    as_flag(event.get("correct")))
        if scenario.ended_at:
            add(scenario.raw.get("endedUtc"), number, "fin_escenario", scenario.meta.name, scenario.completed)
    if run.ended_at:
        add(run.raw.get("endedUtc"), None, "fin_sesion")

    # sorted es estable: lo que comparte instante conserva el orden en que se registró
    return sorted(events, key=lambda e: (e.at is None, e.at or datetime.min))


def events_table(runs):
    columns = (
        *KEYS,
        Column("order", "int", "Orden del evento dentro de la sesión, desde 1"),
        Column("timestamp", "utc", "Momento del evento (UTC)"),
        Column("secondsFromSessionStart", "float", "Segundos desde el inicio de la sesión"),
        Column("scenario", "int", "Escenario del evento. Vacío en el inicio y el fin de la sesión"),
        Column("event", "text", "inicio_sesion, inicio_escenario, intento, seleccion, deseleccion, "
                                "colocacion, fin_escenario o fin_sesion"),
        Column("detail", "text", "Secuencia del intento, módulo y opción, o ficha → hueco"),
        Column("result", "flag", "1 si resolvió, era correcta o completó el escenario. Vacío donde no aplica"),
    )
    rows = []
    for run in runs:
        for index, event in enumerate(run_events(run), start=1):
            row = _keys(run)
            row.update({
                "order": index,
                "timestamp": event.stamp,
                "secondsFromSessionStart": seconds_between(run.started_at, event.at),
                "scenario": event.scenario,
                "event": event.kind,
                "detail": event.detail,
                "result": event.result,
            })
            rows.append(row)
    return Table(
        "eventos", "Eventos",
        "La línea de tiempo de cada sesión: todos los eventos de los cuatro escenarios, en orden.",
        columns, tuple(rows))


# ── Avisos y diccionario ──────────────────────────────────────────────────────

def issues_table(runs):
    columns = (
        *KEYS,
        Column("scenario", "int", "Escenario afectado. Vacío si el aviso es de la sesión entera"),
        Column("code", "text", "Tipo de aviso"),
        Column("message", "text", "Explicación del aviso"),
    )
    rows = []
    for run in runs:
        for issue in run.issues:
            row = _keys(run)
            row.update({"scenario": issue.scenario, "code": issue.code, "message": issue.message})
            rows.append(row)
    return Table(
        "avisos", "Avisos",
        "Lo que huele a dato mal capturado: contadores que no cuadran, retos abiertos tarde, duplicados.",
        columns, tuple(rows))


def dictionary_table(tables):
    columns = (
        Column("table", "text", "Tabla"),
        Column("column", "text", "Columna"),
        Column("type", "text", "Tipo de dato"),
        Column("description", "text", "Qué mide"),
    )
    kinds = {"text": "texto", "int": "entero", "float": "decimal", "flag": "0/1",
             "utc": "fecha y hora UTC (ISO 8601)", "local": "fecha y hora local", "date": "fecha local"}
    rows = [{"table": t.name, "column": c.name, "type": kinds[c.kind], "description": c.description}
            for t in tables for c in t.columns]
    return Table("diccionario", "Diccionario", "Qué significa cada columna de cada tabla.",
                 columns, tuple(rows))


BUILDERS = (sessions_table, scenarios_table, attempts_table, blocks_table,
            selections_table, placements_table, events_table, issues_table)


def build_tables(runs):
    """Todas las tablas del recorte, con el diccionario al final."""
    from .metrics import analysis_table  # metrics depende de este módulo

    tables = [analysis_table(runs), *(build(runs) for build in BUILDERS)]
    return [*tables, dictionary_table(tables)]
