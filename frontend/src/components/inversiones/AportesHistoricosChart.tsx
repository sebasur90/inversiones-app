import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  ComposedChart,
  Scatter,
} from 'recharts'
import dayjs from 'dayjs'
import type { AportesHistoricosOut } from '../../api'
import { formatUSD } from '../../utils'

interface Props {
  aportesHistoricos: AportesHistoricosOut | null
  montoObjetivo?: number | null
}

export default function AportesHistoricosChart({ aportesHistoricos, montoObjetivo }: Props) {
  if (!aportesHistoricos || aportesHistoricos.curva.length === 0) {
    return (
      <div style={{
        background: '#161b22',
        border: '1px solid #30363d',
        borderRadius: 8,
        padding: 16,
      }}>
        <div style={{ color: '#8b949e', fontSize: 12, marginBottom: 8 }}>Histórico de aportes netos acumulados (USD)</div>
        <div style={{ color: '#8b949e', textAlign: 'center', padding: 24 }}>Sin movimientos en esta cartera</div>
      </div>
    )
  }

  const data = aportesHistoricos.curva.map(punto => ({
    ...punto,
    mes_label: punto.mes,
  }))

  const rendimiento_acumulado = aportesHistoricos.valor_actual_usd - (data[data.length - 1]?.aportes_netos_acumulados ?? 0)
  const rendimiento_pct = data.length > 0 && data[data.length - 1].aportes_netos_acumulados > 0
    ? (rendimiento_acumulado / data[data.length - 1].aportes_netos_acumulados) * 100
    : 0

  return (
    <div style={{
      background: '#161b22',
      border: '1px solid #30363d',
      borderRadius: 8,
      padding: 16,
    }}>
      <div style={{ color: '#8b949e', fontSize: 12, marginBottom: 8 }}>Histórico de aportes netos acumulados (USD)</div>
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
          <defs>
            <linearGradient id="colorAportes" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#58a6ff" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#58a6ff" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
          <XAxis
            dataKey="mes_label"
            tick={{ fill: '#8b949e', fontSize: 10 }}
            tickFormatter={v => dayjs(`${v}-01`).format('MMM YY')}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: '#8b949e', fontSize: 10 }}
            tickFormatter={v => `$${(v as number / 1000).toFixed(0)}k`}
            width={45}
          />
          <Tooltip
            contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 6 }}
            labelFormatter={v => dayjs(`${v}-01`).format('MMMM YYYY')}
            formatter={(v: number, name: string) => {
              if (name === 'aportes_netos_acumulados') {
                return [formatUSD(v), 'Aportes acumulados']
              }
              return [v, name]
            }}
          />
          {montoObjetivo && (
            <ReferenceLine
              y={montoObjetivo}
              stroke="#3fb950"
              strokeDasharray="6 3"
              label={{ value: 'Meta', fill: '#3fb950', fontSize: 11 }}
            />
          )}
          <Area
            type="monotone"
            dataKey="aportes_netos_acumulados"
            stroke="#58a6ff"
            strokeWidth={2}
            fill="url(#colorAportes)"
            dot={false}
          />
          {/* Marcador del valor actual (hoy) */}
          <Scatter
            name="Valor actual (hoy)"
            dataKey="__valor_actual"
            fill="#3fb950"
            shape="circle"
            data={[{
              __valor_actual: aportesHistoricos.valor_actual_usd,
              mes_label: data[data.length - 1]?.mes_label || '',
            }]}
          />
        </ComposedChart>
      </ResponsiveContainer>
      <div style={{ marginTop: 12, fontSize: 11, color: '#8b949e' }}>
        <div>
          Últimos aportes netos acumulados: <strong>{formatUSD(data[data.length - 1]?.aportes_netos_acumulados ?? 0)}</strong>
        </div>
        <div>
          Valor actual (hoy): <strong>{formatUSD(aportesHistoricos.valor_actual_usd)}</strong>
        </div>
        <div>
          Rendimiento acumulado: <strong style={{ color: rendimiento_acumulado >= 0 ? '#3fb950' : '#f85149' }}>
            {rendimiento_acumulado >= 0 ? '+' : ''}{formatUSD(rendimiento_acumulado)} ({rendimiento_pct >= 0 ? '+' : ''}{rendimiento_pct.toFixed(1)}%)
          </strong>
        </div>
      </div>
    </div>
  )
}
