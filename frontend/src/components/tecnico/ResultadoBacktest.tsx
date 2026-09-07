import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import type { BacktestOut } from '../../api'
import MetricTile from '../ui/MetricTile'
import BotonExportarCsv from '../ui/BotonExportarCsv'

function formatPctSigned(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

export default function ResultadoBacktest({ resultado }: { resultado: BacktestOut }) {
  const m = resultado.metricas
  const insuficiente = m.estado === 'datos_insuficientes'
  const datosGrafico = resultado.curva_equity.map((p, i) => ({
    fecha: p.fecha, estrategia: p.valor, buyHold: resultado.curva_buy_hold[i]?.valor,
  }))

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
        <MetricTile label="Operaciones" value={String(m.operaciones)} sub={`${m.ganadoras} ganadoras / ${m.perdedoras} perdedoras`} />
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

      <div>
        <div className="font-semibold text-caption text-app-text mb-1.5">Estrategia vs. buy &amp; hold (base 100)</div>
        {datosGrafico.length === 0 ? (
          <div className="h-[200px] flex items-center justify-center text-app-text-dim text-caption">Sin datos para graficar</div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={datosGrafico} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#223028" />
              <XAxis dataKey="fecha" stroke="#8ca39b" tick={{ fontSize: 10, fill: '#8ca39b' }} interval="preserveStartEnd" />
              <YAxis stroke="#8ca39b" tick={{ fontSize: 10, fill: '#8ca39b' }} width={42} />
              <Tooltip contentStyle={{ background: '#17221e', border: '1px solid #223028', borderRadius: 10, fontSize: 12 }} labelStyle={{ color: '#edf2ef' }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="estrategia" name="Estrategia" stroke="#d8b14a" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="buyHold" name="Buy & hold" stroke="#8ca39b" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <div className="font-semibold text-caption text-app-text">Operaciones ({resultado.operaciones.length})</div>
          {resultado.operaciones.length > 0 && (
            <BotonExportarCsv
              nombre={`backtest-${resultado.ticker}`}
              encabezados={['Entrada', 'Salida', 'Precio entrada', 'Precio salida', 'Barras', 'Retorno neto %', 'Motivo salida', 'Abierta']}
              filas={() => resultado.operaciones.map(o => [
                o.fecha_entrada, o.fecha_salida ?? '', o.precio_entrada, o.precio_salida ?? '', o.barras,
                Number(o.retorno_neto_pct.toFixed(4)), o.motivo_salida ?? '', o.abierta ? 'sí' : 'no',
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
                  <td className="py-1.5 pr-2 text-app-text-dim">{o.motivo_salida ?? '—'}</td>
                </tr>
              ))}
              {resultado.operaciones.length === 0 && (
                <tr><td colSpan={4} className="py-3 text-app-text-dim text-center">Sin operaciones en el rango</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
