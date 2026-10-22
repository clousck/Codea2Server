"""Ficha de sesión: lo que el estudio necesita y el visor no puede saber.

La rellena el evaluador en el panel y se guarda junto a las sesiones excluidas y las notas.
Los campos salen del documento de métricas del 19/10/2026 (secciones 7, 8.5 y 9.1).

Desde ese documento los pilares se valoran por actividad (perfiles E1P a E4P): cada escenario
tiene sus dos criterios observables por dimensión y su pregunta de apoyo. La toma de decisiones
sustituye a la abstracción. Las valoraciones de la ficha anterior (una sola por sesión, con
abstracción) siguen guardadas pero no se usan: no se pueden atribuir a una actividad ni
convertir en toma de decisiones sin revisar la evidencia original.
"""

MOMENTS = {"inicial": "Inicial", "final": "Final"}
HELP = {"ninguna": "Sin ayuda", "verbal": "Orientación verbal", "directa": "Ayuda directa"}
CLOSURES = {"completada": "Completó la sesión", "tiempo": "Tiempo agotado",
            "abandono": "Abandono", "tecnica": "Interrupción técnica"}

# 1 = el criterio se cumple · 0 = hubo oportunidad y no se cumple · NO = sin oportunidad o sin evidencia
CODES = {"1": "1 · se cumple", "0": "0 · no se cumple", "NO": "NO · sin evidencia"}

# Las cuatro dimensiones, en el orden del documento: clave, nombre, sigla, registro de observación
# y los dos criterios comunes (sección 7)
PILLARS = {
    "descomposicion": ("Descomposición", "D", "O1",
                       "Identifica las partes o subobjetivos esenciales de la tarea.",
                       "Explica un orden viable de los pasos y una dependencia real entre ellos."),
    "decisiones": ("Toma de decisiones", "TD", "O3",
                   "Justifica una elección mediante una condición, pista o restricción relevante.",
                   "Compara la elección con otra alternativa y explica por qué la prefiere."),
    "algoritmico": ("Pensamiento algorítmico", "PA", "O4",
                    "Propone una secuencia o regla viable para resolver la tarea.",
                    "Predice y explica su resultado antes de ejecutar o recibir la respuesta."),
    "patrones": ("Reconocimiento de patrones", "RP", "O2",
                 "Explica una semejanza útil entre dos casos comparables.",
                 "Aplica y justifica la regla en un caso nuevo equivalente."),
}

