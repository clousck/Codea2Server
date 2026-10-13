"""Métricas del estudio: dos comunes y tres por escenario.

Siguen el documento «Métricas por escenario de CODEA2» del 09/10/2026. Las reglas que
importan están aquí y no en las plantillas:

- La unidad es una sesión en un escenario. Las dificultades no se mezclan nunca.
- Un valor que no se puede calcular queda en None («sin dato»), nunca en cero.
- Cada porcentaje conserva su numerador y su denominador.
- En el escenario 3 no hay tasa de fallos: solved = false es una pasada intermedia, no un error.

El documento se escribió con el formato de JSON anterior al 06/10/2026. Con el actual, E1C
son choques y usos inválidos, y F ya no se puede contrastar con wrongSelections ni
wrongPlacements, que el visor dejó de mandar.
"""

from collections import Counter, defaultdict

from . import sheet as ficha
from .model import SCENARIOS, as_int, is_selected
from .stats import describe

# Nombre y pilares de cada escenario, tal como los llama el documento
TITLES = {
    1: ("Robot y puerta", "Pensamiento algorítmico y descomposición"),
    2: ("Reparación de la nave", "Abstracción y descomposición"),
    3: ("Brazo robótico", "Pensamiento algorítmico y reconocimiento de patrones"),
    4: ("Chips y receptáculos", "Reconocimiento de patrones y abstracción"),
}

# Avisos que ponen en duda el cronómetro de un escenario
_TIME_ISSUES = {"evento_antes", "evento_despues", "tiempo_distinto"}

# El escenario 2 tiene siempre los mismos tres módulos
_MODULES = 3


def _outcome(event, key):
    """True o False si el evento trae un resultado evaluable; None si no."""
    value = event.get(key)
    if isinstance(value, bool):
        return value
    return bool(value) if value in (0, 1) else None


def _percent(part, whole):
    return 100 * part / whole if whole else None


def _first(outcomes):
    """Posición (desde 1) del primer acierto, o None."""
    return next((i for i, ok in enumerate(outcomes, start=1) if ok), None)


def _first_by(events, group_key):
    """El resultado de la primera decisión evaluable de cada módulo o receptáculo."""
    first = {}
    for event in events:
        ok = _outcome(event, "correct")
        if ok is not None:
            first.setdefault(str(event.get(group_key)), ok)
    return first


def scenario_metrics(run, number):
    """Las métricas de una sesión en un escenario. Lo que no aplica o no se puede calcular, None."""
    scenario = run.scenarios[number]
    closure = run.sheet.get("closure", "")
    row = dict.fromkeys(("G", "N", "F", "PF", "K", "A", "M", "P1", "C", "pairs", "pairsExcluded",
                         "unsolved", "seconds"))
    row.update(run=run, number=number, started=scenario.started, gWhy="", timeWhy="",
               timedOut=scenario.timed_out if "timedOut" in scenario.raw else None)

    # MC1 · logro final
    if not scenario.started:
        row["gWhy"] = "no iniciado"
    elif scenario.completed:
        row["G"] = 1
    elif scenario.timed_out:
        # El propio juego cerró la sala por tiempo: es un resultado final, no un registro a medias
        row["G"] = 0
    elif closure == "tecnica":
        row["gWhy"] = "interrupción técnica"
    elif run.ended_at or closure in ("tiempo", "abandono"):
        row["G"] = 0
    else:
        row["gWhy"] = "sin cierre confirmado"

    # MC2 · tiempo registrado, solo con el cronómetro sin avisos
    codes = {issue.code for issue in run.issues if issue.scenario == number}
    if not scenario.started:
        row["timeWhy"] = "no iniciado"
    elif not scenario.completed:
        row["timeWhy"] = "tiempo agotado" if scenario.timed_out else "no completado"
    elif not scenario.total_seconds:
        row["timeWhy"] = "sin tiempo registrado"
    elif codes & _TIME_ISSUES:
        row["timeWhy"] = "cronómetro sin validar"
    else:
        row["seconds"] = scenario.total_seconds

    for key in ("failedAttempts", "errorCollisionBot", "errorInvalidUse", "errorInvalidCommand"):
        row[key] = as_int(scenario.raw.get(key)) if key in scenario.meta.counters else None
    if not scenario.started:
        return row

    events = scenario.events
    if scenario.meta.events_key == "attempts":
        solved = [ok for ok in (_outcome(e, "solved") for e in events) if ok is not None]
        row["N"] = len(solved)
        row["K"] = _first(solved)
        if number == 1:
            row["F"] = solved.count(False)
            row["PF"] = _percent(row["F"], row["N"])
        else:
            row["unsolved"] = solved.count(False)
            row["C"], row["pairs"], row["pairsExcluded"] = _plan_changes(events)
    else:
        if number == 2:
            events = [e for e in events if is_selected(e)]
        outcomes = [ok for ok in (_outcome(e, "correct") for e in events) if ok is not None]
        first = _first_by(events, "module" if number == 2 else "socket")
        row["N"] = len(outcomes)
        row["F"] = outcomes.count(False)
        row["PF"] = _percent(row["F"], row["N"])
        row["M"] = len(first)
        row["A"] = sum(first.values())
        row["P1"] = _percent(row["A"], row["M"])
    return row


