"""Capa de progreso del "ritmo de aportes": niveles, objetivo mensual, logros, récords y misión.

Puro como `aportes_engine`: no toca `Session`, DB ni FastAPI. Recibe lo que aquel ya calculó
(la serie mensual completa y sus estadísticas) más el objetivo del usuario, y devuelve un dict
plano que `schemas.ProgresoAportesOut` valida tal cual.

Vive aparte de `aportes_engine` porque es otro dominio: aquél mide *cuánto* aportás contra tu
propio historial; éste mide *si estás construyendo un hábito*. Son dos catálogos de constantes y
dos archivos de tests distintos, y el motor viejo ya tiene 700 líneas.

Supuestos documentados:
- **Los niveles premian sólo la constancia**, nunca el monto: dependen de meses con aporte y de la
  *mejor* racha, no de cuánta plata entró ni del rendimiento. Se usa la mejor racha y no la actual
  para que un mes flojo no te degrade: **un nivel alcanzado no se pierde**.
- **El cumplimiento del objetivo no entra en el nivel.** Si entrara, configurar una meta podría
  bajarte de nivel, que es exactamente el castigo que un sistema de hábito debe evitar. El
  cumplimiento alimenta logros, récords y misión, y se muestra como sello aparte.
- **Sin objetivo configurado no se inventa ninguno**: todo lo que dependa de él vale `None` y los
  logros de esa familia quedan en "no aplica" con su motivo, nunca en "incumplido".
- Un objetivo recién creado **no juzga el pasado**: se mide desde `vigente_desde`, salvo que el
  usuario pida explícitamente aplicarlo a todo su historial.
- La proyección "si mantengo este ritmo" es aritmética pura: aporte × meses, **sin rendimiento**.
"""
from __future__ import annotations

from datetime import date

EPS = 1e-9

# Escalones de racha y de capital: los mismos de `aportes_engine`, para que los hitos de la
# pestaña Análisis y los logros de Progreso nunca se contradigan.
from .aportes_engine import HITOS_RACHA_MESES, HITOS_TOTAL_USD, _nombre_mes, _usd

# Capital: se agrega el escalón de 1.000, que en `HITOS_TOTAL_USD` no está y es el primer logro
# realista de quien recién arranca.
LOGROS_TOTAL_USD = (1_000,) + HITOS_TOTAL_USD
# Meses con aporte acumulados (no necesariamente seguidos).
LOGROS_MESES_CON_APORTE = (6, 12, 24, 36, 60)
# Meses cumpliendo el objetivo, sueltos y consecutivos.
LOGROS_OBJETIVO_TOTAL = (1, 3, 6, 12)
LOGROS_OBJETIVO_RACHA = (3, 6, 12)
# Horizontes de la proyección "si mantengo este ritmo", en años.
HORIZONTES_ANIOS = (1, 3, 5, 10)
# Aumentos que se ofrecen en "¿y si aportás un poco más?", en USD/mes.
AUMENTOS_USD = (50, 100)
# Un objetivo se considera cumplido con esta tolerancia relativa: quedar a USD 0,40 de la meta
# por el redondeo del MEP no es incumplir.
TOLERANCIA_CUMPLIMIENTO = 0.995
# Racha de cumplimiento a partir de la cual se muestra el sello en el header de nivel.
MESES_SELLO_OBJETIVO = 3
# El sugerido para el modal se redondea a múltiplos de esto, para no proponer "USD 287,43".
REDONDEO_SUGERIDO = 10

# (clave, nombre, emoji, meses con aporte, mejor racha). Orden ascendente; se evalúa de atrás
# hacia adelante y gana el más alto cuyos dos requisitos se cumplen.
NIVELES = (
    ("sin_arrancar", "Sin arrancar", "🌱", 0, 0),
    ("primer_paso", "Primer paso", "👣", 1, 0),
    ("construyendo", "Construyendo el hábito", "🌿", 3, 0),
    ("frecuente", "Inversor frecuente", "🍀", 6, 2),
    ("constante", "Inversor constante", "🔥", 9, 3),
    ("disciplinado", "Inversor disciplinado", "🎯", 12, 6),
    ("constructor", "Constructor de patrimonio", "🚀", 18, 12),
    ("consolidado", "Hábito consolidado", "🏆", 24, 24),
)

