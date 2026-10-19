/** La cuenta de la calculadora de tamaño de posición. Pura: sin React ni red, para poder razonarla
 * (y probarla) aparte de la pantalla. El servidor sólo aporta los insumos (`TamanoPosicionOut`).
 *
 * Idea: se arriesga una cantidad fija `riesgo` y el stop dice cuánto se pierde por cada dólar
 * invertido (la distancia al stop como fracción del precio). Entonces
 * `monto = riesgo ÷ fracción`. Con un stop a 8 % y un riesgo de US$ 100, el monto es US$ 1.250. */

export type ModoRiesgo = 'pct_cartera' | 'usd'
export type ModoStop = 'precio' | 'pct' | 'atr'

export interface EntradaCalculo {
  /** Precio de entrada, en la moneda de la serie del gráfico. */
  precio: number
  modoRiesgo: ModoRiesgo
  /** % de la cartera (modo `pct_cartera`) o dólares (modo `usd`). */
  riesgo: number
  modoStop: ModoStop
  /** Precio del stop, % por debajo del precio o múltiplo del ATR, según `modoStop`. */
  stop: number
  atr: number | null
  valorCarteraUsd: number | null
  /** La serie está en dólares. Si no (una acción local en pesos), hace falta el MEP. */
  serieEnUsd: boolean
  mep: number | null
  /** Último precio del instrumento local en pesos: con la serie del subyacente de un CEDEAR,
   * permite contar CEDEARs sin necesitar el ratio. */
  precioLocalArs: number | null
}

export type ProblemaCalculo =
  | 'sin_precio' | 'riesgo_invalido' | 'sin_cartera' | 'stop_invalido' | 'sin_atr' | 'stop_sobre_el_precio'

export interface ResultadoCalculo {
  riesgoUsd: number
  /** Distancia del precio de entrada al stop, en la moneda de la serie. */
  distancia: number
  distanciaPct: number
  precioStop: number
  /** Cuánto invertir para perder `riesgoUsd` si el precio toca el stop. */
  montoUsd: number
  /** Unidades del instrumento de la serie (acciones, o la unidad del subyacente). */
  unidades: number | null
  /** CEDEARs a comprar = monto × MEP ÷ precio local. Sólo con la serie del subyacente. */
  cedears: number | null
  /** El monto supera el valor actual de la cartera: el stop es demasiado ajustado para ese riesgo. */
  superaLaCartera: boolean
}

export function calcularPosicion(e: EntradaCalculo): ResultadoCalculo | { problema: ProblemaCalculo } {
  if (!(e.precio > 0)) return { problema: 'sin_precio' }

  let riesgoUsd: number
  if (e.modoRiesgo === 'pct_cartera') {
    if (e.valorCarteraUsd == null || !(e.valorCarteraUsd > 0)) return { problema: 'sin_cartera' }
    riesgoUsd = e.valorCarteraUsd * e.riesgo / 100
  } else {
    riesgoUsd = e.riesgo
  }
  if (!(riesgoUsd > 0)) return { problema: 'riesgo_invalido' }

  let distancia: number
  if (e.modoStop === 'precio') {
    if (!(e.stop > 0)) return { problema: 'stop_invalido' }
    distancia = e.precio - e.stop
    if (distancia <= 0) return { problema: 'stop_sobre_el_precio' }
  } else if (e.modoStop === 'pct') {
    if (!(e.stop > 0) || e.stop >= 100) return { problema: 'stop_invalido' }
    distancia = e.precio * e.stop / 100
  } else {
    if (e.atr == null || !(e.atr > 0)) return { problema: 'sin_atr' }
    if (!(e.stop > 0)) return { problema: 'stop_invalido' }
    distancia = e.atr * e.stop
    if (distancia >= e.precio) return { problema: 'stop_invalido' }
  }

  const fraccion = distancia / e.precio
  const montoUsd = riesgoUsd / fraccion
  // En una serie en pesos, el monto en dólares hay que llevarlo a pesos para contar unidades.
  const montoEnSerie = e.serieEnUsd ? montoUsd : e.mep != null && e.mep > 0 ? montoUsd * e.mep : null
  const cedears = e.serieEnUsd && e.mep != null && e.mep > 0 && e.precioLocalArs != null && e.precioLocalArs > 0
    ? montoUsd * e.mep / e.precioLocalArs
    : null
  return {
    riesgoUsd,
    distancia,
    distanciaPct: fraccion * 100,
    precioStop: e.precio - distancia,
    montoUsd,
    unidades: montoEnSerie != null ? montoEnSerie / e.precio : null,
    cedears,
    superaLaCartera: e.valorCarteraUsd != null && montoUsd > e.valorCarteraUsd,
  }
}
