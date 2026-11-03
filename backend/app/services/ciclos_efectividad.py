"""Adaptador DB → `ciclos_efectividad_engine`: qué pasó con el rendimiento relativo después de cada estado del ciclo.

Se recalcula siempre desde las series completas (desde que hay datos, ~2005 para la mayoría): no depende de
`ciclos_estado_historial`, que sólo guarda las últimas semanas de cada corrida. Describe el pasado; ver el motor.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from . import ciclos_analytics as ca
from . import ciclos_catalogo as cc
from . import ciclos_efectividad_engine as ee
from . import ciclos_engine as eng

ALCANCES = ("grupo", "tipo")

LECTURA = (
    "Para cada semana en que el grupo estaba en un estado confirmado, cuánto rindió contra su referencia en las semanas "
    "siguientes, comparado con lo que pasó en cualquier semana. Describe lo ocurrido: no mide si el estado sirve para anticipar nada."
)


def _advertencias(alcance: str, descartados: list[str]) -> list[str]:
    adv = [
        "Las semanas seguidas en un mismo estado se parecen mucho entre sí: lo que cuenta es la cantidad de episodios, no de semanas.",
        "Son 4 estados, 3 horizontes y 2 vistas: es esperable que alguna diferencia contra la base aparezca sólo por azar.",
        "Sólo incluye grupos que existen hoy (sin los que dejaron de existir), en dólares y sin costos, spreads ni impuestos.",
    ]
    if alcance == "tipo":
        adv.append("Al juntar grupos del mismo tipo, sus episodios no son independientes: se mueven con los mismos ciclos de mercado.")
    if descartados:
        adv.append("Sin datos suficientes, no entran: " + ", ".join(descartados) + ".")
    return adv


def efectividad(
    db: Session, grupo_id: str, *, alcance: str = "grupo", benchmark: str | None = None, hoy: date | None = None,
) -> dict:
    """`alcance="grupo"`: sólo ese grupo. `alcance="tipo"`: todos los grupos activos de su mismo tipo, juntos."""
    if alcance not in ALCANCES:
        raise ValueError(f"`alcance` debe ser uno de {', '.join(ALCANCES)}")
    cat = cc.cargar()
    g = ca._grupo(cat, grupo_id)
    fuentes = ca.Fuentes(db, cat)
    elegidos = [g] if alcance == "grupo" else [x for x in cat.activos() if x.tipo == g.tipo]
    bench_principal = ca._benchmark_efectivo(cat, g, benchmark)

    tablas, detalle, descartados = [], [], []
    for x in elegidos:
        b = ca._benchmark_efectivo(cat, x, benchmark if benchmark != x.id else None)
        a_usd = fuentes.nativa(x)
        if b is None or not a_usd:
            descartados.append(x.nombre)
            detalle.append({"id": x.id, "nombre": x.nombre, "semanas": 0, "desde": None, "hasta": None,
                            "motivo": "sin referencia" if b is None else (fuentes.motivo_sin_datos(x) or "sin datos")})
            continue
        t = ee.observaciones(a_usd, fuentes.nativa(b), x.id)
        if t["obs"]:
            tablas.append(t)
        else:
            descartados.append(x.nombre)
        detalle.append({"id": x.id, "nombre": x.nombre, "benchmark": b.nombre, "semanas": len(t["obs"]), "desde": t["desde"],
                        "hasta": t["hasta"], "motivo": t["motivo"]})

    meta_grupos = elegidos
    hasta = max((t["hasta"] for t in tablas), default=None)
    desde = min((t["desde"] for t in tablas), default=None)
    meta = ca._meta(fuentes, meta_grupos, bench_principal if alcance == "grupo" else None, moneda="USD", desde=desde, hasta=hasta,
                    ultima_fecha_datos=hasta, advertencias=_advertencias(alcance, descartados if alcance == "tipo" else []),
                    nota_moneda=False)
    base = {"alcance": alcance, "grupo": ca._info_grupo(g), "benchmark": ca._info_grupo(bench_principal) if bench_principal else None,
            "grupos": detalle, "lectura": LECTURA, "meta": meta, "version": eng.VERSION_ALGORITMO,
            "confirmacion_semanas": eng.CONFIRMACION_SEMANAS, "min_episodios": ee.MIN_EPISODIOS}
    if not tablas:
        motivo = detalle[0]["motivo"] if alcance == "grupo" and detalle else "ningún grupo tiene historia suficiente"
        return {**base, "estado": eng.ESTADO_INSUFICIENTE, "motivo": motivo, "resultado": None}
    return {**base, "estado": eng.ESTADO_OK, "motivo": None, "resultado": ee.resumir(tablas)}
