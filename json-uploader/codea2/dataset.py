"""Las sesiones de la carpeta de subidas, con su estado en el panel y sus avisos."""

from dataclasses import replace
from datetime import datetime, timezone

from .checks import check_run, cross_checks
from .model import build_run

_NO_START = datetime.max.replace(tzinfo=timezone.utc)


class Dataset:
    def __init__(self, store):
        self.store = store
        self._built = {}

    def runs(self):
        """Todas las sesiones legibles, de la más antigua a la más reciente."""
        state = self.store.state()
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
                                note=str(entry.get("note") or ""), sheet=entry))
        self._built = built

        extra = cross_checks(runs)
        runs = [replace(r, issues=r.issues + tuple(extra[r.id])) if r.id in extra else r for r in runs]
        return sorted(runs, key=lambda r: (r.started_at or _NO_START, r.file.name))

    def get(self, run_id):
        return next((r for r in self.runs() if r.id == run_id), None)
