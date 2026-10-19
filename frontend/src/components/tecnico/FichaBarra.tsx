import type { ReactNode } from 'react'
import type { BarraOut, OperacionOut, OperacionPropiaOut, OperacionesGraficoOut, SenalOut } from '../../api'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import { formatMonedaCruda, type Moneda } from '../../utils/formatoMonto'
import {
  COLOR_COMPRA_PROPIA, TEXTO_APROXIMADO, cicloDeFecha, colorResultado, operacionesDeFecha,
} from './operacionesPropias'
import { fechaCorta, formatoPct, formatoPrecio, formatoVolumen } from './formatoEjes'
import { COLOR_MOTIVO, ETIQUETA_MOTIVO, GLIFO_MOTIVO } from './motivosSalida'

const COLOR_ALCISTA = '#10b981'
const COLOR_BAJISTA = '#ef4444'

/**
 * Ficha de la vela bajo la cruz (o, sin cruz, de la última rueda) arriba del gráfico.
 *
 * Alto fijo: si cambiara según la vela, el gráfico saltaría hacia abajo y hacia arriba mientras se
 * recorre con el dedo. En el celular es el único lugar donde se leen los números (no hay hover ni
 * `<title>`), así que también dice la señal de esa rueda y, en el backtest, el estado de la
 * operación con sus niveles de riesgo — los que calculó el motor, no re-derivados acá.
 */
export default function FichaBarra({
  barras, indice, moneda, senales, operaciones, conSenales = false, misOperaciones, acciones, onQuitar,
}: {
  barras: BarraOut[]
  /** Vela de la cruz; `null` = mostrar la última. */
  indice: number | null
  moneda?: string
  senales?: SenalOut[]
  operaciones?: OperacionOut[]
  /** Reserva la línea de señal/operación (gráfico del backtest). */
  conSenales?: boolean
  /** Compras y ventas propias del usuario: reserva una línea con la de la rueda bajo la cruz. */
  misOperaciones?: OperacionesGraficoOut | null
  /** Botones a la derecha de la primera línea (zoom, pantalla completa). */
  acciones?: ReactNode
  onQuitar?: () => void
}) {
  const i = indice != null && barras[indice] ? indice : barras.length - 1
  const b = barras[i]
  const previo = barras[i - 1]?.cierre
  const variacion = b && previo ? (b.cierre / previo - 1) * 100 : null

  const detalle: string[] = []
  if (b?.apertura != null) detalle.push(`Ap ${formatoPrecio(b.apertura)}`)
  if (b?.maximo != null) detalle.push(`Máx ${formatoPrecio(b.maximo)}`)
  if (b?.minimo != null) detalle.push(`Mín ${formatoPrecio(b.minimo)}`)
  if (b?.volumen != null) detalle.push(`Vol ${formatoVolumen(b.volumen)}`)

  return (
    <div className="mb-1">
      <div className="flex items-center justify-between gap-2 min-h-9">
        <div className="min-w-0 flex items-baseline gap-2 whitespace-nowrap overflow-hidden">
          {b && (
            <>
              <span className="text-label text-app-text-faint font-mono tabular-nums">{fechaCorta(b.fecha)}</span>
              <span className="text-strong font-semibold text-app-text font-mono tabular-nums">
                {moneda && <span className="text-label font-normal text-app-text-dim mr-1">{moneda}</span>}
                {formatoPrecio(b.cierre)}
              </span>
              {variacion != null && (
                <span className={`text-caption font-mono tabular-nums ${variacion >= 0 ? 'text-app-pos' : 'text-app-neg'}`}>
                  {formatoPct(variacion)}
                </span>
              )}
            </>
          )}
        </div>
        {acciones && <div className="flex items-center gap-1 shrink-0">{acciones}</div>}
      </div>

      <div className="flex items-center justify-between gap-2 h-6">
        <span className="min-w-0 truncate text-label text-app-text-dim font-mono tabular-nums">
          {detalle.join(' · ')}
        </span>
        {indice != null && onQuitar && (
          <button
            type="button" onClick={onQuitar} aria-label="Quitar la cruz" title="Quitar la cruz"
            className="shrink-0 h-6 px-2 rounded bg-app-surface-2 text-label text-app-text-dim"
          >
            ✕
          </button>
        )}
      </div>

      {misOperaciones && b && (
        <div className="h-5 text-label truncate">
          <LineaMisOperaciones datos={misOperaciones} fecha={b.fecha} />
        </div>
      )}

      {conSenales && b && (
        <div className="h-5 text-label truncate">
          <LineaOperacion indice={i} barra={b} senales={senales ?? []} operaciones={operaciones ?? []} ultimo={barras.length - 1} />
        </div>
      )}
    </div>
  )
}

