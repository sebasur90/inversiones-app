import type { PropuestaRebalanceoItem } from '../../api'
import { formatUSD } from '../../utils'

const ACCION_LABELS: Record<string, string> = {
  comprar: 'Comprar',
  vender: 'Vender',
  mantener: 'Mantener',
}

const ACCION_CLASSES: Record<string, string> = {
  comprar: 'bg-app-teal-soft text-app-teal',
  vender: 'bg-app-coral-soft text-app-coral',
  mantener: 'bg-app-surface-2 text-app-text-dim',
}

export default function PropuestaRebalanceoRow({ item }: { item: PropuestaRebalanceoItem }) {
  const nombre = item.posicion ?? item.categoria

  return (
    <div className="py-2.5 border-b border-app-border-soft last:border-b-0">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="font-bold text-caption text-app-text truncate">{nombre}</div>
          <div className="text-label text-app-text-dim mt-0.5 font-mono tabular-nums">
            {item.peso_actual_pct.toFixed(1)}% → {item.peso_objetivo_pct.toFixed(1)}%
          </div>
        </div>
        <div className="text-right shrink-0">
          <span className={`inline-block font-bold text-label tracking-wide px-1.5 py-0.5 rounded-[6px] ${ACCION_CLASSES[item.accion]}`}>
            {ACCION_LABELS[item.accion].toUpperCase()}
          </span>
          {item.accion !== 'mantener' && (
            <div className="font-mono text-caption font-bold text-app-text tabular-nums mt-1">
              {formatUSD(Math.abs(item.importe_sugerido_usd))}
            </div>
          )}
        </div>
      </div>
      {item.accion !== 'mantener' && item.comision_estimada_usd > 0 && (
        <div className="text-label text-app-text-faint mt-0.5">Comisión estimada: {formatUSD(item.comision_estimada_usd)}</div>
      )}
      <div className="text-label text-app-text-dim mt-1">{item.motivo}</div>
    </div>
  )
}
