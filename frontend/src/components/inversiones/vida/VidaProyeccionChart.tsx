import { useMemo, useState } from 'react'
import {
  ComposedChart,
  Line,
  ReferenceLine,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import type { EscenarioVidaOut } from '../../../api'
import { formatUSD, formatARS } from '../../../utils'
import Segmented from '../../ui/Segmented'

interface Props {
  resultado: EscenarioVidaOut
}

const COLORES = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#14b8a6']
const MAX_PUNTOS = 200 // downsampling: horizontes largos no necesitan un punto por mes

function downsample<T>(puntos: T[], max: number): T[] {
  if (puntos.length <= max) return puntos
  const paso = Math.ceil(puntos.length / max)
  const out = puntos.filter((_, i) => i % paso === 0)
  const ultimo = puntos[puntos.length - 1]
  if (out[out.length - 1] !== ultimo) out.push(ultimo)
  return out
}

export default function VidaProyeccionChart({ resultado }: Props) {
  const formatMonto = resultado.moneda === 'ARS' ? formatARS : formatUSD
  const hayInflacion = resultado.resultados.some(r => r.metricas.patrimonio_final_real != null)
  const [vista, setVista] = useState<'nominal' | 'real'>('nominal')

  const base = resultado.resultados.find(r => r.es_base) ?? resultado.resultados[0]
  const otros = resultado.resultados.filter(r => !r.es_base)

  const mesesMuestreados = useMemo(
    () => downsample(base?.puntos ?? [], MAX_PUNTOS).map(p => p.mes),
    [base],
  )

  const usarReal = vista === 'real' && hayInflacion

  const data = useMemo(() => mesesMuestreados.map(mes => {
    const row: Record<string, number | string> = { mes, anio: Math.round(mes / 12) }
    for (const r of resultado.resultados) {
      const p = r.puntos.find(pt => pt.mes === mes)
      if (!p) continue
      const valor = usarReal ? (p.valor_real ?? p.valor) : p.valor
      row[r.nombre] = valor
    }
    return row
  }), [mesesMuestreados, resultado.resultados, usarReal])

  // Mes en el que se dispara algún flujo extraordinario o algún escenario se agota, para marcarlo.
  const referencias = resultado.resultados
    .filter(r => r.mes_flujo_extraordinario != null || r.se_agota_en_mes != null)
    .flatMap(r => [
      r.mes_flujo_extraordinario != null
        ? { mes: r.mes_flujo_extraordinario, label: r.nombre, color: '#94a3b8' }
        : null,
      r.se_agota_en_mes != null
        ? { mes: r.se_agota_en_mes, label: `${r.nombre}: se agota`, color: '#ef4444' }
        : null,
    ])
    .filter((x): x is { mes: number; label: string; color: string } => x !== null)

  return (
    <div className="space-y-2">
      {hayInflacion && (
        <Segmented<'nominal' | 'real'>
          options={[
            { value: 'nominal', label: 'Nominal' },
            { value: 'real', label: 'Poder de compra de hoy' },
          ]}
          value={vista}
          onChange={setVista}
        />
      )}

      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
          <CartesianGrid stroke="#1c1f2a" strokeDasharray="3 3" />
          <XAxis
            dataKey="anio"
            tick={{ fontSize: 10 }}
            stroke="#94a3b8"
            tickFormatter={(anio: number) => `Año ${anio}`}
          />
          <YAxis
            tick={{ fontSize: 10 }}
            stroke="#94a3b8"
            tickFormatter={(val: number) => `${resultado.moneda === 'ARS' ? '$' : 'U$S'}${(val / 1000).toFixed(0)}k`}
          />
          <Tooltip
            contentStyle={{ background: '#171b26', border: '1px solid #1c1f2a', borderRadius: 10, fontSize: 12 }}
            labelStyle={{ color: '#ccc' }}
            formatter={(val: any) => formatMonto(val as number)}
            labelFormatter={(anio) => `Año ${anio}`}
          />

          {referencias.map((ref, idx) => (
            <ReferenceLine
              key={idx}
              x={Math.round(ref.mes / 12)}
              stroke={ref.color}
              strokeDasharray="4 4"
              label={{ value: ref.label, position: 'insideTopLeft', offset: 10, fontSize: 9, fill: ref.color }}
            />
          ))}

          {base && (
            <Line
              type="monotone"
              dataKey={base.nombre}
              stroke="#94a3b8"
              strokeWidth={2}
              strokeDasharray="5 5"
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          )}
          {otros.map((r, idx) => (
            <Line
              key={r.tipo}
              type="monotone"
              dataKey={r.nombre}
              stroke={COLORES[idx % COLORES.length]}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          ))}

          <Legend wrapperStyle={{ fontSize: 11, paddingTop: 10 }} iconType="line" />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="text-label text-app-text-faint text-center">{resultado.disclaimer}</div>
    </div>
  )
}
