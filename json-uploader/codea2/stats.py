"""Agregados del panel: descriptivos y los datos ya colocados de cada gráfico."""

import math
import statistics
from collections import Counter, defaultdict

from .model import DIFFICULTIES, SCENARIOS, as_flag, as_int, parse_utc, seconds_between
from .tables import COUNTER_DOCS, COUNTER_LABELS, run_events

_TIME_STEPS = (5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200)
_HEAT_LEVELS = 6


def describe(values):
    """Descriptivos de una lista de números. Sin datos, todo queda en None."""
    data = sorted(v for v in values if v is not None)
    count = len(data)
    if not count:
        return {"n": 0, "mean": None, "median": None, "sd": None, "min": None, "max": None, "total": None}
    return {
        "n": count,
        "mean": statistics.fmean(data),
        "median": statistics.median(data),
        "sd": statistics.stdev(data) if count > 1 else None,
        "min": data[0],
        "max": data[-1],
        "total": sum(data),
    }


def _ratio(part, whole):
    return part / whole if whole else None


def count_scale(maximum, target=4):
    """Tope redondo y marcas de un eje de conteos que empieza en cero."""
    maximum = max(int(math.ceil(maximum)), 1)
    for magnitude in range(0, 9):
        for base in (1, 2, 5):
            step = base * 10 ** magnitude
            if maximum / step <= target:
                top = int(math.ceil(maximum / step)) * step
                return top, list(range(0, top + step, step))
    return maximum, [0, maximum]


def time_scale(maximum, target=6):
    """Lo mismo para un eje de segundos: marcas en medios minutos, minutos, cinco minutos..."""
    maximum = max(maximum or 0, 1)
    step = next((s for s in _TIME_STEPS if maximum / s <= target), _TIME_STEPS[-1])
    top = int(math.ceil(maximum / step)) * step
    return top, list(range(0, top + step, step))


# ── Resumen ───────────────────────────────────────────────────────────────────

def headline(runs):
    durations = describe(r.seconds for r in runs if r.ended_at)
    completed = sum(1 for r in runs if r.completed_all)
    uploads = [r.file.mtime for r in runs]
    return {
        "sessions": len(runs),
        "participants": len({r.pin for r in runs}),
        "completed_all": completed,
        "completed_ratio": _ratio(completed, len(runs)),
        "duration": durations,
        "with_issues": sum(1 for r in runs if r.issues),
        "issues": sum(len(r.issues) for r in runs),
        "last_upload": max(uploads) if uploads else None,
    }


def scenario_cards(runs):
    cards = []
    for meta in SCENARIOS.values():
        scenarios = [r.scenarios[meta.number] for r in runs]
        started = [s for s in scenarios if s.started]
        completed = [s for s in scenarios if s.completed]
        cards.append({
            "meta": meta,
            "started": len(started),
            "completed": len(completed),
            "completed_ratio": _ratio(len(completed), len(runs)),
            "time": describe(s.total_seconds for s in completed),
            "events": describe(len(s.events) for s in started),
            "errors": describe(s.errors for s in started),
        })
    return cards


def _difficulty(run):
    """La dificultad de la sesión, o 0 si no es ninguna de las conocidas."""
    return run.difficulty if run.difficulty in DIFFICULTIES else 0


def _difficulties(runs):
    """Las dificultades presentes, con la desconocida al final."""
    present = {_difficulty(run) for run in runs}
    return [d for d in (*DIFFICULTIES, 0) if d in present]


def _lanes(points, gap, limit):
    """Reparte en carriles los puntos que se pisarían entre sí."""
    last = []
    for point in sorted(points, key=lambda p: p["x"]):
        for lane, x in enumerate(last):
            if point["x"] - x >= gap:
                break
        else:
            lane = len(last) if len(last) < limit else min(range(limit), key=last.__getitem__)
            if lane == len(last):
                last.append(0)
        last[lane] = point["x"]
        point["lane"] = lane
    return max(len(last), 1)


