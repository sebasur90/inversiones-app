import { useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent, RefObject } from 'react'
import type { BarraOut, DibujoOut } from '../../api'
import type { EscalaX } from './useEscalaX'
import { formatoPrecio, pasoRedondo, redondearA } from './formatoEjes'
import { geometriaDibujo, indiceDeFecha, rolHorizontal } from './dibujosGrafico'
import type { PuntoDibujo } from './useDibujos'
import { ATRIBUTO_GESTO_PROPIO } from './useVentanaVisible'

const COLOR_HALO = '#121621'
/** Manija de una línea horizontal: el mismo tirador que el borde de una zona (ver `ZonasPrecio`),
 * con un área táctil de 40 px de alto. */
const MANIJA = { ancho: 76, alto: 20, toque: 40 }
/** Radio del área táctil de la punta de una tendencia o un Fibonacci. */
const RADIO_ANCLA_TOQUE = 20
/** Píxeles por paso de precio al arrastrar (igual que las zonas: saltos que se pueden elegir). */
const PX_POR_PASO = 3

/** Lo que el panel le presta a los dibujos para poder arrastrarlos. Sin esto se dibujan quietos. */
export interface ArrastreDibujos {
  svgRef: RefObject<SVGSVGElement | null>
  alto: number
  valorDeY: (y: number) => number
  /** Al soltar: el dibujo con sus puntos nuevos. */
  onMover: (d: DibujoOut) => void
  /** Empieza o termina un arrastre: el panel congela su escala Y mientras tanto (si no, mover la
   * línea que define el máximo cambiaría la escala bajo el dedo). */
  onArrastreActivo: (activo: boolean) => void
}

const dia = (f: string | null | undefined) => (f ?? '').slice(0, 10)

/**
 * Los dibujos manuales sobre el panel de precio: líneas horizontales, de tendencia (extendidas hacia
 * la derecha) y retrocesos de Fibonacci con sus etiquetas. El dibujo seleccionado va más grueso y con
 * una manija en cada anclaje; el primer punto de un dibujo a medio hacer, como un punto con una línea
 * punteada hasta donde está el mouse (en el celular no hay mouse: queda sólo el punto).
 *
 * Una línea horizontal se rotula como **soporte** si está por debajo del último cierre y como
 * **resistencia** si está por encima: es lo que es para el precio de hoy (y cuando el precio la
 * cruza, cambia de papel, que es justamente lo que pasa con un soporte roto).
 *
 * No entran en la escala Y: igual que una zona lejana, un dibujo fuera del tramo que se mira
 * simplemente no se ve. Las líneas son `pointerEvents="none"`: la selección es una cuenta sobre el
 * toque (ver `dibujoEnPunto`), porque los toques los resuelve `useVentanaVisible` con listeners
 * nativos. Lo único que recibe eventos son las manijas del dibujo seleccionado, marcadas como gesto
 * propio (el gráfico no se desplaza mientras se arrastran): la horizontal se mueve de arriba a
 * abajo; las puntas de una tendencia o un Fibonacci, a otra vela y otro precio.
 */
