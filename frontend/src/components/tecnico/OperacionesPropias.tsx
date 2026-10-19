import type { EscalaX } from './useEscalaX'
import { formatoPct, formatoPrecio } from './formatoEjes'
import {
  COLOR_COBRO, COLOR_COMPRA_PROPIA, COLOR_SIN_RESULTADO, TEXTO_APROXIMADO, colorResultado,
  type OperacionesUbicadas,
} from './operacionesPropias'

/** Banda tenue detrás de las velas mientras hubo posición, teñida por cómo terminó (o va). */
export function BandasCiclos({
  ubicadas, escalaX, alto,
}: {
  ubicadas: OperacionesUbicadas
  escalaX: EscalaX
  alto: number
}) {
  return (
    <>
      {ubicadas.ciclos
        .filter(c => c.hasta >= escalaX.inicio && c.desde <= escalaX.fin)
        .map(c => {
          const x1 = Math.max(0, escalaX.xDeIndice(c.desde))
          const x2 = Math.min(escalaX.ancho, escalaX.xDeIndice(c.hasta))
          return (
            <rect
              key={`ciclo-${c.ciclo.ciclo}`} x={x1} y={0} width={Math.max(1, x2 - x1)} height={alto}
              fill={colorResultado(c.ciclo.resultado_usd)} fillOpacity={0.08} pointerEvents="none"
            />
          )
        })}
    </>
  )
}

/** Marcas de compra (▲, debajo del precio) y de venta (▼, arriba; verde si ganó, rojo si perdió)
 * y, para la posición abierta, una línea en el costo promedio con lo que va ganando o perdiendo.
 * Una marca aproximada (el precio no se pudo ubicar con exactitud) se dibuja hueca. */
export function MarcasOperaciones({
  ubicadas, escalaX, alto, yDeValor,
}: {
  ubicadas: OperacionesUbicadas
  escalaX: EscalaX
  alto: number
  yDeValor: (v: number) => number
}) {
  return (
    <g>
      {ubicadas.ciclos.map(c => {
        const puntos = c.vwap.filter(p => escalaX.visible(p.indice))
        if (puntos.length < 2) return null
        const color = colorResultado(c.ciclo.resultado_usd)
        const trazo = puntos.map((p, i) => `${i === 0 ? 'M' : 'L'}${escalaX.xDeIndice(p.indice)},${yDeValor(p.valor)}`).join(' ')
        return (
          <path
            key={`vwap-${c.ciclo.ciclo}`} d={trazo} fill="none" stroke={color} strokeWidth={1}
            strokeDasharray="2 3" opacity={0.9} pointerEvents="none"
          >
            <title>VWAP anclado a tu primera compra: el precio medio al que se operó en el mercado desde entonces</title>
          </path>
        )
      })}

      {ubicadas.ciclos
        .filter(c => c.ciclo.abierto && c.ciclo.costo_promedio_grafico != null && c.hasta >= escalaX.inicio)
        .map(c => {
          const costo = c.ciclo.costo_promedio_grafico as number
          const y = yDeValor(costo)
          if (y < 0 || y > alto) return null
          const color = colorResultado(c.ciclo.no_realizado_usd)
          const x1 = Math.max(0, escalaX.xDeIndice(c.desde))
          const pct = c.ciclo.no_realizado_pct
          const etiqueta = `Costo ${formatoPrecio(costo)}${pct != null ? ` · ${formatoPct(pct)}` : ''}`
          return (
            <g key={`costo-${c.ciclo.ciclo}`}>
              <line x1={x1} x2={escalaX.ancho} y1={y} y2={y} stroke={color} strokeWidth={1.25} strokeDasharray="6 3" opacity={0.85}>
                <title>{`Tu costo promedio en este gráfico: ${formatoPrecio(costo)}`}</title>
              </line>
              <text
                x={x1 + 4} y={y - 4} fontSize={10} fill={color} stroke="#121621" strokeWidth={3}
                paintOrder="stroke" className="font-mono font-bold" pointerEvents="none"
              >
                {etiqueta}
              </text>
            </g>
          )
        })}

      {ubicadas.marcas.filter(m => escalaX.visible(m.indice)).map((m, i) => {
        const { op } = m
        const x = escalaX.xDeIndice(m.indice)
        const y = yDeValor(op.precio_grafico as number)
        const compra = op.tipo === 'compra'
        const color = compra ? COLOR_COMPRA_PROPIA : op.resultado_usd == null ? COLOR_SIN_RESULTADO : colorResultado(op.resultado_usd)
        const glifo = compra ? (op.aproximado ? '△' : '▲') : (op.aproximado ? '▽' : '▼')
        const nombre = compra ? 'Compra' : op.tipo === 'amortizacion' ? 'Amortización' : 'Venta'
        const detalle = [
          `${nombre} de ${op.cantidad} el ${op.fecha}`,
          op.resultado_pct != null ? `resultado ${formatoPct(op.resultado_pct)}` : null,
          op.aproximado && op.motivo_aproximado ? `ubicación aproximada: ${TEXTO_APROXIMADO[op.motivo_aproximado] ?? op.motivo_aproximado}` : null,
        ].filter(Boolean).join(' · ')
        return (
          <text
            key={`${op.fecha}-${op.tipo}-${i}`} x={x} y={y + (compra ? 14 : -6)} fontSize={13}
            textAnchor="middle" fill={color} stroke="#121621" strokeWidth={2} paintOrder="stroke"
          >
            {glifo}
            <title>{detalle}</title>
          </text>
        )
      })}
    </g>
  )
}

/** Dividendos y cupones cobrados: una "D" chica en la base del panel (no tienen precio, no
 * pueden ir a la altura de una vela). */
export function MarcasIngresos({
  ubicadas, escalaX, alto,
}: {
  ubicadas: OperacionesUbicadas
  escalaX: EscalaX
  alto: number
}) {
  return (
    <g>
      {ubicadas.cobros.filter(m => escalaX.visible(m.indice)).map((m, i) => (
        <text
          key={`${m.op.fecha}-${m.op.tipo}-${i}`} x={escalaX.xDeIndice(m.indice)} y={alto - 6} fontSize={10}
          textAnchor="middle" fill={COLOR_COBRO} stroke="#121621" strokeWidth={2} paintOrder="stroke"
          className="font-mono font-bold"
        >
          D
          <title>{`${m.op.tipo === 'cupon' ? 'Cupón' : 'Dividendo'} cobrado el ${m.op.fecha}`}</title>
        </text>
      ))}
    </g>
  )
}