ETIQUETA_REQUISITO = {
    "meses_con_aporte": "Meses con aporte",
    "mejor_racha": "Meses seguidos aportando",
}
# La misma idea en singular/plural, para que "te faltan 1 meses" no exista.
FALTA_REQUISITO = {
    "meses_con_aporte": ("mes con aporte", "meses con aporte"),
    "mejor_racha": ("mes seguido aportando", "meses seguidos aportando"),
}


def _r(v: float | None, nd: int = 2) -> float | None:
    return None if v is None else round(v, nd)


def _pct(parte: float, total: float) -> float | None:
    return None if total <= EPS else parte / total * 100


def _meses_entre(desde: str, hasta: str) -> int:
    """Cantidad de meses de [desde, hasta], ambos inclusive. 0 si están al revés."""
    a_anio, a_mes = int(desde[:4]), int(desde[5:7])
    b_anio, b_mes = int(hasta[:4]), int(hasta[5:7])
    return max(0, (b_anio * 12 + b_mes) - (a_anio * 12 + a_mes) + 1)


# ── Objetivo mensual ─────────────────────────────────────────────────────────

def _cumple(neto: float, objetivo: float) -> bool:
    return neto >= objetivo * TOLERANCIA_CUMPLIMIENTO


def _sugerir(estadisticas: dict) -> tuple[float | None, str | None]:
    """Valor con el que se precarga el modal: el ritmo que el usuario ya demostró tener.

    No es un objetivo: es una sugerencia editable, y se redondea para que no parezca un cálculo
    de precisión falsa.
    """
    for clave, origen in (
        ("promedio_12_usd", "promedio_12"),
        ("promedio_6_usd", "promedio_6"),
        ("promedio_3_usd", "promedio_3"),
        ("promedio_usd", "promedio_historico"),
    ):
        valor = estadisticas.get(clave)
        if valor is not None and valor > EPS:
            redondeado = round(valor / REDONDEO_SUGERIDO) * REDONDEO_SUGERIDO
            return float(max(REDONDEO_SUGERIDO, redondeado)), origen
    return None, None


