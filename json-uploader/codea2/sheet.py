"""Ficha de sesión: lo que el estudio necesita y el visor no puede saber.

La rellena el evaluador en el panel y se guarda junto a las sesiones excluidas y las notas.
Los campos salen del documento de métricas del 09/10/2026 (secciones 7, 8.5 y 9.1).
"""

MOMENTS = {"inicial": "Inicial", "final": "Final"}
HELP = {"ninguna": "Sin ayuda", "verbal": "Orientación verbal", "directa": "Ayuda directa"}
CLOSURES = {"completada": "Completó la sesión", "tiempo": "Tiempo agotado",
            "abandono": "Abandono", "tecnica": "Interrupción técnica"}

# 1 = el criterio se cumple · 0 = hubo oportunidad y no se cumple · NO = sin oportunidad o sin evidencia
CODES = {"1": "1 · se cumple", "0": "0 · no se cumple", "NO": "NO · sin evidencia"}

PILLARS = {
    "descomposicion": ("Descomposición", "Identifica las partes esenciales de la tarea.",
                       "Explica un orden viable y una dependencia entre partes."),
    "patrones": ("Reconocimiento de patrones", "Explica una semejanza útil entre dos casos.",
                 "Aplica y justifica una regla en un caso nuevo."),
    "abstraccion": ("Abstracción", "Identifica los datos necesarios para decidir.",
                    "Justifica qué dato prescindible puede dejar de lado."),
    "algoritmico": ("Pensamiento algorítmico", "Formula una secuencia o regla viable.",
                    "Predice y explica un resultado antes de ejecutar o recibir la respuesta."),
}

_CHOICES = {"moment": MOMENTS, "help": HELP, "closure": CLOSURES}
_TEXTS = ("participant", "gameVersion")


def criterion(pillar, number):
    return f"p_{pillar}_{number}"


def evidence(pillar):
    return f"p_{pillar}_evidence"


def from_form(form):
    """Los campos de la ficha que trae un formulario. Lo que no viene queda en None: no se toca."""
    fields = {}
    for key, choices in _CHOICES.items():
        if key in form:
            fields[key] = form[key] if form[key] in choices else ""
    for key in _TEXTS:
        if key in form:
            fields[key] = form[key].strip()[:80]
    for pillar in PILLARS:
        for number in (1, 2):
            key = criterion(pillar, number)
            if key in form:
                fields[key] = form[key] if form[key] in CODES else ""
        if evidence(pillar) in form:
            fields[evidence(pillar)] = form[evidence(pillar)].strip()[:500]
    return fields


def pillar_score(sheet, pillar):
    """0, 50 o 100 si los dos criterios se observaron; None si falta alguno.

    Es el porcentaje de esta lista de dos criterios, no de dominio del pilar.
    """
    codes = [sheet.get(criterion(pillar, number)) for number in (1, 2)]
    if any(code not in ("0", "1") for code in codes):
        return None
    return sum(int(code) for code in codes) * 50
