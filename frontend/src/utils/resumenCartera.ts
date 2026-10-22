import type { EvolucionPunto, RendimientoPorTickerItem } from '../api'

type Moneda = 'USD' | 'ARS'

export interface MovimientoDelDia {
  ticker: string
  nombre: string
  /** Variación del precio contra el registro anterior, como ratio (0.03 = +3%). */
  pct: number
  /** Cuánto movió esa posición el valor de la cartera, en la moneda pedida. */
  efecto: number
}

export interface VariacionDiaCartera {
  /** Efecto total en la moneda pedida, sumando sólo las posiciones con dato del día. */
  monto: number
  /** Sobre el valor que tenían esas mismas posiciones ayer. */
  pct: number
  conDato: number
  total: number
  movimientos: MovimientoDelDia[]
}

/**
 * Cuánto se movió la cartera en el último día, armado con la variación diaria que ya trae cada
 * posición (`variacion_dia_pct`): no se pide nada nuevo al backend.
 *
 * Es una aproximación y por eso sólo cuenta las posiciones que tienen dato real: las valuadas al
 * costo (sin cotización) no se mueven y no entran. En pesos, el efecto del tipo de cambio sobre
 * un activo que cotiza en dólares no está incluido: la variación es la del precio del activo.
 * Devuelve `null` si ninguna posición tiene dato, para que la pantalla muestre "—" y no un 0%.
 */
export function variacionDiaCartera(
  posiciones: RendimientoPorTickerItem[],
  moneda: Moneda,
): VariacionDiaCartera | null {
  const movimientos: MovimientoDelDia[] = []
  let valorHoy = 0

  for (const p of posiciones) {
    const pct = p.variacion_dia_pct
    const valor = moneda === 'ARS' ? p.valor_actual_ars : p.valor_actual_usd
    if (pct == null || p.valuado_al_costo || !Number.isFinite(pct) || !(valor > 0) || pct <= -1) continue
    // valor_hoy = valor_ayer × (1 + pct)  →  efecto = valor_hoy − valor_ayer.
    movimientos.push({ ticker: p.ticker, nombre: p.nombre, pct, efecto: (valor * pct) / (1 + pct) })
    valorHoy += valor
  }

  if (movimientos.length === 0) return null

  const monto = movimientos.reduce((acc, m) => acc + m.efecto, 0)
  const valorAyer = valorHoy - monto
  return {
    monto,
    pct: valorAyer > 0 ? monto / valorAyer : 0,
    conDato: movimientos.length,
    total: posiciones.length,
    movimientos,
  }
}

/**
 * Las posiciones que más empujaron en cada sentido, por efecto en plata y no por porcentaje:
 * un +8% sobre una posición chica mueve menos la cartera que un +1% sobre la más grande.
 */
export function mayoresMovimientos(movimientos: MovimientoDelDia[], porLado = 2) {
  const suben = movimientos.filter(m => m.efecto > 0).sort((a, b) => b.efecto - a.efecto).slice(0, porLado)
  const bajan = movimientos.filter(m => m.efecto < 0).sort((a, b) => a.efecto - b.efecto).slice(0, porLado)
  return { suben, bajan }
}

/**
 * Ganancia del tramo de la serie, sin contar los aportes: (valor final − valor inicial) −
 * (capital aportado final − capital aportado inicial). Comparar sólo los valores mezclaría lo que
 * ganó la cartera con lo que el usuario puso. `null` con menos de dos puntos.
 */
export function resultadoDelPeriodo(puntos: EvolucionPunto[], moneda: Moneda): number | null {
  if (puntos.length < 2) return null
  const a = puntos[0]
  const b = puntos[puntos.length - 1]
  const valor = (p: EvolucionPunto) => (moneda === 'ARS' ? p.valor_ars : p.valor_usd)
  const capital = (p: EvolucionPunto) => (moneda === 'ARS' ? p.capital_aportado_ars : p.capital_aportado_usd)
  return valor(b) - valor(a) - (capital(b) - capital(a))
}
