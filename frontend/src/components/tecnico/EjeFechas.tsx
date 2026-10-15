import type { BarraOut } from '../../api'
import type { EscalaX } from './useEscalaX'
import { ticksFechas } from './formatoEjes'

const COLOR_EJE = '#94a3b8'
const COLOR_GRID = '#1c1f2a'

/** Fechas bajo el panel de precio, sobre la misma escala X. Va aparte del panel para no cambiar
 * el alto que éste usa en su escala Y. */
export default function EjeFechas({ barras, escalaX }: { barras: BarraOut[]; escalaX: EscalaX }) {
  const ticks = ticksFechas(barras, escalaX)
  return (
    <svg width={escalaX.ancho} height={16} className="block select-none" aria-hidden="true">
      {ticks.map(t => (
        <g key={t.indice}>
          <line x1={t.x} x2={t.x} y1={0} y2={3} stroke={COLOR_GRID} strokeWidth={1.5} />
          <text x={t.x} y={13} fontSize={9} textAnchor="middle" fill={COLOR_EJE} className="font-mono">
            {t.texto}
          </text>
        </g>
      ))}
    </svg>
  )
}
