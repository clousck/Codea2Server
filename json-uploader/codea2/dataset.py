"""Las sesiones de la carpeta de subidas, con su estado en el panel y sus avisos."""

from dataclasses import replace
from datetime import datetime, timezone

from . import sheet as ficha
from .checks import check_run, cross_checks, roster_checks
from .model import build_run

_NO_START = datetime.max.replace(tzinfo=timezone.utc)


class Dataset:
    def __init__(self, store):
        self.store = store
        self._built = {}

    def runs(self):
        """Todas las sesiones legibles, de la más antigua a la más reciente."""
        state = self.store.state()
        supervisors, students = self.store.supervisors(), self.store.students()
        built = {}
        runs = []
        for file in self.store.files():
            if not file.is_run:
                continue
            # Mientras el archivo no cambie, Store devuelve el mismo objeto: no se rehace nada
            cached = self._built.get(file.name)
            if cached is None or cached[0] is not file:
                run = build_run(file)
                cached = (file, replace(run, issues=tuple(check_run(run))))
            built[file.name] = cached
            entry = state.get(file.name) or {}
            runs.append(replace(cached[1], excluded=bool(entry.get("excluded")),
                                note=str(entry.get("note") or ""),
                                sheet=ficha.resolve(entry, cached[1].pin, supervisors, students)))
        self._built = built

        runs.sort(key=lambda r: (r.started_at or _NO_START, r.file.name))
        ficha.propose_moments(runs)
        extra = cross_checks(runs)
        roster = roster_checks(runs, students)
        return [replace(r, issues=r.issues + tuple(extra.get(r.id, ())) + tuple(roster.get(r.id, ())))
                if r.id in extra or r.id in roster else r for r in runs]

    def get(self, run_id):
        return next((r for r in self.runs() if r.id == run_id), None)
