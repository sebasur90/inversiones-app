"""Simulador de decisiones: cómo quedaría la cartera con una o varias operaciones hipotéticas.

Generaliza a `impacto_cartera_analytics.simular_aporte` (que sólo suma un monto) para cubrir lo que necesita el
Centro de Decisiones: un aporte, su distribución entre varios activos, una reducción o salida de una posición y
la reasignación de lo liberado a otra alternativa o a liquidez. `simular_aporte` queda como estaba (su contrato y
sus tests no cambian); un test verifica que con una sola operación positiva los ejes coinciden.

**Todo en memoria**: no escribe movimientos, precios ni nada en la planilla. Parte de
`inversiones_analytics._clasificados_valorizados` (el criterio único de totales de Exposición) y agrupa cada eje
con `_agrupar`, así que "antes" es exactamente lo que muestra Exposición.

Qué es exacto y qué es supuesto se informa por separado:
- Exacto con los datos actuales: los pesos de hoy y la aritmética de los montos simulados.
- Supuesto: que la venta se haría al último precio conocido; la comisión (tu tasa promedio histórica);
  el resultado de la venta sale del costo promedio de la tenencia. **Los impuestos no se calculan**: la app no
  tiene reglas impositivas cargadas.

Los textos describen cómo quedaría la cartera ("pasaría", "quedaría"); nunca indican qué operación hacer.
"""
from __future__ import annotations

import re
from dataclasses import replace

from sqlalchemy.orm import Session

from ..database import RebalanceoObjetivo
from . import catalogo_instrumentos, clasificacion_analytics
from . import impacto_cartera_engine as engine
from . import salud_engine as se
from .clasificacion_analytics import Contexto
from .etiquetas import SIN_CLASIFICAR, SIN_PAIS, SIN_REGION, SIN_SECTOR
from .impacto_cartera_analytics import TickerDesconocido, _clasificacion_nueva, _conocido
from .inversiones_analytics import (
    _agrupar, _atributo, _clasificados_valorizados, _construir_eje_rebalanceo, _targets_por_eje,
    _tasa_comision_promedio, get_configuracion_cartera, get_mep_actual, get_rendimiento_por_ticker,
)

VERSION_REGLAS = 1
MAX_OPERACIONES = 8
MONTO_MAXIMO_USD = 1_000_000_000.0
CARTERA_SIMULADA = "(simulada)"
LIQUIDEZ = "Liquidez (simulada)"
EJE_MONEDA = "Moneda"
TOLERANCIA_USD = 0.01
_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,14}$")

IMPUESTOS = ("Impuestos: no calculados. La app no tiene reglas impositivas cargadas; el resultado de una venta "
             "puede tener efectos fiscales que acá no se ven.")


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f} %".replace(".", ",")


def _validar(operaciones: list[tuple[str, float]]) -> list[tuple[str, float]]:
    if not operaciones:
        raise ValueError("hace falta al menos una operación")
    if len(operaciones) > MAX_OPERACIONES:
        raise ValueError(f"se admiten hasta {MAX_OPERACIONES} operaciones")
    vistas: dict[str, float] = {}
    for ticker, monto in operaciones:
        t = (ticker or "").strip().upper()
        if not _TICKER.match(t):
            raise ValueError(f"el ticker «{ticker}» no es válido")
        if isinstance(monto, bool) or not isinstance(monto, (int, float)) or monto == 0 or abs(monto) > MONTO_MAXIMO_USD:
            raise ValueError("cada monto debe ser distinto de 0 y de hasta 1.000.000.000 USD en valor absoluto")
        vistas[t] = vistas.get(t, 0.0) + float(monto)
    return [(t, m) for t, m in vistas.items() if m != 0]


def _moneda_de(pos, t: str) -> str:
    if t == LIQUIDEZ:
        return "USD"
    inst = pos.instrumentos.get(t)
    if inst is not None and inst.moneda:
        return inst.moneda
    item = catalogo_instrumentos.obtener(t)
    return (item or {}).get("moneda") or SIN_CLASIFICAR


