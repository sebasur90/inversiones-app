"""Motor puro de "¿por qué ganó o perdió mi cartera?": separa el P&L de un período en sus
componentes atribuibles (variación de precio, dividendos, cupones, comisiones) por ticker, y
deriva de ahí agrupaciones, ranking y una explicación en prosa.

Sin dependencias de Session/DB/FastAPI: todas las funciones reciben agregados ya calculados
(V0/V1 de cada ticker, montos brutos/netos de cada tipo de movimiento en el período, ya
convertidos a la moneda elegida) y devuelven dicts planos. Mismo criterio que `risk_engine.py`
y `contribucion_engine.py`: testeable con pytest sin fixtures de BD.

Identidad central, por ticker (y por construcción, sumada, también a nivel cartera/grupo):

    pnl = precio + dividendos + cupones + comisiones

donde `comisiones` en el resultado va con signo negativo (es un costo) y `precio` es un
residual exacto:

    precio = (V1 - V0) - compras_bruto + ventas_bruto + amortizaciones_bruto

Por eso `precio` también absorbe el resultado de ventas/amortizaciones frente al precio de
mercado del día: separar ese resultado en una línea propia exigiría el precio de mercado exacto
de cada operación, que no siempre está disponible con precisión (decisión de producto: una
amortización es "capital devuelto", no se le inventa una ganancia — ver plan de la feature).

**Nada se estima cuando falta un dato.** Cualquier insumo `None` (precio faltante, MEP
faltante) se propaga como `None` a través de las cuentas en vez de tratarse como 0: un ticker
sin precio en V0 o V1 queda con `precio=None` y por lo tanto `pnl=None` ("No disponible"), pero
sus aportes/retiros/dividendos siguen mostrándose si sí se pudieron convertir.
"""
from __future__ import annotations

EPS = 1e-9

# Campos numéricos que se sí o sí pueden ser None a nivel ticker y que agrupar_por_etiqueta
# suma ignorando los None (no los trata como 0 más que para el total sumado).
CAMPOS_SUMABLES = ("pnl", "precio", "dividendos", "cupones", "comisiones", "aportes", "retiros", "amortizaciones")


def descomponer_ticker(
    ticker: str,
    v0: float | None,
    v1: float | None,
    compras_bruto: float | None,
    compras_neto: float | None,
    ventas_bruto: float | None,
    ventas_neto: float | None,
    amortizaciones_bruto: float | None,
    amortizaciones_neto: float | None,
    dividendos: float | None,
    cupones: float | None,
    comisiones: float | None,
) -> dict:
    """Descompone el P&L de un ticker en el período en sus componentes atribuibles.

    Args:
        v0/v1: valor de mercado de la tenencia al inicio/fin del período, en la moneda elegida.
            `None` si no hay precio conocido (o no se pudo convertir) para esa fecha.
        compras_bruto/ventas_bruto/amortizaciones_bruto: suma de `precio × cantidad` de los
            movimientos del período (sin comisión), en la moneda elegida.
        compras_neto/ventas_neto/amortizaciones_neto: los mismos montos con la comisión
            aplicada — son, respectivamente, los aportes y los retiros de capital del período
            (misma convención que `inversiones_analytics._monto_ajustado`).
        dividendos/cupones: montos brutos cobrados en el período (no llevan comisión).
        comisiones: comisión total pagada en el período por este ticker, **positiva** (costo).

    Cualquier argumento en `None` indica que ese componente no se pudo calcular con precisión
    (falta un precio o un tipo de cambio) y se propaga como `None` — nunca como 0 — a todo lo
    que dependa de él.
    """
    aportes = round(compras_neto, 2) if compras_neto is not None else None
    retiros = round(ventas_neto, 2) if ventas_neto is not None else None
    amortizaciones = round(amortizaciones_neto, 2) if amortizaciones_neto is not None else None

    precio = None
    if None not in (v0, v1, compras_bruto, ventas_bruto, amortizaciones_bruto):
        precio = (v1 - v0) - compras_bruto + ventas_bruto + amortizaciones_bruto

    pnl = None
    if precio is not None and None not in (dividendos, cupones, comisiones):
        pnl = precio + dividendos + cupones - comisiones

    return {
        "ticker": ticker,
        "v0": round(v0, 2) if v0 is not None else None,
        "v1": round(v1, 2) if v1 is not None else None,
        "pnl": round(pnl, 2) if pnl is not None else None,
        "precio": round(precio, 2) if precio is not None else None,
        "dividendos": round(dividendos, 2) if dividendos is not None else None,
        "cupones": round(cupones, 2) if cupones is not None else None,
        "comisiones": round(-comisiones, 2) if comisiones is not None else None,
        "aportes": aportes,
        "retiros": retiros,
        "amortizaciones": amortizaciones,
        "disponible": pnl is not None,
    }


def agrupar_por_etiqueta(entries: list[tuple[str, dict]]) -> list[dict]:
    """Agrupa descomposiciones de ticker por una etiqueta (tipo de instrumento, mercado, ...).

    `entries` es `[(etiqueta, descomposicion_de_descomponer_ticker), ...]`. Cada campo suma los
    valores no-`None` de sus miembros (un ticker sin datos no resta información a los que sí la
    tienen); `n_no_disponibles` cuenta cuántos miembros del grupo tienen `pnl=None`, para que el
    caller pueda avisar que el total del grupo es parcial.
    """
    grupos: dict[str, dict] = {}
    for etiqueta, item in entries:
        g = grupos.setdefault(
            etiqueta,
            {"etiqueta": etiqueta, **{k: 0.0 for k in CAMPOS_SUMABLES}, "n_no_disponibles": 0},
        )
        if not item["disponible"]:
            g["n_no_disponibles"] += 1
        for k in CAMPOS_SUMABLES:
            v = item.get(k)
            if v is not None:
                g[k] += v

    resultado = []
    for g in grupos.values():
        gg = dict(g)
        for k in CAMPOS_SUMABLES:
            gg[k] = round(gg[k], 2)
        resultado.append(gg)
    return resultado