# Matrices de las secciones 7.2 a 7.5: criterio 1 y 2 observables y pregunta de apoyo,
# por escenario y dimensión
MATRIX = {
    1: {
        "descomposicion": ("Distingue orientación, desplazamientos y condición de apertura.",
                           "Ordena los pasos y explica qué posición u orientación necesita antes de un "
                           "desplazamiento o de abrir la puerta.",
                           "¿Qué partes tiene tu plan y qué debe ocurrir antes?"),
        "decisiones": ("Justifica el siguiente movimiento o comando considerando posición, orientación u obstáculo.",
                       "Compara ese comando con otro disponible y explica por qué la opción elegida permite "
                       "avanzar en el recorrido previsto.",
                       "¿Por qué este comando y no este otro?"),
        "algoritmico": ("Propone una secuencia viable de comandos para llegar a la puerta y cumplir su "
                        "condición de apertura.",
                        "Antes de ejecutarla, anticipa y explica la posición, orientación o resultado final del robot.",
                        "¿Cuál es tu secuencia y qué ocurrirá al ejecutarla?"),
        "patrones": ("Explica una secuencia o relación común entre dos rutas comparables.",
                     "Adapta y justifica esa relación en una tercera ruta equivalente.",
                     "¿Qué se repite entre estas rutas y cómo lo usarías en esta otra?"),
    },
    2: {
        "descomposicion": ("Separa los módulos por reparar e identifica la necesidad de cada uno.",
                           "Explica un orden viable para resolver un módulo y por qué interpreta su necesidad "
                           "antes de elegir el recurso.",
                           "¿Qué necesita cada módulo y qué debes saber antes de elegir?"),
        "decisiones": ("Justifica el recurso elegido mediante la necesidad o pista del módulo.",
                       "Compara el recurso con otro disponible y explica por qué el segundo no satisface la necesidad.",
                       "¿Por qué este recurso y no la otra opción?"),
        "algoritmico": ("Expone una regla viable para interpretar la necesidad, comparar recursos y elegir.",
                        "Antes de seleccionar o recibir respuesta, anticipa y explica el resultado de aplicar esa regla.",
                        "¿Qué regla seguirás y qué resultado esperas antes de seleccionar?"),
        "patrones": ("Explica una relación común entre necesidad y recurso en dos casos comparables.",
                     "Aplica y justifica esa relación en un nuevo módulo o caso equivalente.",
                     "¿Qué regla comparten estos casos y cómo funcionaría en otro?"),
    },
    3: {
        "descomposicion": ("Separa selección del objeto, configuración y traslado según las acciones reales del brazo.",
                           "Ordena los pasos del traslado y explica una dependencia entre la configuración y el "
                           "movimiento del objeto.",
                           "¿Qué partes tiene el traslado y cómo dependen entre sí?"),
        "decisiones": ("Justifica una elección de secuencia, repeticiones o tipo de objeto según el traslado previsto.",
                       "Compara su configuración con otra posible y explica por qué la elegida resulta adecuada.",
                       "¿Por qué esta configuración y no otra?"),
        "algoritmico": ("Propone una secuencia viable con sus repeticiones y el objeto que corresponda.",
                        "Antes de ejecutarla, anticipa y explica el traslado o resultado esperado del brazo.",
                        "¿Qué hará el brazo con este plan antes de ejecutarlo?"),
        "patrones": ("Reconoce y explica un segmento o relación repetible en dos traslados comparables.",
                     "Adapta y justifica la secuencia o repetición en un traslado nuevo equivalente.",
                     "¿Qué parte se repite y cómo la adaptarías a este traslado nuevo?"),
    },
    4: {
        "descomposicion": ("Separa identificación de atributos, comparación y colocación del chip.",
                           "Ordena los pasos y explica por qué compara los atributos antes de colocar o confirmar el chip.",
                           "¿Qué pasos sigues y qué verificas antes de colocar?"),
        "decisiones": ("Justifica la elección de un chip mediante los atributos requeridos por el receptáculo.",
                       "Compara ese chip con otro y explica por qué prefiere la correspondencia elegida.",
                       "¿Por qué este chip y no el otro?"),
        "algoritmico": ("Expone una regla viable para comparar atributos, colocar el chip y verificar la correspondencia.",
                        "Antes de probarla, anticipa y explica qué colocación será aceptada según esa regla.",
                        "¿Cómo decidirás la colocación y cuál será aceptada antes de probar?"),
        "patrones": ("Explica una regla de correspondencia común entre dos pares de chip y receptáculo.",
                     "Aplica y justifica esa regla en un nuevo par equivalente.",
                     "¿Qué regla comparten estos pares y cómo la usarías con este otro?"),
    },
}

_CHOICES = {"moment": MOMENTS, "help": HELP, "closure": CLOSURES}
_TEXTS = ("participant", "observer", "gameVersion")
SESSION_FIELDS = ("participant", "moment", "help", "closure", "observer", "gameVersion")


def criterion(scenario, pillar, number):
    return f"e{scenario}_{pillar}_{number}"


def evidence(scenario, pillar, number):
    return f"e{scenario}_{pillar}_{number}_ev"


def from_form(form):
    """Los campos de la ficha que trae un formulario. Lo que no viene queda en None: no se toca."""
    fields = {}
    for key, choices in _CHOICES.items():
        if key in form:
            fields[key] = form[key] if form[key] in choices else ""
    for key in _TEXTS:
        if key in form:
            fields[key] = form[key].strip()[:80]
    for scenario in MATRIX:
        for pillar in PILLARS:
            for number in (1, 2):
                key = criterion(scenario, pillar, number)
                if key in form:
                    fields[key] = form[key] if form[key] in CODES else ""
                key = evidence(scenario, pillar, number)
                if key in form:
                    fields[key] = form[key].strip()[:500]
    return fields


def profile(sheet, scenario, pillar):
    """Un pilar en una actividad (sección 7.1).

    C son los criterios con 1 y E los evaluados con 0 o 1. P vale 0, 50 o 100 solo con E = 2;
    si no, queda en None (NC, no calculable). Un NO nunca se convierte en cero.
    """
    codes = [sheet.get(criterion(scenario, pillar, number)) or "" for number in (1, 2)]
    evaluated = [code for code in codes if code in ("0", "1")]
    count = sum(int(code) for code in evaluated)
    return {
        "c1": codes[0], "c2": codes[1],
        "C": count, "E": len(evaluated),
        "P": count * 50 if len(evaluated) == 2 else None,
        "valued": any(codes),
    }


def has_profile(sheet, scenario):
    """Si la ficha valora algún criterio de esta actividad."""
    return any(profile(sheet, scenario, pillar)["valued"] for pillar in PILLARS)
