import { useQuery } from '@tanstack/react-query'
import { getDescomposicionFxPorPosicion, getPreciosTicker, type PrecioPunto, type DescomposicionFxPosicionItem } from '../../api'
import { qk } from '../../api/queryClient'
import { formatARS, formatCantidad, formatPctRatio, formatPrecio, formatUSD } from '../../utils'
import Sparkline from '../../components/charts/Sparkline'
import MetricTile from '../../components/ui/MetricTile'
import { Icon } from '../../components/icons/Icons'
import type { TickerPositionOut } from '../../api'

export default function TickerResumenTab({ position, cartera, monedaSeleccionada }: { position: TickerPositionOut; cartera: string | null; monedaSeleccionada: 'ARS' | 'USD' }) {
  const preciosQuery = useQuery({
    queryKey: qk.de('precios-ticker', position.ticker),
    queryFn: () => getPreciosTicker(position.ticker),
  })
  // La descomposición FX es de la cartera entera: cacheada por cartera, se comparte con
  // cualquier otro ticker que se mire después.
  const fxQuery = useQuery({
    queryKey: qk.de('descomposicion-fx-posicion', cartera),
    queryFn: () => getDescomposicionFxPorPosicion(cartera),
  })

  const precios: PrecioPunto[] = preciosQuery.data?.puntos ?? []
  const descomposicionFxPorTicker: DescomposicionFxPosicionItem | null =
    fxQuery.data?.posiciones.find(p => p.ticker === position.ticker) ?? null

  const esARS = monedaSeleccionada === 'ARS'
  const formatMoneda = esARS ? formatARS : formatUSD
  const valorInvertido = esARS ? position.total_invertido_ars : position.total_invertido_usd
  const valorActual = esARS ? position.valor_actual_ars : position.valor_actual_usd
  const rendimiento = esARS ? position.rendimiento_simple_ars : position.rendimiento_simple_usd
  const positivo = (rendimiento ?? 0) >= 0

  return (
    <div className="pb-4">
      <div className="mt-3">
        <div className="font-mono text-metric-lg font-bold text-app-text tabular-nums">{position.precio_actual != null ? formatPrecio(position.precio_actual) : '—'}</div>
        {rendimiento != null && (
          <span className={`inline-flex items-center gap-0.5 font-mono font-bold text-caption mt-1 tabular-nums ${positivo ? 'text-app-teal' : 'text-app-coral'}`}>
            <Icon name={positivo ? 'up' : 'down'} className="w-3 h-3" />
            {formatPctRatio(rendimiento)} desde promedio
          </span>
        )}
        {(position.objetivo_alcanzado || position.stop_loss_disparado) && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {position.objetivo_alcanzado && (
              <span className="text-label font-bold text-app-teal bg-app-teal/10 border border-app-teal/30 px-2 py-1 rounded-[7px]">
                🎯 Objetivo alcanzado
              </span>
            )}
            {position.stop_loss_disparado && (
              <span className="text-label font-bold text-app-coral bg-app-coral/10 border border-app-coral/30 px-2 py-1 rounded-[7px]">
                🛑 Stop loss disparado
              </span>
            )}
          </div>
        )}
        {precios.length > 0 && (
          <Sparkline
            data={precios.map(p => p.precio)}
            color={positivo ? '#4fd1ae' : '#e2665a'}
            className="w-full h-14 mt-2.5"
          />
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 mt-4">
        <MetricTile label="Cantidad" value={formatCantidad(position.cantidad_actual)} />
        <MetricTile label="Precio promedio" value={formatPrecio(position.precio_promedio)} />
        <MetricTile label="Invertido" infoTerm="invertido" value={formatMoneda(valorInvertido)} />
        <MetricTile label="Valor actual" value={formatMoneda(valorActual)} />
        <MetricTile label="Rend. simple" infoTerm="simple" value={formatPctRatio(rendimiento)} tone={rendimiento == null ? undefined : positivo ? 'pos' : 'neg'} />
        {esARS && position.rendimiento_simple_ars_real != null && (
          <MetricTile label="Rend. ARS real" infoTerm="cer" value={formatPctRatio(position.rendimiento_simple_ars_real)} tone={position.rendimiento_simple_ars_real >= 0 ? 'pos' : 'neg'} />
        )}
        {descomposicionFxPorTicker && descomposicionFxPorTicker.estado === 'ok' && (
          <>
            <MetricTile
              label="Efecto FX"
              infoTerm="efecto_fx"
              value={formatPctRatio(descomposicionFxPorTicker.efecto_fx_pct)}
              tone={descomposicionFxPorTicker.efecto_fx_pct == null ? undefined : descomposicionFxPorTicker.efecto_fx_pct >= 0 ? 'pos' : 'neg'}
            />
            <MetricTile
              label="Retorno activo"
              infoTerm="retorno_activo"
              value={formatPctRatio(descomposicionFxPorTicker.retorno_activo_pct)}
              tone={descomposicionFxPorTicker.retorno_activo_pct == null ? undefined : descomposicionFxPorTicker.retorno_activo_pct >= 0 ? 'pos' : 'neg'}
            />
          </>
        )}
        {position.precio_objetivo != null && (
          <MetricTile
            label="Precio Objetivo"
            infoTerm="objetivo"
            value={formatPrecio(position.precio_objetivo)}
            sub={position.pct_a_objetivo != null ? `${position.pct_a_objetivo >= 0 ? 'falta' : 'superado por'} ${(Math.abs(position.pct_a_objetivo) * 100).toFixed(2)}%` : undefined}
            tone={position.objetivo_alcanzado ? 'pos' : undefined}
          />
        )}
        {position.precio_stop_loss != null && (
          <MetricTile
            label="Stop Loss"
            infoTerm="stopLoss"
            value={formatPrecio(position.precio_stop_loss)}
            sub={position.pct_a_stop_loss != null ? `${position.pct_a_stop_loss <= 0 ? 'superado por' : 'falta'} ${(Math.abs(position.pct_a_stop_loss) * 100).toFixed(2)}%` : undefined}
            tone={position.stop_loss_disparado ? 'neg' : undefined}
          />
        )}
      </div>
    </div>
  )
}
