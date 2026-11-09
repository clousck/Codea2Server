"""Clave de soluciones del escenario 1: número y orden de instrucciones frente a la solución.

El visor manda solutionPercent, que mezcla las dos cosas. Aquí se separan comparando la
sequence de cada intento con la clave, así que también vale para los JSON anteriores al
22/10/2026, que no traen solutionPercent.

La clave copia CodeaSolutions del proyecto de Unity (Scenario1Difficulty.solutions). Cada
dificultad tiene un solo camino válido. Los niveles han cambiado, así que se guardan todas las
versiones y cada sesión se compara con la de los niveles con que se jugó (ver level_for).
**Si cambian los niveles del escenario 1, hay que añadir aquí la versión nueva**: el aviso
«clave_distinta» salta cuando el porcentaje del visor no coincide con el de la clave.
"""

from collections import Counter
from datetime import datetime, timezone

# De la más antigua a la más reciente: (nombre, primer día en que se vio, clave por dificultad)
LEVELS = (
    ("2026-10", None, {
        1: (  # básica, reto.json; confirmada el 22/10/2026 con intentos resueltos al 100 %
            ("Avanzar", "Girar Derecha", "Avanzar 2", "Girar Derecha", "Avanzar 2", "Girar Izquierda",
             "Avanzar", "Usar"),
        ),
        2: (  # intermedia, escenario1_intermedio.json: el camino de arriba (el de abajo no cabe en 11 huecos)
            ("Girar Izquierda", "Avanzar", "Girar Izquierda", "Avanzar 2", "Girar Izquierda", "Avanzar 2",
             "Girar Izquierda", "Avanzar", "Girar Derecha", "Avanzar 2", "Usar"),
        ),
    }),
    # Niveles nuevos, vistos por primera vez el 09/11/2026: el solutionPercent del visor cuadra con
    # esta clave en todos los intentos de ese día, resueltos y fallidos
    ("2026-11", datetime(2026, 11, 9, tzinfo=timezone.utc), {
        1: (
            ("Avanzar 2", "Girar Izquierda", "Avanzar 2", "Girar Izquierda", "Avanzar", "Girar Derecha",
             "Avanzar", "Usar"),
        ),
        2: (  # la de 2026-10 con el primer giro a la derecha
            ("Girar Derecha", "Avanzar", "Girar Izquierda", "Avanzar 2", "Girar Izquierda", "Avanzar 2",
             "Girar Izquierda", "Avanzar", "Girar Derecha", "Avanzar 2", "Usar"),
        ),
    }),
)
CURRENT = LEVELS[-1][0]
SOLUTIONS = LEVELS[-1][2]  # la clave vigente
_BY_NAME = {name: keys for name, _, keys in LEVELS}


def level_for(difficulty, attempts, started_at):
    """Con qué niveles se jugó una sesión.

    Un intento resuelto del escenario 1 lo dice sin dudas: su secuencia es la solución de esos
    niveles. Sin intento resuelto, decide la fecha: la versión vigente el día que empezó.
    """
    for name, _, keys in reversed(LEVELS):
        solutions = keys.get(difficulty, ())
        for attempt in attempts:
            sequence = attempt.get("sequence")
            if attempt.get("solved") is True and isinstance(sequence, list)                     and tuple(str(block) for block in sequence) in solutions:
                return name
    if started_at is None:
        return CURRENT
    for name, since, _ in reversed(LEVELS):
        if since is None or started_at >= since:
            return name
    return LEVELS[0][0]


def _lcs(a, b):
    """Longitud de la subsecuencia común más larga."""
    previous = [0] * (len(b) + 1)
    for x in a:
        current = [0]
        for j, y in enumerate(b, start=1):
            current.append(previous[j - 1] + 1 if x == y else max(previous[j], current[-1]))
        previous = current
    return previous[-1]


def compare(sequence, difficulty, level=None):
    """Un intento frente a la solución más cercana de su dificultad, o None sin clave.

    level es la versión de los niveles (level_for); sin ella, la vigente.

    - missing / extra: instrucciones de la solución que faltan y que sobran, sin mirar el orden.
    - common: instrucciones que coinciden en tipo y cantidad, en cualquier orden.
    - inOrder: de ellas, las que están en el orden de la solución (subsecuencia común más larga).
    - orderPct: inOrder / common × 100. None si no coincide ninguna: no hay orden que valorar.
    - percent: inOrder / la más larga de las dos × 100, la misma cuenta que solutionPercent.
    """
    solutions = _BY_NAME.get(level or CURRENT, SOLUTIONS).get(difficulty)
    if not solutions or not isinstance(sequence, list):
        return None
    attempt = [str(block) for block in sequence]
    best = None
    for solution in solutions:
        in_order = _lcs(attempt, solution)
        longest = max(len(attempt), len(solution))
        percent = 100 * in_order / longest if longest else 100.0
        if best is None or percent > best["percent"]:
            common = sum((Counter(attempt) & Counter(solution)).values())
            best = {
                "solutionLength": len(solution),
                "length": len(attempt),
                "common": common,
                "missing": len(solution) - common,
                "extra": len(attempt) - common,
                "inOrder": in_order,
                "orderPct": 100 * in_order / common if common else None,
                "percent": percent,
            }
    return best
