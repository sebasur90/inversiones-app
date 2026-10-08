"""Variación del día que informa IOL: se guarda, se carga y se aplica a la variación mostrada.

IOL manda en la misma cotización que ya se pide (paneles, `Titulos/FCI`, símbolo suelto) el cierre
anterior y la variación porcentual del día. Guardarlos no cuesta ni una llamada extra, y evita
calcular la variación contra "el registro anterior" de `precios_instrumento`, que puede ser de hace
semanas si el historial tiene huecos (ver `inversiones_analytics._variacion_diaria`).

Vive en un módulo propio, y no dentro de `refresco_precios`, porque lo usan los tres orquestadores
que cotizan: el sync completo, el refresco liviano y la watchlist.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..database import CotizacionDiaria


def construir_cotizaciones_dia(
    filas: list[dict], cotizaciones_iol: dict,
) -> list[dict]:
    """Filas de `CotizacionDiaria` para las filas de precio que salieron de IOL.

    `filas`: las que devuelven `fetch_precios_api` / `fetch_precios_watchlist_catalogo`
    (`{ticker, fecha, precio, moneda, fuente}`). `cotizaciones_iol`: `simbolo -> CotizacionIOL`.

    Sólo `fuente == 'iol'`: lo que vino de data912 no trae variación y no se inventa una. Si el
    precio guardado está calibrado (factor 0,01), el cierre anterior se lleva a la misma escala con
    el mismo factor, que se recupera como `precio guardado / precio crudo de IOL`; el porcentaje es
    invariante a la escala y se guarda tal cual. Un `(precio, moneda)` plano (sin los atributos
    extra) no aporta nada y se saltea.
    """
    por_simbolo = {s.upper().strip(): c for s, c in cotizaciones_iol.items()}
    salida: list[dict] = []
    for fila in filas:
        if fila.get("fuente") != "iol":
            continue
        cot = por_simbolo.get(fila["ticker"].upper().strip())
        if cot is None:
            continue
        cierre = getattr(cot, "cierre_anterior", None)
        variacion = getattr(cot, "variacion_pct", None)
        precio_crudo = float(cot[0])
        if precio_crudo <= 0:
            continue
        factor = float(fila["precio"]) / precio_crudo
        cierre_escalado = round(cierre * factor, 6) if cierre is not None else None
        if variacion is None and cierre is not None:
            variacion = (precio_crudo / cierre - 1.0) * 100.0
        if variacion is None and cierre_escalado is None:
            continue
        salida.append({
            "ticker": fila["ticker"], "fecha": fila["fecha"],
            "cierre_anterior": cierre_escalado,
            "variacion_pct": round(variacion, 6) if variacion is not None else None,
            "fuente": "iol",
        })
    return salida


def guardar(db: Session, filas: list[dict]) -> int:
    """Upsert por `(ticker, fecha)`. Hace `flush`, no `commit`. Devuelve cuántas filas escribió."""
    if not filas:
        return 0
    tickers = {f["ticker"] for f in filas}
    existentes = {
        (r.ticker, r.fecha): r
        for r in db.query(CotizacionDiaria).filter(CotizacionDiaria.ticker.in_(tickers)).all()
    }
    for f in filas:
        fila = existentes.get((f["ticker"], f["fecha"]))
        if fila is None:
            nueva = CotizacionDiaria(**f)
            existentes[(f["ticker"], f["fecha"])] = nueva
            db.add(nueva)
        else:
            fila.cierre_anterior = f["cierre_anterior"]
            fila.variacion_pct = f["variacion_pct"]
            fila.fuente = f["fuente"]
    db.flush()
    return len(filas)


def cargar_por_clave(db: Session, tickers: set[str] | None = None) -> dict[tuple[str, date], tuple[float | None, float | None]]:
    """`{(ticker, fecha): (cierre_anterior, variacion_pct)}`; `variacion_pct` en puntos porcentuales."""
    query = db.query(CotizacionDiaria)
    if tickers is not None:
        if not tickers:
            return {}
        query = query.filter(CotizacionDiaria.ticker.in_(tickers))
    return {
        (r.ticker, r.fecha): (
            float(r.cierre_anterior) if r.cierre_anterior is not None else None,
            float(r.variacion_pct) if r.variacion_pct is not None else None,
        )
        for r in query.all()
    }


def purgar_antiguas(db: Session, hoy: date, dias: int = 400) -> None:
    """Borra lo de hace más de `dias`: la variación sólo importa cerca del presente, y así la tabla
    (una fila por ticker por día) no crece sin límite. No se purga por ticker vigente: la comparten
    cartera y watchlist, y un ticker que sale vuelve a quedar sin filas nuevas por sí solo."""
    db.query(CotizacionDiaria).filter(
        CotizacionDiaria.fecha < hoy - timedelta(days=dias)
    ).delete(synchronize_session=False)
    db.flush()