def _plan(event):
    """Secuencia, repeticiones y objeto de una ejecución, o None si falta alguno."""
    sequence, repetitions = event.get("sequence"), as_int(event.get("repetitions"))
    item = str(event.get("itemType") or "").strip()
    if not isinstance(sequence, list) or not sequence or repetitions is None or not item:
        return None
    return tuple(sequence), repetitions, item


def _plan_changes(events):
    """E3B: (cambios, pares evaluables, pares excluidos) entre ejecuciones consecutivas."""
    plans = [_plan(e) for e in events]
    pairs = list(zip(plans, plans[1:]))
    evaluable = [(a, b) for a, b in pairs if a is not None and b is not None]
    changes = sum(1 for a, b in evaluable if a != b) if evaluable else None
    return changes, len(evaluable), len(pairs) - len(evaluable)


# ── Resumen de un grupo ───────────────────────────────────────────────────────

def _num(value, decimals=1):
    if value is None:
        return "sin dato"
    return f"{value:.{decimals}f}".replace(".", ",")


def _count(value):
    """Un conteo o su mediana: sin decimales salvo que caiga entre dos enteros."""
    if value is None:
        return "sin dato"
    return _num(value, 0 if float(value).is_integer() else 1)


def _pct(value):
    return "sin dato" if value is None else f"{_num(value)}\u00a0%"


def _spread(stats, fmt=_count, unit=""):
    if not stats["n"]:
        return "sin datos"
    return f"mín {fmt(stats['min'])}{unit} · máx {fmt(stats['max'])}{unit} · n = {stats['n']}"


def _card(code, name, value, note, hint, lines=(), ratio=None):
    return {"code": code, "name": name, "value": value, "note": note, "hint": hint,
            "lines": list(lines), "ratio": ratio}


def _counter_line(rows, key, label):
    stats = describe(r[key] for r in rows)
    if not stats["n"]:
        return label, "sin dato"
    return label, f"mediana {_count(stats['median'])} · mín {stats['min']} · máx {stats['max']} · total {stats['total']}"


def _rate_card(code, name, rows, hint, what):
    """Porcentaje de error: promedio de los porcentajes de cada sesión, con el global al lado."""
    rates = describe(r["PF"] for r in rows)
    wrong = sum(r["F"] or 0 for r in rows if r["PF"] is not None)
    total = sum(r["N"] or 0 for r in rows if r["PF"] is not None)
    return _card(code, name, _pct(rates["mean"]),
                 f"promedio de {rates['n']} {'sesión' if rates['n'] == 1 else 'sesiones'}", hint,
                 [("Global", f"{wrong} de {total} {what} = {_pct(_percent(wrong, total))}"),
                  ("Por sesión", _spread(rates, _num, "\u00a0%"))])


def _first_card(code, name, rows, hint, units, required):
    rates = describe(r["P1"] for r in rows)
    right = sum(r["A"] or 0 for r in rows if r["P1"] is not None)
    seen = sum(r["M"] or 0 for r in rows if r["P1"] is not None)
    coverage = describe(r["M"] for r in rows if r["M"] is not None)
    cover = "sin dato" if not coverage["n"] else (
        f"mediana {_count(coverage['median'])}" + (f" de {required} {units}" if required else f" {units}"))
    return _card(code, name, _pct(rates["mean"]),
                 f"promedio de {rates['n']} {'sesión' if rates['n'] == 1 else 'sesiones'}", hint,
                 [("Global", f"{right} de {seen} {units} = {_pct(_percent(right, seen))}"),
                  ("Cobertura", cover)])


