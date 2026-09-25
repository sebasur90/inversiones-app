"""Motor puro del "ritmo de aportes": cuánto capital nuevo entra mes a mes y si ese ritmo mejora.

Sin dependencias de `Session`/DB/FastAPI: recibe la serie mensual ya convertida a USD (ver
`inversiones_analytics.serie_mensual_aportes`) y la fecha de hoy, y devuelve un dict plano que
`schemas.RitmoAportesOut` valida tal cual. Mismo criterio que `contribucion_engine.py`: testeable
con `pytest` sin fixtures de base de datos.

Supuestos documentados:
- "Aporte" de un mes = compras − ventas − amortizaciones (el mismo criterio de
  `get_aportes_historicos` y `patrimonio_analytics`): capital propio que entra o sale. Un mes
  negativo es un retiro neto. Los meses sin movimientos valen 0 y cuentan como "no aportó",
  porque justamente la constancia es lo que se quiere medir.
- No hay metas: todas las comparaciones son contra el propio historial (mes anterior, promedios
  de 3/6/12 meses, mismo mes del año pasado, récords).
- El mes en curso está incompleto: se excluye de promedios, mediana, desvío, récords, tendencia y
  comparación anual, y se muestra aparte con una proyección al ritmo diario. En las rachas suma
  si ya tiene aporte y no corta si todavía está en cero, así un mes recién empezado nunca castiga.
- Las comparaciones internas usan `EPS`; el redondeo es sólo al armar la salida.
"""
from __future__ import annotations

import calendar
import statistics
from datetime import date

EPS = 1e-9

# |Δ| menor a esto entre el promedio de los últimos 3 meses y los 3 anteriores es "sostenido":
# los aportes mensuales son ruidosos (MEP del día, comisiones, un mes con dos sueldos).
UMBRAL_TENDENCIA_PCT = 15.0
# Este mes proyectado vs. promedio de 12 meses: a partir de acá se felicita / se reta.
UMBRAL_VS_PROMEDIO_ALTO = 1.20
UMBRAL_VS_PROMEDIO_BAJO = 0.70
# Antes del día 7 la proyección al ritmo diario es una "estimación temprana".
DIA_PROYECCION_FIABLE = 7
# A partir de este día, si no hubo aporte en el mes, se avisa.
DIA_AVISO_SIN_APORTE = 15
# Con menos meses cerrados no hay contra qué comparar: estado "arrancando".
MESES_MINIMOS_TENDENCIA = 4
# La constancia (desvío / promedio) necesita algo de historia para decir algo.
MESES_MINIMOS_CONSTANCIA = 6
HITOS_TOTAL_USD = (5_000, 10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000)
HITOS_RACHA_MESES = (3, 6, 12, 24, 36)
CV_CONSTANTE = 0.5
CV_IRREGULAR = 1.0
MAX_MENSAJES = 4
# Un hito es "reciente" (se destaca en la pantalla) durante este número de meses.
MESES_HITO_RECIENTE = 2

ETIQUETAS_ESTADO = {
    "arrancando": ("Arrancando", "bien"),
    "acelerando": ("Acelerando", "bien"),
    "sostenido": ("Sostenido", "bien"),
    "frenando": ("Frenando", "atencion"),
    "parado": ("Parado", "riesgo"),
}

MESES_NOMBRE = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mes_key(anio: int, mes: int) -> str:
    return f"{anio:04d}-{mes:02d}"


def _partes(mes_key: str) -> tuple[int, int]:
    anio, mes = mes_key.split("-")
    return int(anio), int(mes)