function LineaOperacion({
  indice, barra, senales, operaciones, ultimo,
}: {
  indice: number
  barra: BarraOut
  senales: SenalOut[]
  operaciones: OperacionOut[]
  ultimo: number
}) {
  const senal = senales.find(s => s.indice === indice)
  if (senal) {
    if (senal.tipo === 'compra') {
      return <span style={{ color: COLOR_ALCISTA }}>▲ Compra a {formatoPrecio(senal.precio)}</span>
    }
    const op = operaciones.find(o => o.indice_salida === indice)
    const color = COLOR_MOTIVO[senal.motivo] ?? COLOR_BAJISTA
    return (
      <span style={{ color }}>
        <span className="font-mono font-bold">{GLIFO_MOTIVO[senal.motivo] ?? '▼'}</span>{' '}
        Venta · {ETIQUETA_MOTIVO[senal.motivo] ?? senal.motivo} a {formatoPrecio(senal.precio)}
        {op && <span className="font-mono"> ({formatoPct(op.retorno_neto_pct)})</span>}
      </span>
    )
  }

  const op = operaciones.find(o => o.indice_entrada <= indice && indice <= (o.indice_salida ?? ultimo))
  if (!op) return <span className="text-app-text-faint">Fuera del mercado</span>

  const resultado = (barra.cierre / op.precio_entrada - 1) * 100
  const trailing = op.trailing?.[indice - op.indice_entrada]
  const niveles: string[] = []
  if (op.nivel_stop_loss != null) niveles.push(`SL ${formatoPrecio(op.nivel_stop_loss)}`)
  if (op.nivel_take_profit != null) niveles.push(`TP ${formatoPrecio(op.nivel_take_profit)}`)
  if (trailing != null) niveles.push(`TS ${formatoPrecio(trailing)}`)
  return (
    <span className="text-app-text-dim">
      Comprado desde {fechaCorta(op.fecha_entrada)}{' '}
      <span className={`font-mono ${resultado >= 0 ? 'text-app-pos' : 'text-app-neg'}`}>{formatoPct(resultado)}</span>
      {niveles.length > 0 && <span className="font-mono"> · {niveles.join(' · ')}</span>}
    </span>
  )
}

const NOMBRE_TIPO: Record<OperacionPropiaOut['tipo'], string> = {
  compra: 'Compraste', venta: 'Vendiste', amortizacion: 'Amortizaste',
}

/** Qué hiciste esa rueda y cómo va la posición. Los importes del resultado pasan por el modo
 * privacidad; el precio al que se operó y los porcentajes se muestran siempre. */
function LineaMisOperaciones({ datos, fecha }: { datos: OperacionesGraficoOut; fecha: string }) {
  const fmt = useFormatoFijo('USD')
  const ops = operacionesDeFecha(datos, fecha)

  if (ops.length > 0) {
    return (
      <span className="font-mono">
        {ops.map((op, i) => {
          const compra = op.tipo === 'compra'
          const color = compra ? COLOR_COMPRA_PROPIA : colorResultado(op.resultado_usd)
          const moneda: Moneda = op.moneda === 'USD' ? 'USD' : 'ARS'
          return (
            <span key={i}>
              {i > 0 && <span className="text-app-text-faint"> · </span>}
              <span style={{ color }}>
                {compra ? (op.aproximado ? '△' : '▲') : (op.aproximado ? '▽' : '▼')} {NOMBRE_TIPO[op.tipo]} {op.cantidad}
              </span>
              <span className="text-app-text-dim">
                {' '}a {formatMonedaCruda(op.precio, moneda)}
                {op.precio_usd_mep != null && moneda === 'ARS' && ` (${formatMonedaCruda(op.precio_usd_mep, 'USD')})`}
              </span>
              {!compra && op.resultado_usd != null && (
                <span style={{ color }}>
                  {' '}· {fmt.montoConSigno(op.resultado_usd)}
                  {op.resultado_pct != null && ` (${formatoPct(op.resultado_pct)})`}
                </span>
              )}
              {op.aproximado && (
                <span className="text-app-text-faint">
                  {' '}· aprox.{op.motivo_aproximado && TEXTO_APROXIMADO[op.motivo_aproximado] ? ` (${TEXTO_APROXIMADO[op.motivo_aproximado]})` : ''}
                </span>
              )}
            </span>
          )
        })}
      </span>
    )
  }

  const ciclo = cicloDeFecha(datos, fecha)
  if (!ciclo) return <span className="text-app-text-faint">Sin posición</span>

  const pct = ciclo.abierto ? ciclo.no_realizado_pct : ciclo.resultado_pct
  const resultado = ciclo.abierto ? ciclo.no_realizado_usd : ciclo.resultado_usd
  return (
    <span className="text-app-text-dim">
      {ciclo.abierto ? 'En posición' : 'Posición'} desde {fechaCorta(ciclo.desde)}
      {ciclo.hasta && ` hasta ${fechaCorta(ciclo.hasta)}`}
      {pct != null && (
        <span className="font-mono" style={{ color: colorResultado(resultado) }}>
          {' '}· {ciclo.abierto ? 'hoy ' : ''}{formatoPct(pct)}
        </span>
      )}
    </span>
  )
}
