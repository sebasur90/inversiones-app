import type { ComparadorFilaOut } from '../../api'
import Card from '../ui/Card'
import MetricTile from '../ui/MetricTile'

function formatPctSigned(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

/** Grilla de riesgo por estrategia (drawdown y su duración, volatilidad, operaciones,
 * % ganadoras/perdedoras, mejor/peor operación, tiempo invertido y tiempo fuera del mercado). */
export default function RiesgoComparadorCards({ filas }: { filas: ComparadorFilaOut[] }) {
  return (
    <div className="flex flex-col gap-3">
      {filas.map(f => {
        const r = f.riesgo
        return (
          <Card key={String(f.estrategia_id ?? 'bh')}>
            <div className="font-semibold text-caption text-app-text mb-2">{f.nombre}</div>
            {!r ? (
              <div className="text-caption text-app-text-dim">
                Sin datos de riesgo: {f.estado === 'definicion_invalida' ? 'la definición no es válida.' : 'no corrió un backtest.'}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <MetricTile
                  label="Máximo drawdown"
                  value={r.max_drawdown_pct != null ? `${r.max_drawdown_pct.toFixed(2)}%` : '—'}
                  tone="neg" infoTerm="drawdown"
                  sub={
                    r.duracion_caida_dias != null
                      ? `${r.duracion_caida_dias} días de caída${
                          r.duracion_recuperacion_dias != null
                            ? ` · ${r.duracion_recuperacion_dias} de recuperación`
                            : r.recuperado === false ? ' · todavía sin recuperar' : ''
                        }`
                      : undefined
                  }
                />
                <MetricTile
                  label="Volatilidad anualizada"
                  value={r.volatilidad_anualizada_pct != null ? `${r.volatilidad_anualizada_pct.toFixed(2)}%` : '—'}
                  infoTerm="volatilidad" insuficiente={r.volatilidad_estado === 'datos_insuficientes'}
                />
                <MetricTile
                  label="Operaciones" value={String(r.operaciones)}
                  sub={`${r.ganadoras} ganadoras / ${r.perdedoras} perdedoras`}
                />
                <MetricTile
                  label="Win rate" value={r.win_rate_pct != null ? `${r.win_rate_pct.toFixed(1)}%` : '—'}
                  insuficiente={r.operaciones_cerradas === 0}
                />
                <MetricTile label="Mejor operación" value={formatPctSigned(r.mejor_operacion_pct)} tone="pos" insuficiente={r.operaciones_cerradas === 0} />
                <MetricTile label="Peor operación" value={formatPctSigned(r.peor_operacion_pct)} tone="neg" insuficiente={r.operaciones_cerradas === 0} />
                <MetricTile label="Tiempo invertido" value={`${r.exposicion_pct.toFixed(1)}%`} infoTerm="comparador_tiempo_invertido" />
                <MetricTile label="Tiempo fuera del mercado" value={`${r.tiempo_fuera_mercado_pct.toFixed(1)}%`} />
                <MetricTile label="Comisiones acumuladas" value={`${r.comisiones_pct_acum.toFixed(2)}%`} />
              </div>
            )}
            {f.advertencias.length > 0 && (
              <div className="mt-2 text-label text-app-text-faint">{f.advertencias.join(' · ')}</div>
            )}
          </Card>
        )
      })}
    </div>
  )
}