def _observaciones(ejes: list[dict], peso_maximo: float | None, liquidez_pct: float | None) -> list[dict]:
    obs: list[engine.Observacion] = []
    atencion, revisar = se._umbrales_peso_ticker(peso_maximo)
    origen = "peso máximo configurado en tu cartera" if peso_maximo is not None else "umbral por defecto"
    regla_emisor = (f"umbrales de Salud de cartera por emisor ({origen}): atención desde {_pct(atencion)}, "
                    f"revisar desde {_pct(revisar)}")
    regla_pais = (f"umbrales de Salud de cartera por país: atención desde {_pct(se.UMBRAL_PAIS_ATENCION_PCT)}, "
                  f"revisar desde {_pct(se.UMBRAL_PAIS_REVISAR_PCT)}")
    for eje in ejes:
        if eje["eje"] == engine.EJE_EMISOR:
            for f in eje["items"]:
                if f["etiqueta"] == LIQUIDEZ:
                    continue
                a, d = f["antes_pct"], f["despues_pct"]
                if d >= atencion and d > a + 0.05:
                    nivel = engine.REVISAR if d >= revisar else engine.ATENCION
                    umbral = revisar if nivel == engine.REVISAR else atencion
                    obs.append(engine.Observacion(
                        nivel, f"{f['etiqueta']} pasaría de {_pct(a)} a {_pct(d)} de la cartera, por encima del umbral "
                        f"de {'revisar' if nivel == engine.REVISAR else 'atención'} ({_pct(umbral)}).", regla_emisor, eje["eje"]))
                elif a >= atencion and d < atencion:
                    obs.append(engine.Observacion(
                        engine.INFO, f"{f['etiqueta']} bajaría de {_pct(a)} a {_pct(d)}, por debajo del umbral de atención "
                        f"({_pct(atencion)}).", regla_emisor, eje["eje"]))
            obs += engine._obs_diversificacion(eje)
        elif eje["eje"] == "País":
            for f in eje["items"]:
                a, d = f["antes_pct"], f["despues_pct"]
                if f["residual"] or f["etiqueta"] == LIQUIDEZ or d < se.UMBRAL_PAIS_ATENCION_PCT or d <= a + 0.05:
                    continue
                nivel = engine.REVISAR if d >= se.UMBRAL_PAIS_REVISAR_PCT else engine.ATENCION
                umbral = se.UMBRAL_PAIS_REVISAR_PCT if nivel == engine.REVISAR else se.UMBRAL_PAIS_ATENCION_PCT
                obs.append(engine.Observacion(
                    nivel, f"{f['etiqueta']} pasaría de {_pct(a)} a {_pct(d)} de la cartera, por encima del umbral de "
                    f"{'revisar' if nivel == engine.REVISAR else 'atención'} ({_pct(umbral)}).", regla_pais, "País"))
    if liquidez_pct:
        obs.append(engine.Observacion(
            engine.INFO, f"La liquidez simulada (lo liberado y no reasignado) quedaría en {_pct(liquidez_pct)} de la cartera.",
            "lo que no se reasigna queda como liquidez: no se asume ningún rendimiento", "Liquidez"))
    orden = {engine.REVISAR: 0, engine.ATENCION: 1, engine.INFO: 2}
    obs.sort(key=lambda o: orden[o.nivel])
    return [o.__dict__ for o in obs]


def _rebalanceo(cartera: str | None, db: Session, pos, despues, ctx_atributo) -> list[dict]:
    """Distancia a los objetivos de la pestaña Rebalanceo, antes y después. Sin objetivos cargados: vacío."""
    objetivos = db.query(RebalanceoObjetivo).all()
    if not objetivos:
        return []
    salida = []
    ejes = [("Tipo", "tipo_base"), ("Sector", "sector"), ("Ticker", None)]
    if clasificacion_analytics.modo_auto():
        ejes.insert(2, ("Región", "region"))
    for nombre, attr in ejes:
        targets = _targets_por_eje(nombre, cartera, objetivos)
        if not targets:
            continue

        def _items(p, a=attr):
            return _agrupar([((t if a is None else ctx_atributo(p, t, a)), u, r) for _, t, u, r in p.valores],
                            sin_dato=SIN_CLASIFICAR)

        filas = []
        for p in (pos, despues):
            eje = _construir_eje_rebalanceo(nombre, _items(p), targets, p.total_usd(), p.total_ars())
            desvio = None
            if eje:
                desvio = (sum(abs(i["delta_pp"]) for i in eje["items"]) + sum(i["porcentaje"] for i in eje["sin_objetivo"])) / 2
            filas.append((eje, desvio))
        (eje_a, da), (eje_d, dd) = filas
        salida.append({
            "eje": nombre,
            "desvio_antes_pp": round(da, 2) if da is not None else None,
            "desvio_despues_pp": round(dd, 2) if dd is not None else None,
            "items": [
                {"etiqueta": ia["etiqueta"], "objetivo_pct": ia["porcentaje_objetivo"],
                 "antes_pct": ia["porcentaje_actual"],
                 "despues_pct": next((x["porcentaje_actual"] for x in (eje_d or {}).get("items", []) if x["etiqueta"] == ia["etiqueta"]), 0.0)}
                for ia in (eje_a or {}).get("items", [])
            ],
            "regla": "desvío = mitad de la suma de |actual − objetivo| (las categorías sin objetivo cuentan como desvío)",
        })
    return salida


