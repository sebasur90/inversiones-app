import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { WatchlistItemOut } from '../../api'
import { alertasDeCompra, type EstadoAlerta } from '../../utils/alertasPrecio'
import { Icon, type IconName } from '../icons/Icons'
import SeverityBadge, { type Severidad } from './SeverityBadge'
import AlertaPrecioBadge from './AlertaPrecioBadge'

const MAX_TICKERS = 4

function iconoDeEstado(_estado: EstadoAlerta): IconName {
  return 'target'
}

const FONDO_SEVERIDAD: Record<Severidad, string> = {
  critico: 'bg-app-coral-soft text-app-coral',
  advertencia: 'bg-app-gold-soft text-app-gold',
  info: 'bg-app-teal-soft text-app-teal',
}

/**
 * Instrumentos de la Watchlist que entraron (o están por entrar) en su zona de compra. Mismo
 * patrón visual que `RequiereAtencion`, pero sin sus otras dos fuentes (hallazgos de
 * diagnóstico y calidad de datos) -- acá sólo hay una cosa que decir: "esto está para comprar".
 *
 * No hace fetch: la watchlist ya está cargada en el contexto (`useInversionesContext`).
 */
export default function OportunidadesCompra({
  watchlist,
  umbralProximidad,
}: {
  watchlist: WatchlistItemOut[]
  umbralProximidad: number
}) {
  const navigate = useNavigate()

  const alertas = useMemo(() => alertasDeCompra(watchlist, umbralProximidad), [watchlist, umbralProximidad])
  if (alertas.length === 0) return null

  const enCartera = new Set(watchlist.filter(w => w.en_cartera).map(w => w.ticker))

  return (
    <section className="mb-4" aria-label="Oportunidades de compra">
      <h3 className="text-strong font-bold text-app-text mb-2">Oportunidades de compra</h3>

      {alertas.slice(0, MAX_TICKERS).map(a => (
        <button
          key={a.ticker}
          onClick={() =>
            enCartera.has(a.ticker)
              ? navigate(`/ticker/${encodeURIComponent(a.ticker)}`)
              : navigate('/watchlist')
          }
          className="w-full flex items-center gap-2.5 text-left bg-app-surface border border-app-border rounded-2xl p-3 mb-2"
        >
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${FONDO_SEVERIDAD[a.severidad]}`}>
            <Icon name={iconoDeEstado(a.estado)} className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-body font-semibold text-app-text truncate">{a.ticker}</div>
            <div className="text-caption text-app-text-dim truncate">{a.nombre}</div>
          </div>
          <AlertaPrecioBadge estado={a.estado} pct={a.pct} />
        </button>
      ))}

      {alertas.length > MAX_TICKERS && (
        <button
          onClick={() => navigate('/watchlist?alerta=con_alerta')}
          className="text-caption font-semibold text-app-text-dim mb-2"
        >
          Ver las {alertas.length - MAX_TICKERS} alertas restantes →
        </button>
      )}
    </section>
  )
}
