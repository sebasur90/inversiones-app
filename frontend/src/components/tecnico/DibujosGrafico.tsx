import type { BarraOut, DibujoOut } from '../../api'
import type { EscalaX } from './useEscalaX'
import { formatoPrecio } from './formatoEjes'
import { geometriaDibujo, indiceDeFecha } from './dibujosGrafico'
import type { PuntoDibujo } from './useDibujos'

const COLOR_HALO = '#121621'

/**
 * Los dibujos manuales sobre el panel de precio: líneas horizontales, de tendencia (extendidas hacia
 * la derecha) y retrocesos de Fibonacci con sus etiquetas. El dibujo seleccionado va más grueso y con
 * una manija en cada anclaje; el primer punto de un dibujo a medio hacer, como un punto con una línea
 * punteada hasta donde está el mouse (en el celular no hay mouse: queda sólo el punto).
 *
 * No entran en la escala Y: igual que una zona lejana, un dibujo fuera del tramo que se mira
 * simplemente no se ve. Todo es `pointerEvents="none"`: la selección es una cuenta sobre el toque
 * (ver `dibujoEnPunto`), porque los toques los resuelve `useVentanaVisible` con listeners nativos.
 */
export default function DibujosGrafico({
  dibujos, barras, escalaX, yDeValor, seleccionado, primerPunto, vistaPrevia,
}: {
  dibujos: DibujoOut[]
  barras: BarraOut[]
  escalaX: EscalaX
  yDeValor: (v: number) => number
  seleccionado: number | null
  primerPunto: PuntoDibujo | null
  /** Dónde está el mouse (índice de barra y precio), para la línea punteada del segundo punto. */
  vistaPrevia: { x: number; y: number } | null
}) {
  return (
    <g pointerEvents="none">
      {dibujos.map(d => {
        const g = geometriaDibujo(d, barras, escalaX, yDeValor)
        const elegido = d.id === seleccionado
        return (
          <g key={d.id}>
            {g.segmentos.map((s, k) => (
              <g key={k}>
                <line
                  x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} stroke={d.color}
                  strokeWidth={elegido ? 2.25 : 1.25} opacity={s.nivel != null && s.nivel !== 0 && s.nivel !== 1 ? 0.7 : 0.95}
                />
                {s.etiqueta && (
                  <text
                    x={s.x2 - 4} y={s.y2 - 3} fontSize={9} textAnchor="end" fill={d.color}
                    stroke={COLOR_HALO} strokeWidth={3} paintOrder="stroke" className="font-mono font-bold"
                  >
                    {`${s.etiqueta} · ${formatoPrecio(precioDeNivel(d, s.nivel))}`}
                  </text>
                )}
              </g>
            ))}
            {d.tipo === 'horizontal' && (
              <text
                x={4} y={g.segmentos[0].y1 - 3} fontSize={9} fill={d.color} stroke={COLOR_HALO} strokeWidth={3}
                paintOrder="stroke" className="font-mono font-bold"
              >
                {formatoPrecio(d.precio1)}
              </text>
            )}
            {elegido && g.anclas.map((a, k) => (
              <circle key={k} cx={a.x} cy={a.y} r={5} fill={COLOR_HALO} stroke={d.color} strokeWidth={2} />
            ))}
          </g>
        )
      })}

      {primerPunto && (
        <PrimerPunto
          punto={primerPunto} barras={barras} escalaX={escalaX} yDeValor={yDeValor} vistaPrevia={vistaPrevia}
        />
      )}
    </g>
  )
}

function precioDeNivel(d: DibujoOut, nivel: number | undefined): number {
  if (d.precio2 == null || nivel == null) return d.precio1
  return d.precio2 + (d.precio1 - d.precio2) * nivel
}

function PrimerPunto({
  punto, barras, escalaX, yDeValor, vistaPrevia,
}: {
  punto: PuntoDibujo
  barras: BarraOut[]
  escalaX: EscalaX
  yDeValor: (v: number) => number
  vistaPrevia: { x: number; y: number } | null
}) {
  const x = escalaX.xDeIndice(indiceDeFecha(barras, punto.fecha))
  const y = yDeValor(punto.precio)
  return (
    <g>
      {vistaPrevia && (
        <line x1={x} y1={y} x2={vistaPrevia.x} y2={vistaPrevia.y} stroke="#e2e8f0" strokeWidth={1.25} strokeDasharray="4 3" opacity={0.8} />
      )}
      <circle cx={x} cy={y} r={5} fill="#e2e8f0" stroke={COLOR_HALO} strokeWidth={2} />
    </g>
  )
}
