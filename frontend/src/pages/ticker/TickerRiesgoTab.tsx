import { formatPctRatio } from '../../utils'
import Card from '../../components/ui/Card'
import MetricTile from '../../components/ui/MetricTile'
import type { TickerRiesgoOut } from '../../api'

export default function TickerRiesgoTab({ riesgo }: { riesgo: TickerRiesgoOut }) {
  return (
    <div className="pb-4">
      <div className="grid grid-cols-2 gap-2 mb-4">
        <MetricTile
          label="Volatilidad"
          infoTerm="volatilidad"
          value={riesgo.volatilidad?.anualizada != null ? formatPctRatio(riesgo.volatilidad.anualizada) : 'N/A'}
        />
        <MetricTile
          label="Sharpe vs Benchmark"
          infoTerm="sharpe"
          value={riesgo.sharpe?.valor != null ? riesgo.sharpe.valor.toFixed(2) : 'N/A'}
          tone={riesgo.sharpe?.valor != null && riesgo.sharpe.valor >= 0 ? 'pos' : undefined}
        />
        <MetricTile
          label="Sortino"
          infoTerm="sortino"
          value={riesgo.sortino?.valor != null ? riesgo.sortino.valor.toFixed(2) : 'N/A'}
          tone={riesgo.sortino?.valor != null && riesgo.sortino.valor >= 0 ? 'pos' : undefined}
        />
        <MetricTile
          label="Calmar"
          infoTerm="calmar"
          value={riesgo.calmar?.valor != null ? riesgo.calmar.valor.toFixed(2) : 'N/A'}
          tone={riesgo.calmar?.valor != null && riesgo.calmar.valor >= 0 ? 'pos' : undefined}
        />
        <MetricTile
          label="Drawdown máximo"
          infoTerm="drawdown"
          value={riesgo.drawdown?.maximo != null ? formatPctRatio(riesgo.drawdown.maximo) : 'N/A'}
          tone="neg"
        />
        {riesgo.calmar?.retorno_anualizado != null && (
          <MetricTile
            label="Retorno anualizado"
            infoTerm="tickerdetalle_retorno_anualizado"
            value={formatPctRatio(riesgo.calmar.retorno_anualizado)}
            tone={riesgo.calmar.retorno_anualizado >= 0 ? 'pos' : 'neg'}
          />
        )}
      </div>

      {riesgo.mejores_periodos && riesgo.mejores_periodos.length > 0 && (
        <Card className="mb-4">
          <h3 className="text-[12px] font-bold text-app-text mb-3">Mejores períodos</h3>
          <div className="space-y-2">
            {riesgo.mejores_periodos.slice(0, 3).map((p, i) => (
              <div key={i} className="flex justify-between items-center py-2 px-2 bg-app-surface/50 rounded-[7px]">
                <span className="text-[11px] text-app-text-dim">{p.anio}-{String(p.mes).padStart(2, '0')}</span>
                <span className={`font-mono font-bold text-[11px] tabular-nums ${p.retorno >= 0 ? 'text-app-teal' : 'text-app-coral'}`}>
                  {formatPctRatio(p.retorno)}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {riesgo.peores_periodos && riesgo.peores_periodos.length > 0 && (
        <Card>
          <h3 className="text-[12px] font-bold text-app-text mb-3">Peores períodos</h3>
          <div className="space-y-2">
            {riesgo.peores_periodos.slice(0, 3).map((p, i) => (
              <div key={i} className="flex justify-between items-center py-2 px-2 bg-app-surface/50 rounded-[7px]">
                <span className="text-[11px] text-app-text-dim">{p.anio}-{String(p.mes).padStart(2, '0')}</span>
                <span className={`font-mono font-bold text-[11px] tabular-nums ${p.retorno >= 0 ? 'text-app-teal' : 'text-app-coral'}`}>
                  {formatPctRatio(p.retorno)}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
