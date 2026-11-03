"""Adaptador DB → `ciclos_tasas_engine`: panel de tasas de interés del Tesoro de EE.UU.

Nivel actual, cambios en puntos porcentuales, forma de la curva y pendientes (larga − corta). Describe lo que muestran
los datos: una curva invertida no es un pronóstico. Las series las baja la misma ingesta de Ciclos (Yahoo, índices CBOE).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from . import ciclos_analytics as ca
from . import ciclos_catalogo as cc
from . import ciclos_engine as eng
from . import ciclos_tasas_engine as te

ANIOS_MAX = 20

LIMITACIONES = (
    "Son tasas de EE.UU. tomadas de Yahoo Finance (índices CBOE): una fuente no oficial, que puede tener huecos o atrasos. No representan las tasas de Argentina.",
    "Una tasa es un nivel en % anual, no un precio: sus cambios se miden en puntos porcentuales (pp), no en %.",
    "La tasa de 3 meses es el rendimiento de la Letra a 13 semanas; las demás, el de los bonos con cupón a ese plazo.",
    "Describe las tasas de hoy y su historia; no anticipa su evolución ni dice qué hacer con ellas.",
)


def _item(fuentes: ca.Fuentes, t: cc.Tasa, hoy: date, anios: int) -> dict:
    base = {"id": t.id, "nombre": t.nombre, "simbolo": t.simbolo, "plazo_meses": t.plazo_meses, "descripcion": t.descripcion}
    serie = fuentes.tasa(t)
    if not serie:
        return {**base, "estado": eng.ESTADO_SIN_DATOS, "motivo": fuentes.motivo_sin_datos_simbolo(t.simbolo), "nivel": None,
                "fecha": None, "cambios": {}, "minimo": None, "maximo": None}
    actual = te.nivel_actual(serie, hoy)
    ventana = [v for f, v in serie if f >= eng.restar_meses(actual["fecha"], anios * 12)]
    return {
        **base, "estado": eng.ESTADO_DESACTUALIZADO if actual["desactualizada"] else eng.ESTADO_OK,
        "motivo": f"el último dato es del {actual['fecha'].isoformat()}" if actual["desactualizada"] else None,
        "nivel": actual["nivel"], "fecha": actual["fecha"], "desde": serie[0][0],
        "cambios": te.cambios(serie, actual["fecha"]), "minimo": min(ventana), "maximo": max(ventana),
    }


def panorama(db: Session, *, anios: int = 5, hoy: date | None = None) -> dict:
    """Tasas, pendientes de la curva y serie semanal de los últimos `anios` años."""
    if not 1 <= anios <= ANIOS_MAX:
        raise ValueError(f"`anios` debe estar entre 1 y {ANIOS_MAX}")
    hoy = hoy or date.today()
    cat = cc.cargar()
    fuentes = ca.Fuentes(db, cat)
    tasas = cat.tasas_activas()
    series = {t.id: fuentes.tasa(t) for t in tasas}
    items = [_item(fuentes, t, hoy, anios) for t in tasas]
    con_datos = [i for i in items if i["nivel"] is not None]
    ultimo = max((i["fecha"] for i in con_datos), default=None)

    pendientes = []
    series_pend: dict[str, eng.Serie] = {}
    desde = eng.restar_meses(ultimo, anios * 12) if ultimo else None
    for p in cat.pendientes_curva:
        larga, corta = series.get(p["larga"], []), series.get(p["corta"], [])
        if not larga or not corta or ultimo is None:
            pendientes.append({**p, "estado": eng.ESTADO_SIN_DATOS, "valor_pp": None, "fecha": None, "invertida": None,
                               "desactualizada": False, "semanas_invertida_52": None, "semanas_52": 0, "cambios": {}})
            continue
        sp = te.pendiente(larga, corta, eng.restar_meses(ultimo, max(anios * 12, 12)), ultimo)
        series_pend[f"pendiente:{p['id']}"] = sp
        r = te.resumen_pendiente(sp, hoy)
        pendientes.append({**p, "estado": eng.ESTADO_OK if r["valor_pp"] is not None else eng.ESTADO_SIN_DATOS, **r,
                           "cambios": te.cambios(sp, r["fecha"]) if r["fecha"] else {}})

    filas = []
    if ultimo is not None:
        niveles = {t.id: series[t.id] for t in tasas}
        filas = te.filas_semanales(niveles, desde, ultimo)
        for f in filas:
            for k, sp in series_pend.items():
                f[k] = te.valor_en(sp, f["fecha"], 0)

    curva = [{"id": i["id"], "nombre": i["nombre"], "plazo_meses": i["plazo_meses"], "nivel": i["nivel"],
              "hace_un_anio": te.valor_en(series[i["id"]], eng.restar_meses(i["fecha"], 12), te.TOLERANCIA_DIAS) if i["fecha"] else None}
             for i in con_datos]

    meta = ca._meta(fuentes, [], None, moneda="% anual", desde=desde, hasta=ultimo, ultima_fecha_datos=ultimo, nota_moneda=False,
                    advertencias=[f"{i['nombre']}: {i['motivo']}." for i in items if i["estado"] != eng.ESTADO_OK and i["motivo"]])
    meta["fuente"] = "Yahoo Finance (índices CBOE de rendimientos del Tesoro de EE.UU.)"
    meta["limitaciones"] = list(LIMITACIONES)
    return {
        "estado": eng.ESTADO_OK if con_datos else eng.ESTADO_SIN_DATOS,
        "motivo": None if con_datos else "todavía no se descargaron las series de tasas (la ingesta de ciclos no corrió)",
        "anios": anios, "tasas": items, "pendientes": pendientes, "curva": curva, "filas": filas,
        "lectura": "Nivel de cada tasa y cambios en puntos porcentuales. La pendiente es la tasa larga menos la corta en la misma fecha; "
                   "si es negativa, las tasas cortas superan a las largas. Es un hecho de los datos de hoy, no un pronóstico.",
        "meta": meta,
    }