def time_strip(runs):
    """Tiempo por escenario: un punto por sesión que lo completó, y la mediana."""
    rows = []
    for meta in SCENARIOS.values():
        points = []
        for run in runs:
            scenario = run.scenarios[meta.number]
            if scenario.completed and scenario.total_seconds is not None:
                points.append({"run": run, "seconds": scenario.total_seconds})
        rows.append({"meta": meta, "points": points,
                     "stats": describe(p["seconds"] for p in points)})

    longest = max((p["seconds"] for row in rows for p in row["points"]), default=0)
    top, ticks = time_scale(longest)
    # Con muchas sesiones los puntos se encogen y se apilan en más carriles
    dense = max(len(row["points"]) for row in rows) > 40
    for row in rows:
        for point in row["points"]:
            point["x"] = point["seconds"] / top
        row["lanes"] = _lanes(row["points"], *((0.016, 8) if dense else (0.022, 5)))
        row["median_x"] = row["stats"]["median"] / top if row["points"] else None
    return {
        "rows": rows,
        "ticks": [{"x": t / top, "seconds": t} for t in ticks],
        "difficulties": _difficulties(p["run"] for row in rows for p in row["points"]),
        "dense": dense,
        "empty": not longest,
    }


def sessions_per_day(runs):
    """Sesiones por día, apiladas por dificultad."""
    days = defaultdict(Counter)
    for run in runs:
        if run.local_date:
            days[run.local_date][_difficulty(run)] += 1
    top, ticks = count_scale(max((sum(c.values()) for c in days.values()), default=0))
    columns = []
    for day in sorted(days):
        counts = days[day]
        parts = [{"difficulty": d, "count": counts[d], "height": counts[d] / top}
                 for d in (*DIFFICULTIES, 0) if counts[d]]
        columns.append({"day": day, "total": sum(counts.values()), "parts": parts})
    return {
        "columns": columns,
        "ticks": [{"y": t / top, "value": t} for t in ticks],
        "difficulties": _difficulties(r for r in runs if r.local_date),
    }


def descriptives(runs):
    """Una fila por escenario y dificultad presente en el recorte."""
    rows = []
    difficulties = _difficulties(runs)
    for meta in SCENARIOS.values():
        for difficulty in difficulties:
            group = [r.scenarios[meta.number] for r in runs if _difficulty(r) == difficulty]
            started = [s for s in group if s.started]
            completed = [s for s in group if s.completed]
            rows.append({
                "meta": meta,
                "difficulty": DIFFICULTIES.get(difficulty, "Desconocida"),
                "sessions": len(group),
                "started": len(started),
                "completed": len(completed),
                "time": describe(s.total_seconds for s in completed),
                "errors": describe(s.errors for s in started),
            })
    return rows


# ── Escenarios ────────────────────────────────────────────────────────────────

def _heat(row_labels, column_labels, counts, marked=()):
    """Tabla de calor: el color acompaña al número de cada celda, no lo sustituye."""
    peak = max(counts.values(), default=0)
    rows = []
    for row in row_labels:
        cells = []
        for column in column_labels:
            count = counts.get((row, column), 0)
            cells.append({
                "count": count,
                "level": math.ceil(count / peak * _HEAT_LEVELS) if count else 0,
                "marked": (row, column) in marked,
            })
        rows.append({"label": row, "cells": cells, "total": sum(c["count"] for c in cells)})
    return {"columns": list(column_labels), "rows": rows, "peak": peak}


def _counters(meta, scenarios):
    """Descriptivos de cada contador del escenario entre las sesiones que lo iniciaron."""
    rows = [{"key": meta.events_key, "label": meta.events_label, "doc": f"Número de {meta.events_label.lower()}",
             "stats": describe(len(s.events) for s in scenarios)}]
    for key in meta.counters:
        rows.append({"key": key, "label": COUNTER_LABELS[key], "doc": COUNTER_DOCS[key],
                     "stats": describe(s.counter(key) for s in scenarios)})
    return rows


