import { Card } from 'antd'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell,
} from 'recharts'
import type { InversionesResumen } from '../../api'
import { formatARS } from '../../utils'

interface BarData {
  name: string
  Invertido: number
  'Valor actual': number
  'Si comprabas USD': number | null
  'Si ajustabas por CER': number | null
}

const COLORS = {
  Invertido: '#8b949e',
  'Valor actual': '#58a6ff',
  'Si comprabas USD': '#3fb950',
  'Si ajustabas por CER': '#f0883e',
}

const renderCustomLabel = (props: any): React.ReactElement | null => {
  const { payload, x, y, width, dataKey } = props
  const isInvertido = dataKey === 'Invertido'
  const value = payload?.[dataKey]
  const invertido = payload?.Invertido ?? 0

  if (isInvertido || value === null || invertido === 0 || value === 0) {
    return null
  }

  const delta = ((value - invertido) / invertido) * 100
  const isPositive = delta > 0
  const color = isPositive ? '#3fb950' : '#f85149'

  return (
    <text
      x={x + width / 2}
      y={y - 8}
      fill={color}
      textAnchor="middle"
      fontSize={12}
      fontWeight="bold"
    >
      {isPositive ? '+' : ''}{delta.toFixed(1)}%
    </text>
  )
}

export default function ComparacionInversionChart({ resumen }: { resumen: InversionesResumen | null }) {
  if (!resumen) {
    return (
      <Card
        title="Comparación: cartera vs. benchmarks (en pesos)"
        size="small"
        style={{ background: '#161b22', border: '1px solid #30363d' }}
        styles={{ header: { color: '#c9d1d9', borderBottom: '1px solid #30363d' } }}
      >
        <div style={{ textAlign: 'center', padding: 40, color: '#8b949e' }}>Sin datos de comparación</div>
      </Card>
    )
  }

  const invertido = resumen.total_invertido_ars
  const data: BarData[] = [
    {
      name: 'Comparación',
      Invertido: invertido,
      'Valor actual': resumen.valor_actual_ars,
      'Si comprabas USD': resumen.valor_benchmark_usd_ars ?? null,
      'Si ajustabas por CER': resumen.total_invertido_ars_real ?? null,
    },
  ]

  return (
    <Card
      title="Comparación: cartera vs. benchmarks (en pesos)"
      size="small"
      style={{ background: '#161b22', border: '1px solid #30363d' }}
      styles={{ header: { color: '#c9d1d9', borderBottom: '1px solid #30363d' } }}
    >
      <ResponsiveContainer width="100%" height={380}>
        <BarChart data={data} margin={{ top: 50, right: 8, left: 8, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
          <XAxis dataKey="name" stroke="#8b949e" tick={{ fontSize: 11 }} />
          <YAxis stroke="#8b949e" tick={{ fontSize: 11 }} tickFormatter={v => `$${v.toLocaleString('es-AR')}`} />
          <Tooltip
            contentStyle={{ background: '#21262d', border: '1px solid #30363d', borderRadius: 8 }}
            formatter={(v: any) => (v !== null ? formatARS(v) : 'N/A')}
            labelFormatter={() => 'Comparación'}
            cursor={{ fill: 'rgba(255,255,255,0.05)' }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="Invertido" fill={COLORS.Invertido} />
          <Bar dataKey="Valor actual" fill={COLORS['Valor actual']} label={renderCustomLabel as any} />
          <Bar dataKey="Si comprabas USD" fill={COLORS['Si comprabas USD']} label={renderCustomLabel as any}>
            {data.map((entry, index) => {
              const isNA = entry['Si comprabas USD'] === null
              return (
                <Cell key={`cell-${index}-2`} fill={isNA ? '#4d5563' : COLORS['Si comprabas USD']} />
              )
            })}
          </Bar>
          <Bar dataKey="Si ajustabas por CER" fill={COLORS['Si ajustabas por CER']} label={renderCustomLabel as any}>
            {data.map((entry, index) => {
              const isNA = entry['Si ajustabas por CER'] === null
              return (
                <Cell key={`cell-${index}-3`} fill={isNA ? '#4d5563' : COLORS['Si ajustabas por CER']} />
              )
            })}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div style={{ marginTop: 16, fontSize: 11, color: '#8b949e' }}>
        {resumen.valor_benchmark_usd_ars === null && (
          <div>⚠ Sin MEP disponible para hoy</div>
        )}
        {resumen.total_invertido_ars_real === null && (
          <div>⚠ Sin CER disponible para algunos períodos</div>
        )}
      </div>
    </Card>
  )
}
