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
import { Paper, useMantineTheme } from '@mantine/core'

interface PerformanceCompareChartProps {
  serie: Record<string, any>[]
}

const COLORS = [
  '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
  '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
]

export default function PerformanceCompareChart({ serie }: PerformanceCompareChartProps) {
  const theme = useMantineTheme()

  if (!serie || serie.length === 0) {
    return (
      <Paper p="xl" style={{ textAlign: 'center', color: theme.colors.gray[6] }}>
        No hay datos para mostrar
      </Paper>
    )
  }

  // Extraer keys de todas las fuentes (excluyendo 'fecha')
  const fuentes = serie.length > 0
    ? Object.keys(serie[0]).filter(k => k !== 'fecha')
    : []

  return (
    <ResponsiveContainer width="100%" height={400}>
      <LineChart
        data={serie}
        margin={{ top: 5, right: 30, left: 0, bottom: 5 }}
      >
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          dataKey="fecha"
          tick={{ fontSize: 12 }}
          style={{ color: theme.colors.gray[6] }}
        />
        <YAxis
          tick={{ fontSize: 12 }}
          style={{ color: theme.colors.gray[6] }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: theme.colors.dark[7],
            border: `1px solid ${theme.colors.gray[7]}`,
            borderRadius: theme.radius.sm,
          }}
          labelStyle={{ color: theme.colors.gray[3] }}
          formatter={(value) => value ? value.toFixed(2) : '—'}
        />
        <Legend />
        {fuentes.map((fuente, idx) => (
          <Line
            key={fuente}
            type="monotone"
            dataKey={fuente}
            stroke={COLORS[idx % COLORS.length]}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
