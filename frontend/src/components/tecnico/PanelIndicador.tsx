import { useRef } from 'react'
import type { EscalaX } from './useEscalaX'
import { manejadoresPuntero } from './crosshair'
import { trazoDeSerie, valoresVisibles } from './trazo'
import { formatoValor } from './formatoEjes'

const PALETA_SUBSERIE: Record<string, string> = {
  valor: '#8b5cf6', k: '#f59e0b', d: '#3b82f6',
  macd: '#10b981', senal: '#ef4444',
  adx: '#f59e0b', di_mas: '#10b981', di_menos: '#ef4444',
  ratio: '#22d3ee', sma: '#f59e0b',
}
const COLOR_GRID = '#1c1f2a'
const COLOR_EJE = '#94a3b8'
const COLOR_HALO = '#121621'

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

  const dominioFijo = tipo === 'RSI' || tipo === 'ESTOCASTICO' || tipo === 'PERCENTIL' || tipo === 'ADX' ? ([0, 100] as const) : null
  // Sólo el tramo visible: al acercar el zoom, un oscilador sin dominio fijo (MACD, ATR, RETORNO)
  // tiene que reescalar sobre lo que se está mirando.
  const valores = Object.values(series).flatMap(s => valoresVisibles(s, escalaX))
  // La fuerza relativa oscila alrededor de 100 (su base): forzar el 0 en la escala la aplastaría.
  const piso = tipo === 'FUERZA_RELATIVA' ? 100 : 0
  const minV = dominioFijo ? dominioFijo[0] : Math.min(piso, ...(valores.length ? valores : [piso]))
  const maxV = dominioFijo ? dominioFijo[1] : Math.max(piso, ...(valores.length ? valores : [piso + 1]))
  const pad = dominioFijo ? 0 : (maxV - minV) * 0.12 || 1
  const y0 = minV - pad
  const y1 = maxV + pad
  const yDeValor = (v: number) => alto - ((v - y0) / (y1 - y0 || 1)) * alto

  const lineasReferencia =
    tipo === 'RSI' ? [30, 70] :
    tipo === 'ESTOCASTICO' ? [20, 80] :
    tipo === 'PERCENTIL' ? [10, 90] :
    tipo === 'ADX' ? [25] :
    tipo === 'FUERZA_RELATIVA' ? [100] :
    tipo === 'MACD' || tipo === 'RETORNO' ? [0] : []

  const anchoBarra = Math.max(1, escalaX.pasoX * 0.6)

  // Valor de cada salida en la vela de la cruz o, sin cruz, en la última: el título del panel es
  // la única forma de leer el número en el celular (no hay hover).
  const indiceValor = hoverIndex ?? escalaX.n - 1
  const valoresTitulo = Object.entries(series).map(([salida, vals]) => ({ salida, valor: vals[indiceValor] }))

  return (
    <div>
      <div className="flex items-baseline gap-x-2 flex-wrap text-label text-app-text-faint px-1 mb-0.5 font-mono tabular-nums">
        <span>{clave}</span>
        {valoresTitulo.map(({ salida, valor }) => (
          <span key={salida} style={{ color: salida === 'histograma' ? COLOR_EJE : PALETA_SUBSERIE[salida] ?? '#3b82f6' }}>
            {valoresTitulo.length > 1 && <span className="text-app-text-faint">{salida} </span>}
            {formatoValor(valor)}
          </span>
        ))}
      </div>
      <svg ref={svgRef} width={escalaX.ancho} height={alto} className="block select-none" {...handlers}>
        {lineasReferencia.map(v => (
          <g key={v}>
            <line x1={0} x2={escalaX.ancho} y1={yDeValor(v)} y2={yDeValor(v)} stroke={COLOR_GRID} strokeDasharray="3 3" />
            <text
              x={escalaX.ancho - 3} y={yDeValor(v) - 2} fontSize={9} textAnchor="end"
              fill={COLOR_EJE} fillOpacity={0.8} stroke={COLOR_HALO} strokeWidth={3} paintOrder="stroke"
              className="font-mono" pointerEvents="none"
            >
              {v}
            </text>
          </g>
        ))}

        {tipo === 'MACD' && series.histograma?.map((v, i) => {
          if (v == null || !escalaX.visible(i)) return null
          const x = escalaX.xDeIndice(i)
          const yZero = yDeValor(0)
          const y = yDeValor(v)
          return (
            <rect
              key={i} x={x - anchoBarra / 2} y={Math.min(y, yZero)}
              width={anchoBarra} height={Math.max(1, Math.abs(y - yZero))}
              fill={v >= 0 ? '#10b981' : '#ef4444'} opacity={0.55}
            />
          )
        })}

        {Object.entries(series).filter(([salida]) => salida !== 'histograma').map(([salida, vals]) => (
          <path
            key={salida} d={trazoDeSerie(vals, escalaX, yDeValor)}
            fill="none" stroke={PALETA_SUBSERIE[salida] ?? '#3b82f6'} strokeWidth={1.5}
          />
        ))}

        {hoverIndex != null && escalaX.visible(hoverIndex) && (
          <line x1={escalaX.xDeIndice(hoverIndex)} x2={escalaX.xDeIndice(hoverIndex)} y1={0} y2={alto} stroke={COLOR_EJE} strokeOpacity={0.5} />
        )}
      </svg>
    </div>
  )
}
