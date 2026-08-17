import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import type { PerformanceRelativaPunto } from '../../api'

interface PerformanceRelativaChartProps {
  serie: PerformanceRelativaPunto[]
}

function formatFechaLabel(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  const mes = (d.getMonth() + 1).toString().padStart(2, '0')
  const anio = d.getFullYear().toString().slice(2)
  return `${mes}/${anio}`
}

function formatFechaTooltip(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function PerformanceRelativaChart({ serie }: PerformanceRelativaChartProps) {
  if (serie.length === 0) {
    return <div className="h-[240px] flex items-center justify-center text-app-text-dim text-[12.5px]">Sin datos para esta vista</div>
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={serie} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#223028" />
        <XAxis
          dataKey="fecha"
          stroke="#8ca39b"
          tick={{ fontSize: 10, fill: '#8ca39b' }}
          tickFormatter={formatFechaLabel}
          interval="preserveStartEnd"
        />
        <YAxis
          stroke="#8ca39b"
          tick={{ fontSize: 10, fill: '#8ca39b' }}
          width={62}
          tickFormatter={v => v.toFixed(0)}
        />
        <Tooltip
          contentStyle={{ background: '#17221e', border: '1px solid #223028', borderRadius: 10, fontSize: 12 }}
          labelStyle={{ color: '#edf2ef' }}
          formatter={(v: number) => v.toFixed(1)}
          labelFormatter={formatFechaTooltip}
        />
        <Legend wrapperStyle={{ fontSize: 11, color: '#8ca39b' }} />
        <Line
          type="monotone"
          dataKey="indice_cartera"
          name="Cartera"
          stroke="#d8b14a"
          strokeWidth={2}
          dot={false}
          connectNulls
        />
        <Line
          type="monotone"
          dataKey="indice_benchmark"
          name="Benchmark"
          stroke="#4fd1ae"
          strokeWidth={2}
          dot={false}
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
