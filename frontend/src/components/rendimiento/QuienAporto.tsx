import { useNavigate } from 'react-router-dom'
import type { PnlPorTickerItem } from '../../api'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import AvatarTicker from '../ui/AvatarTicker'

/**
 * La ganancia (o pérdida) de cada instrumento, de mayor a menor, con una barra que da el tamaño
 * relativo. El orden y las barras usan el total; los instrumentos sin cotización van al final,
 * porque su "no realizado" es el costo y no un resultado de mercado.
 */
export default function QuienAporto({ items, esARS }: { items: PnlPorTickerItem[]; esARS: boolean }) {
  const navigate = useNavigate()
  const { monto } = useFormatoMoneda()

  const filas = items
    .map(item => ({
      item,
      total: esARS ? item.total_ars : item.total_usd,
      realizado: esARS ? item.realizado_ars : item.realizado_usd,
      noRealizado: esARS ? item.no_realizado_ars : item.no_realizado_usd,
    }))
    .sort((a, b) => (b.total ?? -Infinity) - (a.total ?? -Infinity))

  const maximo = Math.max(...filas.map(f => Math.abs(f.total ?? 0)), 0)

  return (
    <div className="flex flex-col gap-1.5">
      {filas.map(({ item, total, realizado, noRealizado }) => {
        const color = total == null ? 'var(--color-app-slate)' : total >= 0 ? 'var(--color-app-pos)' : 'var(--color-app-neg)'
        return (
          <button
            key={item.ticker}
            onClick={() => navigate(`/ticker/${encodeURIComponent(item.ticker)}`)}
            className="flex flex-col gap-2 bg-app-surface border border-app-border rounded-2xl px-3.5 py-3 text-left transition-[border-color,box-shadow,transform] duration-150 hover:border-app-accent/50 hover:shadow-[0_6px_24px_-12px_rgba(59,130,246,0.45)] hover:-translate-y-px active:translate-y-0 active:scale-[0.99]"
          >
            <div className="flex items-center gap-3">
              <AvatarTicker ticker={item.ticker} className="border-app-border text-app-text" />
              <div className="min-w-0 flex-1">
                <div className="font-bold text-body text-app-text">
                  {item.ticker} <span className="font-normal text-app-text-dim">{item.nombre}</span>
                </div>
                <div className="text-caption text-app-text-dim tabular-nums">
                  Vendido {monto(realizado)} · En cartera {monto(noRealizado)}
                  {item.valuado_al_costo ? ' (al costo)' : ''}
                </div>
              </div>
              <div className="font-mono text-body font-bold tabular-nums shrink-0" style={{ color }}>
                {monto(total)}
              </div>
            </div>
            <div aria-hidden="true" className="h-1 rounded-full bg-app-surface-2 overflow-hidden">
              <div className="h-1 rounded-full transition-[width] duration-200" style={{ width: `${maximo > 0 ? (Math.abs(total ?? 0) / maximo) * 100 : 0}%`, background: color }} />
            </div>
          </button>
        )
      })}
    </div>
  )
}
