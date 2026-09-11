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
  Invertido: '#6b7280',
  'Valor actual': '#3b82f6',
  'Si comprabas USD': '#10b981',
  'Si ajustabas por CER': '#8b5cf6',
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
  const color = isPositive ? '#10b981' : '#ef4444'

  return (
    <text x={x + width / 2} y={y - 8} fill={color} textAnchor="middle" fontSize={12} fontWeight="bold">
      {isPositive ? '+' : ''}{delta.toFixed(1)}%
    </text>
  )
}

export default function ComparacionChart({ resumen }: { resumen: InversionesResumen | null }) {
  if (!resumen) {
    return <div className="text-center py-10 text-app-text-dim text-caption">Sin datos de comparación</div>
  }

  const data: BarData[] = [
    {
      name: 'Comparación',
      Invertido: resumen.total_invertido_ars,
      'Valor actual': resumen.valor_actual_ars,
      'Si comprabas USD': resumen.valor_benchmark_usd_ars ?? null,
      'Si ajustabas por CER': resumen.total_invertido_ars_real ?? null,
    },
  ]

  return (
    <div>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} margin={{ top: 44, right: 4, left: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1c1f2a" />
          <XAxis dataKey="name" stroke="#94a3b8" tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <YAxis stroke="#94a3b8" tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={v => `$${v.toLocaleString('es-AR')}`} width={64} />
          <Tooltip
            contentStyle={{ background: '#171b26', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 10, fontSize: 12 }}
            labelStyle={{ color: '#f8fafc' }}
            formatter={(v: any) => (v !== null ? formatARS(v) : 'N/A')}
            labelFormatter={() => 'Comparación'}
            cursor={{ fill: 'rgba(255,255,255,0.04)' }}
          />
          <Legend
            wrapperStyle={{ fontSize: 11, color: '#94a3b8' }}
            formatter={(value: string) =>
              value === 'Si comprabas USD' ? 'USD (MEP)' : value === 'Si ajustabas por CER' ? 'CER' : value
            }
          />
          <Bar dataKey="Invertido" fill={COLORS.Invertido} radius={[4, 4, 0, 0]} />
          <Bar dataKey="Valor actual" fill={COLORS['Valor actual']} label={renderCustomLabel as any} radius={[4, 4, 0, 0]} />
          <Bar dataKey="Si comprabas USD" fill={COLORS['Si comprabas USD']} label={renderCustomLabel as any} radius={[4, 4, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}-2`} fill={entry['Si comprabas USD'] === null ? '#262a35' : COLORS['Si comprabas USD']} />
            ))}
          </Bar>
          <Bar dataKey="Si ajustabas por CER" fill={COLORS['Si ajustabas por CER']} label={renderCustomLabel as any} radius={[4, 4, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}-3`} fill={entry['Si ajustabas por CER'] === null ? '#262a35' : COLORS['Si ajustabas por CER']} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-3 text-label text-app-text-dim space-y-0.5">
        {resumen.valor_benchmark_usd_ars === null && <div>⚠ Sin MEP disponible para hoy</div>}
        {resumen.total_invertido_ars_real === null && <div>⚠ Sin CER disponible para algunos períodos</div>}
      </div>
    </div>
  )
}
