import { useRef } from 'react'
import type { BarraOut, OperacionOut, SenalOut } from '../../api'
import type { EscalaX } from './useEscalaX'
import { manejadoresPuntero } from './crosshair'
import { trazoDeSerie, valoresVisibles } from './trazo'
import { COLOR_MOTIVO, GLIFO_MOTIVO } from './motivosSalida'

export interface OverlayPrecio {
  clave: string
  tipo: string
  color: string
  series: Record<string, (number | null)[]>
}

const COLOR_ALCISTA = '#10b981'
const COLOR_BAJISTA = '#ef4444'
const COLOR_PRECIO = '#3b82f6'
const COLOR_GRID = '#1c1f2a'
const COLOR_EJE = '#94a3b8'
const COLOR_STOP = '#ef4444'
const COLOR_TAKE = '#10b981'
const COLOR_TRAILING = '#fbbf24'

/** Salidas de un indicador de precio que NO están en la escala del precio (p.ej. Bollinger trae
 * `ancho_pct`/`pctb`, que son porcentajes u oscilan 0-1, junto con `media`/`superior`/`inferior`
 * que sí son precios): se excluyen acá para que no aplasten la escala de las velas. */
const SALIDAS_EXCLUIDAS_PRECIO: Record<string, string[]> = {
  BOLLINGER: ['ancho_pct', 'pctb'],
  // `dist_max_pct` (~0 a ~-40) y `dist_min_pct` (~0 a ~+80) son porcentajes: en la escala de las
  // velas aplastarían el precio contra el borde. `maximo`/`minimo`/`medio` sí son precios.
  EXTREMOS: ['dist_max_pct', 'dist_min_pct'],
}
function salidasGraficables(o: OverlayPrecio): [string, (number | null)[]][] {
  const excluidas = SALIDAS_EXCLUIDAS_PRECIO[o.tipo] ?? []
  return Object.entries(o.series).filter(([salida]) => !excluidas.includes(salida))
}

/** Precio (velas o línea de cierres) + overlays de indicadores (SMA/EMA/Bollinger) + señales de
 * estrategia + niveles de riesgo de cada operación, sobre la escala X compartida del gráfico.
 *
 * Los niveles (`operaciones[].nivel_stop_loss`, `nivel_take_profit`, `trailing`) los calcula el
 * motor de backtest y viajan en la respuesta: dibujarlos re-derivándolos acá daría una línea que
 * no es la que efectivamente disparó la salida. */