def _breakdown(runs, number, group_key):
    """Por módulo o receptáculo: decisiones, errores y primer acierto, sumando las sesiones."""
    groups = defaultdict(lambda: {"sessions": 0, "N": 0, "F": 0, "A": 0})
    for run in runs:
        scenario = run.scenarios[number]
        if not scenario.started:
            continue
        events = [e for e in scenario.events if number != 2 or is_selected(e)]
        for event in events:
            ok = _outcome(event, "correct")
            if ok is not None:
                group = groups[str(event.get(group_key))]
                group["N"] += 1
                group["F"] += not ok
        for name, ok in _first_by(events, group_key).items():
            groups[name]["sessions"] += 1
            groups[name]["A"] += ok
    return [{"name": name, **g, "PF": _percent(g["F"], g["N"]), "P1": _percent(g["A"], g["sessions"])}
            for name, g in sorted(groups.items())]


def _required_sockets(rows):
    """Receptáculos del nivel: los que resolvió quien lo completó. None si nadie lo completó aún."""
    solved = [r["M"] for r in rows if r["G"] == 1 and r["M"]]
    return max(solved) if solved else None


def scenario_summary(runs, number):
    meta = SCENARIOS[number]
    rows = [scenario_metrics(run, number) for run in runs]
    evaluable = [r for r in rows if r["G"] is not None]
    done = sum(r["G"] for r in evaluable)
    excluded = Counter(r["gWhy"] for r in rows if r["G"] is None)
    times = describe(r["seconds"] for r in rows)
    untimed = Counter(r["timeWhy"] for r in rows if r["seconds"] is None and r["timeWhy"] != "no iniciado")

    cards = [
        _card("MC1", "Logro final", _pct(_percent(done, len(evaluable))),
              f"{done} de {len(evaluable)} {'sesión evaluable' if len(evaluable) == 1 else 'sesiones evaluables'}",
              "Escenarios completados entre sesiones con resultado final válido. Una sala que agota "
              "su tiempo cuenta como no completada. No entran los no iniciados ni las interrupciones "
              "técnicas sin resultado confirmado.",
              [("Tiempo agotado", f"{sum(1 for r in rows if r['timedOut'])} de {len(evaluable)}"),
               ("Excluidas", ", ".join(f"{n} {why}" for why, n in excluded.items()) or "ninguna")],
              ratio=done / len(evaluable) if evaluable else None),
        _card("MC2", "Tiempo registrado", f"{_num(times['median'])}\u00a0s" if times["n"] else "sin dato",
              "mediana de quienes lo completaron",
              "totalSeconds del escenario, tal como lo registra la aplicación. No es tiempo activo ni "
              "de razonamiento. Solo entran los escenarios completados con el cronómetro sin avisos.",
              [("En minutos", f"{_num(times['median'] / 60, 2)}\u00a0min" if times["n"] else "sin dato"),
               ("Rango", _spread(times, _num, "\u00a0s")),
               ("Sin validar", ", ".join(f"{n} {why}" for why, n in untimed.items()) or "ninguno")]),
    ]

    started = [r for r in rows if r["started"]]
    firsts = describe(r["K"] for r in started)
    totals = describe(r["N"] for r in started)
    unresolved = sum(1 for r in started if r["K"] is None)
    breakdown, group_label = [], ""

    if number == 1:
        cards += [
            _card("E1A", "Intentos hasta la primera resolución", _count(firsts["median"]),
                  f"mediana de K en {firsts['n']} con resolución",
                  "K es la posición del primer intento con solved = true. Quien no lo resuelve queda "
                  "sin K: no se le asigna cero.",
                  [("Promedio de K", _num(firsts["mean"])), ("Rango de K", _spread(firsts)),
                   ("Sin resolución", f"{unresolved} de {len(started)}"),
                   ("Intentos N", f"mediana {_count(totals['median'])}")]),
            _rate_card("E1B", "Intentos fallidos", started,
                       "F son los intentos con solved = false y N todos los intentos con resultado. "
                       "Describe el proceso; no es una calificación.", "intentos"),
            _card("E1C", "Errores por tipo", "", "contadores de la aplicación, por separado",
                  "No se suman entre sí ni con F: un intento puede disparar varios. Desde el 06/10/2026 "
                  "son choques y usos inválidos; el formato anterior traía tres contadores.",
                  [_counter_line(started, "errorCollisionBot", "Choques"),
                   _counter_line(started, "errorInvalidUse", "Usos inválidos"),
                   _counter_line(started, "failedAttempts", "failedAttempts")]),
        ]
    elif number == 3:
        changes = describe(r["C"] for r in started)
        cards += [
            _card("E3A", "Ejecuciones hasta la primera resolución", _count(firsts["median"]),
                  f"mediana de K en {firsts['n']} con resolución",
                  "Una ejecución con solved = false es una ejecución sin resolución registrada, no un "
                  "fallo: el reto pide al menos dos pasadas, una por tipo de objeto.",
                  [("Promedio de K", _num(firsts["mean"])), ("Rango de K", _spread(firsts)),
                   ("Sin resolución", f"{unresolved} de {len(started)}"),
                   ("Ejecuciones N", f"mediana {_count(totals['median'])}")]),
            _card("E3B", "Cambios del plan", _count(changes["median"]),
                  f"mediana de C en {changes['n']} con pares evaluables",
                  "Pares de ejecuciones consecutivas en los que cambia la secuencia, las repeticiones "
                  "o el objeto. Más cambios no significan mejor depuración.",
                  [("Rango de C", _spread(changes)),
                   ("Pares evaluables", str(sum(r["pairs"] or 0 for r in started))),
                   ("Pares excluidos", str(sum(r["pairsExcluded"] or 0 for r in started)))]),
            _card("E3C", "Errores reportados", "", "contadores de la aplicación, por separado",
                  "failedAttempts solo cuenta la pasada que no clasificó nada. No se calcula una tasa "
                  "de fallos de este escenario.",
                  [_counter_line(started, "failedAttempts", "failedAttempts"),
                   _counter_line(started, "errorInvalidCommand", "Comandos inválidos")]),
        ]
    else:
        code, thing, things, units, group_key = (
            ("E2", "Decisiones", "selecciones", "módulos", "module") if number == 2
            else ("E4", "Colocaciones", "colocaciones", "receptáculos", "socket"))
        required = _MODULES if number == 2 else _required_sockets(rows)
        cards += [
            _card(code + "A", f"{thing} evaluadas", _count(totals["median"]),
                  f"mediana de N en {totals['n']} {'sesión' if totals['n'] == 1 else 'sesiones'}",
                  "Cada selección que marca una opción cuenta una vez, aunque repita la misma."
                  if number == 2 else
                  "Cada ficha encajada en un hueco. Agarrar una ficha no es una colocación.",
                  [("Rango de N", _spread(totals)), ("Total", f"{totals['total'] or 0} {things}")]),
            _rate_card(code + "B", f"{thing} incorrectas", started,
                       f"F son las {things} con correct = false y N todas las evaluables.", things),
            _first_card(code + "C", "Primer acierto", started,
                        f"{units.capitalize()} cuya primera decisión fue correcta, entre los que tuvieron "
                        "una primera decisión. Lo que se acierta después de corregir no cuenta.",
                        units, required),
        ]
        breakdown = _breakdown(runs, number, group_key)
        group_label = "Módulo" if number == 2 else "Receptáculo"

    return {
        "meta": meta,
        "title": TITLES[number][0],
        "pillars": TITLES[number][1],
        "sessions": len(rows),
        "cards": cards,
        "breakdown": breakdown,
        "group_label": group_label,
        "rows": [r for r in rows if r["started"]],
    }


