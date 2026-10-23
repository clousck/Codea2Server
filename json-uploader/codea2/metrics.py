"""Métricas del estudio: dos comunes, tres por escenario y el perfil de pilares de cada actividad.

Siguen el documento «Métricas por escenario de CODEA2» del 19/10/2026. Las reglas que
importan están aquí y no en las plantillas:

- La unidad es una sesión en un escenario. Las dificultades no se mezclan nunca.
- Un valor que no se puede calcular queda en None («sin dato»), nunca en cero.
- Cada porcentaje conserva su numerador y su denominador.
- En el escenario 3 no hay tasa de fallos: solved = false es una pasada intermedia, no un error.
- E1P a E4P salen de la ficha, no del JSON: dos criterios por dimensión y actividad, y un
  porcentaje (0, 50 o 100) solo cuando los dos se evaluaron. Nunca se suman en una nota global.

El documento nombra campos del formato anterior al 06/10/2026. Con el actual (22/10/2026), E1C
son choques y usos inválidos (la secuencia incompleta queda en attempts), E3C es failedAttempts
y comandos inválidos, F se cuenta de la lista porque wrongSelections y wrongPlacements ya no
vienen, y el escenario 2 trae además sus pruebas (Probar) en attempts. solutionPercent no es
métrica del documento: se enseña como contexto de E1A y E3A.
"""

from collections import Counter, defaultdict

from . import sheet as ficha
from .model import SCENARIOS, as_flag, as_int, is_selected, solution_percent
from .solutions import SOLUTIONS, compare
from .stats import describe

# Nombre y pilares de cada escenario, tal como los relaciona la tabla 1.1 del documento
TITLES = {
    1: ("Robot y puerta", "Pensamiento algorítmico; descomposición si explica qué parte del plan corrigió"),
    2: ("Reparación de la nave", "Toma de decisiones y descomposición; patrones si aplica la regla a otro módulo"),
    3: ("Brazo robótico", "Pensamiento algorítmico; patrones si explica cómo adaptó la secuencia o la repetición"),
    4: ("Chips y receptáculos", "Reconocimiento de patrones y toma de decisiones"),
}

# Avisos que ponen en duda el cronómetro de un escenario
_TIME_ISSUES = {
    "evento_antes": "hay un evento anterior al inicio del reto",
    "evento_despues": "hay un evento posterior al fin del reto",
    "tiempo_distinto": "totalSeconds no coincide con el reloj",
}

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
                         "unsolved", "seconds", "recorded", "S1", "Smean", "Sbest", "Sn", "tries", "failedTries",
                         "I1missing", "I1extra", "I1order", "Imissing", "Iextra", "Iorder", "In"))
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
    # Lo que registró la aplicación se enseña siempre; a MC2 solo pasa si es fiable
    row["recorded"] = scenario.total_seconds if scenario.started else None
    if not scenario.started:
        row["timeWhy"] = "no iniciado"
    elif not scenario.completed:
        row["timeWhy"] = "tiempo agotado" if scenario.timed_out else "no completado"
    elif not scenario.total_seconds:
        row["timeWhy"] = "sin tiempo registrado"
    elif codes & _TIME_ISSUES.keys():
        row["timeWhy"] = "sin validar: " + "; ".join(why for code, why in _TIME_ISSUES.items() if code in codes)
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
        # Contexto, no métrica del documento: lo cerca que quedó el primer intento de la solución.
        # En el escenario 1 se usa la cuenta del panel sobre la clave: la del visor falló (22/10/2026)
        percent = (lambda e: _key_percent(e, run.difficulty)) if number == 1 else solution_percent
        row["S1"] = next((v for v in (percent(e) for e in events if _outcome(e, "solved") is not None)), None)
        if number == 1:
            # E1S: cercanía de los intentos que no resolvieron (el que resuelve vale 100)
            failed = [percent(e) for e in events if _outcome(e, "solved") is False]
            failed = [v for v in failed if v is not None]
            row["Sn"] = len(failed)
            row["Smean"] = sum(failed) / len(failed) if failed else None
            row["Sbest"] = max(failed) if failed else None
            # E1I: número y orden de instrucciones frente a la clave de soluciones
            keyed = [(compare(e.get("sequence"), run.difficulty), _outcome(e, "solved")) for e in events]
            keyed = [(k, ok) for k, ok in keyed if k is not None and ok is not None]
            if keyed:
                first = keyed[0][0]
                row.update(I1missing=first["missing"], I1extra=first["extra"], I1order=first["orderPct"])
            wrong = [k for k, ok in keyed if not ok]
            if wrong:
                orders = [k["orderPct"] for k in wrong if k["orderPct"] is not None]
                row.update(In=len(wrong), Imissing=sum(k["missing"] for k in wrong) / len(wrong),
                           Iextra=sum(k["extra"] for k in wrong) / len(wrong),
                           Iorder=sum(orders) / len(orders) if orders else None)
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
        if scenario.has_tries:
            row["tries"] = len(scenario.tries)
            row["failedTries"] = sum(1 for e in scenario.tries if not as_flag(e.get("solved")))
    return row