export default function PanelPrecio({
  barras, escalaX, alto, tieneVelas, overlays, senales, operaciones, primeraBarraEvaluable, moneda, hoverIndex, onHover,
}: {
  barras: BarraOut[]
  escalaX: EscalaX
  alto: number
  tieneVelas: boolean
  overlays: OverlayPrecio[]
  senales?: SenalOut[]
  operaciones?: OperacionOut[]
  primeraBarraEvaluable?: number | null
  moneda?: string
  hoverIndex: number | null
  onHover: (i: number | null) => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const handlers = manejadoresPuntero(svgRef, escalaX, onHover)

  const cierres = barras.map(b => b.cierre)
  const valoresBase = tieneVelas
    ? [
        ...valoresVisibles(barras.map(b => b.maximo ?? b.cierre), escalaX),
        ...valoresVisibles(barras.map(b => b.minimo ?? b.cierre), escalaX),
      ]
    : valoresVisibles(cierres, escalaX)
  const valoresOverlay = overlays.flatMap(o => salidasGraficables(o).flatMap(([, s]) => valoresVisibles(s, escalaX)))
  const valoresSenales = (senales ?? []).filter(s => escalaX.visible(s.indice)).map(s => s.precio)
  const todos = [...valoresBase, ...valoresOverlay, ...valoresSenales]
  const minV = todos.length ? Math.min(...todos) : 0
  const maxV = todos.length ? Math.max(...todos) : 1
  const pad = (maxV - minV) * 0.08 || Math.abs(maxV) * 0.05 || 1
  const y0 = minV - pad
  const y1 = maxV + pad
  const yDeValor = (v: number) => alto - ((v - y0) / (y1 - y0 || 1)) * alto

  const anchoVela = Math.max(1, escalaX.pasoX * 0.62)
  const ultimoIndice = barras.length - 1
  const visibles: number[] = []
  for (let i = Math.max(0, escalaX.inicio); i <= Math.min(ultimoIndice, escalaX.fin); i++) visibles.push(i)

  /** Los niveles de riesgo se recortan al tramo de su operación, no a toda la serie: una línea de
   * stop loss extendida más allá de la salida sugeriría una protección que ya no existía. */
  const tramo = (o: OperacionOut) => {
    const desde = o.indice_entrada
    const hasta = o.indice_salida ?? ultimoIndice
    return { desde, hasta, x1: escalaX.xDeIndice(desde), x2: escalaX.xDeIndice(hasta) }
  }
  const opsVisibles = (operaciones ?? []).filter(o => {
    const { desde, hasta } = tramo(o)
    return hasta >= escalaX.inicio && desde <= escalaX.fin
  })

  return (
    <svg ref={svgRef} width={escalaX.ancho} height={alto} className="block touch-none select-none" {...handlers}>
      {primeraBarraEvaluable != null && primeraBarraEvaluable > 0 && escalaX.inicio < primeraBarraEvaluable && (
        <rect
          x={0} y={0}
          width={Math.max(0, escalaX.xDeIndice(primeraBarraEvaluable) - escalaX.pasoX / 2)}
          height={alto} fill="#000" fillOpacity={0.22}
        />
      )}

      {[0.25, 0.5, 0.75].map(f => (
        <line key={f} x1={0} x2={escalaX.ancho} y1={alto * f} y2={alto * f} stroke={COLOR_GRID} strokeDasharray="3 3" />
      ))}

      {/* Banda tenue mientras la estrategia estuvo comprada. */}
      {opsVisibles.map((o, i) => {
        const { x1, x2 } = tramo(o)
        return (
          <rect
            key={`pos-${i}`} x={x1} y={0} width={Math.max(1, x2 - x1)} height={alto}
            fill={COLOR_ALCISTA} fillOpacity={0.06}
          />
        )
      })}

      {moneda && (
        <text x={4} y={12} fontSize={10} fill={COLOR_EJE} fillOpacity={0.85} className="font-mono">
          {moneda}
        </text>
      )}

      {tieneVelas ? (
        visibles.map(i => {
          const b = barras[i]
          const alcista = b.cierre >= (b.apertura ?? b.cierre)
          const color = alcista ? COLOR_ALCISTA : COLOR_BAJISTA
          const x = escalaX.xDeIndice(i)
          const yAlto = yDeValor(b.maximo ?? b.cierre)
          const yBajo = yDeValor(b.minimo ?? b.cierre)
          const yApertura = yDeValor(b.apertura ?? b.cierre)
          const yCierre = yDeValor(b.cierre)
          const yTop = Math.min(yApertura, yCierre)
          const yBottom = Math.max(yApertura, yCierre)
          return (
            <g key={i}>
              <line x1={x} x2={x} y1={yAlto} y2={yBajo} stroke={color} strokeWidth={1} />
              <rect x={x - anchoVela / 2} y={yTop} width={anchoVela} height={Math.max(1, yBottom - yTop)} fill={color} />
            </g>
          )
        })
      ) : (
        <path d={trazoDeSerie(cierres, escalaX, yDeValor)} fill="none" stroke={COLOR_PRECIO} strokeWidth={1.75} />
      )}

      {overlays.map(o => salidasGraficables(o).map(([salida, vals]) => (
        <path
          key={`${o.clave}-${salida}`}
          d={trazoDeSerie(vals, escalaX, yDeValor)}
          fill="none"
          stroke={o.color}
          strokeWidth={salida === 'superior' || salida === 'inferior' ? 1 : 1.5}
          strokeDasharray={salida === 'superior' || salida === 'inferior' ? '4 3' : undefined}
          opacity={salida === 'superior' || salida === 'inferior' ? 0.7 : 1}
        />
      )))}

      {/* Niveles de riesgo por operación: stop loss y take profit son constantes; el trailing es
          una escalera que sólo sube. */}
      {opsVisibles.map((o, i) => {
        const { desde, hasta, x1, x2 } = tramo(o)
        const escalera = trazoEscalera(o.trailing ?? null, desde, hasta, escalaX, yDeValor)
        return (
          <g key={`riesgo-${i}`}>
            {o.nivel_stop_loss != null && (
              <line
                x1={x1} x2={x2} y1={yDeValor(o.nivel_stop_loss)} y2={yDeValor(o.nivel_stop_loss)}
                stroke={COLOR_STOP} strokeWidth={1} strokeDasharray="5 3" opacity={0.75}
              >
                <title>Stop loss: {o.nivel_stop_loss.toFixed(2)}</title>
              </line>
            )}
            {o.nivel_take_profit != null && (
              <line
                x1={x1} x2={x2} y1={yDeValor(o.nivel_take_profit)} y2={yDeValor(o.nivel_take_profit)}
                stroke={COLOR_TAKE} strokeWidth={1} strokeDasharray="5 3" opacity={0.75}
              >
                <title>Take profit: {o.nivel_take_profit.toFixed(2)}</title>
              </line>
            )}
            {escalera && (
              <path d={escalera} fill="none" stroke={COLOR_TRAILING} strokeWidth={1.25} strokeDasharray="2 2" opacity={0.9}>
                <title>Trailing stop</title>
              </path>
            )}
          </g>
        )
      })}

      {(senales ?? []).filter(s => escalaX.visible(s.indice)).map((s, i) => {
        const x = escalaX.xDeIndice(s.indice)
        const compra = s.tipo === 'compra'
        const y = yDeValor(s.precio) + (compra ? 14 : -8)
        const glifo = compra ? '▲' : GLIFO_MOTIVO[s.motivo] ?? '▼'
        return (
          <text
            key={i} x={x} y={y} fontSize={glifo.length > 1 ? 9 : 12} textAnchor="middle"
            fill={compra ? COLOR_ALCISTA : COLOR_MOTIVO[s.motivo] ?? COLOR_BAJISTA}
            className={glifo.length > 1 ? 'font-mono font-bold' : undefined}
          >
            {glifo}
            <title>{`${s.fecha} · ${compra ? 'compra' : 'venta'} a ${s.precio.toFixed(2)}`}</title>
          </text>
        )
      })}

      {hoverIndex != null && barras[hoverIndex] && escalaX.visible(hoverIndex) && (
        <line x1={escalaX.xDeIndice(hoverIndex)} x2={escalaX.xDeIndice(hoverIndex)} y1={0} y2={alto} stroke={COLOR_EJE} strokeOpacity={0.5} />
      )}
    </svg>
  )
}

/** Path en escalones del trailing stop: horizontal mientras el nivel no cambia, vertical cuando
 * sube. Dibujarlo como línea recta entre puntos daría la impresión de que el stop subía de a poco
 * durante la rueda, cuando en realidad salta de una barra a la otra. */
function trazoEscalera(
  niveles: number[] | null, desde: number, hasta: number, escalaX: EscalaX, yDeValor: (v: number) => number,
): string {
  if (!niveles || niveles.length === 0) return ''
  let d = ''
  for (let k = 0; k < niveles.length; k++) {
    const i = desde + k
    if (i > hasta || !escalaX.visible(i)) continue
    const x = escalaX.xDeIndice(i)
    const y = yDeValor(niveles[k])
    const medio = escalaX.pasoX / 2
    if (!d) {
      d = `M ${x - medio} ${y}`
    } else {
      d += ` L ${x - medio} ${y}`
    }
    d += ` L ${x + medio} ${y}`
  }
  return d
}
