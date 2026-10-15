import type { ReactNode } from 'react'
import type { BarraOut, OperacionOut, SenalOut } from '../../api'
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
  barras, indice, moneda, senales, operaciones, conSenales = false, acciones, onQuitar,
}: {
  barras: BarraOut[]
  /** Vela de la cruz; `null` = mostrar la última. */
  indice: number | null
  moneda?: string
  senales?: SenalOut[]
  operaciones?: OperacionOut[]
  /** Reserva la línea de señal/operación (gráfico del backtest). */
  conSenales?: boolean
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
