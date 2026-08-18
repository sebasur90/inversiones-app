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
  '#4fd1ae', '#d8b14a', '#e2665a', '#5b8ba0', '#9c7aa0', '#7e9c90',
  '#3fb599', '#c9a53a', '#c9544a', '#4a7688',
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
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(139, 153, 166, 0.2)" />
        <XAxis
          dataKey="fecha"
          tick={{ fontSize: 11, fill: 'rgba(139, 153, 166, 0.6)' }}
        />
        <YAxis
          tick={{ fontSize: 11, fill: 'rgba(139, 153, 166, 0.6)' }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'rgba(28, 38, 51, 0.95)',
            border: '1px solid rgba(139, 153, 166, 0.3)',
            borderRadius: '8px',
          }}
          labelStyle={{ color: 'rgba(139, 153, 166, 0.8)' }}
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