def _key_percent(event, difficulty):
    """La cuenta de solutionPercent con la clave del panel; sin clave, la del visor."""
    key = compare(event.get("sequence"), difficulty)
    return key["percent"] if key else solution_percent(event)


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


def _closeness_line(rows):
    stats = describe(r["S1"] for r in rows)
    if not stats["n"]:
        return "Cercanía del 1.er intento", "sin dato (JSON anteriores al 22/10/2026)"
    return "Cercanía del 1.er intento", f"mediana {_num(stats['median'], 0)}\u00a0% · n = {stats['n']}"


def _solution_card(rows):
    """E1S: lo cerca que quedaron de la solución, en número y orden de instrucciones.

    No es una métrica del documento: la calcula el visor (solutionPercent, desde el 22/10/2026).
    """
    first = describe(r["S1"] for r in rows)
    mean = describe(r["Smean"] for r in rows)
    best = describe(r["Sbest"] for r in rows)
    stuck = describe(r["Sbest"] for r in rows if r["K"] is None)
    pct = lambda stats: f"mediana {_num(stats['median'], 0)}\u00a0%" if stats["n"] else "sin dato"
    return _card("E1S", "Cercanía a la solución", f"{_num(first['median'], 0)}\u00a0%" if first["n"] else "sin dato",
                 f"mediana del 1.er intento en {first['n']} {'sesión' if first['n'] == 1 else 'sesiones'}",
                 "La cuenta de solutionPercent hecha por el panel con la clave de soluciones: subsecuencia común "
                 "más larga entre el intento y la solución, dividida entre la más larga de las dos. Resta si "
                 "falta o sobra una instrucción y si está fuera de orden; no separa las dos cosas (eso es E1I). "
                 "No usa la del visor, que falló el 22/10/2026; vale también para JSON antiguos. Complemento de "
                 "E1A y E1B, no métrica del documento.",
                 [("Intentos fallidos", pct(mean) + (f" (media por sesión, n = {mean['n']})" if mean["n"] else "")),
                  ("Mejor sin resolver", pct(best)),
                  ("Sin resolución", pct(stuck) + " de su mejor intento" if stuck["n"] else "ninguna con dato")],
                 ratio=first["median"] / 100 if first["n"] else None)


def _instructions_card(rows):
    """E1I: separa lo que solutionPercent mezcla, comparando cada secuencia con la clave de soluciones."""
    order = describe(r["I1order"] for r in rows)
    missing = describe(r["I1missing"] for r in rows)
    extra = describe(r["I1extra"] for r in rows)
    failed_order = describe(r["Iorder"] for r in rows)
    failed_missing = describe(r["Imissing"] for r in rows)
    failed_extra = describe(r["Iextra"] for r in rows)
    sizes = " · ".join(f"{'básica' if d == 1 else 'intermedia'} {len(s[0])}" for d, s in SOLUTIONS.items())

    def counts(a, b):
        if not a["n"]:
            return "sin dato"
        return f"faltan {_count(a['median'])} · sobran {_count(b['median'])} (medianas)"

    return _card("E1I", "Número y orden de instrucciones",
                 f"{_num(order['median'], 0)}\u00a0%" if order["n"] else "sin dato",
                 f"en orden en el 1.er intento, mediana de {order['n']} {'sesión' if order['n'] == 1 else 'sesiones'}",
                 "Cada secuencia frente a la solución de su dificultad (clave de CodeaSolutions). Número: "
                 "instrucciones de la solución que faltan y que sobran, sin mirar el orden. Orden: de las "
                 "instrucciones que coinciden, cuántas están en el orden de la solución. Complemento de E1A y "
                 "E1B, no métrica del documento.",
                 [("1.er intento", counts(missing, extra)),
                  ("Intentos fallidos", counts(failed_missing, failed_extra)),
                  ("Orden en fallidos", f"mediana {_num(failed_order['median'], 0)}\u00a0%" if failed_order["n"]
                   else "sin dato"),
                  ("Clave", f"{sizes} instrucciones")],
                 ratio=order["median"] / 100 if order["n"] else None)


