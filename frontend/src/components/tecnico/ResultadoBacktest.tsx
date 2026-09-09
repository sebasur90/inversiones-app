import { useState } from 'react'
import type { BacktestOut, EstrategiaDsl } from '../../api'
import MetricTile from '../ui/MetricTile'
import BotonExportarCsv from '../ui/BotonExportarCsv'
import GraficoBacktest from './GraficoBacktest'
import GraficoFullscreen from './GraficoFullscreen'
import { DESCRIPCION_MOTIVO, etiquetaMotivo } from './motivosSalida'

function formatPctSigned(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

export default function ResultadoBacktest({ resultado, dsl }: { resultado: BacktestOut; dsl: EstrategiaDsl }) {
  const m = resultado.metricas
  const insuficiente = m.estado === 'datos_insuficientes'
  const unaSolaCerrada = m.operaciones_cerradas === 1
  const tieneGrafico = resultado.barras.length > 0
  const [fullscreen, setFullscreen] = useState(false)

  const propsGrafico = {
    barras: resultado.barras,
    indicadoresSeries: resultado.indicadores,
    dslIndicadores: dsl.indicadores,
    senales: resultado.senales,
    operaciones: resultado.operaciones,
    primeraBarraEvaluable: resultado.primera_barra_evaluable,
    curvaEquity: resultado.curva_equity,
    curvaBuyHold: resultado.curva_buy_hold,
    indiceDesde: resultado.indice_desde,
    moneda: resultado.moneda,
    tieneVelas: resultado.barras.some(b => b.apertura != null),
    tieneVolumen: resultado.barras.some(b => b.volumen != null),
  }

  // Sólo los motivos que efectivamente aparecieron: explicar los cinco siempre sería ruido.
  const motivosUsados = Array.from(
    new Set(resultado.operaciones.map(o => o.motivo_salida).filter((x): x is string => !!x)),
  )

  return (
    <div className="flex flex-col gap-3">
      {resultado.variante === 'subyacente' && (
        <div className="text-label text-app-text-dim">
          Backtest sobre el subyacente en {resultado.moneda || 'USD'} (precios de entrada/salida en esa moneda).
        </div>
      )}

      {resultado.advertencias.length > 0 && (
        <div className="bg-app-surface-2 rounded-lg px-3 py-2 text-label text-app-text-dim">
          {resultado.advertencias.join(' · ')}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <MetricTile label="Retorno total" value={formatPctSigned(m.retorno_total_pct)} tone={m.retorno_total_pct >= 0 ? 'pos' : 'neg'} />
        <MetricTile label="Buy & hold" value={formatPctSigned(m.retorno_buy_hold_pct)} />
        <MetricTile
          label="Exceso vs. buy & hold" tone={m.exceso_vs_buy_hold_pp >= 0 ? 'pos' : 'neg'}
          value={`${m.exceso_vs_buy_hold_pp >= 0 ? '+' : ''}${m.exceso_vs_buy_hold_pp.toFixed(2)} pp`}
        />
        <MetricTile label="Retorno anualizado" value={formatPctSigned(m.retorno_anualizado_pct)} />
        <MetricTile
          label="Operaciones" value={String(m.operaciones)}
          sub={`${m.ganadoras} ganadoras / ${m.perdedoras} perdedoras${m.operaciones_cerradas < m.operaciones ? ' · 1 abierta' : ''}`}
        />
        {m.retorno_abierta_pct != null && (
          <MetricTile
            label="Operación abierta (no realizado)" value={formatPctSigned(m.retorno_abierta_pct)}
            tone={m.retorno_abierta_pct >= 0 ? 'pos' : 'neg'}
          />
        )}
        <MetricTile label="Win rate" value={m.win_rate_pct != null ? `${m.win_rate_pct.toFixed(1)}%` : '—'} insuficiente={insuficiente} />
        <MetricTile label="Profit factor" value={m.profit_factor != null ? m.profit_factor.toFixed(2) : '—'} insuficiente={insuficiente} />
        <MetricTile label="Máximo drawdown" value={m.max_drawdown_pct != null ? `${m.max_drawdown_pct.toFixed(2)}%` : '—'} tone="neg" />
        <MetricTile label="Retorno medio / operación" value={formatPctSigned(m.retorno_medio_operacion_pct)} insuficiente={insuficiente} />
        <MetricTile label="Mejor operación" value={formatPctSigned(m.mejor_operacion_pct)} tone="pos" insuficiente={insuficiente} />
        <MetricTile label="Peor operación" value={formatPctSigned(m.peor_operacion_pct)} tone="neg" insuficiente={insuficiente} />
        <MetricTile label="Exposición" value={`${m.exposicion_pct.toFixed(1)}%`} />
        <MetricTile label="Duración media" value={m.duracion_media_barras != null ? `${m.duracion_media_barras.toFixed(1)} barras` : '—'} insuficiente={insuficiente} />
        <MetricTile label="Comisiones acumuladas" value={`${m.comisiones_pct_acum.toFixed(2)}%`} />
      </div>

      {insuficiente && (
        <div className="text-label text-app-text-dim">
          La estrategia no cerró ninguna operación en el rango{resultado.operaciones.some(o => o.abierta) ? ' (quedó una posición abierta al final)' : ''}:
          las métricas por operación (win rate, profit factor, duración…) necesitan al menos una operación cerrada. Probá ampliar el período o ajustar las reglas de salida.
        </div>
      )}
      {!insuficiente && unaSolaCerrada && (
        <div className="text-label text-app-text-dim">
          Las métricas por operación están basadas en una sola operación cerrada: tomalas como referencia, no como estadística.
        </div>
      )}

      <div>
        <div className="font-semibold text-caption text-app-text mb-1.5">Precio, estrategia y señales</div>
        {tieneGrafico ? (
          <GraficoBacktest {...propsGrafico} onToggleFullscreen={() => setFullscreen(true)} />
        ) : (
          <div className="h-[200px] flex items-center justify-center text-app-text-dim text-caption">Sin datos para graficar</div>
        )}
      </div>

      {tieneGrafico && (
        <GraficoFullscreen
          open={fullscreen} onClose={() => setFullscreen(false)}
          title={`${resultado.ticker} · Backtest${resultado.moneda ? ` (${resultado.moneda})` : ''}`}
        >
          <GraficoBacktest {...propsGrafico} fullscreen onToggleFullscreen={() => setFullscreen(false)} />
        </GraficoFullscreen>
      )}

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <div className="font-semibold text-caption text-app-text">Operaciones ({resultado.operaciones.length})</div>
          {resultado.operaciones.length > 0 && (
            <BotonExportarCsv
              nombre={`backtest-${resultado.ticker}`}
              encabezados={['Entrada', 'Salida', 'Precio entrada', 'Precio salida', 'Barras', 'Retorno neto %', 'Motivo salida', 'Abierta']}
              filas={() => resultado.operaciones.map(o => [
                o.fecha_entrada, o.fecha_salida ?? '', o.precio_entrada, o.precio_salida ?? '', o.barras,
                Number(o.retorno_neto_pct.toFixed(4)), o.motivo_salida ? etiquetaMotivo(o.motivo_salida) : '', o.abierta ? 'sí' : 'no',
              ])}
            />
          )}
        </div>
        <div className="overflow-x-auto -mx-4 px-4">
          <table className="w-full text-caption">
            <thead>
              <tr className="text-label text-app-text-faint uppercase text-left">
                <th className="py-1 pr-2 font-semibold">Entrada</th>
                <th className="py-1 pr-2 font-semibold">Salida</th>
                <th className="py-1 pr-2 font-semibold text-right">Retorno neto</th>
                <th className="py-1 pr-2 font-semibold">Motivo</th>
              </tr>
            </thead>
            <tbody>
              {resultado.operaciones.map((o, i) => (
                <tr key={i} className="border-t border-app-border-soft">
                  <td className="py-1.5 pr-2 font-mono whitespace-nowrap">{o.fecha_entrada}</td>
                  <td className="py-1.5 pr-2 font-mono whitespace-nowrap">{o.fecha_salida ?? (o.abierta ? 'Abierta' : '—')}</td>
                  <td className={`py-1.5 pr-2 text-right font-mono tabular-nums ${o.retorno_neto_pct >= 0 ? 'text-app-teal' : 'text-app-coral'}`}>
                    {formatPctSigned(o.retorno_neto_pct)}
                  </td>
                  <td className="py-1.5 pr-2 text-app-text-dim">{etiquetaMotivo(o.motivo_salida)}</td>
                </tr>
              ))}
              {resultado.operaciones.length === 0 && (
                <tr><td colSpan={4} className="py-3 text-app-text-dim text-center">Sin operaciones en el rango</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {motivosUsados.length > 0 && (
          <div className="mt-2 text-label text-app-text-dim space-y-0.5">
            {motivosUsados.map(m2 => (
              <div key={m2}>
                <span className="text-app-text font-semibold">{etiquetaMotivo(m2)}</span>: {DESCRIPCION_MOTIVO[m2] ?? '—'}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
