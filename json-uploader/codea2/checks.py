"""Avisos de integridad.

Esta telemetría no falla reventando: falla saliendo a cero. Un escenario que nunca
arrancó o un contador que nadie incrementó dan un JSON válido y vacío. Aquí se busca
lo que huele a cable olvidado. Son avisos y no errores: un cero puede ser legítimo.
"""

from collections import defaultdict
from datetime import timedelta

from .model import Issue, as_flag, as_int, is_selected, parse_utc

# Margen para dar un evento por posterior al fin de su escenario. Hacia el inicio no hay
# margen: el reto se abre antes de la narración, así que un evento anterior, aunque sea
# por milésimas, es un reto que se abrió tarde.
_SLACK = timedelta(seconds=1)

# Diferencia entre totalSeconds y el reloj a partir de la cual se avisa
_CLOCK_TOLERANCE = 2.0


def check_run(run):
    issues = []

    def add(code, message, scenario=None):
        issues.append(Issue(code, scenario, message))

    if run.file.status == "repaired":
        add("json_cortado", "El JSON estaba cortado y se recuperó cerrando las estructuras abiertas: "
                            "puede faltar el final de la sesión.")
    if run.pin and run.session_id is not None and run.file.name != run.expected_name:
        add("nombre_distinto", f"El nombre del archivo no coincide con su contenido: sería {run.expected_name}.")
    if run.difficulty not in (1, 2):
        add("dificultad", f"Dificultad desconocida ({run.raw.get('difficulty')!r}): se esperaba 1 o 2.")
    if run.started_at is None:
        add("sin_inicio", "La sesión no tiene un startedUtc válido.")
    if run.ended_at is None:
        add("sin_cierre", "La sesión no se cerró (endedUtc vacío): la app terminó antes de cerrar "
                          "la run o el archivo se subió a mitad de partida.")
    elif run.started_at and run.ended_at < run.started_at:
        add("reloj", "endedUtc es anterior a startedUtc.")

    for number, scenario in run.scenarios.items():
        _check_scenario(run, number, scenario, add)
    return issues


def _check_scenario(run, number, scenario, add):
    if not scenario.present:
        add("sin_registro", "El JSON no trae este escenario.", number)
        return

    events = scenario.events
    later_started = any(s.started for n, s in run.scenarios.items() if n > number)

    if not scenario.started:
        if events:
            add("eventos_sin_inicio", f"Tiene {len(events)} evento(s) pero figura como no iniciado: "
                                      "el reto no llegó a abrirse.", number)
        elif later_started:
            add("no_iniciado", "No se inició, pero un escenario posterior sí.", number)
        return

    if scenario.started_at is None:
        add("sin_inicio", "Figura como iniciado, pero sin startedUtc.", number)

    solved = [e for e in events if as_flag(e.get("solved"))]
    if scenario.completed:
        if not events:
            add("sin_eventos", "Completado sin ningún evento registrado.", number)
        elif scenario.meta.events_key == "attempts" and not solved:
            add("sin_resuelto", "Completado, pero ningún intento quedó marcado como resuelto.", number)
    else:
        if solved:
            add("resuelto_sin_completar", "Hay un intento resuelto, pero el escenario no figura "
                                          "como completado.", number)
        # Una sala que agota su tiempo cede el paso a la siguiente: ahí no hay nada raro
        if later_started and not scenario.timed_out:
            add("sin_completar", "Quedó sin completar, pero un escenario posterior sí se inició.", number)

    if scenario.completed and scenario.timed_out:
        add("agotado_y_completado", "Figura a la vez como completado y con el tiempo agotado.", number)

    stamps = [parse_utc(e.get("timestamp")) for e in events]
    if scenario.started_at:
        early = sum(1 for t in stamps if t and t < scenario.started_at)
        if early:
            add("evento_antes", f"{early} evento(s) con hora anterior al inicio del escenario: "
                                "el reto se abrió después de que el niño empezara, y totalSeconds "
                                "se queda corto.", number)
    if scenario.ended_at:
        late = sum(1 for t in stamps if t and t > scenario.ended_at + _SLACK)
        if late:
            add("evento_despues", f"{late} evento(s) con hora posterior al fin del escenario.", number)

    clock, total = scenario.clock_seconds, scenario.total_seconds
    if scenario.completed and clock is not None and total is not None and abs(clock - total) > _CLOCK_TOLERANCE:
        add("tiempo_distinto", f"totalSeconds ({total:.1f} s) y el reloj entre startedUtc y endedUtc "
                               f"({clock:.1f} s) difieren en {abs(clock - total):.1f} s.", number)

    _check_counters(scenario, number, events, add)


def _check_counters(scenario, number, events, add):
    def mismatch(key, counted, what):
        stored = as_int(scenario.raw.get(key))
        if stored is not None and stored != counted:
            add("contador", f"{key} vale {stored}, pero en la lista hay {counted} {what}.", number)

    if number == 2:
        wrong = sum(1 for e in events if is_selected(e) and not as_flag(e.get("correct")))
        mismatch("wrongSelections", wrong, "selección(es) incorrecta(s)")
    elif number == 4:
        wrong = sum(1 for e in events if not as_flag(e.get("correct")))
        mismatch("wrongPlacements", wrong, "colocación(es) incorrecta(s)")
    else:
        failed = scenario.counter("failedAttempts")
        if failed is not None and failed > len(events):
            add("contador", f"failedAttempts vale {failed}, pero solo hay {len(events)} intento(s).", number)

    if number == 3:
        untyped = sum(1 for e in events if not str(e.get("itemType") or "").strip())
        if untyped:
            add("sin_tipo", f"{untyped} intento(s) sin itemType: el programa corrió sin ficha de tipo.", number)

    # Soltar más de lo que se agarró no puede pasar: apunta a agarres atribuidos a otro escenario
    for grabbed_key, released_key in (("blocksGrabbed", "blocksReleased"), ("chipsGrabbed", "chipsReleased")):
        grabbed, released = scenario.counter(grabbed_key), scenario.counter(released_key)
        if grabbed is not None and released is not None and released > grabbed:
            add("agarres", f"{released_key} ({released}) supera a {grabbed_key} ({grabbed}).", number)


def cross_checks(runs):
    """Avisos que dependen de comparar sesiones entre sí. Devuelve {id de sesión: [avisos]}."""
    found = defaultdict(list)
    by_identity = defaultdict(list)
    for run in runs:
        if run.pin and run.session_id is not None:
            by_identity[(run.pin, run.session_id, run.device_id)].append(run)

    for group in by_identity.values():
        if len(group) < 2:
            continue
        for run in group:
            same = [o.file.name for o in group if o is not run and o.started_at == run.started_at]
            other = [o.file.name for o in group if o is not run and o.started_at != run.started_at]
            if same:
                found[run.id].append(Issue("duplicada", None, (
                    f"Es la misma sesión que {', '.join(same)} (mismo pin, sessionId e inicio): "
                    "cuenta doble mientras no se excluya una.")))
            if other:
                found[run.id].append(Issue("pin_repetido", None, (
                    f"Comparte pin y sessionId con {', '.join(other)}, pero empezó a otra hora: "
                    "dos visores usaron el mismo PIN con el mismo contador.")))
    return found
