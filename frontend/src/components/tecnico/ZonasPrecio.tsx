import { useRef } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import type { TipoZona } from '../../api'

/** Un borde de una zona. `null` = ese lado está abierto. */
export interface ZonaDibujo {
  piso: number | null
  techo: number | null
}

export interface ZonasDibujo {
  compra?: ZonaDibujo | null
  venta?: ZonaDibujo | null
  /** Niveles de la **posición**, ya resueltos a precio absoluto. Se dibujan, no se editan acá. */
  stopLoss?: number | null
  objetivo?: number | null
}

export type BordeZona = 'piso' | 'techo'

export const COLOR_ZONA_COMPRA = '#22d3ee'
export const COLOR_ZONA_VENTA = '#a78bfa'
/** Mismos colores que los niveles de riesgo del backtest: significan lo mismo (stop y objetivo). */
export const COLOR_NIVEL_STOP = '#ef4444'
export const COLOR_NIVEL_OBJETIVO = '#10b981'

/** Alto del área táctil de un handle. 24 px es lo mínimo que un dedo acierta sin pelearse con el
 * gráfico; la línea visible es de 1.5 px y va centrada. */
const ALTO_HANDLE = 24

/** Todos los precios que la zona aporta al dominio Y del panel, para que la banda no quede fuera
 * de la vista. Lo usa `PanelPrecio` antes de calcular la escala. */
export function valoresDeZonas(zonas: ZonasDibujo | undefined): number[] {
  if (!zonas) return []
  const out: number[] = []
  for (const zona of [zonas.compra, zonas.venta]) {
    if (!zona) continue
    if (zona.piso != null) out.push(zona.piso)
    if (zona.techo != null) out.push(zona.techo)
  }
  if (zonas.stopLoss != null) out.push(zonas.stopLoss)
  if (zonas.objetivo != null) out.push(zonas.objetivo)
  return out
}

export function hayAlgoQueDibujar(zonas: ZonasDibujo | undefined): boolean {
  return valoresDeZonas(zonas).length > 0
}

function etiquetaZona(tipo: TipoZona, zona: ZonaDibujo): string {
  const nombre = tipo === 'compra' ? 'Compra' : 'Venta'
  const { piso, techo } = zona
  if (piso != null && techo != null) return `${nombre} ${piso.toFixed(2)}–${techo.toFixed(2)}`
  if (techo != null) return `${nombre} ≤ ${techo.toFixed(2)}`
  if (piso != null) return `${nombre} ≥ ${piso.toFixed(2)}`
  return nombre
}

/**
 * Zonas de compra y venta sobre el panel de precio, y los niveles de la posición.
 *
 * Se dibuja como banda sombreada entre los dos bordes (o como una sola línea cuando la zona está
 * abierta de un lado). El borde que **dispara** el aviso va con línea llena y el opuesto punteado:
 * en una zona de compra dispara el techo (el precio baja y entra) y en una de venta el piso.
 *
 * En modo edición cada borde lleva un handle arrastrable. El arrastre usa `setPointerCapture` y
 * corta la propagación: si el evento llegara al contenedor del gráfico, el mismo gesto haría
 * también pan (`useVentanaVisible`) y mover un borde desplazaría la ventana visible.
 */
