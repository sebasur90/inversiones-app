"""Adaptador DB → `ciclos_regimen`: lee las series macro guardadas y arma el régimen con la cobertura de cada descarga."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..database import CiclosMacroEstado, CiclosMacroObs
from . import ciclos_macro_catalogo as mc
from . import ciclos_regimen as reg


def leer_series(db: Session, ids: list[str]) -> dict[str, list[tuple[date, float]]]:
    out: dict[str, list[tuple[date, float]]] = {}
    if not ids:
        return out
    filas = (db.query(CiclosMacroObs.serie_id, CiclosMacroObs.fecha, CiclosMacroObs.valor)
             .filter(CiclosMacroObs.serie_id.in_(ids)).order_by(CiclosMacroObs.serie_id, CiclosMacroObs.fecha))
    for sid, fecha, valor in filas:
        out.setdefault(sid, []).append((fecha, float(valor)))
    return out


def regimen(db: Session, hoy: date | None = None) -> dict:
    """El régimen vigente. Cada serie lleva, además de su evaluación, el estado de su última descarga."""
    cat = mc.cargar()
    res = reg.evaluar(leer_series(db, list(cat.series)), cat, hoy)
    estados = {e.serie_id: e for e in db.query(CiclosMacroEstado).all()}

    def _descarga(serie: dict) -> None:
        e = estados.get(serie["id"])
        serie["descarga"] = {
            "estado": e.estado if e else "sin_intentar", "ultimo_ok": e.ultimo_ok if e else None,
            "error": e.error if e else None, "n_obs": e.n_obs if e else 0,
            "primera_fecha": e.primera_fecha if e else None,
        }

    for eje in res["ejes"].values():
        for s in eje["series"]:
            _descarga(s)
    for lista in res["contexto"].values():
        for s in lista:
            _descarga(s)
    res["ultima_actualizacion"] = max((e.ultimo_ok for e in estados.values() if e.ultimo_ok), default=None)
    return res