def _evaluar_objetivo(items: list[dict], objetivo: dict | None, primer_mes: str,
                      mes_actual: str, hoy: date, estadisticas: dict) -> dict:
    """Cumplimiento mes a mes + el detalle del mes en curso.

    Los meses anteriores a `vigente_desde` quedan en `None` (no en `False`): no se incumple una
    meta que todavía no existía.
    """
    sugerido, sugerido_origen = _sugerir(estadisticas)
    if objetivo is None:
        return {
            "configurado": False,
            "monto_usd": None,
            "vigente_desde": None,
            "fijado_en": None,
            "retroactivo": False,
            "sugerido_usd": sugerido,
            "sugerido_origen": sugerido_origen,
            "mes_actual": None,
            "meses_evaluados": None,
            "meses_cumplidos": None,
            "meses_cumplidos_pct": None,
            "racha_cumplimiento": None,
            "record_cumplimiento": None,
            "por_mes": {},
        }

    monto = float(objetivo["monto_usd"])
    desde = primer_mes if objetivo.get("retroactivo") else max(objetivo["vigente_desde"], primer_mes)

    # Cumplimiento sólo sobre meses cerrados y vigentes: el mes en curso se juzga aparte, cuando
    # termine, y los futuros no existen.
    por_mes: dict[str, dict] = {}
    cerrados_vigentes = []
    for it in items:
        if it["futuro"] or it["mes"] < desde:
            continue
        cumple = None if it["en_curso"] else _cumple(it["neto"], monto)
        por_mes[it["mes"]] = {
            "objetivo_usd": monto,
            "cumplimiento_pct": _r(_pct(it["neto"], monto), 1),
            "cumple_objetivo": cumple,
        }
        if cumple is not None:
            cerrados_vigentes.append((it["mes"], cumple))

    cumplidos = sum(1 for _, c in cerrados_vigentes if c)
    racha = 0
    for _, c in reversed(cerrados_vigentes):
        if c:
            racha += 1
        else:
            break
    record, corrida = 0, 0
    for _, c in cerrados_vigentes:
        corrida = corrida + 1 if c else 0
        record = max(record, corrida)

    actual = next((it for it in items if it["en_curso"]), None)
    aportado = actual["neto"] if actual else 0.0
    restante = max(0.0, monto - aportado)
    dias_restantes = _dias_restantes(hoy)
    proyeccion = aportado * _dias_mes(hoy) / hoy.day if hoy.day else 0.0

    mes_en_curso = {
        "objetivo_usd": monto,
        "aportado_usd": _r(aportado),
        "cumplimiento_pct": _r(_pct(aportado, monto), 1),
        "restante_usd": _r(restante),
        "cumplido": _cumple(aportado, monto),
        "vigente": mes_actual >= desde,
        "dias_restantes": dias_restantes,
        # Ritmo que haría falta de acá al cierre. Con el mes ya cumplido o sin días por delante
        # no hay ritmo que pedir: `None`, y la UI no muestra la línea.
        "ritmo_necesario_diario_usd": (
            _r(restante / dias_restantes) if restante > EPS and dias_restantes > 0 else None
        ),
        "ritmo_necesario_semanal_usd": (
            _r(restante / max(1.0, dias_restantes / 7)) if restante > EPS and dias_restantes > 0 else None
        ),
        "alcanzable_al_ritmo_actual": _cumple(proyeccion, monto),
    }

    return {
        "configurado": True,
        "monto_usd": _r(monto),
        # `vigente_desde` es el mes desde el que realmente se está midiendo (con `retroactivo`,
        # el primer mes del historial). `fijado_en` es el mes en que el usuario creó el objetivo:
        # es el que hay que mostrarle cuando explica qué pasa al desmarcar la retroactividad.
        "vigente_desde": desde,
        "fijado_en": objetivo["vigente_desde"],
        "retroactivo": bool(objetivo.get("retroactivo")),
        "sugerido_usd": sugerido,
        "sugerido_origen": sugerido_origen,
        "mes_actual": mes_en_curso,
        "meses_evaluados": len(cerrados_vigentes),
        "meses_cumplidos": cumplidos,
        "meses_cumplidos_pct": _r(_pct(cumplidos, len(cerrados_vigentes)), 1),
        "racha_cumplimiento": racha,
        "record_cumplimiento": record,
        "por_mes": por_mes,
    }


def _dias_mes(hoy: date) -> int:
    import calendar
    return calendar.monthrange(hoy.year, hoy.month)[1]


def _dias_restantes(hoy: date) -> int:
    return _dias_mes(hoy) - hoy.day


# ── Nivel de constancia ──────────────────────────────────────────────────────

