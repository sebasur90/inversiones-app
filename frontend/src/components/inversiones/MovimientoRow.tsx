import type { MovimientoInversion } from '../../api'
import { formatUSD } from '../../utils'

const TIPO_LABELS: Record<string, string> = {
  compra: 'Compra',
  venta: 'Venta',
  dividendo: 'Dividendo',
  cupon: 'Cupón',
  amortizacion: 'Amortización',
}

const TIPO_BADGE_CLASSES: Record<string, string> = {
  compra: 'bg-app-steel/15 text-app-steel',
  venta: 'bg-app-plum/15 text-app-plum',
  dividendo: 'bg-app-teal-soft text-app-teal',
  cupon: 'bg-app-teal-soft text-app-teal',
  amortizacion: 'bg-app-plum/15 text-app-plum',
}

const MOVIMIENTOS_INGRESO = ['dividendo', 'cupon']

function formatMonto(mov: MovimientoInversion): string {
  const monto = mov.cantidad != null ? mov.cantidad * mov.precio : mov.precio
  const prefijo = MOVIMIENTOS_INGRESO.includes(mov.tipo_movimiento) ? '+' : mov.tipo_movimiento === 'compra' ? '−' : '+'
  const valor = mov.moneda === 'USD' ? formatUSD(Math.abs(monto)) : `$${Math.abs(monto).toLocaleString('es-AR')}`
  return `${prefijo}${valor}`
}

export default function MovimientoRow({ mov }: { mov: MovimientoInversion }) {
  const esIngreso = MOVIMIENTOS_INGRESO.includes(mov.tipo_movimiento)
  const detalle = mov.cantidad != null ? `${mov.cantidad.toLocaleString('es-AR', { maximumFractionDigits: 8 })} @ ${mov.precio.toLocaleString('es-AR', { maximumFractionDigits: 6 })} ${mov.moneda}` : mov.moneda

  return (
    <div className="flex items-center gap-2.5 py-2.5 border-b border-app-border-soft last:border-b-0">
      <div className="w-9 h-9 rounded-[11px] bg-app-surface-2 border border-app-border flex items-center justify-center font-mono text-[10px] font-bold text-app-text shrink-0">
        {mov.ticker.slice(0, 4)}
      </div>
      <div className="flex-1 min-w-0">
        <span className={`inline-block font-bold text-[9.5px] tracking-wide px-1.5 py-0.5 rounded-[6px] ${TIPO_BADGE_CLASSES[mov.tipo_movimiento] ?? 'bg-app-surface-2 text-app-text-dim'}`}>
          {(TIPO_LABELS[mov.tipo_movimiento] ?? mov.tipo_movimiento).toUpperCase()}
        </span>
        <div className="text-[10.5px] text-app-text-dim mt-1 truncate">{detalle}</div>
      </div>
      <div className={`font-mono text-[12.5px] font-bold tabular-nums shrink-0 ${esIngreso ? 'text-app-teal' : 'text-app-text'}`}>{formatMonto(mov)}</div>
    </div>
  )
}
