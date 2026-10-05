"""Detección de splits no ajustados en una serie de precios.

A IOL se le piden las series **sin ajustar** (`/sinAjustar`, ver `market_data/iol.py`), así que un
split queda en la serie como un escalón: el precio cae a la mitad (o a un décimo) de un día al
otro sin que haya pasado nada económico. Los indicadores técnicos leen ese escalón como un
movimiento de precio real, y un backtest puede "operar" una caída del 50% que nunca existió.

Peor: la variante `@SUB` (el subyacente en USD, que viene de yfinance) **sí** está ajustada, así
que las dos variantes del mismo ticker no son comparables aunque la UI las ofrezca juntas.

Esto **no ajusta** la serie: para eso haría falta una tabla de splits y recalcular el histórico.
Lo que hace es detectar el escalón y avisar, para que nadie saque conclusiones de un gráfico que
tiene un salto artificial.

Cómo lo distingue de un movimiento real: un salto por split tiene un ratio cercano a una fracción
simple (1:2, 1:3, 1:10, 2:1, 10:1…). Un derrumbe genuino rara vez cae exactamente a la mitad de
un día al otro. No es infalible -- de ahí que la advertencia diga "posible".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Ratios típicos de split, como `precio_nuevo / precio_viejo`. 0.5 = 1:2 (el precio se parte al
# medio y la tenencia se duplica); 2.0 = 2:1 (split inverso).
_RATIOS_CONOCIDOS: tuple[tuple[float, str], ...] = (
    (0.5, "1:2"),
    (1 / 3, "1:3"),
    (0.25, "1:4"),
    (0.2, "1:5"),
    (0.1, "1:10"),
    (0.05, "1:20"),
    (0.01, "1:100"),
    (2.0, "2:1"),
    (3.0, "3:1"),
    (4.0, "4:1"),
    (5.0, "5:1"),
    (10.0, "10:1"),
    (20.0, "20:1"),
    (100.0, "100:1"),
)

# Cuánto puede desviarse el ratio observado del teórico y seguir contando como split. 8% deja
# pasar el ruido normal de un cierre a otro sin aceptar cualquier caída fuerte como split.
TOLERANCIA = 0.08

# Por debajo de este cambio no se mira nada: evita falsos positivos en series de precios chicos
# donde el redondeo mueve el ratio.
CAMBIO_MINIMO = 0.25


@dataclass(frozen=True)
class Salto:
    """Un escalón sospechoso entre dos barras consecutivas."""
    fecha: date
    fecha_previa: date
    precio_previo: float
    precio: float
    ratio: float
    etiqueta: str  # "1:10", "2:1", …

    @property
    def descripcion(self) -> str:
        return (
            f"{self.fecha_previa.isoformat()} → {self.fecha.isoformat()}: "
            f"{self.precio_previo:g} → {self.precio:g} (≈ {self.etiqueta})"
        )


def _etiqueta_de_ratio(ratio: float) -> str | None:
    """La fracción simple a la que se parece `ratio`, o `None` si no se parece a ninguna."""
    for teorico, etiqueta in _RATIOS_CONOCIDOS:
        if abs(ratio - teorico) <= teorico * TOLERANCIA:
            return etiqueta
    return None


def detectar_saltos(barras) -> list[Salto]:
    """Escalones compatibles con un split en una serie de barras ordenada por fecha.

    `barras` es cualquier secuencia de objetos con `.fecha` y `.cierre` (sirve tanto `Barra` de
    `ohlcv_analytics` como las filas de `BarraOHLCV`).
    """
    saltos: list[Salto] = []
    previa = None
    for barra in barras:
        cierre = getattr(barra, "cierre", None)
        if cierre is None:
            continue
        cierre = float(cierre)
        if cierre <= 0:
            previa = None  # un cierre no positivo corta la comparación en vez de ensuciarla
            continue
        if previa is not None:
            anterior = float(previa.cierre)
            ratio = cierre / anterior
            if abs(ratio - 1.0) >= CAMBIO_MINIMO:
                etiqueta = _etiqueta_de_ratio(ratio)
                if etiqueta is not None:
                    saltos.append(Salto(
                        fecha=barra.fecha, fecha_previa=previa.fecha,
                        precio_previo=anterior, precio=cierre,
                        ratio=round(ratio, 6), etiqueta=etiqueta,
                    ))
        previa = barra
    return saltos