def _nivel(meses_con_aporte: int, mejor_racha: int) -> dict:
    """El nivel más alto cuyos dos requisitos se cumplen, con el porqué explícito.

    Nunca baja: ambos ejes son monótonos (meses acumulados y *mejor* racha histórica).
    """
    idx = 0
    for i, (_, _, _, req_meses, req_racha) in enumerate(NIVELES):
        if meses_con_aporte >= req_meses and mejor_racha >= req_racha:
            idx = i
    clave, nombre, emoji, req_meses, req_racha = NIVELES[idx]

    motivos = []
    if meses_con_aporte > 0:
        motivos.append(
            f"Aportaste en {meses_con_aporte} {'mes' if meses_con_aporte == 1 else 'meses'}"
        )
    if mejor_racha > 0:
        motivos.append(
            f"Tu mejor racha es de {mejor_racha} {'mes' if mejor_racha == 1 else 'meses'} seguidos"
        )
    if not motivos:
        motivos.append("Todavía no registraste ningún aporte")

    siguiente = None
    if idx + 1 < len(NIVELES):
        s_clave, s_nombre, s_emoji, s_meses, s_racha = NIVELES[idx + 1]
        requisitos = [
            {
                "clave": "meses_con_aporte",
                "etiqueta": ETIQUETA_REQUISITO["meses_con_aporte"],
                "actual": meses_con_aporte,
                "objetivo": s_meses,
                "cumple": meses_con_aporte >= s_meses,
            },
            {
                "clave": "mejor_racha",
                "etiqueta": ETIQUETA_REQUISITO["mejor_racha"],
                "actual": mejor_racha,
                "objetivo": s_racha,
                "cumple": mejor_racha >= s_racha,
            },
        ]
        # Sólo cuentan los requisitos que piden algo: un objetivo en 0 ya está cumplido y
        # metido en el promedio daría un progreso inflado.
        con_exigencia = [r for r in requisitos if r["objetivo"] > 0]
        progreso = (
            min(100.0, min(r["actual"] / r["objetivo"] for r in con_exigencia) * 100)
            if con_exigencia else 100.0
        )
        faltan = [r for r in requisitos if not r["cumple"]]
        partes = []
        for r in faltan:
            n = r["objetivo"] - r["actual"]
            singular, plural = FALTA_REQUISITO[r["clave"]]
            partes.append(f"{n} {singular if n == 1 else plural}")
        verbo = "Te falta" if len(faltan) == 1 and faltan[0]["objetivo"] - faltan[0]["actual"] == 1 else "Te faltan"
        siguiente = {
            "clave": s_clave,
            "nombre": s_nombre,
            "emoji": s_emoji,
            "requisitos": requisitos,
            "progreso_pct": _r(progreso, 1),
            "falta_texto": f"{verbo} {' y '.join(partes)}" if faltan else "Ya cumplís los requisitos",
        }

    return {
        "clave": clave,
        "nombre": nombre,
        "emoji": emoji,
        "orden": idx,
        "total_niveles": len(NIVELES) - 1,
        "motivos": motivos,
        "siguiente": siguiente,
        "sello_objetivo": None,  # lo completa `calcular_progreso` si hay racha de cumplimiento
    }


# ── Logros ───────────────────────────────────────────────────────────────────

def _logro(clave, titulo, descripcion, categoria, emoji, unidad, objetivo, actual,
           fecha=None, sin_objetivo=False) -> dict:
    desbloqueado = actual is not None and actual >= objetivo - EPS
    return {
        "clave": clave,
        "titulo": titulo,
        "descripcion": descripcion,
        "categoria": categoria,
        "emoji": emoji,
        "unidad": unidad,
        "objetivo": float(objetivo),
        "actual": None if actual is None else _r(float(actual)),
        "progreso_pct": None if actual is None else _r(min(100.0, max(0.0, actual / objetivo * 100)), 1),
        "desbloqueado": desbloqueado,
        "fecha": fecha if desbloqueado else None,
        "bloqueado_por_falta_objetivo": sin_objetivo,
    }


def _fechas_desbloqueo(items: list[dict]) -> dict[str, str]:
    """Una sola pasada cronológica: en qué mes se cruzó cada umbral de capital, de racha y de
    meses con aporte. Sirve para poder decir "lo lograste en marzo 2024" y no sólo "lo lograste"."""
    fechas: dict[str, str] = {}
    acumulado = 0.0
    corrida = 0
    con_aporte = 0
    for it in items:
        if it["futuro"]:
            break
        acumulado += it["neto"]
        if it["neto"] > EPS:
            corrida += 1
            con_aporte += 1
            fechas.setdefault("primer_aporte", it["mes"])
        else:
            corrida = 0
        for u in LOGROS_TOTAL_USD:
            if acumulado >= u - EPS:
                fechas.setdefault(f"total_{u}", it["mes"])
        for u in HITOS_RACHA_MESES:
            if corrida >= u:
                fechas.setdefault(f"racha_{u}", it["mes"])
        for u in LOGROS_MESES_CON_APORTE:
            if con_aporte >= u:
                fechas.setdefault(f"meses_{u}", it["mes"])
    return fechas


