"""Motor puro del diario de operaciones: resume cómo opera el usuario a partir de sus compras y
ventas con el contexto de mercado de cada una (ver `operaciones_grafico`).

Sin DB ni red. Recibe las operaciones y los ciclos de tenencia como dicts (los de
`get_operaciones_grafico`, con el `ticker` agregado) y devuelve los números del resumen y las frases
que los cuentan en palabras. Una frase sólo se dice cuando hay muestra suficiente (`MIN_MUESTRA`):
con dos compras, "tendés a comprar caro" sería una anécdota presentada como hábito.
"""
from __future__ import annotations

MIN_MUESTRA = 3
# Umbrales de las frases. Posición en el rango de 52 semanas: 0 = mínimo anual, 100 = máximo.
RANGO_ALTO, RANGO_BAJO = 70.0, 30.0
RSI_ALTO, RSI_BAJO = 60.0, 40.0
SUBA_POSTERIOR_PCT = 10.0     # una venta "se adelantó" si a 90 días el precio estaba 10 % más arriba
MAYORIA_ALTA, MAYORIA_BAJA = 70.0, 30.0   # % de compras sobre la SMA(200)


def _media(valores: list[float]) -> float | None:
    return sum(valores) / len(valores) if valores else None


def _validos(ops: list[dict], campo: str) -> list[float]:
    return [o[campo] for o in ops if o.get(campo) is not None]


def resumir(operaciones: list[dict], ciclos: list[dict]) -> dict:
    compras = [o for o in operaciones if o["tipo"] == "compra"]
    ventas = [o for o in operaciones if o["tipo"] == "venta"]

    rsi = _validos(compras, "rsi")
    dist = _validos(compras, "dist_sma200_pct")
    rango = _validos(compras, "rango_52s_pct")
    post90 = _validos(ventas, "post_90_pct")
    cerrados = [c for c in ciclos if not c["abierto"] and c.get("resultado_pct") is not None]

    return {
        "n_compras": len(compras),
        "n_ventas": len(ventas),
        "n_rsi": len(rsi),
        "rsi_medio_compras": _media(rsi),
        "n_sma200": len(dist),
        "pct_compras_sobre_sma200": 100.0 * sum(1 for d in dist if d > 0) / len(dist) if dist else None,
        "n_rango": len(rango),
        "rango_52s_medio_compras": _media(rango),
        "n_ventas_con_post90": len(post90),
        "n_ventas_subieron": sum(1 for p in post90 if p > SUBA_POSTERIOR_PCT),
        "n_ciclos_cerrados": len(cerrados),
        "n_ciclos_ganadores": sum(1 for c in cerrados if (c.get("resultado_usd") or 0) > 0),
        "resultado_medio_ciclos_pct": _media([c["resultado_pct"] for c in cerrados]),
    }


def frases(r: dict) -> list[str]:
    """El resumen en palabras. Lista vacía si no hay de qué hablar."""
    out: list[str] = []

    if r["n_rango"] >= MIN_MUESTRA:
        m = r["rango_52s_medio_compras"]
        if m >= RANGO_ALTO:
            out.append(f"Tendés a comprar cerca de máximos: en promedio, al {m:.0f}% del rango de las últimas 52 semanas.")
        elif m <= RANGO_BAJO:
            out.append(f"Tendés a comprar cerca de mínimos: en promedio, al {m:.0f}% del rango de las últimas 52 semanas.")
        else:
            out.append(f"Comprás a mitad de camino del rango anual (en promedio, al {m:.0f}%).")

    if r["n_sma200"] >= MIN_MUESTRA:
        p = r["pct_compras_sobre_sma200"]
        sobre = round(p * r["n_sma200"] / 100)
        if p >= MAYORIA_ALTA:
            out.append(f"Comprás a favor de la tendencia: en {sobre} de {r['n_sma200']} compras el precio estaba sobre su media de 200 ruedas.")
        elif p <= MAYORIA_BAJA:
            out.append(f"Comprás las caídas: en {r['n_sma200'] - sobre} de {r['n_sma200']} compras el precio estaba bajo su media de 200 ruedas.")
        else:
            out.append(f"Comprás tanto sobre como bajo la media de 200 ruedas ({sobre} de {r['n_sma200']} sobre ella).")

    if r["n_rsi"] >= MIN_MUESTRA:
        m = r["rsi_medio_compras"]
        if m >= RSI_ALTO:
            out.append(f"Tus compras llegan con el RSI alto (promedio {m:.0f}): el precio ya venía recalentado.")
        elif m <= RSI_BAJO:
            out.append(f"Tus compras llegan con el RSI bajo (promedio {m:.0f}): comprás cuando el precio ya cayó.")

    if r["n_ventas_con_post90"] >= MIN_MUESTRA:
        k, n = r["n_ventas_subieron"], r["n_ventas_con_post90"]
        if k == 0:
            out.append(f"Ninguna de tus {n} ventas se adelantó a una suba de más de {SUBA_POSTERIOR_PCT:.0f}% a 90 días.")
        else:
            out.append(f"Vendiste antes de subas de más de {SUBA_POSTERIOR_PCT:.0f}% (a 90 días) en {k} de {n} ventas.")

    if r["n_ciclos_cerrados"] >= MIN_MUESTRA:
        k, n, m = r["n_ciclos_ganadores"], r["n_ciclos_cerrados"], r["resultado_medio_ciclos_pct"]
        signo = "+" if m >= 0 else "−"
        out.append(f"De {n} posiciones cerradas ganaste en {k}; el resultado medio fue {signo}{abs(m):.1f}%.")

    return out
