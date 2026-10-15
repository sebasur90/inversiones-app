import { useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import type { TipoZona } from '../../api'
import { ATRIBUTO_GESTO_PROPIO } from './useVentanaVisible'
import { formatoPrecio, pasoRedondo, redondearA } from './formatoEjes'

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

/** Manija de un borde: un tirador con el precio, sobre el lado izquierdo (el derecho es del eje de
 * precios). El área táctil es más grande que lo que se ve: 40 px de alto es lo que un dedo acierta
 * sin apuntar. Va escalonada (piso a la izquierda, techo a su lado) para que, en una zona angosta,
 * las dos manijas no queden una encima de la otra. */
const MANIJA = { ancho: 70, alto: 20, toque: 40, separacion: 6 }
/** Píxeles de precio que vale un paso del arrastre: con 3 px por paso el borde se mueve de a
 * saltos que se pueden elegir, no de a decimales al azar. */
const PX_POR_PASO = 3

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
  if (piso != null && techo != null) return `${nombre} ${formatoPrecio(piso)}–${formatoPrecio(techo)}`
  if (techo != null) return `${nombre} ≤ ${formatoPrecio(techo)}`
  if (piso != null) return `${nombre} ≥ ${formatoPrecio(piso)}`
  return nombre
}

/**
 * Zonas de compra y venta sobre el panel de precio, y los niveles de la posición.
 *
 * Se dibuja como banda sombreada entre los dos bordes (o como una sola línea cuando la zona está
 * abierta de un lado). El borde que **dispara** el aviso va con línea llena y el opuesto punteado:
 * en una zona de compra dispara el techo (el precio baja y entra) y en una de venta el piso.
 *
 * En modo edición cada borde lleva una manija arrastrable con su precio. Las manijas se marcan con
 * `ATRIBUTO_GESTO_PROPIO`: `useVentanaVisible` no toma los gestos que empiezan ahí (si no, mover un
 * borde desplazaría también la ventana) y el resto del gráfico sigue navegable mientras se edita
 * — se puede acercar el tramo reciente para ubicar la zona contra las velas. El arrastre usa
 * `setPointerCapture`, se redondea a un paso que depende de la escala y no deja cruzar los bordes.
 */
export default function ZonasPrecio({
  zonas, ancho, alto, yDeValor, valorDeY, svgRef, editando, onArrastrar, onArrastreActivo,
}: {
  zonas: ZonasDibujo
  ancho: number
  alto: number
  yDeValor: (v: number) => number
  valorDeY: (y: number) => number
  svgRef: React.RefObject<SVGSVGElement | null>
  editando?: boolean
  onArrastrar?: (tipo: TipoZona, borde: BordeZona, valor: number) => void
  /** Avisa cuándo empieza y termina un arrastre: el panel congela su escala Y mientras tanto. */
  onArrastreActivo?: (activo: boolean) => void
}) {
  // El ref lo leen los handlers (sin esperar al render); el estado resalta la manija activa.
  const arrastre = useRef<{ tipo: TipoZona; borde: BordeZona; desfase: number } | null>(null)
  const [activa, setActiva] = useState<string | null>(null)

  /** Cuánto vale un paso del arrastre, según la escala actual del panel. */
  const paso = pasoRedondo(Math.abs(valorDeY(0) - valorDeY(PX_POR_PASO)))

  function alBajar(e: ReactPointerEvent, tipo: TipoZona, borde: BordeZona, yBorde: number) {
    if (!editando || !onArrastrar) return
    e.stopPropagation()
    e.preventDefault()
    const rect = svgRef.current?.getBoundingClientRect()
    // Se recuerda dónde agarró el dedo respecto de la línea: si no, el borde saltaría al punto
    // tocado (que puede estar 15 px más abajo, dentro del área táctil).
    const desfase = rect ? yBorde - (e.clientY - rect.top) : 0
    arrastre.current = { tipo, borde, desfase }
    setActiva(`${tipo}-${borde}`)
    onArrastreActivo?.(true)
    e.currentTarget.setPointerCapture(e.pointerId)
    navigator.vibrate?.(8)
  }

  function alMover(e: ReactPointerEvent) {
    const actual = arrastre.current
    if (!actual || !onArrastrar) return
    e.stopPropagation()
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    const y = Math.min(Math.max(e.clientY - rect.top + actual.desfase, 0), alto)
    let valor = redondearA(valorDeY(y), paso)
    // El piso no puede pasar al techo ni al revés: el borrador quedaría inválido a mitad del gesto
    // y el usuario tendría que adivinar qué pasó.
    const zona = zonas[actual.tipo]
    if (actual.borde === 'piso' && zona?.techo != null) valor = Math.min(valor, redondearA(zona.techo - paso, paso))
    if (actual.borde === 'techo' && zona?.piso != null) valor = Math.max(valor, redondearA(zona.piso + paso, paso))
    if (valor > 0) onArrastrar(actual.tipo, actual.borde, valor)
  }

  function alSoltar(e: ReactPointerEvent) {
    if (!arrastre.current) return
    e.stopPropagation()
    arrastre.current = null
    setActiva(null)
    onArrastreActivo?.(false)
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
                  {editando && (() => {
                    const x = 2 + (borde === 'techo' ? MANIJA.ancho + MANIJA.separacion : 0)
                    const esActiva = activa === `${tipo}-${borde}`
                    return (
                      <g
                        {...{ [ATRIBUTO_GESTO_PROPIO]: '' }}
                        style={{ cursor: 'ns-resize', touchAction: 'none' }}
                        onPointerDown={e => alBajar(e, tipo, borde, y)}
                        onPointerMove={alMover}
                        onPointerUp={alSoltar}
                        onPointerCancel={alSoltar}
                      >
                        <title>{`Arrastrá para mover el ${borde} de la zona de ${tipo}`}</title>
                        {/* Área táctil: más grande que el tirador, invisible. */}
                        <rect
                          x={x - 2} y={y - MANIJA.toque / 2} width={MANIJA.ancho + 4} height={MANIJA.toque}
                          fill="transparent"
                        />
                        {esActiva && (
                          <line x1={0} x2={ancho} y1={y} y2={y} stroke={color} strokeWidth={2.5} opacity={0.9} />
                        )}
                        <rect
                          x={x} y={y - MANIJA.alto / 2} width={MANIJA.ancho} height={MANIJA.alto} rx={MANIJA.alto / 2}
                          fill={color} stroke={esActiva ? '#fff' : 'none'} strokeWidth={1.5}
                        />
                        <text
                          x={x + MANIJA.ancho / 2} y={y + 3.5} fontSize={10} textAnchor="middle"
                          fill="#0a0e18" className="font-mono font-bold" pointerEvents="none"
                        >
                          {`↕ ${formatoPrecio(valor)}`}
                        </text>
                      </g>
                    )
                  })()}
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

      <IndicadoresFuera zonas={zonas} ancho={ancho} alto={alto} yDeValor={yDeValor} />

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
              {`${texto} ${formatoPrecio(valor)}`}
            </text>
          </g>
        )
      ))}
    </g>
  )
}