def _anio_completo(items: list[dict], hoy: date) -> tuple[int, str | None]:
    """Mejor cantidad de meses con aporte dentro de un año calendario ya cerrado, y el año en que
    se completaron los 12. Un año en curso no cuenta: todavía puede fallar."""
    por_anio: dict[int, int] = {}
    for it in items:
        if it["futuro"] or it["anio"] >= hoy.year:
            continue
        por_anio.setdefault(it["anio"], 0)
        if it["neto"] > EPS:
            por_anio[it["anio"]] += 1
    if not por_anio:
        return 0, None
    mejor = max(por_anio.values())
    anio = next((a for a in sorted(por_anio) if por_anio[a] >= 12), None)
    return mejor, f"{anio}-12" if anio else None


def _logros(items: list[dict], estadisticas: dict, rachas: dict, objetivo: dict,
            hoy: date, mejor_anio: dict | None, ytd: float,
            meses_con_aporte: int, mejor_racha: int) -> list[dict]:
    fechas = _fechas_desbloqueo(items)
    total = estadisticas["total_neto_usd"] or 0.0
    mejor_mes = estadisticas.get("mejor_mes")

    out = [
        _logro("primer_aporte", "Primer aporte", "Registraste tu primer aporte.",
               "inicio", "🏁", "conteo", 1, min(meses_con_aporte, 1), fechas.get("primer_aporte")),
    ]

    for u in HITOS_RACHA_MESES:
        out.append(_logro(
            f"racha_{u}", f"{u} meses seguidos",
            f"Aportaste {u} meses consecutivos sin saltarte ninguno.",
            "constancia", "🔥", "meses", u, mejor_racha, fechas.get(f"racha_{u}")))

    for u in LOGROS_MESES_CON_APORTE:
        out.append(_logro(
            f"meses_{u}", f"{u} meses aportando",
            f"Llegaste a {u} meses con aporte, seguidos o no.",
            "constancia", "📅", "meses", u, meses_con_aporte, fechas.get(f"meses_{u}")))

    mejor_anio_meses, fecha_anio = _anio_completo(items, hoy)
    out.append(_logro(
        "anio_completo", "Un año entero", "Aportaste los 12 meses de un mismo año calendario.",
        "constancia", "🗓️", "meses", 12, mejor_anio_meses, fecha_anio))

    for u in LOGROS_TOTAL_USD:
        out.append(_logro(
            f"total_{u}", f"{_usd(u)} aportados",
            f"Tu capital aportado neto superó los {_usd(u)}.",
            "capital", "💰", "usd", u, total, fechas.get(f"total_{u}")))

    # Mejora personal: sólo tiene sentido con un año cerrado contra el cual compararse.
    if mejor_anio is not None:
        out.append(_logro(
            "supera_mejor_anio", "Tu mejor año",
            f"Este año ya superó a {mejor_anio['anio']}, tu mejor año hasta ahora.",
            "mejora", "📈", "usd", max(mejor_anio["total_usd"], EPS), ytd,
            f"{hoy.year}-{hoy.month:02d}"))

    sin_obj = not objetivo["configurado"]
    cumplidos = objetivo["meses_cumplidos"]
    racha_obj = None if sin_obj else max(objetivo["racha_cumplimiento"], objetivo["record_cumplimiento"])
    for u in LOGROS_OBJETIVO_TOTAL:
        out.append(_logro(
            f"objetivo_{u}", f"Objetivo cumplido ×{u}" if u > 1 else "Objetivo cumplido",
            f"Cumpliste tu objetivo mensual en {u} {'mes' if u == 1 else 'meses'}.",
            "objetivo", "🎯", "meses", u, cumplidos, None, sin_objetivo=sin_obj))
    for u in LOGROS_OBJETIVO_RACHA:
        out.append(_logro(
            f"objetivo_racha_{u}", f"{u} meses seguidos cumpliendo",
            f"Cumpliste tu objetivo {u} meses consecutivos.",
            "objetivo", "🏅", "meses", u, racha_obj, None, sin_objetivo=sin_obj))

    # Desbloqueados primero (los más recientes arriba), después lo que está más cerca de caer, y
    # al final lo que ni siquiera se puede intentar todavía.
    out.sort(key=lambda l: (
        not l["desbloqueado"],
        -(int(l["fecha"].replace("-", "")) if l["desbloqueado"] and l["fecha"] else 0),
        l["bloqueado_por_falta_objetivo"],
        -(l["progreso_pct"] or 0),
    ))
    return out


