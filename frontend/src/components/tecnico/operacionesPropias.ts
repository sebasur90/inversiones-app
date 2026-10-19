import type { BarraOut, CicloPosicionOut, OperacionPropiaOut, OperacionesGraficoOut } from '../../api'

/** Lo que el usuario ya operó, ubicado sobre las barras que el gráfico tiene en pantalla.
 *
 * El backend manda fechas y precios del gráfico; acá se traducen a índices de barra. Una operación
 * cuya vela no está cargada (período más corto que su fecha) simplemente no aparece: no es un
 * error, el selector de período alcanza para verla. */

export const COLOR_COMPRA_PROPIA = '#38bdf8'
export const COLOR_COBRO = '#f59e0b'
export const COLOR_GANANCIA = '#10b981'
export const COLOR_PERDIDA = '#ef4444'
export const COLOR_SIN_RESULTADO = '#94a3b8'

export function colorResultado(resultado: number | null | undefined): string {
  if (resultado == null) return COLOR_SIN_RESULTADO
  return resultado >= 0 ? COLOR_GANANCIA : COLOR_PERDIDA
}

export const TEXTO_APROXIMADO: Record<string, string> = {
  sin_vela_local: 'no hay vela del instrumento local ese día',
  recortado_al_rango: 'el precio caía fuera de la vela del gráfico',
  fecha_cercana: 'no hubo rueda ese día en esta serie',
  sin_tipo_de_cambio: 'falta el tipo de cambio de esa fecha',
}

export interface MarcaOperacion {
  indice: number
  op: OperacionPropiaOut
}

export interface CicloUbicado {
  ciclo: CicloPosicionOut
  /** Primera y última barra del ciclo dentro de las que están cargadas. */
  desde: number
  hasta: number
  /** El ciclo ya había empezado antes de la primera barra cargada. */
  empiezaAntes: boolean
  /** VWAP anclado a la primera compra, ya traducido a índices de barra. */
  vwap: { indice: number; valor: number }[]
}

export interface OperacionesUbicadas {
  /** Compras, ventas y amortizaciones: se dibujan a la altura de su precio. */
  marcas: MarcaOperacion[]
  /** Dividendos y cupones: sin precio en el gráfico, van en la base del panel. */
  cobros: MarcaOperacion[]
  ciclos: CicloUbicado[]
}

export const esCobro = (tipo: OperacionPropiaOut['tipo']) => tipo === 'dividendo' || tipo === 'cupon'

const dia = (f: string) => f.slice(0, 10)

/** Primer índice con fecha >= `fecha`, o -1. Las barras vienen ordenadas. */
function primerIndiceDesde(barras: BarraOut[], fecha: string): number {
  let lo = 0
  let hi = barras.length
  while (lo < hi) {
    const medio = (lo + hi) >> 1
    if (dia(barras[medio].fecha) < fecha) lo = medio + 1
    else hi = medio
  }
  return lo < barras.length ? lo : -1
}

export function ubicarOperaciones(barras: BarraOut[], datos: OperacionesGraficoOut): OperacionesUbicadas {
  const indicePorFecha = new Map<string, number>()
  barras.forEach((b, i) => indicePorFecha.set(dia(b.fecha), i))

  const marcas: MarcaOperacion[] = []
  const cobros: MarcaOperacion[] = []
  for (const op of datos.operaciones) {
    if (op.fecha_barra == null) continue
    const indice = indicePorFecha.get(dia(op.fecha_barra))
    if (indice == null) continue
    if (esCobro(op.tipo)) cobros.push({ indice, op })
    else if (op.precio_grafico != null) marcas.push({ indice, op })
  }

  const ciclos: CicloUbicado[] = []
  if (barras.length > 0) {
    const primera = dia(barras[0].fecha)
    for (const ciclo of datos.ciclos) {
      const desde = primerIndiceDesde(barras, dia(ciclo.desde))
      // La barra que contiene el cierre del ciclo es la primera con fecha >= `hasta`: con barras
      // semanales o mensuales (fechadas en la última rueda del período) la última con fecha <= `hasta`
      // dejaría afuera el tramo final, y un ciclo que cabe en una barra desaparecería.
      const hastaBarra = ciclo.hasta ? primerIndiceDesde(barras, dia(ciclo.hasta)) : -1
      const hasta = hastaBarra >= 0 ? hastaBarra : barras.length - 1
      if (desde < 0 || hasta < 0 || desde > hasta) continue
      const vwap = (ciclo.vwap ?? []).flatMap(p => {
        const indice = indicePorFecha.get(dia(p.fecha))
        return indice != null ? [{ indice, valor: p.valor }] : []
      })
      ciclos.push({ ciclo, desde, hasta, empiezaAntes: dia(ciclo.desde) < primera, vwap })
    }
  }
  return { marcas, cobros, ciclos }
}