export default function ZonasPrecio({
  zonas, ancho, alto, yDeValor, valorDeY, svgRef, editando, onArrastrar,
}: {
  zonas: ZonasDibujo
  ancho: number
  alto: number
  yDeValor: (v: number) => number
  valorDeY: (y: number) => number
  svgRef: React.RefObject<SVGSVGElement | null>
  editando?: boolean
  onArrastrar?: (tipo: TipoZona, borde: BordeZona, valor: number) => void
}) {
  // Ref y no estado: el arrastre dispara en cada movimiento del puntero y re-renderizar para
  // guardar cuál borde se está moviendo sería tirar frames (mismo criterio que `useVentanaVisible`).
  const arrastre = useRef<{ tipo: TipoZona; borde: BordeZona } | null>(null)

  function alBajar(e: ReactPointerEvent, tipo: TipoZona, borde: BordeZona) {
    if (!editando || !onArrastrar) return
    e.stopPropagation()
    e.preventDefault()
    arrastre.current = { tipo, borde }
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  function alMover(e: ReactPointerEvent) {
    const actual = arrastre.current
    if (!actual || !onArrastrar) return
    e.stopPropagation()
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    const y = Math.min(Math.max(e.clientY - rect.top, 0), alto)
    const valor = valorDeY(y)
    if (valor > 0) onArrastrar(actual.tipo, actual.borde, valor)
  }

  function alSoltar(e: ReactPointerEvent) {
    if (!arrastre.current) return
    e.stopPropagation()
    arrastre.current = null
  }

  const bandas: { tipo: TipoZona; zona: ZonaDibujo; color: string }[] = []
  if (zonas.compra) bandas.push({ tipo: 'compra', zona: zonas.compra, color: COLOR_ZONA_COMPRA })
  if (zonas.venta) bandas.push({ tipo: 'venta', zona: zonas.venta, color: COLOR_ZONA_VENTA })

  return (
    <g>
      {bandas.map(({ tipo, zona, color }) => {
        const { piso, techo } = zona
        // El borde que dispara: techo si se compra (se cruza hacia abajo), piso si se vende.
        const bordeDisparo: BordeZona = tipo === 'compra' ? 'techo' : 'piso'
        const yPiso = piso != null ? yDeValor(piso) : null
        const yTecho = techo != null ? yDeValor(techo) : null
        const etiqueta = etiquetaZona(tipo, zona)

        return (
          <g key={tipo}>
            {yPiso != null && yTecho != null && (
              <rect
                x={0} y={Math.min(yPiso, yTecho)} width={ancho}
                height={Math.max(1, Math.abs(yPiso - yTecho))}
                fill={color} fillOpacity={0.12}
              >
                <title>{etiqueta}</title>
              </rect>
            )}

            {(['piso', 'techo'] as BordeZona[]).map(borde => {
              const valor = borde === 'piso' ? piso : techo
              if (valor == null) return null
              const y = yDeValor(valor)
              const dispara = borde === bordeDisparo
              return (
                <g key={borde}>
                  <line
                    x1={0} x2={ancho} y1={y} y2={y}
                    stroke={color} strokeWidth={dispara ? 1.75 : 1}
                    strokeDasharray={dispara ? undefined : '5 4'}
                    opacity={dispara ? 0.95 : 0.6}
                  >
                    <title>{`${etiqueta}${dispara ? ' · este borde dispara el aviso' : ''}`}</title>
                  </line>
                  {editando && (
                    <>
                      {/* Área táctil: ancha, invisible, y por encima de la línea. */}
                      <rect
                        x={0} y={y - ALTO_HANDLE / 2} width={ancho} height={ALTO_HANDLE}
                        fill="transparent" style={{ cursor: 'ns-resize' }}
                        onPointerDown={e => alBajar(e, tipo, borde)}
                        onPointerMove={alMover}
                        onPointerUp={alSoltar}
                        onPointerCancel={alSoltar}
                      />
                      {/* Tirador visible, en el borde izquierdo para no tapar la etiqueta. */}
                      <rect
                        x={2} y={y - 4} width={22} height={8} rx={4}
                        fill={color} fillOpacity={0.9} pointerEvents="none"
                      />
                    </>
                  )}
                </g>
              )
            })}

            {(yTecho != null || yPiso != null) && (
              <text
                x={ancho - 4}
                y={(tipo === 'compra' ? (yTecho ?? yPiso!) : (yPiso ?? yTecho!)) - 5}
                fontSize={10} textAnchor="end" fill={color}
                className="font-mono font-bold" pointerEvents="none"
              >
                {etiqueta}
              </text>
            )}
          </g>
        )
      })}

      {/* Niveles de la posición: referencia, no editables acá. */}
      {([
        { valor: zonas.stopLoss, color: COLOR_NIVEL_STOP, texto: 'Stop loss' },
        { valor: zonas.objetivo, color: COLOR_NIVEL_OBJETIVO, texto: 'Objetivo' },
      ] as const).map(({ valor, color, texto }) => (
        valor == null ? null : (
          <g key={texto} pointerEvents="none">
            <line
              x1={0} x2={ancho} y1={yDeValor(valor)} y2={yDeValor(valor)}
              stroke={color} strokeWidth={1} strokeDasharray="2 3" opacity={0.65}
            >
              <title>{`${texto} de la posición: ${valor.toFixed(2)}`}</title>
            </line>
            <text
              x={4} y={yDeValor(valor) - 4} fontSize={9} fill={color} fillOpacity={0.9}
              className="font-mono"
            >
              {`${texto} ${valor.toFixed(2)}`}
            </text>
          </g>
        )
      ))}
    </g>
  )
}