# ── Récords ──────────────────────────────────────────────────────────────────

def _records(estadisticas: dict, rachas: dict, por_anio: list[dict], objetivo: dict,
             items: list[dict]) -> dict:
    cerrados_por_anio = [a for a in por_anio if not a["en_curso"]]
    mayor_anual = max(cerrados_por_anio, key=lambda a: a["total_usd"], default=None)
    con_promedio = [a for a in cerrados_por_anio if a["promedio_mensual_usd"] is not None]
    mayor_promedio = max(con_promedio, key=lambda a: a["promedio_mensual_usd"], default=None)

    mas_cumpliendo = None
    if objetivo["configurado"]:
        por_anio_cumplidos: dict[int, int] = {}
        for it in items:
            det = objetivo["por_mes"].get(it["mes"])
            if det and det["cumple_objetivo"]:
                por_anio_cumplidos[it["anio"]] = por_anio_cumplidos.get(it["anio"], 0) + 1
        if por_anio_cumplidos:
            anio = max(por_anio_cumplidos, key=lambda a: (por_anio_cumplidos[a], -a))
            mas_cumpliendo = {"anio": anio, "meses": por_anio_cumplidos[anio]}

    record_racha = rachas["aportando_record"]
    return {
        "mayor_aporte_mensual": estadisticas.get("mejor_mes"),
        "mejor_racha": {
            "meses": record_racha["meses"],
            "desde": record_racha["desde"],
            "hasta": record_racha["hasta"],
        },
        "mayor_aporte_anual": (
            {"anio": mayor_anual["anio"], "total_usd": mayor_anual["total_usd"]}
            if mayor_anual else None
        ),
        "mayor_promedio_mensual_anual": (
            {"anio": mayor_promedio["anio"], "promedio_usd": mayor_promedio["promedio_mensual_usd"]}
            if mayor_promedio else None
        ),
        "mas_meses_cumpliendo_objetivo": mas_cumpliendo,
    }


# ── Evolución, proyección y misión ───────────────────────────────────────────

def _evolucion(estado_ritmo: dict, estadisticas: dict) -> dict:
    """Frase objetiva sobre la tendencia. Describe, no culpa: "bajó 15%", nunca "deberías aportar
    más". El umbral de "estable" es el mismo que usa `aportes_engine` para el estado del ritmo."""
    from .aportes_engine import UMBRAL_TENDENCIA_PCT

    p3 = estado_ritmo.get("promedio_3_usd")
    p3_ant = estado_ritmo.get("promedio_3_anterior_usd")
    delta = estado_ritmo.get("tendencia_3v3_pct")

    if p3 is None or p3_ant is None or delta is None:
        meses = estadisticas["meses_historia"]
        return {
            "clave": "sin_historial",
            "frase": (
                f"Todavía no hay dos trimestres para comparar: llevás {meses} "
                f"{'mes cerrado' if meses == 1 else 'meses cerrados'}."
            ),
            "delta_pct": None,
            "promedio_actual_usd": _r(p3),
            "promedio_anterior_usd": _r(p3_ant),
        }

    if delta >= UMBRAL_TENDENCIA_PCT:
        clave = "sube"
        frase = (f"Tu promedio de los últimos 3 meses ({_usd(p3)}) está {abs(delta):.0f}% arriba "
                 f"del trimestre anterior ({_usd(p3_ant)}).")
    elif delta <= -UMBRAL_TENDENCIA_PCT:
        clave = "baja"
        frase = (f"Tu promedio de los últimos 3 meses ({_usd(p3)}) está {abs(delta):.0f}% abajo "
                 f"del trimestre anterior ({_usd(p3_ant)}).")
    else:
        clave = "estable"
        frase = (f"Tu promedio mensual se mantiene estable: {_usd(p3)} en los últimos 3 meses "
                 f"contra {_usd(p3_ant)} en los 3 anteriores.")
    return {
        "clave": clave,
        "frase": frase,
        "delta_pct": _r(delta, 1),
        "promedio_actual_usd": _r(p3),
        "promedio_anterior_usd": _r(p3_ant),
    }