def _histogram(values, cap):
    """Columnas 1, 2, ..., cap+ con cuántas sesiones cayeron en cada una."""
    counts = Counter(min(v, cap) for v in values)
    top, ticks = count_scale(max(counts.values(), default=0))
    columns = [{"label": f"{v}+" if v == cap else str(v), "count": counts[v], "height": counts[v] / top}
               for v in range(1, cap + 1)]
    return {"columns": columns, "ticks": [{"y": t / top, "value": t} for t in ticks], "n": len(values)}


def _sequences(runs, number, limit=12):
    """Las secuencias que más se ejecutaron, con cuántas sesiones las probaron."""
    seen = defaultdict(lambda: {"count": 0, "runs": set(), "solved": 0})
    for run in runs:
        for event in run.scenarios[number].events:
            blocks = event.get("sequence")
            blocks = tuple(str(b) for b in blocks) if isinstance(blocks, list) else ()
            entry = seen[blocks]
            entry["count"] += 1
            entry["runs"].add(run.id)
            entry["solved"] += as_flag(event.get("solved"))
    ranked = sorted(seen.items(), key=lambda item: (-item[1]["count"], item[0]))
    return {
        "rows": [{"blocks": blocks, "count": e["count"], "sessions": len(e["runs"]), "solved": e["solved"]}
                 for blocks, e in ranked[:limit]],
        "distinct": len(ranked),
        "hidden": max(len(ranked) - limit, 0),
    }


def _section(runs, number):
    meta = SCENARIOS[number]
    scenarios = [r.scenarios[number] for r in runs]
    started = [s for s in scenarios if s.started]
    completed = [s for s in scenarios if s.completed]
    return {
        "meta": meta,
        "sessions": len(runs),
        "started": len(started),
        "completed": len(completed),
        "completed_ratio": _ratio(len(completed), len(runs)),
        "time": describe(s.total_seconds for s in completed),
        "errors": describe(s.errors for s in started),
        "counters": _counters(meta, started),
    }, started, completed


def scenario_1(runs):
    section, started, completed = _section(runs, 1)
    section["attempts"] = _histogram([len(s.events) for s in completed if s.events], cap=6)
    section["sequences"] = _sequences(runs, 1)
    return section


def scenario_2(runs):
    section, started, _ = _section(runs, 2)
    picks = Counter()
    correct = set()
    modules = defaultdict(lambda: {"sessions": 0, "selections": 0, "wrong": 0, "removed": 0, "clean": 0})
    for scenario in started:
        wrong_by_module = Counter()
        touched = set()
        for event in scenario.events:
            module, option = str(event.get("module")), str(event.get("option"))
            touched.add(module)
            if as_flag(event.get("correct")):
                correct.add((module, option))
            if as_flag(event.get("selected")):
                picks[(module, option)] += 1
                modules[module]["selections"] += 1
                if not as_flag(event.get("correct")):
                    modules[module]["wrong"] += 1
                    wrong_by_module[module] += 1
            else:
                modules[module]["removed"] += 1
        for module in touched:
            modules[module]["sessions"] += 1
            modules[module]["clean"] += not wrong_by_module[module]

    module_names = sorted(modules)
    options = sorted({option for _, option in picks}, key=lambda o: (-sum(picks[(m, o)] for m in module_names), o))
    section["modules"] = [{"name": name, **modules[name]} for name in module_names]
    # Las opciones van en filas: son frases largas, y los módulos caben de sobra en columnas
    section["picks"] = _heat(options, module_names,
                             {(option, module): count for (module, option), count in picks.items()},
                             {(option, module) for module, option in correct})
    return section


def scenario_3(runs):
    section, started, completed = _section(runs, 3)
    grid = Counter()
    for scenario in started:
        for event in scenario.events:
            repetitions = as_int(event.get("repetitions"))
            if repetitions is not None:
                grid[(str(event.get("itemType") or "(sin ficha)"), repetitions)] += 1
    types = sorted({t for t, _ in grid})
    most = max((r for _, r in grid), default=0)
    section["repetitions"] = _heat(types, list(range(0, most + 1)), grid)
    section["attempts"] = _histogram([len(s.events) for s in completed if s.events], cap=6)
    section["sequences"] = _sequences(runs, 3)
    return section


