import type { RendimientoPorTickerItem } from '../../api'
import { formatPctRatio, formatARSCrudo, formatUSDCrudo, formatPrecio } from '../../utils'
import VariacionDia from '../ui/VariacionDia'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import { pctDelEstado, severidadDeEstado, type EstadoAlerta } from '../../utils/alertasPrecio'
import { Icon } from '../icons/Icons'
import AvatarTicker from '../ui/AvatarTicker'
import InfoTooltip from '../../help/components/InfoTooltip'
import AlertaPrecioBadge from './AlertaPrecioBadge'
import type { Severidad } from './SeverityBadge'

// El avatar del ticker se tiñe con la severidad: en una lista larga el color del borde se
// ve antes que el badge y ancla la fila de un vistazo.
const AVATAR_ALERTA: Record<Severidad, string> = {
  critico: 'border-app-neg/40 text-app-neg',
  advertencia: 'border-app-accent/40 text-app-accent',
  info: 'border-app-pos/40 text-app-pos',
}

export default function PosicionRow({
  item,
  moneda,
  onClick,
  alerta = null,
  peso = null,
}: {
  item: RendimientoPorTickerItem
  moneda: 'USD' | 'ARS'
  onClick: () => void
  /** Estado de sus niveles de precio. `null` deja la fila exactamente como sin alertas. */
  alerta?: EstadoAlerta | null
  /** Qué parte de la cartera es esta posición, como ratio (0.22 = 22%). Sin él, la fila queda igual. */
  peso?: number | null
}) {
  const esARS = moneda === 'ARS'
  const valor = esARS ? item.valor_actual_ars : item.valor_actual_usd
  const rendimiento = esARS ? item.rendimiento_simple_ars : item.rendimiento_simple_usd
  const fmt = useFormatoFijo(moneda)
  const positivo = (rendimiento ?? 0) >= 0
  const avatarAlerta = alerta ? AVATAR_ALERTA[severidadDeEstado(alerta)] : 'border-app-border text-app-text'

  return (
    <button
      onClick={onClick}
      aria-label={`Ver detalle de ${item.ticker} — ${item.nombre}`}
      className="group w-full flex items-center gap-2.5 py-2.5 border-b border-app-border-soft last:border-b-0 text-left rounded-lg transition-colors duration-150 hover:bg-white/[0.035] active:bg-white/[0.06]"
    >
      <AvatarTicker ticker={item.ticker} className={avatarAlerta} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 min-w-0">
          <div className="text-caption font-bold text-app-text truncate">{item.nombre}</div>
          {alerta && <AlertaPrecioBadge estado={alerta} pct={pctDelEstado(item, alerta)} compacto />}
        </div>
        <div className="flex items-center gap-1 text-label text-app-text-dim mt-0.5">
          <span className="truncate">
            <span className="inline-flex items-center gap-0.5">
              {item.tipo_instrumento}
              <InfoTooltip term="posiciones_tipo_instrumento" />
            </span>
            {' · '}
            <span className="inline-flex items-center gap-0.5">
              {item.mercado}
              <InfoTooltip term="posiciones_mercado" />
            </span>
          </span>
        </div>
        {/* Envuelve en vez de desbordar: en un celular angosto el precio y la variación no
            entran al lado de la columna derecha y terminaban encimados sobre ella. */}
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-label mt-0.5">
          <span className="font-mono text-app-text-dim tabular-nums whitespace-nowrap">
            {item.moneda === 'ARS' ? formatARSCrudo(item.precio_actual) : item.moneda === 'USD' ? formatUSDCrudo(item.precio_actual) : formatPrecio(item.precio_actual)}
          </span>
          {/* Sin cotización: el precio de arriba es el costo de compra, no un precio de mercado. */}
          {item.valuado_al_costo ? (
            <span className="text-app-text-faint whitespace-nowrap">al costo</span>
          ) : (
            <VariacionDia pct={item.variacion_dia_pct} className="whitespace-nowrap" />
          )}
        </div>
        {peso != null && Number.isFinite(peso) && peso > 0 && (
          <div className="flex items-center gap-2 mt-1.5" title="Qué parte de tu cartera es esta posición">
            <div aria-hidden="true" className="flex-1 h-1 rounded-full bg-app-surface-2 overflow-hidden">
              <div className="h-1 rounded-full bg-app-accent" style={{ width: `${Math.min(100, peso * 100)}%` }} />
            </div>
            <span className="font-mono text-label text-app-text-dim tabular-nums w-9 text-right">
              {peso < 0.005 ? '<1' : Math.round(peso * 100)}%
            </span>
          </div>
        )}
      </div>
      <div className="text-right shrink-0">
        <div className="font-mono text-caption font-bold text-app-text tabular-nums">{fmt.monto(valor)}</div>
        {rendimiento != null && (
          // El resultado va en una píldora: se distingue de un vistazo en una lista larga y no
          // depende sólo del color (lleva la flecha y el signo).
          <div
            className={`inline-flex items-center justify-end gap-0.5 whitespace-nowrap font-mono text-label font-bold mt-1 px-2 py-0.5 rounded-full tabular-nums ${
              positivo ? 'bg-app-pos-soft text-app-pos' : 'bg-app-neg-soft text-app-neg'
            }`}
          >
            <Icon name={positivo ? 'up' : 'down'} className="w-2.5 h-2.5" />
            {formatPctRatio(rendimiento)}
            <InfoTooltip term="posiciones_rendimiento_simple" />
          </div>
        )}
      </div>
      <Icon
        name="chevron"
        className="w-3.5 h-3.5 -rotate-90 text-app-text-faint shrink-0 transition-[transform,color] duration-150 group-hover:translate-x-0.5 group-hover:text-app-text"
      />
    </button>
  )
}
