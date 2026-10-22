"""Clave de soluciones del escenario 1: número y orden de instrucciones frente a la solución.

El visor manda solutionPercent, que mezcla las dos cosas. Aquí se separan comparando la
sequence de cada intento con la clave, así que también vale para los JSON anteriores al
22/10/2026, que no traen solutionPercent.

La clave copia CodeaSolutions del proyecto de Unity (Scenario1Difficulty.solutions),
confirmada el 22/10/2026 con intentos resueltos al 100 % en las dos dificultades. Cada
dificultad tiene un solo camino válido.
**Si cambian los niveles del escenario 1, hay que actualizarla aquí**: el aviso
«clave_distinta» salta cuando el porcentaje del visor no coincide con el de esta clave.
"""

from collections import Counter

SOLUTIONS = {
    1: (  # básica, reto.json
        ("Avanzar", "Girar Derecha", "Avanzar 2", "Girar Derecha", "Avanzar 2", "Girar Izquierda",
         "Avanzar", "Usar"),
    ),
    2: (  # intermedia, escenario1_intermedio.json: el camino de arriba (el de abajo no cabe en 11 huecos)
        ("Girar Izquierda", "Avanzar", "Girar Izquierda", "Avanzar 2", "Girar Izquierda", "Avanzar 2",
         "Girar Izquierda", "Avanzar", "Girar Derecha", "Avanzar 2", "Usar"),
    ),
}


def _lcs(a, b):
    """Longitud de la subsecuencia común más larga."""
    previous = [0] * (len(b) + 1)
    for x in a:
        current = [0]
        for j, y in enumerate(b, start=1):
            current.append(previous[j - 1] + 1 if x == y else max(previous[j], current[-1]))
        previous = current
    return previous[-1]


def compare(sequence, difficulty):
    """Un intento frente a la solución más cercana de su dificultad, o None sin clave.

    - missing / extra: instrucciones de la solución que faltan y que sobran, sin mirar el orden.
    - common: instrucciones que coinciden en tipo y cantidad, en cualquier orden.
    - inOrder: de ellas, las que están en el orden de la solución (subsecuencia común más larga).
    - orderPct: inOrder / common × 100. None si no coincide ninguna: no hay orden que valorar.
    - percent: inOrder / la más larga de las dos × 100, la misma cuenta que solutionPercent.
    """
    solutions = SOLUTIONS.get(difficulty)
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