def profile_summary(runs, number):
    """E1P a E4P: cada dimensión por separado, con las sesiones completas y las pendientes (sección 7.7)."""
    started = [run for run in runs if run.scenarios[number].started]
    rows = []
    for key, (name, short, code, _, _) in ficha.PILLARS.items():
        profiles = [ficha.profile(run.sheet, number, key) for run in started]
        scores = [p["P"] for p in profiles if p["P"] is not None]
        observed, criteria, question = ficha.MATRIX[number][key]
        rows.append({
            "key": key, "name": name, "short": short, "code": code,
            "criteria": (observed, criteria), "question": question,
            "n": len(scores),
            "pending": len(profiles) - len(scores),
            "partial": sum(1 for p in profiles if p["P"] is None and p["valued"]),
            "spread": [scores.count(value) for value in (0, 50, 100)],
            "mean": sum(scores) / len(scores) if scores else None,
        })
    return {"code": f"E{number}P", "sessions": len(started), "rows": rows,
            "with_sheet": sum(1 for run in started if ficha.has_profile(run.sheet, number))}


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
    untimed = Counter(r["timeWhy"].split(":")[0] for r in rows
                      if r["seconds"] is None and r["timeWhy"] != "no iniciado")

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
                  "No se suman entre sí ni con F: un intento puede disparar varios. El documento nombra "
                  "colisión, secuencia incompleta y comando inválido; el visor manda choques (colisión) y "
                  "usos inválidos (comando inválido). La secuencia incompleta no tiene contador: se ejecuta "
                  "y queda en los intentos.",
                  [_counter_line(started, "errorCollisionBot", "Choques"),
                   _counter_line(started, "errorInvalidUse", "Usos inválidos"),
                   _counter_line(started, "failedAttempts", "failedAttempts")]),
            _solution_card(started),
            _instructions_card(started),
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
                   ("Ejecuciones N", f"mediana {_count(totals['median'])}"), _closeness_line(started)]),
            _card("E3B", "Cambios del plan", _count(changes["median"]),
                  f"mediana de C en {changes['n']} con pares evaluables",
                  "Pares de ejecuciones consecutivas en los que cambia la secuencia, las repeticiones "
                  "o el objeto. Más cambios no significan mejor depuración.",
                  [("Rango de C", _spread(changes)),
                   ("Pares evaluables", str(sum(r["pairs"] or 0 for r in started))),
                   ("Pares excluidos", str(sum(r["pairsExcluded"] or 0 for r in started)))]),
            _card("E3C", "Errores reportados", "", "contadores de la aplicación, por separado",
                  "Se guardan por separado y no se sustituyen entre sí: failedAttempts solo cuenta la "
                  "pasada que no clasificó nada. Colisión y secuencia incompleta no aplican aquí: no hay "
                  "robot que choque y la fila incompleta cuenta como comando inválido. No se calcula una "
                  "tasa de fallos de este escenario.",
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
        if number == 2:
            tried = [r for r in started if r["tries"] is not None]
            cards[-2]["lines"].append(
                ("Pruebas fallidas", f"{sum(r['failedTries'] for r in tried)} de {sum(r['tries'] for r in tried)} "
                                     f"(failedAttempts, en {len(tried)} {'sesión' if len(tried) == 1 else 'sesiones'})" if tried
                 else "sin dato (JSON anteriores al 22/10/2026)"))
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
        "profile": profile_summary(runs, number),
    }


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
        Column("observer", "text", "Quién observó, de la ficha"),
        Column("gameVersion", "text", "Versión del juego, de la ficha"),
        Column("scenario", "int", "Número de escenario (1 a 4)"),
        Column("scenarioName", "text", "Nombre del escenario en el documento de métricas"),
        Column("G", "flag", "MC1 · Logro final: 1 completado, 0 no completado. Vacío si no es evaluable"),
        Column("timedOut", "flag", "1 si la sala agotó su tiempo y la historia pasó a la siguiente. Vacío en los JSON que no lo traen"),
        Column("G_excluded", "text", "Por qué G no es evaluable: no iniciado, interrupción técnica o sin cierre confirmado"),
        Column("totalSeconds", "float", "MC2 · Tiempo registrado por la aplicación, solo si se completó y su cronómetro no tiene avisos"),
        Column("time_excluded", "text", "Por qué el tiempo no entra en MC2"),
        Column("recordedSeconds", "float", "totalSeconds del escenario tal como viene en el JSON, entre o no en MC2"),
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
        Column("tries", "int", "E2 · Pruebas (Probar). Vacío en los demás escenarios y en los JSON anteriores al 22/10/2026"),
        Column("failedTries", "int", "E2 · Pruebas que no repararon el módulo"),
        Column("firstSolutionPercent", "float", "Cercanía a la solución del primer intento o ejecución. E1: cuenta del "
                                                "panel sobre la clave; E3: solutionPercent del visor (vacío si anotó -1). "
                                                "Contexto, no métrica del documento"),
        Column("failedSolutionPercent", "float", "E1S · Cercanía media de los intentos que no resolvieron (cuenta del panel)"),
        Column("bestFailedSolutionPercent", "float", "E1S · Mejor cercanía entre los intentos que no resolvieron"),
        Column("failedSolutionCount", "int", "E1S · Intentos sin resolver con cercanía calculable"),
        Column("firstMissing", "int", "E1I · Instrucciones de la solución que faltan en el primer intento"),
        Column("firstExtra", "int", "E1I · Instrucciones que sobran en el primer intento"),
        Column("firstOrderPct", "float", "E1I · De las instrucciones que coinciden en el primer intento, % en el "
                                         "orden de la solución"),
        Column("failedMissing", "float", "E1I · Instrucciones que faltan, media de los intentos que no resolvieron"),
        Column("failedExtra", "float", "E1I · Instrucciones que sobran, media de los intentos que no resolvieron"),
        Column("failedOrderPct", "float", "E1I · % en orden, media de los intentos que no resolvieron"),
        *(column for key, (name, short, code, _, _) in ficha.PILLARS.items() for column in (
            Column(f"{short}_C", "int", f"E1P a E4P · {name} ({code}): criterios con 1. Vacío si no se valoró ninguno"),
            Column(f"{short}_E", "int", f"E1P a E4P · {name} ({code}): criterios evaluados con 0 o 1, de 2"),
            Column(f"{short}_P", "int", f"E1P a E4P · {name} ({code}): 0, 50 o 100 solo con los dos evaluados. "
                                        "Vacío es NC. No es un porcentaje de dominio"),
        )),
        Column("issues", "text", "Avisos de integridad de este escenario en esta sesión"),
    )
    rows = []
    for run in runs:
        for number in SCENARIOS:
            m = scenario_metrics(run, number)
            row = _keys(run)
            row.update({key: run.sheet.get(key, "") for key in ficha.SESSION_FIELDS})
            row.update({
                "scenario": number, "scenarioName": TITLES[number][0],
                "G": m["G"], "timedOut": m["timedOut"], "G_excluded": m["gWhy"],
                "totalSeconds": m["seconds"], "time_excluded": m["timeWhy"] if m["seconds"] is None else "",
                "recordedSeconds": m["recorded"],
                "N": m["N"], "F": m["F"], "errorPct": m["PF"], "K": m["K"], "unsolved": m["unsolved"],
                "firstCorrect": m["A"], "firstObserved": m["M"], "firstPct": m["P1"],
                "planChanges": m["C"], "pairsEvaluable": m["pairs"], "pairsExcluded": m["pairsExcluded"],
                "failedAttempts": m["failedAttempts"], "errorCollisionBot": m["errorCollisionBot"],
                "errorInvalidUse": m["errorInvalidUse"], "errorInvalidCommand": m["errorInvalidCommand"],
                "tries": m["tries"], "failedTries": m["failedTries"], "firstSolutionPercent": m["S1"],
                "failedSolutionPercent": m["Smean"], "bestFailedSolutionPercent": m["Sbest"],
                "failedSolutionCount": m["Sn"],
                "firstMissing": m["I1missing"], "firstExtra": m["I1extra"], "firstOrderPct": m["I1order"],
                "failedMissing": m["Imissing"], "failedExtra": m["Iextra"], "failedOrderPct": m["Iorder"],
                "issues": " ".join(sorted({i.code for i in run.issues if i.scenario == number})),
            })
            for key, (_, short, _, _, _) in ficha.PILLARS.items():
                profile = ficha.profile(run.sheet, number, key)
                if profile["valued"]:
                    row.update({f"{short}_C": profile["C"], f"{short}_E": profile["E"], f"{short}_P": profile["P"]})
            rows.append(row)
    return Table(
        "analisis", "Análisis",
        "La tabla del estudio: una fila por sesión y escenario con las métricas del documento del 19/10/2026.",
        columns, tuple(rows))


