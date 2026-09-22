import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

interface Punto {
  fecha: string
  [key: string]: string | number | null
}

interface CostoOportunidadChartProps {
  serie: Punto[]
  dataKeyCartera: string
  dataKeyReferencia: string
  nombreReferencia: string
  formatValor: (v: number) => string
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

// Molde compartido por los dos gráficos de la pantalla (base 100 y en dinero): mismo grid,
// ejes y tooltip que `PerformanceRelativaChart`, parametrizado en las dos series a mostrar.
export default function CostoOportunidadChart({
  serie, dataKeyCartera, dataKeyReferencia, nombreReferencia, formatValor,
}: CostoOportunidadChartProps) {
  if (serie.length === 0) {
    return <div className="h-[240px] flex items-center justify-center text-app-text-dim text-caption">Sin datos para esta vista</div>
  }
  if (serie.length === 1) {
    return <div className="h-[240px] flex items-center justify-center text-app-text-dim text-caption">Un solo punto en el período: no hay evolución para graficar</div>
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={serie} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1c1f2a" />
        <XAxis
          dataKey="fecha"
          stroke="#94a3b8"
          tick={{ fontSize: 10, fill: '#94a3b8' }}
          tickFormatter={formatFechaLabel}
          interval="preserveStartEnd"
        />
        <YAxis
          stroke="#94a3b8"
          tick={{ fontSize: 10, fill: '#94a3b8' }}
          width={62}
          tickFormatter={v => formatValor(v)}
        />
        <Tooltip
          contentStyle={{ background: '#171b26', border: '1px solid #1c1f2a', borderRadius: 10, fontSize: 12 }}
          labelStyle={{ color: '#f8fafc' }}
          formatter={(v: number) => formatValor(v)}
          labelFormatter={formatFechaTooltip}
        />
        <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
        <Line
          type="monotone"
          dataKey={dataKeyCartera}
          name="Cartera"
          stroke="#3b82f6"
          strokeWidth={2}
          dot={false}
          connectNulls
        />
        <Line
          type="monotone"
          dataKey={dataKeyReferencia}
          name={nombreReferencia}
          stroke="#10b981"
          strokeWidth={2}
          dot={false}
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