def con_contribucion(items: list[dict], base: float) -> list[dict]:
    """Agrega `contribucion_pct = pnl / base × 100` a cada item (copia, no muta).

    Mismo denominador para todos los items de una lista: la suma de `contribucion_pct` reconcilia
    con el retorno simple del período (igual criterio que `contribucion_engine`/`contribucion_analytics`,
    que usa el costo total como denominador común). `None` si el ítem no tiene `pnl` o si `base`
    es ~0 (período sin capital de referencia).
    """
    resultado = []
    for it in items:
        it2 = dict(it)
        pnl = it.get("pnl")
        it2["contribucion_pct"] = (
            round(pnl / base * 100, 2) if (pnl is not None and abs(base) > EPS) else None
        )
        resultado.append(it2)
    return resultado


def ranking(items: list[dict], n: int = 5, positivos: bool = True) -> list[dict]:
    """Top `n` ítems por P&L: contribuyentes (`positivos=True`) o detractores (`False`).

    Sólo entre los que tienen `pnl` conocido y distinto de 0 — un ticker "No disponible" no
    puede aparecer en ningún ranking sin inventarle un valor.
    """
    candidatos = [it for it in items if it.get("pnl") is not None and abs(it["pnl"]) > EPS]
    if positivos:
        candidatos = [it for it in candidatos if it["pnl"] > 0]
        candidatos.sort(key=lambda it: -it["pnl"])
    else:
        candidatos = [it for it in candidatos if it["pnl"] < 0]
        candidatos.sort(key=lambda it: it["pnl"])
    return candidatos[:n]


def descomponer_fx_periodo(pnl_ars: float | None, pnl_usd: float | None, mep_hoy: float | None) -> dict:
    """Separa, en dinero, cuánto del P&L en ARS es "el activo en dólares" y cuánto es el
    movimiento del dólar (MEP) — identidad exacta, sin estimación:

        resultado_activos_ars = pnl_usd × MEP_hoy   (lo que hubiera dado el mismo resultado en
                                                       dólares, valuado al tipo de cambio de hoy)
        efecto_mep_ars = pnl_ars - resultado_activos_ars

    Sólo tiene sentido en la vista ARS: en USD el tipo de cambio ya está incorporado en el
    precio en dólares de cada activo, así que el caller no debe invocar esto para esa vista.
    """
    if pnl_ars is None or pnl_usd is None or mep_hoy is None:
        return {"estado": "no_disponible", "resultado_activos_ars": None, "efecto_mep_ars": None}
    resultado_activos_ars = pnl_usd * mep_hoy
    efecto_mep_ars = pnl_ars - resultado_activos_ars
    return {
        "estado": "ok",
        "resultado_activos_ars": round(resultado_activos_ars, 2),
        "efecto_mep_ars": round(efecto_mep_ars, 2),
    }


def _fmt_monto(v: float, moneda: str) -> str:
    """Formatea un monto para las frases de `explicar`: "USD 820" / "$ 1.234.567"."""
    signo = "-" if v < 0 else ""
    entero = f"{abs(round(v)):,.0f}".replace(",", ".")
    prefijo = "USD" if moneda == "usd" else "$"
    return f"{signo}{prefijo} {entero}"


def explicar(
    pnl_total: float | None,
    precio_total: float | None,
    dividendos_total: float | None,
    cupones_total: float | None,
    comisiones_total: float | None,
    moneda: str,
) -> dict:
    """Explicación en prosa para principiantes del resultado total del período.

    `comisiones_total` acá ya viene con el signo de `descomponer_ticker` (negativo = costo).
    Devuelve `{"titulo": str, "frases": list[str]}`; con `pnl_total=None` da un título genérico
    sin inventar números.
    """
    if pnl_total is None:
        return {
            "titulo": "No se pudo calcular el resultado completo de este período: faltan precios o tipo de cambio para algún instrumento.",
            "frases": [],
        }

    verbo = "subió" if pnl_total >= 0 else "bajó"
    titulo = f"Tu cartera {verbo} {_fmt_monto(abs(pnl_total), moneda)} durante el período."

    frases: list[str] = []
    if precio_total is not None and abs(precio_total) > EPS:
        origen = "provinieron" if precio_total >= 0 else "se perdieron"
        frases.append(f"{_fmt_monto(abs(precio_total), moneda)} {origen} de variaciones de precio.")

    ingresos = (dividendos_total or 0.0) + (cupones_total or 0.0)
    if dividendos_total is not None and cupones_total is not None and abs(ingresos) > EPS:
        frases.append(f"{_fmt_monto(ingresos, moneda)} de dividendos/cupones.")

    if comisiones_total is not None and abs(comisiones_total) > EPS:
        frases.append(f"{_fmt_monto(abs(comisiones_total), moneda)} se fueron en comisiones.")

    return {"titulo": titulo, "frases": frases}