/** Las operaciones propias de la rueda `fecha` (varias en un día es normal). */
export function operacionesDeFecha(datos: OperacionesGraficoOut, fecha: string): OperacionPropiaOut[] {
  return datos.operaciones.filter(o => o.fecha_barra != null && dia(o.fecha_barra) === dia(fecha))
}

/** El ciclo de tenencia que cubre la barra de `fecha`, si lo hay. Una barra cubre desde la
 * anterior (`fechaPrevia`, excluida) hasta su propia fecha: con barras diarias es la rueda misma y
 * con semanales o mensuales, todo el período. */
export function cicloDeFecha(
  datos: OperacionesGraficoOut, fecha: string, fechaPrevia?: string,
): CicloPosicionOut | undefined {
  const f = dia(fecha)
  const previa = fechaPrevia ? dia(fechaPrevia) : null
  return datos.ciclos.find(c =>
    dia(c.desde) <= f && (c.hasta == null || (previa != null ? dia(c.hasta) > previa : f <= dia(c.hasta))))
}

const signo = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(0)}%`

/** Los campos de contexto que lleva toda operación (en el gráfico y en el diario). */
export interface ContextoOperacion {
  tipo: string
  rsi: number | null
  dist_sma200_pct: number | null
  rango_52s_pct: number | null
  post_30_pct: number | null
  post_90_pct: number | null
  post_180_pct: number | null
}

/** Una línea con el contexto de mercado de una compra ("RSI 28 · −12% vs SMA200 · 15% del rango
 * anual") o con lo que pasó después de una venta ("después: +4% a 30d · +18% a 90d"). `null` para
 * lo demás (amortizaciones, cobros). Son indicadores y porcentajes, no importes: se muestran siempre. */
export function textoContexto(op: ContextoOperacion): string | null {
  if (op.tipo === 'compra') {
    const partes = [
      op.rsi != null ? `RSI ${op.rsi.toFixed(0)}` : null,
      op.dist_sma200_pct != null ? `${signo(op.dist_sma200_pct)} vs SMA200` : null,
      op.rango_52s_pct != null ? `${op.rango_52s_pct.toFixed(0)}% del rango anual` : null,
    ].filter(Boolean)
    return partes.length > 0 ? partes.join(' · ') : 'sin historia para el contexto'
  }
  if (op.tipo === 'venta') {
    const partes = [
      op.post_30_pct != null ? `${signo(op.post_30_pct)} a 30d` : null,
      op.post_90_pct != null ? `${signo(op.post_90_pct)} a 90d` : null,
      op.post_180_pct != null ? `${signo(op.post_180_pct)} a 180d` : null,
    ].filter(Boolean)
    return partes.length > 0 ? `después: ${partes.join(' · ')}` : 'todavía no pasaron 30 días'
  }
  return null
}

const CLAVE_MIS_OPERACIONES = 'tecnico-mis-operaciones'

/** El interruptor de "mis compras y ventas" se recuerda entre visitas (y entre el gráfico técnico y
 * el del backtest). Es una comodidad: si el almacenamiento no está disponible (ventana privada,
 * datos bloqueados) arranca apagado. */
export function leerVerOperaciones(): boolean {
  try {
    return localStorage.getItem(CLAVE_MIS_OPERACIONES) === '1'
  } catch {
    return false
  }
}

export function guardarVerOperaciones(ver: boolean): void {
  try {
    localStorage.setItem(CLAVE_MIS_OPERACIONES, ver ? '1' : '0')
  } catch {
    /* sin almacenamiento: queda sólo para esta visita */
  }
}
