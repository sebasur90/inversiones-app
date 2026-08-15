import type { EvolucionPunto, InversionesResumen } from '../../api'
import { formatARS, formatPctRatio, formatUSD } from '../../utils'
import { Icon } from '../icons/Icons'
import Sparkline from '../charts/Sparkline'
import InfoTerm from '../ui/InfoTerm'

export default function HeroValorCard({
  resumen,
  moneda,
  evolucion,
}: {
  resumen: InversionesResumen | null
  moneda: 'USD' | 'ARS'
  evolucion: EvolucionPunto[]
}) {
  const esARS = moneda === 'ARS'
  const valorActual = esARS ? resumen?.valor_actual_ars : resumen?.valor_actual_usd
  const totalInvertido = esARS ? resumen?.total_invertido_ars : resumen?.total_invertido_usd
  const rendimiento = esARS ? resumen?.rendimiento_simple_ars : resumen?.rendimiento_simple_usd
  const formatMoneda = esARS ? formatARS : formatUSD
  const deltaAbs = valorActual != null && totalInvertido != null ? valorActual - totalInvertido : null
  const positivo = (rendimiento ?? 0) >= 0

  const serie = evolucion.map(p => (esARS ? p.valor_ars : p.valor_usd))

  return (
    <div className="bg-gradient-to-br from-app-surface to-app-surface-2 border border-app-border rounded-[18px] p-[18px] mb-3.5">
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-app-text-dim mb-1.5">Valor actual</div>
      <div className="font-mono text-[32px] font-semibold tracking-tight tabular-nums text-app-text">
        {resumen ? formatMoneda(valorActual) : '—'}
      </div>
      {!esARS && resumen && <div className="font-mono text-[12px] text-app-text-dim mt-0.5 tabular-nums">≈ {formatARS(resumen.valor_actual_ars)}</div>}

      {resumen && rendimiento != null && (
        <div className="mt-2.5">
          <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">
            <InfoTerm term="simple" label="Rendimiento total" />
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-0.5 font-mono font-bold text-[12px] px-2 py-1 rounded-lg tabular-nums ${
                positivo ? 'text-app-teal bg-app-teal-soft' : 'text-app-coral bg-app-coral-soft'
              }`}
            >
              <Icon name={positivo ? 'up' : 'down'} className="w-3 h-3" />
              {formatPctRatio(rendimiento)}
            </span>
            {deltaAbs != null && (
              <span className="font-mono text-[11px] text-app-text-dim tabular-nums">
                {deltaAbs >= 0 ? '+' : ''}
                {formatMoneda(deltaAbs)} vs. invertido
              </span>
            )}
          </div>
        </div>
      )}

      <Sparkline data={serie} color={positivo ? '#4fd1ae' : '#e2665a'} className="w-full h-13 mt-2.5" />
    </div>
  )
}
