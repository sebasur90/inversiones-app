"""Exploración en Jupyter: llevar el DSL a un DataFrame y envolver el backtest para que se vea
bien en un notebook. Reusa `estrategia_engine.compilar` — cero cálculo propio.
"""
from __future__ import annotations

import pandas as pd

from ..services import estrategia_engine
from ..services.estrategia_engine import compilar

__all__ = ["a_dataframe", "ResultadoLab", "comparar_con_mascara"]


def a_dataframe(barras, dsl: dict) -> pd.DataFrame:
    """Índice = fecha; columnas OHLCV; una `f"{id}.{salida}"` por serie de indicador declarada;
    más `entrada` / `salida` (bool trivaluado del motor). `len(df) == len(barras)` siempre."""
    compilado = compilar(dsl, barras)
    df = pd.DataFrame(
        {
            "apertura": [b.apertura for b in barras],
            "maximo": [b.maximo for b in barras],
            "minimo": [b.minimo for b in barras],
            "cierre": [b.cierre for b in barras],
            "volumen": [b.volumen for b in barras],
        },
        index=pd.Index([b.fecha for b in barras], name="fecha"),
    )
    for id_, series_dict in compilado.series.items():
        for salida, valores in series_dict.items():
            df[f"{id_}.{salida}"] = valores
    df["entrada"] = compilado.entrada
    df["salida"] = compilado.salida
    return df


class ResultadoLab:
    """Envoltorio de `estrategia_engine.ResultadoBacktest` con vistas de DataFrame para Jupyter."""

    def __init__(self, resultado: estrategia_engine.ResultadoBacktest, dsl: dict):
        self._r = resultado
        self._dsl = dsl

    @property
    def metricas(self) -> dict:
        return self._r.metricas

    @property
    def advertencias(self) -> list[str]:
        return list(self._r.advertencias)

    @property
    def operaciones(self) -> pd.DataFrame:
        return pd.DataFrame([vars(o) for o in self._r.operaciones])

    @property
    def senales(self) -> pd.DataFrame:
        return pd.DataFrame([vars(s) for s in self._r.senales])

    @property
    def equity(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "equity": [v for _, v in self._r.curva_equity],
                "buy_hold": [v for _, v in self._r.curva_buy_hold],
            },
            index=pd.Index([f for f, _ in self._r.curva_equity], name="fecha"),
        )

    def _repr_html_(self) -> str:
        m = self._r.metricas
        filas = "".join(
            f"<tr><th style='text-align:left'>{k}</th><td>{m[k]}</td></tr>"
            for k in (
                "estado", "retorno_total_pct", "retorno_buy_hold_pct", "exceso_vs_buy_hold_pp",
                "operaciones", "operaciones_cerradas", "win_rate_pct", "profit_factor",
                "max_drawdown_pct", "exposicion_pct",
            )
            if k in m
        )
        adv = f"<p><em>advertencias: {', '.join(self._r.advertencias)}</em></p>" if self._r.advertencias else ""
        return f"<h4>ResultadoLab</h4><table>{filas}</table>{adv}"

    def __repr__(self) -> str:
        m = self._r.metricas
        return (
            f"<ResultadoLab retorno={m.get('retorno_total_pct')}% "
            f"ops={m.get('operaciones')} win_rate={m.get('win_rate_pct')}>"
        )


def comparar_con_mascara(estrategia, barras, mascara, *, condicion: str = "entrada") -> pd.DataFrame:
    """El camino inverso al que el builder deliberadamente no ofrece (traducir máscaras de pandas
    al DSL): devuelve las barras donde tu máscara booleana difiere de la condición ya compilada
    del DSL. Prototipás libre en pandas y después *verificás* tu traducción al builder. Las barras
    en warm-up (condición `None`) se omiten."""
    dsl = estrategia.definicion() if hasattr(estrategia, "definicion") else estrategia
    compilado = compilar(dsl, barras)
    serie = compilado.entrada if condicion == "entrada" else compilado.salida
    valores_mascara = list(mascara)

    filas = []
    for i, barra in enumerate(barras):
        dsl_val = serie[i]
        if dsl_val is None:
            continue
        msk_val = valores_mascara[i] if i < len(valores_mascara) else None
        msk_bool = bool(msk_val) if msk_val is not None else False
        if bool(dsl_val) != msk_bool:
            filas.append({
                "fecha": barra.fecha, "cierre": barra.cierre,
                "dsl": bool(dsl_val), "mascara": msk_bool,
            })
    return pd.DataFrame(filas, columns=["fecha", "cierre", "dsl", "mascara"]).set_index("fecha") \
        if filas else pd.DataFrame(columns=["cierre", "dsl", "mascara"])
