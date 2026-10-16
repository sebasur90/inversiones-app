"""Diagnóstico integral de una empresa: valuación, calidad, crecimiento, solidez y confianza. Puro.

**No hay puntaje único** (mismo criterio que `salud_engine`): cada dimensión responde una pregunta
distinta con un estado en palabras, las razones que lo explican, la regla que se aplicó y lo que
falta para tener más certeza. Mezclar todo en un número ocultaría justo lo que importa: una
empresa puede estar barata *y* ser frágil.

- **Valuación**: ¿barata o cara frente a sus pares? Es la lectura de `valuacion_engine` (conteo por
  familias de métricas: ganancias, ventas/EBITDA, flujo, valor libro) y no se juzga como buena ni mala.
- **Calidad**: márgenes y retornos. Compara contra los pares, pero un margen negativo es "débil"
  aunque los pares estén peor.
- **Crecimiento**: ingresos y ganancias del último trimestre contra el mismo de hace un año
  (observado) y lo que el mercado descuenta para el próximo año (estimado).
- **Solidez financiera**: deuda, flujo de caja, liquidez, dividendo cubierto, volatilidad.
- **Confianza de los datos**: cuánto de lo anterior se apoya en datos completos, frescos y
  comparables. Con confianza baja el resto se muestra igual, marcado.

Reglas generales:
- **Faltante no es negativo.** Un dato que Yahoo no informa se lista en "qué falta"; nunca baja un
  estado ni se reemplaza por cero.
- **No aplica no es faltante.** Un banco no tiene EV/EBITDA ni margen bruto; un ETF no tiene margen.
- **Origen de cada razón**: `observado` (lo informó Yahoo), `estimado` (proviene de estimaciones de
  analistas) o `calculado` (lo derivó la app). La conclusión de cada dimensión es siempre de la app.
- Sin historia contable de varios años: la consistencia de resultados **no se evalúa** y se dice.

`VERSION_REGLAS` viaja en cada respuesta: si cambia una regla o un umbral, se sube, para poder
comparar diagnósticos de fechas distintas (historial de la etapa 5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from statistics import median

from . import valuacion_engine as ve

VERSION_REGLAS = 2

# -- Niveles (para el semáforo de la pantalla) --
BIEN, ATENCION, RIESGO, NEUTRO, SIN_DATOS, NO_APLICA = (
    "bien", "atencion", "riesgo", "neutro", "sin_datos", "no_aplica")

# -- Umbrales absolutos (visibles: se citan en las reglas que se muestran) --
CAIDA_INGRESOS = -0.02        # ingresos cayendo más de 2% interanual = "en caída"
DEUDA_ALTA = 2.0              # Deuda/Patrimonio en veces
BETA_ALTA = 1.5
LIQUIDEZ_BAJA = 1.0           # activo corriente / pasivo corriente
PAYOUT_NO_CUBIERTO = 1.0      # dividendos / ganancias
DIFERENCIA_ESPERADO = 0.10    # 10 puntos entre crecimiento esperado y observado

# -- Confianza --
COBERTURA_ALTA = 0.70
COBERTURA_MEDIA = 0.40
PARES_ALTA = 4
PARES_MEDIA = 2
DIAS_DATOS_BAJA = 60
DIAS_CONTABLE_MEDIA = 150     # el último balance tiene más de ~2 trimestres
DIAS_CONTABLE_BAJA = 270
DIAS_PERIODOS_DISTINTOS = 120

SECTORES_SIN_EBITDA = ve.SECTORES_SIN_EBITDA

# Sin dato no cuenta como faltante: no todas las empresas pagan dividendo ni tienen PEG.
OPCIONALES = frozenset({"div_yield", "peg"})
NO_APLICAN_FINANCIERO_O_INMOBILIARIO = frozenset({"ev_ebitda", "ps", "margen_bruto", "deuda_patrimonio"})

CALIDAD_FAMILIAS = {
    "margenes": ("Márgenes", ("margen_bruto", "margen_operativo", "margen_neto")),
    "retornos": ("Retornos", ("roe", "roa")),
}
CRECIMIENTO_FAMILIAS = {
    "ingresos": ("Ingresos", ("crec_ingresos",)),
    "ganancias": ("Ganancias", ("crec_ganancias",)),
    "esperado": ("Esperado", ("crec_esperado",)),
}

# Lo que sería relevante para el tipo de empresa y Yahoo no entrega: se dice, no se inventa.
NOTA_SECTOR = {
    "Financiero": "indicadores propios de bancos y aseguradoras (capital regulatorio, morosidad, margen financiero) no disponibles",
    "Inmobiliario": "FFO (flujo de fondos operativos) y ocupación no disponibles",
    "Energía": "reservas, costo de extracción y sensibilidad al precio de la materia prima no disponibles",
    "Materiales": "sensibilidad al precio de la materia prima y ciclo del sector no disponibles",
    "Servicios públicos": "tarifas reguladas e inversión comprometida no disponibles",
}

HISTORIA_NO_DISPONIBLE = (
    "Historia de varios años de ingresos, márgenes y ganancias (sólo se dispone del último trimestre contra el "
    "mismo de hace un año): la consistencia de los resultados no se puede evaluar"
)


@dataclass
class Razon:
    texto: str
    tono: str                       # "positivo" | "negativo" | "alerta" | "neutro"
    origen: str                     # "observado" | "estimado" | "calculado"
    metricas: list[str] = field(default_factory=list)
    regla: str = ""


@dataclass
class Dimension:
    clave: str                      # valuacion | calidad | crecimiento | solidez | confianza
    nombre: str
    estado: str                     # palabra: "Barata", "Débil", "Sólida", "Alta"…
    nivel: str                      # BIEN | ATENCION | RIESGO | NEUTRO | SIN_DATOS | NO_APLICA
    resumen: str
    regla: str
    razones: list[Razon] = field(default_factory=list)
    faltantes: list[str] = field(default_factory=list)
    percentil: int | None = None    # mediana de los percentiles favorables de sus métricas (100 = mejor del grupo)
    votos: list[dict] = field(default_factory=list)   # cómo votó cada familia, cuando aplica


@dataclass
class Diagnostico:
    version_reglas: int
    dimensiones: list[Dimension]
    confianza: str                  # "alta" | "media" | "baja" | "sin_datos"


# ---------------------------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------------------------

def origen_metrica(clave: str, ficha: ve.Ficha) -> str:
    """De dónde sale el valor de una métrica en la tabla: lo que informó Yahoo, una estimación o un cálculo de la app."""
    if clave in ve.METRICAS_ESTIMADAS:
        return "estimado"
    if clave in ficha.recalculadas or clave in ve.METRICAS_CALCULADAS:
        return "calculado"
    return "observado"


def _origen_conjunto(claves: list[str], ficha: ve.Ficha) -> str:
    if not claves:
        return "calculado"      # una conclusión de la app sin una métrica puntual detrás
    origenes = {origen_metrica(c, ficha) for c in claves}
    for o in ("estimado", "calculado"):
        if o in origenes:
            return o
    return "observado"


def _aplica(clave: str, sector: str | None) -> bool:
    if sector in SECTORES_SIN_EBITDA and clave in NO_APLICAN_FINANCIERO_O_INMOBILIARIO:
        return False
    if sector == "Financiero" and clave == "fcf_yield":
        return False
    return True


def _nombres(claves) -> str:
    return ve._lista([ve.METRICA_POR_CLAVE[c].nombre for c in claves])


def _percentil_medio(rs: list[ve.ResultadoMetrica]) -> int | None:
    valores = [r.percentil for r in rs if r.percentil is not None]
    return round(median(valores)) if valores else None


def _votar(rs: list[ve.ResultadoMetrica], familias: dict) -> list[dict]:
    """Un voto por familia (mismo criterio que `ve.votar_familias`): lo que vota la mayoría de sus métricas; empate = media."""
    votos = []
    for clave, (nombre, claves) in familias.items():
        con_banda = [r for r in rs if r.clave in claves and r.banda is not None]
        if not con_banda:
            continue
        mejores = sum(1 for r in con_banda if r.banda == "mejor")
        peores = sum(1 for r in con_banda if r.banda == "peor")
        banda = "mejor" if mejores > peores else "peor" if peores > mejores else "media"
        votos.append({"familia": clave, "nombre": nombre, "banda": banda, "metricas": [r.clave for r in con_banda]})
    return votos


def _sin_datos(clave: str, nombre: str, motivo: str, regla: str = "") -> Dimension:
    return Dimension(clave, nombre, "Sin datos", SIN_DATOS, motivo, regla or "hacen falta datos del emisor", faltantes=[motivo])


def _no_aplica(clave: str, nombre: str) -> Dimension:
    return Dimension(
        clave, nombre, "No aplica", NO_APLICA,
        "No aplica a un ETF: sus indicadores son los de las empresas que contiene, no los de un negocio propio.",
        "los ETF sólo se evalúan por valuación (gastos, P/B, dividendo) y confianza de los datos",
    )


def _faltantes_de(res: ve.ResultadoValuacion, claves, obj: ve.Ficha) -> list[str]:
    """Métricas aplicables que Yahoo no informó (o que se descartaron por moneda)."""
    salida = []
    for r in res.metricas:
        if r.clave not in claves or r.valor is not None or r.clave in OPCIONALES or not _aplica(r.clave, obj.sector):
            continue
        if r.clave in ("pe", "crec_ganancias", "crec_esperado", "forward_pe") and obj.sin_ganancias:
            continue  # sin ganancias no es un dato que falta: el indicador no aplica
        salida.append(
            f"{r.nombre} (se descartó: el balance está en otra moneda)" if r.clave in obj.descartadas_moneda
            else r.nombre
        )
    return salida


# ---------------------------------------------------------------------------------------------
# Valuación
# ---------------------------------------------------------------------------------------------

def _valuacion(obj: ve.Ficha, res: ve.ResultadoValuacion) -> Dimension:
    nivel = {ve.LECTURA_TRAMPA: ATENCION, ve.LECTURA_SIN_DATOS: SIN_DATOS}.get(res.lectura, NEUTRO)
    razones = []
    for f in res.frases:
        grupos = {ve.METRICA_POR_CLAVE[c].grupo for c in f.metricas}
        if grupos and not grupos <= {"valuacion", "momentum"}:
            continue  # las frases de calidad y crecimiento van en sus dimensiones
        razones.append(Razon(f.texto, f.tono, _origen_conjunto(f.metricas, obj), list(f.metricas), f.regla))
    claves = [m.clave for m in ve.metricas_para(obj.es_etf) if m.grupo == "valuacion"]
    valuacion = [r for r in res.metricas if r.grupo == "valuacion"]
    return Dimension(
        "valuacion", "Valuación", res.lectura_texto, nivel,
        f"{res.lectura_texto}. Comparada contra {res.n_pares_con_datos} "
        f"{'par' if res.n_pares_con_datos == 1 else 'pares'} con datos.",
        res.regla_lectura, razones, _faltantes_de(res, claves, obj), _percentil_medio(valuacion),
        votos=[{"familia": v.familia, "nombre": v.nombre, "banda": v.banda, "metricas": v.metricas,
                "solo_apoya": v.solo_apoya} for v in res.familias],
    )


# ---------------------------------------------------------------------------------------------
# Calidad
# ---------------------------------------------------------------------------------------------

REGLA_CALIDAD = (
    "débil: margen operativo o neto negativo, ROE negativo, o 2+ familias (márgenes, retornos) en el cuarto "
    "peor del grupo y ninguna en el mejor; alta: 2+ familias en el cuarto mejor y ninguna en el peor; "
    "media: el resto; sin conclusión: menos de 2 familias comparables"
)


def _calidad(obj: ve.Ficha, res: ve.ResultadoValuacion) -> Dimension:
    claves = [c for _, cs in CALIDAD_FAMILIAS.values() for c in cs]
    rs = [r for r in res.metricas if r.clave in claves]
    votos = _votar(rs, CALIDAD_FAMILIAS)
    percentil = _percentil_medio(rs)
    faltantes = _faltantes_de(res, claves, obj)
    valores = obj.valores
    razones: list[Razon] = []

    alertas = []
    if (valores.get("margen_neto") or 0) < 0:
        alertas.append(("margen_neto", f"Pierde plata: margen neto de {ve._pct(valores['margen_neto'])}."))
    if (valores.get("margen_operativo") or 0) < 0:
        alertas.append(("margen_operativo", f"Su negocio no cubre sus costos: margen operativo de {ve._pct(valores['margen_operativo'])}."))
    if (valores.get("roe") or 0) < 0:
        alertas.append(("roe", f"Retorno sobre el patrimonio negativo ({ve._pct(valores['roe'])})."))
    for clave, texto in alertas:
        razones.append(Razon(texto, "alerta", "observado", [clave], "margen o retorno negativo, sin importar los pares"))

    mejores = [v for v in votos if v["banda"] == "mejor"]
    peores = [v for v in votos if v["banda"] == "peor"]
    for v in mejores:
        razones.append(Razon(f"{v['nombre']} mejores que los de sus pares ({_nombres(v['metricas'])}).", "positivo",
                             "observado", v["metricas"], "cuarto mejor del grupo"))
    for v in peores:
        razones.append(Razon(f"{v['nombre']} peores que los de sus pares ({_nombres(v['metricas'])}).", "negativo",
                             "observado", v["metricas"], "cuarto peor del grupo"))

    if alertas:
        estado, nivel = "Débil", RIESGO
        resumen = "Tiene resultados negativos: " + ve._lista([_nombres([c]) for c, _ in alertas]) + "."
    elif len(votos) < 2:
        estado, nivel = "Sin conclusión", SIN_DATOS
        resumen = "No hay suficientes métricas comparables contra pares para juzgar la calidad."
    elif len(mejores) >= 2 and not peores:
        estado, nivel = "Alta", BIEN
        resumen = "Márgenes y retornos por encima de los de sus pares."
    elif len(peores) >= 2 and not mejores:
        estado, nivel = "Débil", RIESGO
        resumen = "Márgenes y retornos por debajo de los de sus pares."
    else:
        estado, nivel = "Media", NEUTRO
        resumen = "Márgenes y retornos en línea con sus pares, o con señales contrarias."
    nota = NOTA_SECTOR.get(obj.sector)
    if nota:
        faltantes.append(nota[0].upper() + nota[1:])
    return Dimension("calidad", "Calidad del negocio", estado, nivel, resumen, REGLA_CALIDAD, razones, faltantes,
                     percentil, votos=votos)


# ---------------------------------------------------------------------------------------------
# Crecimiento
# ---------------------------------------------------------------------------------------------

REGLA_CRECIMIENTO = (
    f"en caída: ingresos cayendo más de {abs(CAIDA_INGRESOS) * 100:.0f}% interanual; alto: ingresos y ganancias "
    "en el cuarto mejor del grupo (el crecimiento esperado, que es una estimación, suma pero no decide solo) y "
    "ninguno en el peor; bajo: 2+ en el cuarto peor y ninguno en el mejor; medio: el resto"
)


def _crecimiento(obj: ve.Ficha, res: ve.ResultadoValuacion) -> Dimension:
    claves = [c for _, cs in CRECIMIENTO_FAMILIAS.values() for c in cs]
    # Con ganancias negativas el "crecimiento" de ganancias (de una base negativa) no significa nada.
    rs = [r for r in res.metricas if r.clave in claves and not (obj.sin_ganancias and r.clave in ("crec_ganancias", "crec_esperado"))]
    votos = _votar(rs, CRECIMIENTO_FAMILIAS)
    valores = obj.valores
    ingresos, ganancias, esperado = valores.get("crec_ingresos"), valores.get("crec_ganancias"), valores.get("crec_esperado")
    razones: list[Razon] = []

    if ingresos is not None:
        razones.append(Razon(f"Los ingresos {'crecieron' if ingresos >= 0 else 'cayeron'} {ve._pct(ingresos)} frente al mismo "
                             "trimestre del año anterior.", "positivo" if ingresos > 0 else "negativo" if ingresos < 0 else "neutro",
                             "observado", ["crec_ingresos"], "último trimestre contra el mismo de hace un año"))
    if obj.sin_ganancias:
        razones.append(Razon("Sin ganancias en los últimos 12 meses: el crecimiento de ganancias no aplica.", "alerta",
                             "observado", ["crec_ganancias"], "resultado neto ≤ 0"))
    elif ganancias is not None:
        razones.append(Razon(f"Las ganancias {'crecieron' if ganancias >= 0 else 'cayeron'} {ve._pct(ganancias)} frente al mismo "
                             "trimestre del año anterior.", "positivo" if ganancias > 0 else "negativo" if ganancias < 0 else "neutro",
                             "observado", ["crec_ganancias"], "último trimestre contra el mismo de hace un año"))
    if esperado is not None and not obj.sin_ganancias:
        razones.append(Razon(
            f"El mercado descuenta ganancias {ve._pct(esperado)} para el próximo año (estimación implícita en el P/E estimado).",
            "neutro", "estimado", ["crec_esperado"], "P/E de los últimos 12 meses ÷ P/E estimado − 1"))
        if ganancias is not None and abs(esperado - ganancias) >= DIFERENCIA_ESPERADO:
            mas = esperado > ganancias
            razones.append(Razon(
                f"Se espera {'más' if mas else 'menos'} crecimiento ({ve._pct(esperado)}) que el observado en el último "
                f"trimestre ({ve._pct(ganancias)}).", "neutro", "estimado", ["crec_esperado", "crec_ganancias"],
                f"diferencia de al menos {DIFERENCIA_ESPERADO * 100:.0f} puntos entre lo esperado y lo observado"))

    decisivas = [v for v in votos if v["familia"] != "esperado"]
    apoyo_mejor = any(v["familia"] == "esperado" and v["banda"] == "mejor" for v in votos)
    mejores = [v for v in decisivas if v["banda"] == "mejor"]
    peores = [v for v in decisivas if v["banda"] == "peor"]
    for v in votos:
        if v["banda"] in ("mejor", "peor"):
            razones.append(Razon(
                f"Crecimiento de {v['nombre'].lower()} {'mayor' if v['banda'] == 'mejor' else 'menor'} que el de sus pares.",
                "positivo" if v["banda"] == "mejor" else "negativo",
                "estimado" if v["familia"] == "esperado" else "observado", v["metricas"],
                "cuarto mejor del grupo" if v["banda"] == "mejor" else "cuarto peor del grupo"))

    if ingresos is not None and ingresos < CAIDA_INGRESOS:
        estado, nivel = "En caída", RIESGO
        resumen = f"Los ingresos caen {ve._pct(abs(ingresos))} interanual."
    elif len(votos) < 2:
        estado, nivel = "Sin conclusión", SIN_DATOS
        resumen = "No hay suficientes métricas comparables contra pares para juzgar el crecimiento."
    elif len(mejores) + (1 if mejores and apoyo_mejor else 0) >= 2 and not peores:
        estado, nivel = "Alto", BIEN
        resumen = "Crece más que sus pares."
    elif len(peores) >= 2 and not mejores:
        estado, nivel = "Bajo", ATENCION
        resumen = "Crece menos que sus pares."
    else:
        estado, nivel = "Medio", NEUTRO
        resumen = "Crecimiento en línea con sus pares, o con señales contrarias."

    faltantes = _faltantes_de(res, claves, obj)
    faltantes.append(HISTORIA_NO_DISPONIBLE)
    if esperado is None and not obj.sin_ganancias:
        faltantes.append("Estimaciones de crecimiento de analistas (sólo se infieren del P/E estimado, que no está disponible)")
    return Dimension("crecimiento", "Crecimiento", estado, nivel, resumen, REGLA_CRECIMIENTO, razones, faltantes,
                     _percentil_medio(rs), votos=votos)


# ---------------------------------------------------------------------------------------------
# Solidez financiera
# ---------------------------------------------------------------------------------------------

REGLA_SOLIDEZ = (
    f"frágil: 2+ señales fuertes (deuda mayor a {DEUDA_ALTA:.0f} veces el patrimonio, flujo de caja libre negativo, "
    f"sin ganancias, dividendo mayor a las ganancias); con señales de atención: 1 señal fuerte, liquidez corriente "
    f"menor a {LIQUIDEZ_BAJA:.0f}, beta mayor a {BETA_ALTA}, o deuda en el cuarto peor del grupo; sólida: 2+ "
    "indicadores evaluados y ninguna señal; sin conclusión: menos de 2 indicadores con dato"
)


def _solidez(obj: ve.Ficha, res: ve.ResultadoValuacion) -> Dimension:
    valores, extra = obj.valores, obj.extra
    por_clave = {r.clave: r for r in res.metricas}
    fuertes: list[Razon] = []
    moderadas: list[Razon] = []
    sanos: list[Razon] = []
    evaluados = 0

    deuda = valores.get("deuda_patrimonio")
    if deuda is not None:
        evaluados += 1
        if deuda > DEUDA_ALTA:
            fuertes.append(Razon(f"Endeudamiento alto: debe {deuda:.1f} veces su patrimonio.", "alerta", "observado",
                                 ["deuda_patrimonio"], f"Deuda/Patrimonio mayor a {DEUDA_ALTA:.0f}"))
        elif por_clave["deuda_patrimonio"].banda == "peor":
            moderadas.append(Razon(f"Más endeudada que sus pares ({deuda:.1f} veces su patrimonio).", "negativo", "observado",
                                   ["deuda_patrimonio"], "cuarto peor del grupo"))
        else:
            sanos.append(Razon(f"Endeudamiento moderado ({deuda:.1f} veces su patrimonio).", "positivo", "observado",
                               ["deuda_patrimonio"], f"Deuda/Patrimonio hasta {DEUDA_ALTA:.0f}"))

    if obj.sin_ganancias:
        evaluados += 1
        fuertes.append(Razon("No tiene ganancias en los últimos 12 meses.", "alerta", "observado", ["pe"], "resultado neto ≤ 0"))
    elif valores.get("pe") is not None:
        evaluados += 1

    fcf = valores.get("fcf_yield")
    if fcf is not None:
        evaluados += 1
        if fcf < 0:
            fuertes.append(Razon("Consume caja: su flujo de caja libre es negativo.", "alerta", "calculado", ["fcf_yield"],
                                 "flujo de caja libre ÷ capitalización < 0"))
        else:
            sanos.append(Razon("Genera caja: su flujo de caja libre es positivo.", "positivo", "calculado", ["fcf_yield"],
                               "flujo de caja libre ÷ capitalización ≥ 0"))

    payout = extra.get("payout")
    if payout is not None and payout > 0:
        evaluados += 1
        if payout > PAYOUT_NO_CUBIERTO:
            fuertes.append(Razon(f"Paga más dividendos que lo que gana ({ve._pct(payout)} de sus ganancias): difícil de sostener.",
                                 "alerta", "observado", [], f"dividendos ÷ ganancias mayor a {PAYOUT_NO_CUBIERTO * 100:.0f}%"))
        else:
            sanos.append(Razon(f"El dividendo se cubre con ganancias (usa {ve._pct(payout)} de ellas).", "positivo", "observado",
                               [], f"dividendos ÷ ganancias hasta {PAYOUT_NO_CUBIERTO * 100:.0f}%"))

    liquidez = extra.get("liquidez_corriente")
    if liquidez is not None:
        evaluados += 1
        if liquidez < LIQUIDEZ_BAJA:
            moderadas.append(Razon(f"Liquidez corriente de {liquidez:.2f}: sus deudas de corto plazo superan lo que tiene a "
                                   "corto plazo (en algunos negocios, como retail o restaurantes, es normal).", "negativo",
                                   "observado", [], f"liquidez corriente menor a {LIQUIDEZ_BAJA:.0f}"))
        else:
            sanos.append(Razon(f"Liquidez corriente de {liquidez:.2f}: cubre sus deudas de corto plazo.", "positivo", "observado",
                               [], f"liquidez corriente de al menos {LIQUIDEZ_BAJA:.0f}"))

    beta = extra.get("beta")
    if beta is not None:
        evaluados += 1
        if beta > BETA_ALTA:
            moderadas.append(Razon(f"Muy volátil: su beta es {beta:.2f} (se mueve {beta:.1f} veces lo que el mercado).",
                                   "negativo", "observado", [], f"beta mayor a {BETA_ALTA}"))

    if len(fuertes) >= 2:
        estado, nivel = "Frágil", RIESGO
        resumen = "Varias señales de fragilidad financiera."
    elif fuertes or moderadas:
        estado, nivel = "Con señales de atención", ATENCION
        resumen = "Hay señales a revisar."
    elif evaluados >= 2:
        estado, nivel = "Sólida", BIEN
        resumen = "Sin señales de fragilidad en los indicadores disponibles."
    else:
        estado, nivel = "Sin conclusión", SIN_DATOS
        resumen = "Hay muy pocos indicadores de solidez disponibles."

    faltantes = []
    if deuda is None and _aplica("deuda_patrimonio", obj.sector):
        faltantes.append("Deuda/Patrimonio")
    if liquidez is None and obj.sector not in SECTORES_SIN_EBITDA:
        faltantes.append("Liquidez corriente (se informa cuando Yahoo la trae)")
    if fcf is None and _aplica("fcf_yield", obj.sector) and not obj.sin_ganancias:
        faltantes.append("Flujo de caja libre")
    nota = NOTA_SECTOR.get(obj.sector)
    if nota:
        faltantes.append(nota[0].upper() + nota[1:])
    rs_deuda = [por_clave[c] for c in ("deuda_patrimonio",) if c in por_clave]
    return Dimension("solidez", "Solidez financiera", estado, nivel, resumen, REGLA_SOLIDEZ,
                     fuertes + moderadas + sanos, faltantes, _percentil_medio(rs_deuda))


# ---------------------------------------------------------------------------------------------
# Confianza de los datos
# ---------------------------------------------------------------------------------------------

REGLA_CONFIANZA = (
    f"se toma el peor de cuatro chequeos. Cobertura (métricas aplicables con dato): alta desde {COBERTURA_ALTA * 100:.0f}%, "
    f"media desde {COBERTURA_MEDIA * 100:.0f}%. Pares con datos: alta desde {PARES_ALTA}, media desde {PARES_MEDIA}. "
    f"Frescura: alta hasta {ve.DIAS_DATO_VIEJO} días, media hasta {DIAS_DATOS_BAJA}, baja después; el último balance "
    f"cuenta como media pasados {DIAS_CONTABLE_MEDIA} días y baja pasados {DIAS_CONTABLE_BAJA}. Conversión de moneda "
    "o balances de períodos distintos: como mucho media"
)
_NIVEL_CONFIANZA = {2: "alta", 1: "media", 0: "baja"}


def _confianza(obj: ve.Ficha, res: ve.ResultadoValuacion, pares: list[ve.Ficha], hoy: date) -> Dimension:
    puntos: list[int] = []
    razones: list[Razon] = []
    faltantes: list[str] = []

    # -- cobertura --
    omitir = {"pe", "forward_pe", "crec_ganancias", "crec_esperado"} if obj.sin_ganancias else set()
    aplicables = [r for r in res.metricas if r.grupo != "momentum" and r.clave not in OPCIONALES
                  and r.clave not in omitir and _aplica(r.clave, obj.sector)]
    con_dato = [r for r in aplicables if r.valor is not None]
    cobertura = len(con_dato) / len(aplicables) if aplicables else 0.0
    nivel_cob = 2 if cobertura >= COBERTURA_ALTA else 1 if cobertura >= COBERTURA_MEDIA else 0
    puntos.append(nivel_cob)
    razones.append(Razon(f"Hay dato para {len(con_dato)} de {len(aplicables)} métricas aplicables ({cobertura * 100:.0f}%).",
                         "positivo" if nivel_cob == 2 else "alerta" if nivel_cob == 0 else "neutro", "calculado", []))
    faltantes += [r.nombre for r in aplicables if r.valor is None]

    # -- pares --
    n = res.n_pares_con_datos
    nivel_par = 2 if n >= PARES_ALTA else 1 if n >= PARES_MEDIA else 0
    puntos.append(nivel_par)
    razones.append(Razon(
        f"{n} {'par' if n == 1 else 'pares'} con datos." + (" Con tan pocos, la comparación es débil." if nivel_par < 2 else ""),
        "positivo" if nivel_par == 2 else "alerta" if nivel_par == 0 else "neutro", "calculado", []))

    # -- frescura de la descarga --
    if obj.fecha_dato is None:
        puntos.append(0)
    else:
        dias = (hoy - obj.fecha_dato).days
        nivel_fr = 2 if dias <= ve.DIAS_DATO_VIEJO else 1 if dias <= DIAS_DATOS_BAJA else 0
        puntos.append(nivel_fr)
        razones.append(Razon(f"Datos descargados el {obj.fecha_dato.strftime('%d/%m/%Y')} (hace {dias} días).",
                             "positivo" if nivel_fr == 2 else "alerta" if nivel_fr == 0 else "neutro", "observado", []))

    # -- período contable --
    if obj.periodo_contable is None:
        faltantes.append("Fecha del último balance (se completa en la próxima descarga)")
    else:
        edad = (hoy - obj.periodo_contable).days
        nivel_ct = 2 if edad <= DIAS_CONTABLE_MEDIA else 1 if edad <= DIAS_CONTABLE_BAJA else 0
        puntos.append(nivel_ct)
        razones.append(Razon(f"El último balance informado es del {obj.periodo_contable.strftime('%d/%m/%Y')}.",
                             "positivo" if nivel_ct == 2 else "alerta" if nivel_ct == 0 else "neutro", "observado", []))
        distintos = [p for p in pares if p.periodo_contable
                     and abs((p.periodo_contable - obj.periodo_contable).days) > DIAS_PERIODOS_DISTINTOS]
        con_periodo = [p for p in pares if p.periodo_contable]
        if len(con_periodo) >= 2 and len(distintos) * 2 >= len(con_periodo):
            puntos.append(1)
            razones.append(Razon(
                f"{len(distintos)} de {len(con_periodo)} pares tienen balances de otro período (más de "
                f"{DIAS_PERIODOS_DISTINTOS} días de diferencia): los múltiplos no son del todo comparables.",
                "alerta", "calculado", [], "diferencia de períodos contables con la mitad o más de los pares"))

    # -- moneda --
    if obj.recalculadas or obj.descartadas_moneda:
        puntos.append(1)
        razones.append(Razon("El balance está en otra moneda que la cotización: algunos ratios se recalcularon en USD "
                             "o se descartaron.", "alerta", "calculado", list(obj.recalculadas + obj.descartadas_moneda)))
    if obj.momentum_aproximado:
        puntos.append(1)
        razones.append(Razon("El rendimiento de precio se midió en moneda local.", "alerta", "calculado", []))
    if any(r.metodo == "directo" for r in res.metricas):
        razones.append(Razon("Algunas métricas se compararon contra un solo par (diferencia, no percentil).",
                             "alerta", "calculado", [r.clave for r in res.metricas if r.metodo == "directo"]))

    nivel = min(puntos)
    estado = _NIVEL_CONFIANZA[nivel].capitalize()
    resumen = {
        2: "Datos completos, recientes y con suficientes pares: las conclusiones son razonablemente firmes.",
        1: "Los datos tienen limitaciones: tomá las conclusiones con cautela.",
        0: "Datos escasos, viejos o con pocos pares: las conclusiones son poco confiables.",
    }[nivel]
    return Dimension("confianza", "Confianza de los datos", estado, {2: BIEN, 1: ATENCION, 0: RIESGO}[nivel],
                     resumen, REGLA_CONFIANZA, razones, faltantes)


# ---------------------------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------------------------

def diagnostico_sin_datos() -> Diagnostico:
    """Emisor sin fundamentales todavía: todo pendiente, nada inventado."""
    motivo = "todavía no hay fundamentales de este emisor"
    dims = [
        _sin_datos("valuacion", "Valuación", motivo), _sin_datos("calidad", "Calidad del negocio", motivo),
        _sin_datos("crecimiento", "Crecimiento", motivo), _sin_datos("solidez", "Solidez financiera", motivo),
        _sin_datos("confianza", "Confianza de los datos", motivo),
    ]
    return Diagnostico(VERSION_REGLAS, dims, "sin_datos")


def diagnosticar(obj: ve.Ficha, res: ve.ResultadoValuacion, pares: list[ve.Ficha], hoy: date | None = None) -> Diagnostico:
    """Las cinco dimensiones de `obj`, ya comparado (`res`) contra sus `pares`."""
    hoy = hoy or date.today()
    if obj.es_etf:
        dims = [_valuacion(obj, res), _no_aplica("calidad", "Calidad del negocio"), _no_aplica("crecimiento", "Crecimiento"),
                _no_aplica("solidez", "Solidez financiera"), _confianza(obj, res, pares, hoy)]
    else:
        dims = [_valuacion(obj, res), _calidad(obj, res), _crecimiento(obj, res), _solidez(obj, res),
                _confianza(obj, res, pares, hoy)]
    return Diagnostico(VERSION_REGLAS, dims, dims[-1].estado.lower())
