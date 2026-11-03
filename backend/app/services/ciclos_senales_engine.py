"""Detección de cambios de estado de rotación sobre el historial semanal. Puro. **No envía nada.**

Es la base para una segunda etapa (alertas por Telegram): acá sólo se decide qué cambios ocurrieron y si
están **confirmados**. Reglas:

- Sólo se mira el último tramo de semanas consecutivas: una semana faltante en el historial corta la
  serie, así que una actualización incompleta no genera un cambio.
- Un cambio de cuadrante es confirmado si se sostiene `confirmacion` semanas seguidas
  (`ciclos_engine.transiciones`); antes de eso es `pendiente`.
- Los eventos describen lo ocurrido con los datos; no dicen qué hacer.

Eventos (`tipo`): `empieza_a_mejorar` (Lagging → Improving), `pasa_a_liderar` (Improving → Leading),
`pierde_momentum` (Leading → Weakening) y `pierde_fortaleza_relativa` (RS-Ratio cruza por debajo de 100:
Leading o Weakening → Improving o Lagging). Un mismo cambio puede llevar más de un tipo.
"""
from __future__ import annotations

from . import ciclos_engine as eng

CAMBIOS = {
    (eng.LAGGING, eng.IMPROVING): "empieza_a_mejorar",
    (eng.IMPROVING, eng.LEADING): "pasa_a_liderar",
    (eng.LEADING, eng.WEAKENING): "pierde_momentum",
}
CON_FORTALEZA = (eng.LEADING, eng.WEAKENING)
SIN_FORTALEZA = (eng.IMPROVING, eng.LAGGING)


def _tipos(anterior: str | None, actual: str) -> list[str]:
    if anterior is None:
        return []
    tipos = [CAMBIOS[(anterior, actual)]] if (anterior, actual) in CAMBIOS else []
    if anterior in CON_FORTALEZA and actual in SIN_FORTALEZA:
        tipos.append("pierde_fortaleza_relativa")
    return tipos


def detectar(historial: list[dict], confirmacion: int = eng.CONFIRMACION_SEMANAS) -> dict:
    """`historial` = `[{"semana": date, "cuadrante": str}]` de semanas cerradas y completas, ordenado."""
    filas = sorted(((h["semana"], h["cuadrante"]) for h in historial), key=lambda f: f[0])
    tramo, descartadas = eng.ultimo_tramo_continuo(filas)
    puntos = [{"fecha": f, "cuadrante": c} for f, c in tramo]
    tr = eng.transiciones(puntos, confirmacion)

    eventos = []
    for c in tr["cambios_confirmados"]:
        for tipo in _tipos(c["anterior"], c["cuadrante"]):
            eventos.append({"tipo": tipo, "desde": c["desde"], "de": c["anterior"], "a": c["cuadrante"],
                            "semanas_sostenido": c["semanas"], "confirmado": True})
    pendiente = tr["pendiente"]
    if pendiente and tr["cuadrante_confirmado"]:
        for tipo in _tipos(tr["cuadrante_confirmado"], pendiente["cuadrante"]):
            eventos.append({"tipo": tipo, "desde": pendiente["desde"], "de": tr["cuadrante_confirmado"], "a": pendiente["cuadrante"],
                            "semanas_sostenido": pendiente["semanas"], "confirmado": False})
    ultimo = tr["cambios_confirmados"][-1] if tr["cambios_confirmados"] else None
    return {
        "eventos": eventos, "estado_confirmado": tr["cuadrante_confirmado"],
        "semanas_en_estado": ultimo["semanas"] if ultimo else 0,
        "liderazgo_sostenido": bool(ultimo and ultimo["cuadrante"] == eng.LEADING and ultimo["semanas"] >= confirmacion),
        "semanas_usadas": len(tramo), "semanas_descartadas": descartadas, "confirmacion_semanas": confirmacion,
    }
