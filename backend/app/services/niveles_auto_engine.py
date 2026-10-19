"""Motor puro de soportes y resistencias automáticos.

Sin DB ni red. Trabaja con `indicadores_engine.Barra`.

Método:
1. **Pivotes** con fractales de ventana `N`: un máximo es pivote si es mayor que los `N` máximos
   de la izquierda y no menor que los `N` de la derecha (en una meseta cuenta el primero); el
   mínimo, simétrico. Un pivote sólo se confirma `N` barras después, así que las últimas `N`
   barras no tienen.
2. **Agrupado** por cercanía: pivotes (máximos y mínimos juntos: un techo roto suele volverse
   piso) que quedan a menos de `tolerancia_atr × ATR(14)` del promedio del grupo son un mismo
   nivel, cuyo precio es el promedio de sus pivotes.
3. **Puntaje** = suma, sobre los pivotes del nivel, de un peso que se reduce a la mitad cada
   `vida_media` barras de antigüedad: más toques y más recientes pesan más.
4. Se devuelven los `max_por_lado` más fuertes **por encima** del último cierre (resistencias) y
   los más fuertes **por debajo** (soportes). Un nivel de un solo toque es ruido, no un nivel:
   hacen falta al menos `min_toques`.
"""
from __future__ import annotations

from . import indicadores_engine as ind

VENTANA_FRACTAL = 5
TOLERANCIA_ATR = 0.5
MAX_POR_LADO = 3
MIN_TOQUES = 2
# Si la serie es muy corta para tener ATR, la tolerancia es una fracción del último cierre.
TOLERANCIA_SIN_ATR_PCT = 0.01


def pivotes(barras: list[ind.Barra], ventana: int = VENTANA_FRACTAL) -> list[tuple[int, float, str]]:
    """`(indice, precio, "maximo"|"minimo")` de cada pivote confirmado, en orden de índice."""
    n = len(barras)
    hl = [ind._hl(b) for b in barras]
    out: list[tuple[int, float, str]] = []
    for i in range(ventana, n - ventana):
        alto, bajo = hl[i]
        izq_alto = [hl[j][0] for j in range(i - ventana, i)]
        der_alto = [hl[j][0] for j in range(i + 1, i + ventana + 1)]
        if alto > max(izq_alto) and alto >= max(der_alto):
            out.append((i, alto, "maximo"))
        izq_bajo = [hl[j][1] for j in range(i - ventana, i)]
        der_bajo = [hl[j][1] for j in range(i + 1, i + ventana + 1)]
        if bajo < min(izq_bajo) and bajo <= min(der_bajo):
            out.append((i, bajo, "minimo"))
    return out


def niveles_automaticos(
    barras: list[ind.Barra], ventana: int = VENTANA_FRACTAL, tolerancia_atr: float = TOLERANCIA_ATR,
    max_por_lado: int = MAX_POR_LADO, min_toques: int = MIN_TOQUES,
) -> list[dict]:
    """Los niveles más fuertes sobre y bajo el último cierre, de mayor a menor precio:
    `{precio, toques, ultima_fecha, tipo: "resistencia"|"soporte", puntaje}`."""
    n = len(barras)
    pv = pivotes(barras, ventana)
    if not pv:
        return []

    ultimo_cierre = barras[-1].cierre
    atr_valores = [v for v in ind.atr(barras, 14) if v is not None]
    tolerancia = (
        tolerancia_atr * atr_valores[-1] if atr_valores else TOLERANCIA_SIN_ATR_PCT * abs(ultimo_cierre)
    )
    vida_media = max(63, n // 3)

    # Agrupado: se recorre por precio y cada pivote se une al grupo vigente si queda cerca de su promedio.
    grupos: list[list[tuple[int, float, str]]] = []
    for p in sorted(pv, key=lambda x: x[1]):
        if grupos and abs(p[1] - sum(q[1] for q in grupos[-1]) / len(grupos[-1])) <= tolerancia:
            grupos[-1].append(p)
        else:
            grupos.append([p])

    niveles = []
    for g in grupos:
        if len(g) < min_toques:
            continue
        precio = sum(q[1] for q in g) / len(g)
        puntaje = sum(0.5 ** ((n - 1 - q[0]) / vida_media) for q in g)
        niveles.append({
            "precio": precio, "toques": len(g), "ultima_fecha": barras[max(q[0] for q in g)].fecha,
            "tipo": "resistencia" if precio > ultimo_cierre else "soporte", "puntaje": puntaje,
        })

    elegidos: list[dict] = []
    for tipo in ("resistencia", "soporte"):
        del_lado = sorted((x for x in niveles if x["tipo"] == tipo), key=lambda x: -x["puntaje"])
        elegidos.extend(del_lado[:max_por_lado])
    return sorted(elegidos, key=lambda x: -x["precio"])