def _mes_siguiente(anio: int, mes: int) -> tuple[int, int]:
    return (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def _sumar_meses(mes_key: str, n: int) -> str:
    anio, mes = _partes(mes_key)
    total = anio * 12 + (mes - 1) + n
    return _mes_key(total // 12, total % 12 + 1)


def _nombre_mes(mes_key: str) -> str:
    anio, mes = _partes(mes_key)
    return f"{MESES_NOMBRE[mes - 1]} {anio}"


def _prom(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _r(v: float | None, nd: int = 2) -> float | None:
    return None if v is None else round(v, nd)


def _usd(v: float) -> str:
    """Formato compacto para los textos de los mensajes: USD 1.250."""
    entero = int(round(abs(v)))
    texto = f"{entero:,}".replace(",", ".")
    return f"{'-' if v < 0 else ''}USD {texto}"


def _pct_txt(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{'+' if v >= 0 else ''}{v:.0f}%"


def _delta_pct(valor: float, ref: float | None) -> float | None:
    if ref is None or abs(ref) <= EPS:
        return None
    return (valor - ref) / abs(ref) * 100


def _delta(valor: float, ref: float | None) -> dict | None:
    if ref is None:
        return None
    return {
        "referencia_usd": _r(ref),
        "delta_usd": _r(valor - ref),
        "delta_pct": _r(_delta_pct(valor, ref), 1),
    }


def _comparacion(neto: float, proy: float, ref: float | None) -> dict | None:
    base = _delta(neto, ref)
    if base is None:
        return None
    base["delta_proyectado_usd"] = _r(proy - ref)
    base["delta_proyectado_pct"] = _r(_delta_pct(proy, ref), 1)
    return base


def _mes_ref(item: dict | None) -> dict | None:
    if item is None:
        return None
    return {"mes": item["mes"], "neto_usd": _r(item["neto"])}


def _max_por_neto(items: list[dict]) -> dict | None:
    """Empate → el más antiguo (los ítems vienen en orden cronológico)."""
    mejor = None
    for it in items:
        if mejor is None or it["neto"] > mejor["neto"] + EPS:
            mejor = it
    return mejor


def _min_por_neto(items: list[dict]) -> dict | None:
    peor = None
    for it in items:
        if peor is None or it["neto"] < peor["neto"] - EPS:
            peor = it
    return peor


def _racha_final(items: list[dict]) -> tuple[int, int]:
    """(largo, índice de inicio) de la racha de meses con aporte que termina en el último ítem."""
    n = 0
    for it in reversed(items):
        if it["neto"] > EPS:
            n += 1
        else:
            break
    return n, len(items) - n


def _sin_datos(hoy: date) -> dict:
    return {
        "estado": "sin_datos",
        "hoy": hoy,
        "primer_mes": None,
        "serie_mensual": [],
        "por_anio": [],
        "mejor_anio": None,
        "este_mes": None,
        "anio_en_curso": None,
        "rachas": None,
        "estadisticas": None,
        "estado_ritmo": None,
        "hitos_alcanzados": [],
        "proximos_hitos": [],
        "mensajes": [],
        "progreso": None,
    }


# ── Motor ────────────────────────────────────────────────────────────────────

def calcular_ritmo(serie: dict[str, dict], hoy: date, objetivo: dict | None = None) -> dict:
    """`serie`: {"YYYY-MM": {"neto", "compras", "salidas"}} sólo con los meses que tuvieron
    movimientos, en USD; `salidas` en valor absoluto. Los huecos se rellenan acá con ceros.

    `objetivo` es la meta mensual del usuario (`{monto_usd, vigente_desde, retroactivo}`) o `None`.
    Todo lo que agrega va bajo la clave `progreso`, sin tocar el resto del payload."""
    if not serie:
        return _sin_datos(hoy)

    mes_actual = _mes_key(hoy.year, hoy.month)
    primer_mes = min(serie)
    ultimo_mes = max(mes_actual, max(serie))

    # ── Serie completa, en orden, con ceros en los meses sin movimientos ──
    items: list[dict] = []
    anio, mes = _partes(primer_mes)
    while True:
        key = _mes_key(anio, mes)
        datos = serie.get(key, {})
        neto = float(datos.get("neto", 0.0))
        items.append({
            "mes": key,
            "anio": anio,
            "neto": neto,
            "compras": float(datos.get("compras", 0.0)),
            "salidas": float(datos.get("salidas", 0.0)),
            "en_curso": key == mes_actual,
            "futuro": key > mes_actual,
        })
        if key == ultimo_mes:
            break
        anio, mes = _mes_siguiente(anio, mes)

    cerrados = [it for it in items if it["mes"] < mes_actual]
    actual = next((it for it in items if it["en_curso"]), None)
    if actual is None:
        # Movimientos sólo con fecha futura: no hay nada que medir todavía.
        return _sin_datos(hoy)
    n = len(cerrados)

    def ult(k: int) -> list[dict] | None:
        return cerrados[-k:] if n >= k else None

    def prom_ult(k: int) -> float | None:
        xs = ult(k)
        return _prom([it["neto"] for it in xs]) if xs else None

    # ── Este mes ──
    dia = hoy.day
    dias_mes = calendar.monthrange(hoy.year, hoy.month)[1]
    neto_actual = actual["neto"]
    proyeccion = neto_actual * dias_mes / dia
    proyeccion_fiable = dia >= DIA_PROYECCION_FIABLE

    # ── Estadísticas sobre meses cerrados ──
    netos_cerrados = [it["neto"] for it in cerrados]
    mejor_mes = _max_por_neto(cerrados)
    peor_mes = _min_por_neto(cerrados)
    cerrados_anio = [it for it in cerrados if it["anio"] == hoy.year]
    promedio = _prom(netos_cerrados)
    mediana = statistics.median(netos_cerrados) if netos_cerrados else None
    desvio = statistics.pstdev(netos_cerrados) if n >= 2 else None
    coef_var = (desvio / promedio) if (desvio is not None and promedio is not None and promedio > EPS) else None
    constancia = None
    if coef_var is not None and n >= MESES_MINIMOS_CONSTANCIA:
        if coef_var < CV_CONSTANTE:
            constancia = {"nivel": "bien", "etiqueta": "Constante"}
        elif coef_var <= CV_IRREGULAR:
            constancia = {"nivel": "atencion", "etiqueta": "Irregular"}
        else:
            constancia = {"nivel": "riesgo", "etiqueta": "Muy irregular"}
    p3, p6, p12 = prom_ult(3), prom_ult(6), prom_ult(12)
    total_neto = sum(it["neto"] for it in items if not it["futuro"])
    total_compras = sum(it["compras"] for it in items if not it["futuro"])
    total_salidas = sum(it["salidas"] for it in items if not it["futuro"])

    es_record_parcial = mejor_mes is not None and neto_actual > mejor_mes["neto"] + EPS

    por_mes = {it["mes"]: it for it in items}
    mismo_mes_anio_anterior = por_mes.get(_mes_key(hoy.year - 1, hoy.month))
    este_mes = {
        "mes": mes_actual,
        "neto_usd": _r(neto_actual),
        "compras_usd": _r(actual["compras"]),
        "salidas_usd": _r(actual["salidas"]),
        "dia": dia,
        "dias_mes": dias_mes,
        "dias_restantes": dias_mes - dia,
        "proyeccion_usd": _r(proyeccion),
        "proyeccion_fiable": proyeccion_fiable,
        "es_record_parcial": es_record_parcial,
        "vs_mes_anterior": _comparacion(neto_actual, proyeccion, cerrados[-1]["neto"] if cerrados else None),
        "vs_promedio_3": _comparacion(neto_actual, proyeccion, p3),
        "vs_promedio_6": _comparacion(neto_actual, proyeccion, p6),
        "vs_promedio_12": _comparacion(neto_actual, proyeccion, p12),
        "vs_mismo_mes_anio_anterior": _comparacion(
            neto_actual, proyeccion, mismo_mes_anio_anterior["neto"] if mismo_mes_anio_anterior else None
        ),
    }

    # ── Año en curso y proyecciones a fin de año ──
    ytd = sum(it["neto"] for it in cerrados_anio) + neto_actual
    promedio_ytd = _prom([it["neto"] for it in cerrados_anio])
    meses_restantes = 12 - hoy.month
    ytd_sin_actual = ytd - neto_actual
    anio_anterior = [it for it in items if it["anio"] == hoy.year - 1]
    anio_anterior_total = sum(it["neto"] for it in anio_anterior) if anio_anterior else None

    # Mismo período del año pasado: los meses ya cerrados + el mes equivalente prorrateado al día.
    vs_mismo_periodo = None
    if primer_mes <= _mes_key(hoy.year - 1, hoy.month):
        ref = sum(it["neto"] for it in anio_anterior if _partes(it["mes"])[1] < hoy.month)
        equivalente = por_mes.get(_mes_key(hoy.year - 1, hoy.month))
        if equivalente:
            ref += equivalente["neto"] * dia / dias_mes
        vs_mismo_periodo = _delta(ytd, ref)

    def proyectar(ritmo: float | None, incluye_actual_propio: bool) -> float | None:
        if ritmo is None:
            return None
        if incluye_actual_propio:
            # El mes en curso aporta su propia proyección (ya es ≥ lo real cuando neto ≥ 0).
            return ytd_sin_actual + ritmo * (meses_restantes + 1)
        # El mes en curso aporta lo que ya hiciste o el ritmo, lo que sea mayor: lo ya aportado
        # nunca se descuenta.
        return ytd_sin_actual + max(neto_actual, ritmo) + ritmo * meses_restantes

    proyecciones = [
        {
            "clave": "este_mes",
            "etiqueta": "Al ritmo de este mes",
            "ritmo_mensual_usd": _r(proyeccion),
            "total_fin_anio_usd": _r(proyectar(proyeccion, True)),
        },
        {
            "clave": "promedio_3",
            "etiqueta": "Al promedio de los últimos 3 meses",
            "ritmo_mensual_usd": _r(p3),
            "total_fin_anio_usd": _r(proyectar(p3, False)),
        },
        {
            "clave": "promedio_ytd",
            "etiqueta": f"Al promedio de {hoy.year}",
            "ritmo_mensual_usd": _r(promedio_ytd),
            "total_fin_anio_usd": _r(proyectar(promedio_ytd, False)),
        },
    ]
    anio_en_curso = {
        "anio": hoy.year,
        "ytd_usd": _r(ytd),
        "meses_cerrados": len(cerrados_anio),
        "meses_restantes": meses_restantes,
        "promedio_mensual_ytd_usd": _r(promedio_ytd),
        "anio_anterior_total_usd": _r(anio_anterior_total),
        "vs_mismo_periodo_anio_anterior": vs_mismo_periodo,
        "proyecciones": proyecciones,
    }

    # ── Rachas ──
    racha_len, racha_ini = _racha_final(cerrados)
    incluye_actual = neto_actual > EPS
    if incluye_actual:
        racha_len += 1
    if racha_len == 0:
        racha_actual = {"meses": 0, "desde": None, "hasta": None, "incluye_mes_en_curso": False}
    else:
        desde = cerrados[racha_ini]["mes"] if racha_ini < n else mes_actual
        hasta = mes_actual if incluye_actual else cerrados[-1]["mes"]
        racha_actual = {"meses": racha_len, "desde": desde, "hasta": hasta, "incluye_mes_en_curso": incluye_actual}

    # Récord: la racha más larga en cerrados (+ el mes en curso si extiende la última); empate → la más reciente.
    record = {"meses": 0, "desde": None, "hasta": None, "incluye_mes_en_curso": False}
    corrida = 0
    for i, it in enumerate(cerrados):
        corrida = corrida + 1 if it["neto"] > EPS else 0
        if corrida >= record["meses"] and corrida > 0:
            record = {"meses": corrida, "desde": cerrados[i - corrida + 1]["mes"], "hasta": it["mes"], "incluye_mes_en_curso": False}
    if racha_actual["meses"] >= record["meses"] and racha_actual["meses"] > 0:
        record = dict(racha_actual)

    sin_aportar_actual = 0
    for it in reversed(cerrados):
        if it["neto"] <= EPS:
            sin_aportar_actual += 1
        else:
            break

    sobre_promedio_12 = None
    if p12 is not None:
        sobre_promedio_12 = 0
        for it in reversed(cerrados):
            if it["neto"] > p12 + EPS:
                sobre_promedio_12 += 1
            else:
                break

    direccion, direccion_meses = "ninguna", 0
    if n >= 2:
        subiendo = bajando = 0
        for i in range(n - 1, 0, -1):
            if cerrados[i]["neto"] > cerrados[i - 1]["neto"] + EPS and bajando == 0:
                subiendo += 1
            elif cerrados[i]["neto"] < cerrados[i - 1]["neto"] - EPS and subiendo == 0:
                bajando += 1
            else:
                break
        if subiendo:
            direccion, direccion_meses = "subiendo", subiendo
        elif bajando:
            direccion, direccion_meses = "bajando", bajando

    ultimos_12 = cerrados[-12:]
    rachas = {
        "aportando_actual": racha_actual,
        "aportando_record": record,
        "sin_aportar_actual": sin_aportar_actual,
        "sobre_promedio_12_actual": sobre_promedio_12,
        "direccion": direccion,
        "direccion_meses": direccion_meses,
        "meses_sin_aportar_ultimos_12": sum(1 for it in ultimos_12 if it["neto"] <= EPS),
        "meses_considerados_ultimos_12": len(ultimos_12),
    }

    estadisticas = {
        "meses_historia": n,
        "meses_con_aporte": sum(1 for it in cerrados if it["neto"] > EPS),
        "meses_con_retiro": sum(1 for it in cerrados if it["neto"] < -EPS),
        "total_neto_usd": _r(total_neto),
        "total_compras_usd": _r(total_compras),
        "total_salidas_usd": _r(total_salidas),
        "promedio_usd": _r(promedio),
        "mediana_usd": _r(mediana),
        "desvio_usd": _r(desvio),
        "coef_variacion": _r(coef_var, 3),
        "constancia": constancia,
        "promedio_3_usd": _r(p3),
        "promedio_6_usd": _r(p6),
        "promedio_12_usd": _r(p12),
        "mejor_mes": _mes_ref(mejor_mes),
        "peor_mes": _mes_ref(peor_mes),
        "mejor_mes_anio": _mes_ref(_max_por_neto(cerrados_anio)),
        "peor_mes_anio": _mes_ref(_min_por_neto(cerrados_anio)),
    }

    # ── Estado del ritmo: últimos 3 meses vs. los 3 anteriores ──
    if n >= 6:
        p3_ant = _prom([it["neto"] for it in cerrados[-6:-3]])
    elif n >= MESES_MINIMOS_TENDENCIA:
        p3_ant = _prom([it["neto"] for it in cerrados[:-3]])
    else:
        p3_ant = None
    p6_ant = _prom([it["neto"] for it in cerrados[-12:-6]]) if n >= 12 else None
    t3 = _delta_pct(p3, p3_ant) if p3 is not None else None
    t6 = _delta_pct(p6, p6_ant) if p6 is not None else None

    if n < MESES_MINIMOS_TENDENCIA:
        estado = "arrancando"
        detalle = f"Todavía hay poco historial ({n} {'mes cerrado' if n == 1 else 'meses cerrados'}): a partir de {MESES_MINIMOS_TENDENCIA} aparecen las comparaciones."
    elif p3 <= EPS and neto_actual <= EPS:
        estado = "parado"
        detalle = "Sin aporte neto en los últimos 3 meses cerrados ni en lo que va de este mes."
    elif p3_ant <= EPS and p3 > EPS:
        estado = "acelerando"
        detalle = f"Volviste a aportar: {_usd(p3)}/mes en los últimos 3 meses, después de un período en cero."
    else:
        if t3 is not None and t3 >= UMBRAL_TENDENCIA_PCT:
            estado = "acelerando"
        elif t3 is not None and t3 <= -UMBRAL_TENDENCIA_PCT:
            estado = "frenando"
        else:
            estado = "sostenido"
        detalle = f"Últimos 3 meses: {_usd(p3)}/mes vs. {_usd(p3_ant)}/mes los 3 anteriores ({_pct_txt(t3)})."
    etiqueta, nivel = ETIQUETAS_ESTADO[estado]
    estado_ritmo = {
        "estado": estado,
        "etiqueta": etiqueta,
        "nivel": nivel,
        "detalle": detalle,
        "tendencia_3v3_pct": _r(t3, 1),
        "tendencia_6v6_pct": _r(t6, 1),
        "promedio_3_usd": _r(p3),
        "promedio_3_anterior_usd": _r(p3_ant),
        "promedio_6_usd": _r(p6),
        "promedio_6_anterior_usd": _r(p6_ant),
    }

    # ── Comparación anual ──
    por_anio: list[dict] = []
    anios = sorted({it["anio"] for it in items if not it["futuro"]})
    totales: dict[int, float] = {
        a: sum(it["neto"] for it in items if it["anio"] == a and not it["futuro"]) for a in anios
    }
    for a in anios:
        del_anio = [it for it in items if it["anio"] == a and not it["futuro"]]
        cerrados_a = [it for it in del_anio if not it["en_curso"]]
        anterior = totales.get(a - 1)
        por_anio.append({
            "anio": a,
            "total_usd": _r(totales[a]),
            "compras_usd": _r(sum(it["compras"] for it in del_anio)),
            "salidas_usd": _r(sum(it["salidas"] for it in del_anio)),
            "promedio_mensual_usd": _r(_prom([it["neto"] for it in cerrados_a])),
            "meses_con_aporte": sum(1 for it in del_anio if it["neto"] > EPS),
            "meses_en_rango": len(del_anio),
            "var_vs_anio_anterior_pct": _r(_delta_pct(totales[a], anterior) if anterior is not None else None, 1),
            "en_curso": a == hoy.year,
            "mejor_mes": _mes_ref(_max_por_neto(cerrados_a)),
        })
    por_anio.sort(key=lambda x: -x["anio"])
    anios_cerrados = [a for a in anios if a != hoy.year]
    mejor_anio = None
    if anios_cerrados:
        a_mejor = max(anios_cerrados, key=lambda a: (totales[a], -a))
        mejor_anio = {"anio": a_mejor, "total_usd": _r(totales[a_mejor])}

    # ── Hitos ──
    hitos: list[dict] = []
    limite_reciente = _sumar_meses(mes_actual, -MESES_HITO_RECIENTE)

    def hito(clave: str, titulo: str, descripcion: str, fecha: str) -> None:
        hitos.append({"clave": clave, "titulo": titulo, "descripcion": descripcion, "fecha": fecha, "reciente": fecha >= limite_reciente})

    hito("primer_aporte", "Primer aporte", f"Empezaste a invertir en {_nombre_mes(primer_mes)}.", primer_mes)
    acumulado = 0.0
    corrida = 0
    max_total_alcanzado = 0
    rachas_alcanzadas: set[int] = set()
    acumulado_anio = 0.0
    hito_mejor_anio_puesto = False
    for it in items:
        if it["futuro"]:
            break
        acumulado += it["neto"]
        for umbral in HITOS_TOTAL_USD:
            if umbral > max_total_alcanzado and acumulado >= umbral - EPS:
                max_total_alcanzado = umbral
                hito(f"total_{umbral}", f"{_usd(umbral)} aportados", f"Tu capital aportado neto cruzó los {_usd(umbral)} en {_nombre_mes(it['mes'])}.", it["mes"])
        corrida = corrida + 1 if it["neto"] > EPS else 0
        for umbral in HITOS_RACHA_MESES:
            if corrida >= umbral and umbral not in rachas_alcanzadas:
                rachas_alcanzadas.add(umbral)
                hito(f"racha_{umbral}", f"{umbral} meses seguidos aportando", f"Llegaste a {umbral} meses consecutivos con aporte en {_nombre_mes(it['mes'])}.", it["mes"])
        if it["anio"] == hoy.year and mejor_anio is not None and not hito_mejor_anio_puesto:
            acumulado_anio += it["neto"]
            if acumulado_anio > mejor_anio["total_usd"] + EPS:
                hito_mejor_anio_puesto = True
                hito("mejor_anio_en_curso", "Tu mejor año", f"{hoy.year} ya superó a {mejor_anio['anio']} ({_usd(mejor_anio['total_usd'])}) en {_nombre_mes(it['mes'])}.", it["mes"])
    if mejor_mes is not None and mejor_mes["neto"] > EPS:
        hito("record_mensual", f"Récord mensual: {_usd(mejor_mes['neto'])}", f"Tu mes con más aporte fue {_nombre_mes(mejor_mes['mes'])}.", mejor_mes["mes"])
    hitos.sort(key=lambda h: h["fecha"], reverse=True)

    proximos: list[dict] = []
    siguiente_total = next((u for u in HITOS_TOTAL_USD if u > max_total_alcanzado), None)
    if siguiente_total is not None:
        falta = max(0.0, siguiente_total - total_neto)
        proximos.append({
            "clave": f"total_{siguiente_total}",
            "titulo": f"{_usd(siguiente_total)} aportados",
            "unidad": "usd",
            "valor_objetivo": float(siguiente_total),
            "valor_actual": _r(total_neto),
            "falta": _r(falta),
            "progreso_pct": _r(max(0.0, min(100.0, total_neto / siguiente_total * 100)), 1),
        })
    siguiente_racha = next((u for u in HITOS_RACHA_MESES if u > racha_actual["meses"]), None)
    if siguiente_racha is not None:
        proximos.append({
            "clave": f"racha_{siguiente_racha}",
            "titulo": f"{siguiente_racha} meses seguidos aportando",
            "unidad": "meses",
            "valor_objetivo": float(siguiente_racha),
            "valor_actual": float(racha_actual["meses"]),
            "falta": float(siguiente_racha - racha_actual["meses"]),
            "progreso_pct": _r(racha_actual["meses"] / siguiente_racha * 100, 1),
        })

    # ── Mensajes ──
    mensajes = _armar_mensajes(
        estado=estado, t3=t3, sin_aportar_actual=sin_aportar_actual, promedio=promedio,
        es_record_parcial=es_record_parcial, mejor_mes=mejor_mes, neto_actual=neto_actual,
        cerrados=cerrados, dia=dia, dias_restantes=dias_mes - dia, racha_actual=racha_actual,
        proyeccion=proyeccion, proyeccion_fiable=proyeccion_fiable, p12=p12,
        vs_mismo_periodo=vs_mismo_periodo, proyecciones=proyecciones,
        anio_anterior_total=anio_anterior_total, proximos=proximos, hoy=hoy,
    )

    # ── Progreso (niveles, objetivo, logros, récords, misión) ──
    # Se importa acá y no arriba para evitar el import circular: el motor de progreso reutiliza
    # las constantes y los formateadores de este módulo.
    from . import aportes_progreso_engine

    progreso, cumplimiento_por_mes = aportes_progreso_engine.calcular_progreso(
        items=items, estadisticas=estadisticas, rachas=rachas, estado_ritmo=estado_ritmo,
        por_anio=por_anio, mejor_anio=mejor_anio, primer_mes=primer_mes,
        mes_actual=mes_actual, ytd=ytd, hoy=hoy, objetivo=objetivo,
    )

    # Promedio móvil de 3 para el gráfico: el mes en curso usa su proyección para que la línea
    # no se desplome al principio de cada mes.
    serie_out: list[dict] = []
    valores_movil = [proyeccion if it["en_curso"] else it["neto"] for it in items]
    for i, it in enumerate(items):
        movil = _prom(valores_movil[i - 2:i + 1]) if i >= 2 and not it["futuro"] else None
        # El cumplimiento viaja en la propia serie para que el calendario pueda pintarlo sin
        # cruzar dos arrays en el frontend. `None` = mes sin objetivo vigente, nunca "incumplido".
        cumplimiento = cumplimiento_por_mes.get(it["mes"], {})
        serie_out.append({
            "mes": it["mes"],
            "neto_usd": _r(it["neto"]),
            "compras_usd": _r(it["compras"]),
            "salidas_usd": _r(it["salidas"]),
            "en_curso": it["en_curso"],
            "futuro": it["futuro"],
            "con_aporte": it["neto"] > EPS,
            "promedio_movil_3_usd": _r(movil),
            "objetivo_usd": cumplimiento.get("objetivo_usd"),
            "cumplimiento_pct": cumplimiento.get("cumplimiento_pct"),
            "cumple_objetivo": cumplimiento.get("cumple_objetivo"),
        })

    return {
        "estado": "ok",
        "hoy": hoy,
        "primer_mes": primer_mes,
        "serie_mensual": serie_out,
        "por_anio": por_anio,
        "mejor_anio": mejor_anio,
        "este_mes": este_mes,
        "anio_en_curso": anio_en_curso,
        "rachas": rachas,
        "estadisticas": estadisticas,
        "estado_ritmo": estado_ritmo,
        "hitos_alcanzados": hitos,
        "proximos_hitos": proximos,
        "mensajes": mensajes,
        "progreso": progreso,
    }


def _armar_mensajes(
    *, estado, t3, sin_aportar_actual, promedio, es_record_parcial, mejor_mes, neto_actual,
    cerrados, dia, dias_restantes, racha_actual, proyeccion, proyeccion_fiable, p12,
    vs_mismo_periodo, proyecciones, anio_anterior_total, proximos, hoy,
) -> list[dict]:
    """Reglas en orden de prioridad; una por familia; como mucho MAX_MENSAJES."""
    mensajes: list[dict] = []

    def agregar(clave: str, tono: str, titulo: str, detalle: str) -> None:
        if len(mensajes) < MAX_MENSAJES and not any(m["clave"] == clave for m in mensajes):
            mensajes.append({"clave": clave, "tono": tono, "titulo": titulo, "detalle": detalle})

    ultimo = cerrados[-1] if cerrados else None

    # 1. Parado
    if estado == "parado":
        meses_txt = f"Llevás {sin_aportar_actual} {'mes' if sin_aportar_actual == 1 else 'meses'} cerrados sin aportar"
        prom_txt = f"; tu promedio histórico era {_usd(promedio)}/mes." if promedio and promedio > EPS else "."
        agregar("parado", "negativo", "Frenaste los aportes", meses_txt + prom_txt)

    # 2. Récord en curso
    if es_record_parcial and mejor_mes is not None:
        agregar("record_en_curso", "positivo", "Vas por un mes récord",
                f"{_usd(neto_actual)} este mes; tu mejor mes era {_usd(mejor_mes['neto'])} ({_nombre_mes(mejor_mes['mes'])}).")

    # 3. Récord reciente
    if mejor_mes is not None and ultimo is not None and mejor_mes["mes"] == ultimo["mes"] and ultimo["neto"] > EPS:
        agregar("record_reciente", "positivo", f"Mes récord en {_nombre_mes(ultimo['mes'])}",
                f"Aportaste {_usd(ultimo['neto'])}, el máximo de tu historial.")

    # 4. Mitad de mes sin aportar
    if neto_actual <= EPS and dia >= DIA_AVISO_SIN_APORTE and ultimo is not None and ultimo["neto"] > EPS:
        agregar("sin_aporte_mes", "negativo", "Vas a mitad de mes sin aportar",
                f"Quedan {dias_restantes} días; el mes pasado aportaste {_usd(ultimo['neto'])}.")

    # 5. Tendencia
    if estado == "acelerando" and t3 is not None:
        agregar("acelerando", "positivo", "Acelerando", f"{_pct_txt(t3)} vs. el trimestre anterior. Seguí así.")
    elif estado == "acelerando":
        agregar("acelerando", "positivo", "Volviste a aportar", "Después de un período en cero, los últimos 3 meses vuelven a sumar.")
    elif estado == "frenando":
        agregar("frenando", "negativo", "Frenando", f"{_pct_txt(t3)} vs. el trimestre anterior. Mirá qué meses bajaron.")

    # 6. Racha
    if racha_actual["meses"] >= 3:
        siguiente = next((u for u in HITOS_RACHA_MESES if u > racha_actual["meses"]), None)
        cola = f" Te faltan {siguiente - racha_actual['meses']} para llegar a {siguiente}." if siguiente else ""
        agregar("racha", "positivo", f"{racha_actual['meses']} meses seguidos aportando", f"Desde {_nombre_mes(racha_actual['desde'])}.{cola}")

    # 7. Este mes vs. promedio 12
    if proyeccion_fiable and p12 is not None and p12 > EPS:
        ratio = proyeccion / p12
        pct = _delta_pct(proyeccion, p12)
        if ratio >= UMBRAL_VS_PROMEDIO_ALTO:
            agregar("arriba_promedio", "positivo", f"Este mes venís {_pct_txt(pct)} arriba de tu promedio",
                    f"Al ritmo actual cerrás en {_usd(proyeccion)}; tu promedio de 12 meses es {_usd(p12)}.")
        elif ratio < UMBRAL_VS_PROMEDIO_BAJO:
            agregar("abajo_promedio", "negativo", f"Este mes venís {_pct_txt(pct)} abajo de tu promedio",
                    f"Al ritmo actual cerrás en {_usd(proyeccion)}; tu promedio de 12 meses es {_usd(p12)}. Quedan {dias_restantes} días.")

    # 8. Vs. año pasado a esta altura
    if vs_mismo_periodo is not None and vs_mismo_periodo["delta_pct"] is not None:
        d = vs_mismo_periodo["delta_pct"]
        if d >= UMBRAL_TENDENCIA_PCT:
            agregar("vs_anio_pasado", "positivo", f"Vas {_pct_txt(d)} vs. el año pasado a esta altura",
                    f"{_usd(vs_mismo_periodo['referencia_usd'] + vs_mismo_periodo['delta_usd'])} contra {_usd(vs_mismo_periodo['referencia_usd'])} en {hoy.year - 1}.")
        elif d <= -UMBRAL_TENDENCIA_PCT:
            agregar("vs_anio_pasado", "negativo", f"Vas {_pct_txt(d)} vs. el año pasado a esta altura",
                    f"{_usd(vs_mismo_periodo['referencia_usd'] + vs_mismo_periodo['delta_usd'])} contra {_usd(vs_mismo_periodo['referencia_usd'])} en {hoy.year - 1}.")

    # 9. Proyección a fin de año
    proy3 = next((p for p in proyecciones if p["clave"] == "promedio_3"), None)
    if proy3 is not None and proy3["total_fin_anio_usd"] is not None:
        cola = f" El año pasado: {_usd(anio_anterior_total)}." if anio_anterior_total is not None else ""
        agregar("proyeccion_anio", "neutro", f"Si seguís así cerrás {hoy.year} con {_usd(proy3['total_fin_anio_usd'])}",
                f"Al ritmo de los últimos 3 meses ({_usd(proy3['ritmo_mensual_usd'])}/mes).{cola}")

    # 10. Próximo hito
    if proximos:
        p = proximos[0]
        falta_txt = _usd(p["falta"]) if p["unidad"] == "usd" else f"{int(p['falta'])} {'mes' if p['falta'] == 1 else 'meses'}"
        agregar("proximo_hito", "neutro", f"Te faltan {falta_txt} para llegar a {p['titulo']}",
                f"Llevás {int(p['progreso_pct'])}% del camino.")

    # 11. Arrancando
    if estado == "arrancando":
        agregar("arrancando", "neutro", "Todavía hay poco historial",
                f"A partir de {MESES_MINIMOS_TENDENCIA} meses cerrados aparecen las comparaciones de tendencia.")

    return mensajes
