import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

interface PerformanceCompareChartProps {
  serie: Record<string, any>[]
}

const COLORS = [
  '#10b981', '#3b82f6', '#ef4444', '#f59e0b', '#8b5cf6', '#6b7280',
  '#34d399', '#60a5fa', '#f87171', '#fbbf24',
]

export default function PerformanceCompareChart({ serie }: PerformanceCompareChartProps) {
  if (!serie || serie.length === 0) {
    return (
      <div className="bg-app-surface border border-app-border rounded-lg p-4 text-center text-app-text-dim">
        No hay datos para mostrar
      </div>
    )
  }

  const fuentes = serie.length > 0
    ? Object.keys(serie[0]).filter(k => k !== 'fecha')
    : []

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart
        data={serie}
        margin={{ top: 5, right: 30, left: 0, bottom: 5 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.2)" />
        <XAxis
          dataKey="fecha"
          tick={{ fontSize: 11, fill: 'rgba(148, 163, 184, 0.6)' }}
        />
        <YAxis
          tick={{ fontSize: 11, fill: 'rgba(148, 163, 184, 0.6)' }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'rgba(23, 27, 38, 0.95)',
            border: '1px solid rgba(148, 163, 184, 0.3)',
            borderRadius: '8px',
          }}
          labelStyle={{ color: 'rgba(148, 163, 184, 0.8)' }}
          formatter={(value: any) => typeof value === 'number' ? value.toFixed(2) : String(value ?? '—')}
        />
        <Legend wrapperStyle={{ paddingTop: '16px' }} />
        {fuentes.map((fuente, idx) => (
          <Line
            key={fuente}
            type="monotone"
            dataKey={fuente}
            stroke={COLORS[idx % COLORS.length]}
            dot={false}
            isAnimationActive={false}
            connectNulls
            strokeWidth={2}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
