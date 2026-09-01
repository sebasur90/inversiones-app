import {
  XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, ComposedChart, Area, Scatter,
} from 'recharts'
import dayjs from 'dayjs'
import type { AportesHistoricosOut } from '../../api'
import { formatUSD } from '../../utils'

export default function AportesChart({
  aportesHistoricos,
  montoObjetivo,
}: {
  aportesHistoricos: AportesHistoricosOut | null
  montoObjetivo?: number | null
}) {
  if (!aportesHistoricos || aportesHistoricos.curva.length === 0) {
    return <div className="text-center py-8 text-app-text-dim text-caption">Sin movimientos en esta cartera</div>
  }

  const data = aportesHistoricos.curva.map(punto => ({ ...punto, mes_label: punto.mes }))
  const acumuladoFinal = data[data.length - 1]?.aportes_netos_acumulados ?? 0
  const rendimientoAcumulado = aportesHistoricos.valor_actual_usd - acumuladoFinal
  const rendimientoPct = acumuladoFinal > 0 ? (rendimientoAcumulado / acumuladoFinal) * 100 : 0

  return (
    <div>
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
          <defs>
            <linearGradient id="aportesFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#d8b14a" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#d8b14a" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#223028" />
          <XAxis
            dataKey="mes_label"
            tick={{ fill: '#8ca39b', fontSize: 10 }}
            tickFormatter={v => dayjs(`${v}-01`).format('MMM YY')}
            interval="preserveStartEnd"
          />
          <YAxis tick={{ fill: '#8ca39b', fontSize: 10 }} tickFormatter={v => `$${((v as number) / 1000).toFixed(0)}k`} width={42} />
          <Tooltip
            contentStyle={{ background: '#17221e', border: '1px solid #223028', borderRadius: 10, fontSize: 12 }}
            labelStyle={{ color: '#edf2ef' }}
            labelFormatter={v => dayjs(`${v}-01`).format('MMMM YYYY')}
            formatter={(v: number, name: string) => (name === 'aportes_netos_acumulados' ? [formatUSD(v), 'Aportes acumulados'] : [v, name])}
          />
          {montoObjetivo && (
            <ReferenceLine y={montoObjetivo} stroke="#4fd1ae" strokeDasharray="6 3" label={{ value: 'Meta', fill: '#4fd1ae', fontSize: 11 }} />
          )}
          <Area type="monotone" dataKey="aportes_netos_acumulados" stroke="#d8b14a" strokeWidth={2} fill="url(#aportesFill)" dot={false} />
          <Scatter
            name="Valor actual (hoy)"
            dataKey="__valor_actual"
            fill="#4fd1ae"
            shape="circle"
            data={[{ __valor_actual: aportesHistoricos.valor_actual_usd, mes_label: data[data.length - 1]?.mes_label || '' }]}
          />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="mt-3 text-label text-app-text-dim space-y-1">
        <div>Últimos aportes netos acumulados: <strong className="text-app-text">{formatUSD(acumuladoFinal)}</strong></div>
        <div>Valor actual (hoy): <strong className="text-app-text">{formatUSD(aportesHistoricos.valor_actual_usd)}</strong></div>
        <div>
          Rendimiento acumulado:{' '}
          <strong className={rendimientoAcumulado >= 0 ? 'text-app-teal' : 'text-app-coral'}>
            {rendimientoAcumulado >= 0 ? '+' : ''}{formatUSD(rendimientoAcumulado)} ({rendimientoPct >= 0 ? '+' : ''}{rendimientoPct.toFixed(1)}%)
          </strong>
        </div>
      </div>
    </div>
  )
}
