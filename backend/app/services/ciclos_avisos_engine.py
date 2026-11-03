"""Qué cambios de estado de Ciclos de mercado se avisan y cómo se redacta el mensaje. Puro: sin DB ni red.

Parte de lo que ya decide `ciclos_senales_engine` (cambios **confirmados**: el estado nuevo se sostuvo
`CONFIRMACION_SEMANAS` semanas) y sólo resuelve cuáles son novedad. Un cambio confirmado se detecta en cada
corrida mientras dure el tramo, así que su identidad es `(grupo, benchmark, tipo, semana en que empezó)`.

Cada cambio no registrado cae en una sola categoría, en este orden:

1. **Primera vez** (todavía no se evaluó nunca): `sembrado`. Se toma el estado actual como punto de
   partida, sin avisar. Es la misma idea que el resto de las alertas: nadie quiere decenas de mensajes por
   cambios que ya habían pasado cuando se prendió el aviso.
2. **Viejo** (empezó hace más de `MAX_DIAS_CAMBIO` días): `viejo`. Cubre un historial recién generado o un
   servidor que estuvo apagado semanas. Se registra sin avisar: llegaría tarde y fuera de contexto.
3. Lo demás es `nuevo`.

Después, `ciclos_avisos` descarta de los nuevos los grupos donde no hay posición. Nada de lo que se redacta acá
dice qué hacer: describe un cambio en la fuerza relativa de un grupo y cuánto pesa en la cartera.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from . import ciclos_engine as eng
from .alertas_engine import escapar_html

#: Un cambio confirmado tarda dos semanas en confirmarse desde que empieza; con este margen una corrida que se
#: saltea unos días o un feriado largo no lo dejan afuera, y uno realmente viejo no se anuncia como novedad.
MAX_DIAS_CAMBIO = 35

NUEVO, SEMBRADO, VIEJO = "nuevo", "sembrado", "viejo"

NOMBRE_CUADRANTE = {
    eng.LEADING: "Leading",
    eng.WEAKENING: "Weakening",
    eng.LAGGING: "Lagging",
    eng.IMPROVING: "Improving",
}

#: Qué describe cada tipo de cambio (`ciclos_senales_engine`). Son hechos sobre la fuerza relativa, no consignas.
FRASE_TIPO = {
    "empieza_a_mejorar": "empieza a recuperar fuerza relativa",
    "pasa_a_liderar": "pasa a liderar frente a la referencia",
    "pierde_momentum": "mantiene fortaleza pero pierde momentum",
    "pierde_fortaleza_relativa": "pierde fortaleza relativa frente a la referencia",
}

PIE = ("Describe un cambio en la fuerza relativa del grupo; no es una indicación de operar. "
       "Detalle en la app → Ciclos.")

MAX_TICKERS = 4


@dataclass(frozen=True)
class Cambio:
    """Un cambio confirmado de un grupo contra su benchmark."""
    grupo_id: str
    benchmark_id: str
    tipo: str
    desde: date
    de: str
    a: str
    semanas: int = 0

    @property
    def clave(self) -> tuple[str, str, str, date]:
        return (self.grupo_id, self.benchmark_id, self.tipo, self.desde)


def desde_senales(grupo_id: str, benchmark_id: str, senales: dict) -> list[Cambio]:
    """Los cambios **confirmados** de `ciclos_senales_engine.detectar`. Los pendientes no se avisan."""
    return [
        Cambio(grupo_id, benchmark_id, e["tipo"], e["desde"], e["de"], e["a"], int(e.get("semanas_sostenido") or 0))
        for e in senales.get("eventos", []) if e.get("confirmado")
    ]


def clasificar(
    cambios: list[Cambio], registrados: set[tuple], hoy: date, primera_vez: bool = False,
    max_dias: int = MAX_DIAS_CAMBIO,
) -> dict[str, list[Cambio]]:
    """Reparte los cambios todavía no registrados en `nuevo`, `sembrado` y `viejo`. Determinista."""
    salida: dict[str, list[Cambio]] = {NUEVO: [], SEMBRADO: [], VIEJO: []}
    for c in sorted(cambios, key=lambda x: (x.desde, x.grupo_id, x.benchmark_id, x.tipo)):
        if c.clave in registrados:
            continue
        if primera_vez:
            salida[SEMBRADO].append(c)
        elif (hoy - c.desde).days > max_dias:
            salida[VIEJO].append(c)
        else:
            salida[NUEVO].append(c)
    return salida


# ---------------------------------------------------------------------------------------------
# Mensaje
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class AvisoGrupo:
    """Lo que el mensaje dice de un grupo: el cambio y cuánto pesa en la cartera."""
    nombre: str
    tipo_grupo: str
    benchmark: str
    de: str
    a: str
    desde: date
    semanas: int
    tipos: tuple[str, ...]
    peso_pct: float
    tickers: tuple[str, ...]


def agrupar(cambios: list[Cambio]) -> list[list[Cambio]]:
    """Un mismo cambio de cuadrante puede llevar más de un tipo (p. ej. perder momentum y fortaleza): se
    cuenta como un solo aviso por `(grupo, benchmark, desde)`."""
    por_cambio: dict[tuple, list[Cambio]] = {}
    for c in sorted(cambios, key=lambda x: x.tipo):
        por_cambio.setdefault((c.grupo_id, c.benchmark_id, c.desde), []).append(c)
    return sorted(por_cambio.values(), key=lambda g: (g[0].desde, g[0].grupo_id))


def _pct(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",") + " %"


def _fecha(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _bloque(a: AvisoGrupo) -> list[str]:
    frases = "; ".join(FRASE_TIPO.get(t, t) for t in a.tipos)
    lineas = [
        f"• <b>{escapar_html(a.nombre)}</b> ({escapar_html(a.tipo_grupo)}) · {NOMBRE_CUADRANTE.get(a.de, a.de)} → "
        f"<b>{NOMBRE_CUADRANTE.get(a.a, a.a)}</b>",
        f"  {escapar_html(frases[:1].upper() + frases[1:])} frente a {escapar_html(a.benchmark)}.",
        f"  Sostenido {a.semanas} semanas, desde la semana del {_fecha(a.desde)}.",
    ]
    tickers = ", ".join(escapar_html(t) for t in a.tickers[:MAX_TICKERS])
    if len(a.tickers) > MAX_TICKERS:
        tickers += f" y {len(a.tickers) - MAX_TICKERS} más"
    lineas.append(f"  En tu cartera: {_pct(a.peso_pct)} del capital ({tickers}).")
    return lineas


def texto_notificacion(avisos: list[AvisoGrupo]) -> str:
    """Un único mensaje HTML con todos los cambios de la corrida. Los más pesados en la cartera, primero."""
    avisos = sorted(avisos, key=lambda a: (-a.peso_pct, a.nombre))
    titulo = "<b>CICLOS DE MERCADO</b> · cambio confirmado" if len(avisos) == 1 else (
        f"<b>CICLOS DE MERCADO</b> · {len(avisos)} cambios confirmados")
    lineas = [titulo, ""]
    for a in avisos:
        lineas.extend(_bloque(a))
        lineas.append("")
    lineas.append(f"<i>{escapar_html(PIE)}</i>")
    return "\n".join(lineas)