def scenario_4(runs):
    section, started, _ = _section(runs, 4)
    grid = Counter()
    sockets = defaultdict(lambda: {"placements": 0, "wrong": 0, "sessions": 0, "first_try": 0})
    for scenario in started:
        first = {}
        for event in scenario.events:
            socket, chip = str(event.get("socket")), str(event.get("chip"))
            right = as_flag(event.get("correct"))
            grid[(socket, chip)] += 1
            sockets[socket]["placements"] += 1
            sockets[socket]["wrong"] += not right
            first.setdefault(socket, right)
        for socket, right in first.items():
            sockets[socket]["sessions"] += 1
            sockets[socket]["first_try"] += right

    socket_names = sorted(sockets)
    # Primero las fichas que tienen hueco, en el mismo orden: los aciertos caen en la diagonal
    chips = [s for s in socket_names if any(c == s for _, c in grid)]
    chips += sorted({c for _, c in grid} - set(chips))
    section["confusion"] = _heat(socket_names, chips, grid, {(s, s) for s in socket_names})
    section["sockets"] = [{"name": name, **sockets[name]} for name in socket_names]
    return section


def scenario_sections(runs):
    return [scenario_1(runs), scenario_2(runs), scenario_3(runs), scenario_4(runs)]


# ── Detalle de una sesión ─────────────────────────────────────────────────────

_EVENT_LABELS = {"intento": "Intento", "seleccion": "Selección", "deseleccion": "Deselección",
                 "colocacion": "Colocación"}


def _mark_state(event):
    """ok, bad o neutral. Quitar una opción y una pasada intermedia del brazo no son ni acierto ni error."""
    if event.kind == "deseleccion":
        return "neutral"
    if event.result:
        return "ok"
    # En el escenario 3 hacen falta varias pasadas: la que no completa el reto no es un fallo
    return "neutral" if event.kind == "intento" and event.scenario == 3 else "bad"


def timeline(run):
    """La sesión sobre una barra de tiempo: tramos de escenario y eventos encima."""
    events = [e for e in run_events(run) if e.at]
    if not run.started_at or not events:
        return None
    end = max(run.ended_at or run.started_at, events[-1].at)
    total = seconds_between(run.started_at, end)
    if not total or total <= 0:
        return None

    def position(moment):
        return min(max(seconds_between(run.started_at, moment) / total, 0), 1)

    segments = []
    for number, scenario in run.scenarios.items():
        if not scenario.started_at:
            continue
        stop = scenario.ended_at or end
        left = position(scenario.started_at)
        segments.append({
            "meta": scenario.meta,
            "left": left,
            "width": max(position(stop) - left, 0),
            "seconds": scenario.total_seconds,
            "completed": scenario.completed,
            "start": seconds_between(run.started_at, scenario.started_at),
        })

    marks = [{"x": position(e.at), "label": _EVENT_LABELS[e.kind], "detail": e.detail,
              "state": _mark_state(e), "scenario": e.scenario,
              "seconds": seconds_between(run.started_at, e.at)}
             for e in events if e.kind in _EVENT_LABELS]
    _, ticks = time_scale(total)
    return {
        "segments": segments,
        "marks": marks,
        "ticks": [{"x": t / total, "seconds": t} for t in ticks if t <= total],
    }


def scenario_detail(scenario):
    """Los eventos de un escenario listos para pintar, con su hora y su desfase."""
    rows = []
    for index, event in enumerate(scenario.events, start=1):
        blocks = event.get("sequence")
        rows.append({
            "index": index,
            "at": parse_utc(event.get("timestamp")),
            "offset": scenario.offset(event),
            "event": event,
            "blocks": [str(b) for b in blocks] if isinstance(blocks, list) else [],
            "solved": as_flag(event.get("solved")),
            "selected": as_flag(event.get("selected")),
            "correct": as_flag(event.get("correct")),
            "repetitions": as_int(event.get("repetitions")),
        })
    return rows
