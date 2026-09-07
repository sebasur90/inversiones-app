import { useRef } from 'react'
import type { EscalaX } from './useEscalaX'
import { manejadoresPuntero } from './crosshair'
import { trazoDeSerie } from './trazo'

const PALETA_SUBSERIE: Record<string, string> = {
  valor: '#9c7aa0', k: '#5b8ba0', d: '#d8b14a',
  macd: '#4fd1ae', senal: '#e2665a',
}
const COLOR_GRID = '#223028'
const COLOR_EJE = '#8ca39b'

/** Panel oscilador genérico (RSI, MACD, Estocástico, ATR): una escala propia, no la de precio.
 * RSI/Estocástico usan dominio fijo [0,100] con líneas de referencia de sobrecompra/sobreventa;
 * MACD dibuja el histograma como barras + las dos líneas, con línea de cero. */
export default function PanelIndicador({
  tipo, clave, series, escalaX, alto, hoverIndex, onHover,
}: {
  tipo: string
  clave: string
  series: Record<string, (number | null)[]>
  escalaX: EscalaX
  alto: number
  hoverIndex: number | null
  onHover: (i: number | null) => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const handlers = manejadoresPuntero(svgRef, escalaX, onHover)

  const dominioFijo = tipo === 'RSI' || tipo === 'ESTOCASTICO' || tipo === 'PERCENTIL' ? ([0, 100] as const) : null
  const valores = Object.values(series).flatMap(s => s.filter((v): v is number => v != null))
  const minV = dominioFijo ? dominioFijo[0] : Math.min(0, ...(valores.length ? valores : [0]))
  const maxV = dominioFijo ? dominioFijo[1] : Math.max(0, ...(valores.length ? valores : [1]))
  const pad = dominioFijo ? 0 : (maxV - minV) * 0.12 || 1
  const y0 = minV - pad
  const y1 = maxV + pad
  const yDeValor = (v: number) => alto - ((v - y0) / (y1 - y0 || 1)) * alto

  const lineasReferencia =
    tipo === 'RSI' ? [30, 70] :
    tipo === 'ESTOCASTICO' ? [20, 80] :
    tipo === 'PERCENTIL' ? [10, 90] :
    tipo === 'MACD' || tipo === 'RETORNO' ? [0] : []

  const anchoBarra = Math.max(1, escalaX.pasoX * 0.6)

  return (
    <div>
      <div className="text-label text-app-text-faint px-1 mb-0.5 font-mono">{clave}</div>
      <svg ref={svgRef} width={escalaX.ancho} height={alto} className="block touch-none select-none" {...handlers}>
        {lineasReferencia.map(v => (
          <line key={v} x1={0} x2={escalaX.ancho} y1={yDeValor(v)} y2={yDeValor(v)} stroke={COLOR_GRID} strokeDasharray="3 3" />
        ))}

        {tipo === 'MACD' && series.histograma?.map((v, i) => {
          if (v == null) return null
          const x = escalaX.xDeIndice(i)
          const yZero = yDeValor(0)
          const y = yDeValor(v)
          return (
            <rect
              key={i} x={x - anchoBarra / 2} y={Math.min(y, yZero)}
              width={anchoBarra} height={Math.max(1, Math.abs(y - yZero))}
              fill={v >= 0 ? '#4fd1ae' : '#e2665a'} opacity={0.55}
            />
          )
        })}

        {Object.entries(series).filter(([salida]) => salida !== 'histograma').map(([salida, vals]) => (
          <path
            key={salida} d={trazoDeSerie(vals, escalaX, yDeValor)}
            fill="none" stroke={PALETA_SUBSERIE[salida] ?? '#d8b14a'} strokeWidth={1.5}
          />
        ))}

        {hoverIndex != null && (
          <line x1={escalaX.xDeIndice(hoverIndex)} x2={escalaX.xDeIndice(hoverIndex)} y1={0} y2={alto} stroke={COLOR_EJE} strokeOpacity={0.5} />
        )}
      </svg>
    </div>
  )
}
