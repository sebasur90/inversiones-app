import { useRef } from 'react'
import type { BarraOut, SenalOut } from '../../api'
import type { EscalaX } from './useEscalaX'
import { manejadoresPuntero } from './crosshair'
import { trazoDeSerie } from './trazo'

export interface OverlayPrecio {
  clave: string
  tipo: string
  color: string
  series: Record<string, (number | null)[]>
}

const COLOR_ALCISTA = '#4fd1ae'
const COLOR_BAJISTA = '#e2665a'
const COLOR_PRECIO = '#d8b14a'
const COLOR_GRID = '#223028'
const COLOR_EJE = '#8ca39b'

/** Precio (velas o línea de cierres) + overlays de indicadores (SMA/EMA/Bollinger) + flechas de
 * señales de estrategia, sobre la escala X compartida del gráfico técnico. */
export default function PanelPrecio({
  barras, escalaX, alto, tieneVelas, overlays, senales, primeraBarraEvaluable, moneda, hoverIndex, onHover,
}: {
  barras: BarraOut[]
  escalaX: EscalaX
  alto: number
  tieneVelas: boolean
  overlays: OverlayPrecio[]
  senales?: SenalOut[]
  primeraBarraEvaluable?: number | null
  moneda?: string
  hoverIndex: number | null
  onHover: (i: number | null) => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const handlers = manejadoresPuntero(svgRef, escalaX, onHover)

  const valoresBase = tieneVelas
    ? barras.flatMap(b => [b.maximo ?? b.cierre, b.minimo ?? b.cierre])
    : barras.map(b => b.cierre)
  const valoresOverlay = overlays.flatMap(o => Object.values(o.series).flatMap(s => s.filter((v): v is number => v != null)))
  const valoresSenales = (senales ?? []).map(s => s.precio)
  const todos = [...valoresBase, ...valoresOverlay, ...valoresSenales]
  const minV = todos.length ? Math.min(...todos) : 0
  const maxV = todos.length ? Math.max(...todos) : 1
  const pad = (maxV - minV) * 0.08 || Math.abs(maxV) * 0.05 || 1
  const y0 = minV - pad
  const y1 = maxV + pad
  const yDeValor = (v: number) => alto - ((v - y0) / (y1 - y0 || 1)) * alto

  const anchoVela = Math.max(1, escalaX.pasoX * 0.62)

  return (
    <svg ref={svgRef} width={escalaX.ancho} height={alto} className="block touch-none select-none" {...handlers}>
      {primeraBarraEvaluable != null && primeraBarraEvaluable > 0 && (
        <rect
          x={0} y={0}
          width={Math.max(0, escalaX.xDeIndice(primeraBarraEvaluable) - escalaX.pasoX / 2)}
          height={alto} fill="#000" fillOpacity={0.22}
        />
      )}

      {[0.25, 0.5, 0.75].map(f => (
        <line key={f} x1={0} x2={escalaX.ancho} y1={alto * f} y2={alto * f} stroke={COLOR_GRID} strokeDasharray="3 3" />
      ))}

      {moneda && (
        <text x={4} y={12} fontSize={10} fill={COLOR_EJE} fillOpacity={0.85} className="font-mono">
          {moneda}
        </text>
      )}

      {tieneVelas ? (
        barras.map((b, i) => {
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
        <path d={trazoDeSerie(barras.map(b => b.cierre), escalaX, yDeValor)} fill="none" stroke={COLOR_PRECIO} strokeWidth={1.75} />
      )}

      {overlays.map(o => Object.entries(o.series).map(([salida, vals]) => (
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

      {(senales ?? []).map((s, i) => {
        const x = escalaX.xDeIndice(s.indice)
        const compra = s.tipo === 'compra'
        const y = yDeValor(s.precio) + (compra ? 14 : -8)
        return (
          <text key={i} x={x} y={y} fontSize={12} textAnchor="middle" fill={compra ? COLOR_ALCISTA : COLOR_BAJISTA}>
            {compra ? '▲' : '▼'}
          </text>
        )
      })}

      {hoverIndex != null && barras[hoverIndex] && (
        <line x1={escalaX.xDeIndice(hoverIndex)} x2={escalaX.xDeIndice(hoverIndex)} y1={0} y2={alto} stroke={COLOR_EJE} strokeOpacity={0.5} />
      )}
    </svg>
  )
}