def _proyeccion_ritmo(estadisticas: dict) -> dict:
    """Cuánto habrías aportado en 1/3/5/10 años sosteniendo el ritmo actual. Sin rendimiento: es
    una suma, no una predicción, y el disclaimer viaja en el payload para que la UI no lo olvide."""
    ritmo, origen = None, "insuficiente"
    for clave, nombre in (
        ("promedio_12_usd", "promedio_12"),
        ("promedio_6_usd", "promedio_6"),
        ("promedio_3_usd", "promedio_3"),
        ("promedio_usd", "promedio_historico"),
    ):
        valor = estadisticas.get(clave)
        if valor is not None and valor > EPS:
            ritmo, origen = valor, nombre
            break

    horizontes = [] if ritmo is None else [
        {"anios": a, "meses": a * 12, "total_usd": _r(ritmo * a * 12)} for a in HORIZONTES_ANIOS
    ]
    escenarios = [] if ritmo is None else [
        {
            "clave": f"mas_{d}",
            "delta_mensual_usd": float(d),
            "ritmo_resultante_usd": _r(ritmo + d),
            "horizontes": [
                {
                    "anios": a,
                    "meses": a * 12,
                    "total_usd": _r((ritmo + d) * a * 12),
                    "extra_usd": _r(d * a * 12),
                }
                for a in HORIZONTES_ANIOS
            ],
        }
        for d in AUMENTOS_USD
    ]
    return {
        "ritmo_mensual_usd": _r(ritmo),
        "origen": origen,
        "horizontes": horizontes,
        "escenarios_aumento": escenarios,
        "disclaimer": (
            "Proyección basada únicamente en mantener el ritmo de aportes actual. "
            "No incluye rendimiento de las inversiones ni inflación."
        ),
    }


def _mision(objetivo: dict, rachas: dict, estadisticas: dict, hoy: date,
            meses_con_aporte: int) -> dict | None:
    """El próximo paso concreto, siempre de comportamiento y nunca de mercado.

    Se elige la primera regla aplicable, de más inmediata a más lejana. Nunca pide aportar más de
    lo que el propio historial muestra que el usuario puede.
    """
    from .aportes_engine import MESES_NOMBRE

    if meses_con_aporte == 0:
        return {
            "clave": "primer_aporte",
            "titulo": "Hacé tu primer aporte",
            "detalle": "Cuando registres tu primera compra vas a empezar a construir tu historial.",
            "unidad": "conteo",
            "actual": 0.0,
            "objetivo": 1.0,
            "progreso_pct": 0.0,
            "por_que": "Todavía no hay movimientos de compra registrados.",
        }

    mes_txt = MESES_NOMBRE[hoy.month - 1]
    if objetivo["configurado"] and objetivo["mes_actual"] and objetivo["mes_actual"]["vigente"]:
        mes = objetivo["mes_actual"]
        if not mes["cumplido"]:
            return {
                "clave": "objetivo_mes",
                "titulo": f"Completar tu objetivo de {mes_txt}",
                "detalle": f"Llevás {_usd(mes['aportado_usd'])} de {_usd(mes['objetivo_usd'])}.",
                "unidad": "usd",
                "actual": mes["aportado_usd"],
                "objetivo": mes["objetivo_usd"],
                "progreso_pct": _r(min(100.0, mes["cumplimiento_pct"] or 0.0), 1),
                "por_que": f"Quedan {mes['dias_restantes']} días de {mes_txt}.",
            }
        racha_obj = objetivo["racha_cumplimiento"] or 0
        siguiente = next((u for u in LOGROS_OBJETIVO_RACHA if u > racha_obj), None)
        if siguiente:
            return {
                "clave": f"objetivo_racha_{siguiente}",
                "titulo": f"Cumplir tu objetivo {siguiente} meses seguidos",
                "detalle": (
                    f"Llevás {racha_obj} de {siguiente} aportando al menos "
                    f"{_usd(objetivo['monto_usd'])} por mes."
                ),
                "unidad": "meses",
                "actual": float(racha_obj),
                "objetivo": float(siguiente),
                "progreso_pct": _r(racha_obj / siguiente * 100, 1),
                "por_que": "Ya cumpliste el objetivo de este mes.",
            }

    racha = rachas["aportando_actual"]["meses"]
    siguiente = next((u for u in HITOS_RACHA_MESES if u > racha), None)
    if siguiente:
        faltan = siguiente - racha
        return {
            "clave": f"racha_{siguiente}",
            "titulo": f"Llegar a {siguiente} meses seguidos aportando",
            "detalle": f"Llevás {racha} de {siguiente}.",
            "unidad": "meses",
            "actual": float(racha),
            "objetivo": float(siguiente),
            "progreso_pct": _r(racha / siguiente * 100, 1),
            "por_que": f"Te falta{'n' if faltan > 1 else ''} {faltan} {'mes' if faltan == 1 else 'meses'}.",
        }

    total = estadisticas["total_neto_usd"] or 0.0
    umbral = next((u for u in LOGROS_TOTAL_USD if u > total), None)
    if umbral:
        return {
            "clave": f"total_{umbral}",
            "titulo": f"Llegar a {_usd(umbral)} aportados",
            "detalle": f"Llevás {_usd(total)}.",
            "unidad": "usd",
            "actual": _r(total),
            "objetivo": float(umbral),
            "progreso_pct": _r(total / umbral * 100, 1),
            "por_que": "Es tu próximo escalón de capital aportado.",
        }
    return None


