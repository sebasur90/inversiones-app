import { useRef } from 'react'
import type { BarraOut } from '../../api'
import type { EscalaX } from './useEscalaX'
import { manejadoresPuntero } from './crosshair'
import { trazoDeSerie, valoresVisibles } from './trazo'

const COLOR_ALCISTA = '#10b981'
const COLOR_BAJISTA = '#ef4444'
const COLOR_EJE = '#94a3b8'

/** Barras de volumen (coloreadas según si la rueda subió o bajó) + overlays de OBV/volumen
 * promedio, en su propia escala. */
export default function PanelVolumen({
  barras, overlays, escalaX, alto, hoverIndex, onHover,
}: {
  barras: BarraOut[]
  overlays: { clave: string; color: string; series: Record<string, (number | null)[]> }[]
  escalaX: EscalaX
  alto: number
  hoverIndex: number | null
  onHover: (i: number | null) => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const handlers = manejadoresPuntero(svgRef, escalaX, onHover)

  // Escala sobre el tramo visible: con zoom en un tramo tranquilo, un pico de volumen de otro
  // mes no tiene por qué aplastar las barras que se están mirando.
  const volumenes = valoresVisibles(barras.map(b => b.volumen ?? 0), escalaX)
  const maxVol = Math.max(1, ...volumenes)
  const yDeVol = (v: number) => alto - (v / maxVol) * alto
  const anchoBarra = Math.max(1, escalaX.pasoX * 0.62)

  const overlayValores = overlays.flatMap(o => Object.values(o.series).flatMap(s => valoresVisibles(s, escalaX)))
  const maxOverlay = Math.max(1, ...overlayValores)
  const minOverlay = Math.min(0, ...overlayValores)
  const yDeOverlay = (v: number) => alto - ((v - minOverlay) / (maxOverlay - minOverlay || 1)) * alto

  return (
    <div>
      <div className="text-label text-app-text-faint px-1 mb-0.5">Volumen</div>
      <svg ref={svgRef} width={escalaX.ancho} height={alto} className="block touch-none select-none" {...handlers}>
        {barras.map((b, i) => {
          if (b.volumen == null || !escalaX.visible(i)) return null
          const alcista = b.cierre >= (b.apertura ?? (barras[i - 1]?.cierre ?? b.cierre))
          const x = escalaX.xDeIndice(i)
          const y = yDeVol(b.volumen)
          return (
            <rect key={i} x={x - anchoBarra / 2} y={y} width={anchoBarra} height={Math.max(1, alto - y)}
                  fill={alcista ? COLOR_ALCISTA : COLOR_BAJISTA} opacity={0.55} />
          )
        })}

        {overlays.map(o => Object.entries(o.series).map(([salida, vals]) => (
          <path key={`${o.clave}-${salida}`} d={trazoDeSerie(vals, escalaX, yDeOverlay)} fill="none" stroke={o.color} strokeWidth={1.5} />
        )))}

        {hoverIndex != null && escalaX.visible(hoverIndex) && (
          <line x1={escalaX.xDeIndice(hoverIndex)} x2={escalaX.xDeIndice(hoverIndex)} y1={0} y2={alto} stroke={COLOR_EJE} strokeOpacity={0.5} />
        )}
      </svg>
    </div>
  )
}