def pillar_summary(runs):
    """Sección 7: cuántas sesiones tienen los dos criterios de cada pilar y qué puntuación dan."""
    rows = []
    for key, (name, first, second) in ficha.PILLARS.items():
        scores = [s for s in (ficha.pillar_score(run.sheet, key) for run in runs) if s is not None]
        rows.append({"name": name, "criteria": (first, second), "n": len(scores),
                     "mean": sum(scores) / len(scores) if scores else None,
                     "spread": [scores.count(value) for value in (0, 50, 100)]})
    return rows


def with_sheet(runs):
    return sum(1 for run in runs if any(run.sheet.get(key) for key in ("participant", "moment", "closure", "help")))


# ── Tabla de análisis (sección 9.1) ───────────────────────────────────────────

def analysis_table(runs):
    """Una fila por sesión y escenario, con las métricas y lo que hace falta para auditarlas."""
    from .tables import KEYS, Column, Table, _keys

    columns = (
        *KEYS,
        Column("participant", "text", "Código de participante, de la ficha de sesión"),
        Column("moment", "text", "Momento de evaluación (inicial o final), de la ficha"),
        Column("help", "text", "Ayuda recibida, de la ficha"),
        Column("closure", "text", "Motivo de cierre, de la ficha"),
        Column("gameVersion", "text", "Versión del juego, de la ficha"),
        Column("scenario", "int", "Número de escenario (1 a 4)"),
        Column("scenarioName", "text", "Nombre del escenario en el documento de métricas"),
        Column("G", "flag", "MC1 · Logro final: 1 completado, 0 no completado. Vacío si no es evaluable"),
        Column("timedOut", "flag", "1 si la sala agotó su tiempo y la historia pasó a la siguiente. Vacío en los JSON que no lo traen"),
        Column("G_excluded", "text", "Por qué G no es evaluable: no iniciado, interrupción técnica o sin cierre confirmado"),
        Column("totalSeconds", "float", "MC2 · Tiempo registrado por la aplicación, solo si se completó y su cronómetro no tiene avisos"),
        Column("time_excluded", "text", "Por qué el tiempo no entra en MC2"),
        Column("N", "int", "Eventos evaluables: intentos (E1), selecciones (E2), ejecuciones (E3) o colocaciones (E4)"),
        Column("F", "int", "Eventos incorrectos. Vacío en el escenario 3, donde no está definido"),
        Column("errorPct", "float", "100 × F / N. Vacío si N es cero o en el escenario 3"),
        Column("K", "int", "Posición del primer intento o ejecución con solved = true (E1 y E3). Vacío si no hubo"),
        Column("unsolved", "int", "E3 · Ejecuciones sin resolución registrada. No son fallos"),
        Column("firstCorrect", "int", "A · Módulos o receptáculos acertados en la primera decisión (E2 y E4)"),
        Column("firstObserved", "int", "M · Módulos o receptáculos con una primera decisión evaluable (E2 y E4)"),
        Column("firstPct", "float", "100 × A / M"),
        Column("planChanges", "int", "E3B · Pares de ejecuciones consecutivas en los que cambió el plan"),
        Column("pairsEvaluable", "int", "E3B · Pares de ejecuciones consecutivas comparables"),
        Column("pairsExcluded", "int", "E3B · Pares que no se pudieron comparar por faltar un dato"),
        Column("failedAttempts", "int", "Contador de la aplicación (E1 y E3)"),
        Column("errorCollisionBot", "int", "E1C · Choques"),
        Column("errorInvalidUse", "int", "E1C · Usos inválidos"),
        Column("errorInvalidCommand", "int", "E3C · Comandos inválidos"),
        Column("issues", "text", "Avisos de integridad de este escenario en esta sesión"),
    )
    rows = []
    for run in runs:
        for number in SCENARIOS:
            m = scenario_metrics(run, number)
            row = _keys(run)
            row.update({key: run.sheet.get(key, "") for key in ("participant", "moment", "help", "closure", "gameVersion")})
            row.update({
                "scenario": number, "scenarioName": TITLES[number][0],
                "G": m["G"], "timedOut": m["timedOut"], "G_excluded": m["gWhy"],
                "totalSeconds": m["seconds"], "time_excluded": m["timeWhy"] if m["seconds"] is None else "",
                "N": m["N"], "F": m["F"], "errorPct": m["PF"], "K": m["K"], "unsolved": m["unsolved"],
                "firstCorrect": m["A"], "firstObserved": m["M"], "firstPct": m["P1"],
                "planChanges": m["C"], "pairsEvaluable": m["pairs"], "pairsExcluded": m["pairsExcluded"],
                "failedAttempts": m["failedAttempts"], "errorCollisionBot": m["errorCollisionBot"],
                "errorInvalidUse": m["errorInvalidUse"], "errorInvalidCommand": m["errorInvalidCommand"],
                "issues": " ".join(sorted({i.code for i in run.issues if i.scenario == number})),
            })
            rows.append(row)
    return Table(
        "analisis", "Análisis",
        "La tabla del estudio: una fila por sesión y escenario con las métricas del documento del 09/10/2026.",
        columns, tuple(rows))