def simular_operaciones(cartera: str | None, db: Session, operaciones: list[tuple[str, float]]) -> dict:
    """Montos en USD: positivos suman (aporte o reasignación), negativos reducen una tenencia existente.

    Lo que se libera y no se reasigna queda como liquidez simulada. `ValueError` si algo no vale,
    `TickerDesconocido` si un ticker a sumar no está en la cartera, la watchlist ni el catálogo.
    """
    ops = _validar(operaciones)
    pos = _clasificados_valorizados(cartera, db)
    ctx = Contexto(db)
    mep = get_mep_actual(db)
    rend = {r["ticker"]: r for r in get_rendimiento_por_ticker(cartera, db)}

    valores = list(pos.valores)
    clasif = dict(pos.clasif)
    ventas, notas = [], []
    for t, m in ops:
        if m < 0:
            tenencia = sum(v for _, tk, v, _ in valores if tk == t)
            if tenencia <= 0:
                raise ValueError(f"no hay tenencia de {t} en {'la cartera' if cartera else 'el consolidado'} para reducir")
            if -m > tenencia + TOLERANCIA_USD:
                raise ValueError(f"la reducción de {t} ({-m:,.2f} USD) supera la tenencia ({tenencia:,.2f} USD)")
            factor = max(0.0, 1.0 + m / tenencia)
            valores = [(c, tk, v * factor, a * factor) if tk == t else (c, tk, v, a) for c, tk, v, a in valores]
            r = rend.get(t) or {}
            fraccion = min(1.0, -m / r["valor_actual_usd"]) if r.get("valor_actual_usd") else None
            resultado = None
            if fraccion is not None and not r.get("costo_incompleto") and r.get("valor_invertido_usd") is not None:
                resultado = -m - fraccion * r["valor_invertido_usd"]
            ventas.append({
                "ticker": t,
                "monto_usd": -m,
                "fraccion": fraccion,
                "cantidad_estimada": fraccion * r["cantidad_actual"] if fraccion is not None and r.get("cantidad_actual") else None,
                "precio_referencia": r.get("precio_actual"),
                "fecha_precio": r.get("fecha_precio"),
                "valuado_al_costo": bool(r.get("valuado_al_costo")),
                "resultado_estimado_usd": resultado,
                "regla": "resultado = monto − fracción reducida × costo de la tenencia (costo promedio, como Posiciones)",
            })
            if r.get("valuado_al_costo"):
                notas.append(f"{t} no tiene cotización: se valuó al costo, así que el resultado estimado de la reducción es 0.")
        else:
            if not _conocido(ctx, db, t, ctx.base(t), pos):
                raise TickerDesconocido(t)
            clasif.setdefault(t, _clasificacion_nueva(ctx, db, t))
            valores.append((cartera or CARTERA_SIMULADA, t, m, m * mep if mep else 0.0))

    neto = sum(m for _, m in ops)
    liquidez_usd = -neto if neto < 0 else 0.0
    if liquidez_usd > TOLERANCIA_USD:
        valores.append((cartera or CARTERA_SIMULADA, LIQUIDEZ, liquidez_usd, liquidez_usd * mep if mep else 0.0))
    despues = replace(pos, valores=valores, clasif=clasif)

    def _attr(p, t, a):
        if t == LIQUIDEZ:
            return "Liquidez"
        return _atributo(p.instrumentos, t, a, p.clasif)

    def _emisor(t):
        return LIQUIDEZ if t == LIQUIDEZ else ctx.base(t)

    def _entradas(p, etiqueta):
        return [(etiqueta(tk), v_usd, v_ars) for _, tk, v_usd, v_ars in p.valores]

    afectadas_emisor = {ctx.base(t) for t, _ in ops} | ({LIQUIDEZ} if liquidez_usd > TOLERANCIA_USD else set())
    ejes_in = [engine.EjeEntrada(engine.EJE_EMISOR, _agrupar(_entradas(pos, _emisor)),
                                 _agrupar(_entradas(despues, _emisor)), next(iter(afectadas_emisor)))]
    clasificados = [("Sector", "sector", SIN_SECTOR), ("País", "pais", SIN_PAIS)]
    if clasificacion_analytics.modo_auto():
        clasificados.append(("Región", "region", SIN_REGION))
    clasificados.append(("Tipo de instrumento", "tipo_instrumento", SIN_CLASIFICAR))
    for nombre, attr, sin_dato in clasificados:
        ejes_in.append(engine.EjeEntrada(
            nombre,
            _agrupar(_entradas(pos, lambda tk, a=attr: _attr(pos, tk, a)), sin_dato=sin_dato),
            _agrupar(_entradas(despues, lambda tk, a=attr: _attr(despues, tk, a)), sin_dato=sin_dato),
            "",
        ))
    ejes_in.append(engine.EjeEntrada(
        EJE_MONEDA, _agrupar(_entradas(pos, lambda tk: _moneda_de(pos, tk)), sin_dato=SIN_CLASIFICAR),
        _agrupar(_entradas(despues, lambda tk: _moneda_de(despues, tk)), sin_dato=SIN_CLASIFICAR), ""))

    ejes = []
    for e in ejes_in:
        eje = engine.comparar_eje(e)
        for f in eje["items"]:
            f["afectada"] = abs(f["delta_pp"]) > 1e-9
        eje["etiqueta_compra"] = None
        ejes.append(eje)

    total_despues = despues.total_usd()
    liquidez_pct = liquidez_usd / total_despues * 100 if total_despues > 0 and liquidez_usd > TOLERANCIA_USD else None
    config = get_configuracion_cartera(cartera, db)
    tasa = _tasa_comision_promedio(cartera, db)
    operado = sum(abs(m) for _, m in ops)
    if not mep:
        notas.append("No hay un MEP cargado: los montos simulados no suman a los totales en pesos.")
    if not pos.valores:
        notas.append("La cartera no tiene posiciones valuadas.")

    return {
        "version_reglas": VERSION_REGLAS,
        "cartera": cartera,
        "operaciones": [{"ticker": t, "monto_usd": m, "tipo": "reduccion" if m < 0 else "suma"} for t, m in ops],
        "total": {
            "antes_usd": pos.total_usd(), "despues_usd": total_despues,
            "antes_ars": pos.total_ars(), "despues_ars": despues.total_ars(),
        },
        "aporte_nuevo_usd": neto if neto > 0 else 0.0,
        "liquidez_usd": liquidez_usd,
        "ejes": ejes,
        "observaciones": _observaciones(ejes, config["peso_maximo"], liquidez_pct),
        "ventas": ventas,
        "comision_estimada_usd": operado * tasa / 100 if tasa is not None else None,
        "tasa_comision_pct": tasa,
        "rebalanceo": _rebalanceo(cartera, db, pos, despues, _attr),
        "exacto": [
            "Pesos de hoy: mismas cotizaciones y criterio que Exposición.",
            "Pesos de después: la aritmética de los montos simulados sobre esos valores.",
        ],
        "supuestos": [
            "Una reducción se haría al último precio conocido de la tenencia.",
            "El resultado de una reducción sale del costo promedio de la tenencia (como Posiciones).",
            ("Comisión: tu tasa promedio histórica." if tasa is not None
             else "Comisión: sin estimar (no hay comisiones cargadas en tus movimientos)."),
            IMPUESTOS,
            "No se simula ningún rendimiento futuro: sólo cómo quedaría la mezcla.",
        ],
        "notas": notas,
        "avisos": pos.avisos(),
    }