def pillars_table(runs):
    """Sección 7.7: una fila por sesión, escenario y dimensión, con lo valorado en la ficha.

    Solo salen las actividades que la ficha valora: lo que nadie observó no es una fila de ceros.
    """
    from .tables import KEYS, Column, Table, _keys

    columns = (
        *KEYS,
        Column("participant", "text", "Código de participante, de la ficha"),
        Column("moment", "text", "Momento de evaluación (inicial o final), de la ficha"),
        Column("help", "text", "Ayuda recibida, de la ficha"),
        Column("observer", "text", "Quién observó, de la ficha"),
        Column("gameVersion", "text", "Versión del juego, de la ficha"),
        Column("scenario", "int", "Número de escenario (1 a 4)"),
        Column("profile", "text", "Perfil del documento: E1P, E2P, E3P o E4P"),
        Column("dimension", "text", "D descomposición, TD toma de decisiones, PA pensamiento algorítmico, "
                                    "RP reconocimiento de patrones"),
        Column("record", "text", "Registro de observación: O1 (D), O3 (TD), O4 (PA) u O2 (RP)"),
        Column("C1", "text", "Criterio 1: 1 se cumple, 0 no se cumple pese a haber oportunidad, NO sin evidencia"),
        Column("C2", "text", "Criterio 2, con los mismos códigos"),
        Column("C", "int", "Criterios con 1"),
        Column("E", "int", "Criterios evaluados con 0 o 1, de 2"),
        Column("P", "int", "C / 2 × 100 (0, 50 o 100) solo si E = 2. Vacío es NC, no calculable"),
        Column("evidence1", "text", "Frase, secuencia o esquema que respalda el criterio 1"),
        Column("evidence2", "text", "Frase, secuencia o esquema que respalda el criterio 2"),
    )
    rows = []
    for run in runs:
        for number in SCENARIOS:
            if not ficha.has_profile(run.sheet, number):
                continue
            for key, (_, short, code, _, _) in ficha.PILLARS.items():
                profile = ficha.profile(run.sheet, number, key)
                row = _keys(run)
                row.update({k: run.sheet.get(k, "") for k in ("participant", "moment", "help", "observer", "gameVersion")})
                row.update({
                    "scenario": number, "profile": f"E{number}P", "dimension": short, "record": code,
                    "C1": profile["c1"], "C2": profile["c2"], "C": profile["C"], "E": profile["E"], "P": profile["P"],
                    "evidence1": run.sheet.get(ficha.evidence(number, key, 1), ""),
                    "evidence2": run.sheet.get(ficha.evidence(number, key, 2), ""),
                })
                rows.append(row)
    return Table(
        "pilares", "Pilares",
        "El perfil de evidencias de cada actividad (E1P a E4P): una fila por sesión, escenario y dimensión.",
        columns, tuple(rows))