/**
 * Flechas en el borde superior o inferior del panel para las zonas y niveles que quedan fuera de
 * la escala (zoom sobre un tramo viejo, con el precio lejos de la zona). Sin esto, la zona
 * "desaparecía" al hacer zoom y no se sabía si seguía ahí ni para qué lado estaba.
 */
function IndicadoresFuera({
  zonas, ancho, alto, yDeValor,
}: {
  zonas: ZonasDibujo
  ancho: number
  alto: number
  yDeValor: (v: number) => number
}) {
  const items: { texto: string; color: string; lado: 'arriba' | 'abajo' }[] = []
  const lado = (valores: number[]): 'arriba' | 'abajo' | null => {
    const ys = valores.map(yDeValor)
    if (ys.length === 0) return null
    if (ys.every(y => y < 0)) return 'arriba'
    if (ys.every(y => y > alto)) return 'abajo'
    return null
  }

  for (const [tipo, zona, color] of [
    ['compra', zonas.compra, COLOR_ZONA_COMPRA],
    ['venta', zonas.venta, COLOR_ZONA_VENTA],
  ] as const) {
    if (!zona) continue
    const valores = [zona.piso, zona.techo].filter((v): v is number => v != null)
    const l = lado(valores)
    if (l) items.push({ texto: etiquetaZona(tipo, zona), color, lado: l })
  }
  for (const [valor, color, texto] of [
    [zonas.stopLoss, COLOR_NIVEL_STOP, 'Stop loss'],
    [zonas.objetivo, COLOR_NIVEL_OBJETIVO, 'Objetivo'],
  ] as const) {
    if (valor == null) continue
    const l = lado([valor])
    if (l) items.push({ texto: `${texto} ${formatoPrecio(valor)}`, color, lado: l })
  }

  const arriba = items.filter(i => i.lado === 'arriba')
  const abajo = items.filter(i => i.lado === 'abajo')
  return (
    <g pointerEvents="none">
      {arriba.map((it, k) => (
        <text
          key={`a-${it.texto}`} x={ancho / 2} y={12 + k * 13} fontSize={10} textAnchor="middle"
          fill={it.color} stroke="#121621" strokeWidth={3} paintOrder="stroke" className="font-mono font-bold"
        >
          {`▲ ${it.texto}`}
        </text>
      ))}
      {abajo.map((it, k) => (
        <text
          key={`b-${it.texto}`} x={ancho / 2} y={alto - 5 - k * 13} fontSize={10} textAnchor="middle"
          fill={it.color} stroke="#121621" strokeWidth={3} paintOrder="stroke" className="font-mono font-bold"
        >
          {`▼ ${it.texto}`}
        </text>
      ))}
    </g>
  )
}