export default function DibujosGrafico({
  dibujos: guardados, barras, escalaX, yDeValor, seleccionado, primerPunto, vistaPrevia, arrastre,
}: {
  dibujos: DibujoOut[]
  barras: BarraOut[]
  escalaX: EscalaX
  yDeValor: (v: number) => number
  seleccionado: number | null
  primerPunto: PuntoDibujo | null
  /** Dónde está el mouse (índice de barra y precio), para la línea punteada del segundo punto. */
  vistaPrevia: { x: number; y: number } | null
  arrastre?: ArrastreDibujos
}) {
  // El ref lo leen los handlers sin esperar al render; el estado dibuja la línea donde va el dedo.
  const gesto = useRef<{ ancla: 0 | 1; dx: number; dy: number; base: DibujoOut; actual: DibujoOut } | null>(null)
  const [moviendo, setMoviendo] = useState<DibujoOut | null>(null)
  const dibujos = moviendo ? guardados.map(d => (d.id === moviendo.id ? moviendo : d)) : guardados
  const ultimoCierre = barras[barras.length - 1]?.cierre ?? null

  function alBajar(e: ReactPointerEvent, d: DibujoOut, ancla: 0 | 1, ax: number, ay: number) {
    if (!arrastre) return
    e.stopPropagation()
    e.preventDefault()
    const rect = arrastre.svgRef.current?.getBoundingClientRect()
    // Se recuerda dónde agarró el dedo respecto del punto: si no, la línea saltaría al lugar tocado.
    gesto.current = {
      ancla, base: d, actual: d,
      dx: rect ? ax - (e.clientX - rect.left) : 0,
      dy: rect ? ay - (e.clientY - rect.top) : 0,
    }
    setMoviendo(d)
    arrastre.onArrastreActivo(true)
    e.currentTarget.setPointerCapture(e.pointerId)
    navigator.vibrate?.(8)
  }

  function alMover(e: ReactPointerEvent) {
    const g = gesto.current
    const rect = arrastre?.svgRef.current?.getBoundingClientRect()
    if (!g || !arrastre || !rect) return
    e.stopPropagation()
    const { valorDeY, alto } = arrastre
    const y = Math.min(Math.max(e.clientY - rect.top + g.dy, 0), alto)
    const precio = redondearA(valorDeY(y), pasoRedondo(Math.abs(valorDeY(y) - valorDeY(y + PX_POR_PASO))))
    if (!(precio > 0)) return
    let nuevo: DibujoOut
    if (g.base.tipo === 'horizontal') {
      nuevo = { ...g.actual, precio1: precio }
    } else {
      const x = Math.min(Math.max(e.clientX - rect.left + g.dx, 0), escalaX.ancho)
      const fecha = dia(barras[escalaX.indiceDeX(x)]?.fecha)
      const [fechaPropia, fechaOtra, precioOtro] = g.ancla === 0
        ? [g.actual.fecha1, g.actual.fecha2, g.actual.precio2]
        : [g.actual.fecha2, g.actual.fecha1, g.actual.precio1]
      // El servidor no acepta las dos puntas en el mismo día, ni un Fibonacci sin recorrido: en
      // esos casos esa coordenada se queda donde estaba.
      const fechaNueva = fecha && fecha !== dia(fechaOtra) ? fecha : dia(fechaPropia)
      const precioNuevo = g.base.tipo === 'fibonacci' && precio === precioOtro
        ? (g.ancla === 0 ? g.actual.precio1 : g.actual.precio2 ?? precio)
        : precio
      nuevo = g.ancla === 0
        ? { ...g.actual, fecha1: fechaNueva, precio1: precioNuevo }
        : { ...g.actual, fecha2: fechaNueva, precio2: precioNuevo }
    }
    g.actual = nuevo
    setMoviendo(nuevo)
  }

  function alSoltar(e: ReactPointerEvent) {
    const g = gesto.current
    if (!g || !arrastre) return
    e.stopPropagation()
    gesto.current = null
    arrastre.onArrastreActivo(false)
    if (g.actual !== g.base) arrastre.onMover(g.actual)
    setMoviendo(null)
  }

  const manejadores = (d: DibujoOut, ancla: 0 | 1, x: number, y: number) => ({
    [ATRIBUTO_GESTO_PROPIO]: '',
    style: { touchAction: 'none' as const, cursor: d.tipo === 'horizontal' ? 'ns-resize' : 'move' },
    onPointerDown: (e: ReactPointerEvent) => alBajar(e, d, ancla, x, y),
    onPointerMove: alMover,
    onPointerUp: alSoltar,
    onPointerCancel: alSoltar,
  })

  return (
    <g>
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
            {d.tipo === 'horizontal' && !(elegido && arrastre) && (
              <text
                x={4} y={g.segmentos[0].y1 - 3} fontSize={9} fill={d.color} stroke={COLOR_HALO} strokeWidth={3}
                paintOrder="stroke" className="font-mono font-bold"
              >
                {`${rolHorizontal(d.precio1, ultimoCierre)} ${formatoPrecio(d.precio1)}`}
              </text>
            )}
            {elegido && d.tipo !== 'horizontal' && g.anclas.map((a, k) => (
              <circle key={k} cx={a.x} cy={a.y} r={moviendo?.id === d.id ? 7 : 5} fill={COLOR_HALO} stroke={d.color} strokeWidth={2} />
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

      {/* Manijas del dibujo seleccionado: lo único de los dibujos que recibe toques. */}
      {arrastre && dibujos.filter(d => d.id === seleccionado).map(d => {
        const g = geometriaDibujo(d, barras, escalaX, yDeValor)
        if (d.tipo === 'horizontal') {
          const y = g.segmentos[0].y1
          const activa = moviendo?.id === d.id
          return (
            <g key={d.id} {...manejadores(d, 0, 0, y)}>
              <title>Arrastrá para mover la línea</title>
              <rect x={0} y={y - MANIJA.toque / 2} width={MANIJA.ancho + 6} height={MANIJA.toque} fill="transparent" />
              <rect
                x={2} y={y - MANIJA.alto / 2} width={MANIJA.ancho} height={MANIJA.alto} rx={MANIJA.alto / 2}
                fill={d.color} stroke={activa ? '#fff' : 'none'} strokeWidth={1.5}
              />
              <text
                x={2 + MANIJA.ancho / 2} y={y + 3.5} fontSize={10} textAnchor="middle"
                fill="#0a0e18" className="font-mono font-bold" pointerEvents="none"
              >
                {`↕ ${formatoPrecio(d.precio1)}`}
              </text>
            </g>
          )
        }
        return (
          <g key={d.id}>
            {g.anclas.map((a, k) => (
              <circle
                key={k} cx={a.x} cy={a.y} r={RADIO_ANCLA_TOQUE} fill="transparent"
                {...manejadores(d, k === 0 ? 0 : 1, a.x, a.y)}
              >
                <title>Arrastrá para mover esta punta</title>
              </circle>
            ))}
          </g>
        )
      })}
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