# ── Entrada ──────────────────────────────────────────────────────────────────

def calcular_progreso(*, items: list[dict], estadisticas: dict, rachas: dict, estado_ritmo: dict,
                      por_anio: list[dict], mejor_anio: dict | None, primer_mes: str,
                      mes_actual: str, ytd: float, hoy: date,
                      objetivo: dict | None) -> tuple[dict, dict[str, dict]]:
    """`items` son los meses ya rellenados con ceros de `aportes_engine`; el resto son sus
    resultados. `objetivo` es `None` si el usuario no configuró meta.

    Devuelve `(progreso, por_mes)`: lo segundo es el cumplimiento mes a mes, que `aportes_engine`
    mezcla en `serie_mensual` para que el calendario pueda pintar el objetivo sin cruzar arrays
    en el frontend.
    """
    obj = _evaluar_objetivo(items, objetivo, primer_mes, mes_actual, hoy, estadisticas)

    mejor_racha = max(rachas["aportando_actual"]["meses"], rachas["aportando_record"]["meses"])
    # `estadisticas.meses_con_aporte` sólo mira meses cerrados. Para el nivel se suma el mes en
    # curso si ya tiene aporte: quien aportó por primera vez este mes ya dio el primer paso, y
    # decirle "sin arrancar" sería falso. Mismo criterio que usan las rachas.
    actual = next((it for it in items if it["en_curso"]), None)
    meses_con_aporte = estadisticas["meses_con_aporte"] + (
        1 if actual is not None and actual["neto"] > EPS else 0
    )
    nivel = _nivel(meses_con_aporte, mejor_racha)
    if obj["configurado"] and (obj["racha_cumplimiento"] or 0) >= MESES_SELLO_OBJETIVO:
        nivel["sello_objetivo"] = {
            "etiqueta": "Cumpliendo tu objetivo",
            "meses": obj["racha_cumplimiento"],
        }

    progreso = {
        "nivel": nivel,
        "logros": _logros(items, estadisticas, rachas, obj, hoy, mejor_anio, ytd,
                          meses_con_aporte, mejor_racha),
        "records": _records(estadisticas, rachas, por_anio, obj, items),
        "evolucion": _evolucion(estado_ritmo, estadisticas),
        "proyeccion_ritmo": _proyeccion_ritmo(estadisticas),
        "mision": _mision(obj, rachas, estadisticas, hoy, meses_con_aporte),
    }
    # `por_mes` sale por separado: es el detalle que se mezcla en la serie, no parte del objetivo.
    por_mes = obj.pop("por_mes")
    progreso["objetivo"] = obj
    return progreso, por_mes
