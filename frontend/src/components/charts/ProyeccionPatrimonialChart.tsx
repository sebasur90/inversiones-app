import {
  XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, ComposedChart, Line,
} from 'recharts'
import dayjs from 'dayjs'
import type { EvolucionOut } from '../../api'
import type { PuntoSimulado } from '../../utils/proyeccion'
import { formatUSD } from '../../utils'

interface ProyeccionPatrimonialChartProps {
  evolucionReal: EvolucionOut | null
  planPuntos: PuntoSimulado[]
  proyeccionPuntos: PuntoSimulado[]
  montoObjetivo: number
  fechaLimite: string
  esProyeccionAlcanzable: boolean
}

export default function ProyeccionPatrimonialChart({
  evolucionReal,
  planPuntos,
  proyeccionPuntos,
  montoObjetivo,
  fechaLimite,
  esProyeccionAlcanzable,
}: ProyeccionPatrimonialChartProps) {
  if (!evolucionReal || evolucionReal.puntos.length === 0) {
    return (
      <div className="text-center py-8 text-app-text-dim text-caption">
        Sin datos históricos para mostrar proyección
      </div>
    )
  }

  // Construir un array único ordenado por fecha, con null donde falte cada serie
  const todosPuntos = new Map<string, { fecha: string; valorReal?: number; valorPlan?: number; valorProyeccion?: number }>()

  // Agregar datos históricos reales
  for (const punto of evolucionReal.puntos) {
    todosPuntos.set(punto.fecha, {
      fecha: punto.fecha,
      valorReal: punto.valor_usd,
    })
  }

  // Agregar plan (datos esperados desde el inicio)
  for (const punto of planPuntos) {
    const existing = todosPuntos.get(punto.fecha) || { fecha: punto.fecha }
    todosPuntos.set(punto.fecha, {
      ...existing,
      valorPlan: punto.valorUsd,
    })
  }

  // Agregar proyección (del hoy hacia adelante)
  for (const punto of proyeccionPuntos) {
    const existing = todosPuntos.get(punto.fecha) || { fecha: punto.fecha }
    todosPuntos.set(punto.fecha, {
      ...existing,
      valorProyeccion: punto.valorUsd,
    })
  }

  // Ordenar por fecha y convertir a array
  const datosGrafico = Array.from(todosPuntos.values()).sort((a, b) =>
    dayjs(a.fecha).isBefore(dayjs(b.fecha)) ? -1 : 1
  )

  const ultimoPuntoReal = evolucionReal.puntos[evolucionReal.puntos.length - 1]
  const colorProyeccion = esProyeccionAlcanzable ? '#4fd1ae' : '#e2665a' // teal / coral

  return (
    <div>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={datosGrafico} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
          <defs>
            <linearGradient id="realFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#d8b14a" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#d8b14a" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#223028" />
          <XAxis
            dataKey="fecha"
            stroke="#8ca39b"
            tick={{ fontSize: 10, fill: '#8ca39b' }}
            tickFormatter={v => dayjs(v).format('MMM YY')}
            interval="preserveStartEnd"
          />
          <YAxis
            stroke="#8ca39b"
            tick={{ fontSize: 10, fill: '#8ca39b' }}
            width={62}
            tickFormatter={v => `$${((v as number) / 1000).toFixed(0)}k`}
          />
          <Tooltip
            contentStyle={{ background: '#17221e', border: '1px solid #223028', borderRadius: 10, fontSize: 12 }}
            labelStyle={{ color: '#edf2ef' }}
            labelFormatter={v => dayjs(v).format('MMM DD, YYYY')}
            formatter={(value: any, name: string) => {
              if (name === 'valorReal') return [formatUSD(value), 'Valor real']
              if (name === 'valorPlan') return [formatUSD(value), 'Plan']
              if (name === 'valorProyeccion') return [formatUSD(value), 'Proyección']
              return [value, name]
            }}
          />

          {/* Meta (línea horizontal) */}
          <ReferenceLine
            y={montoObjetivo}
            stroke="#4fd1ae"
            strokeDasharray="6 3"
            label={{
              value: 'Meta',
              fill: '#4fd1ae',
              fontSize: 11,
              position: 'right',
            }}
          />

          {/* Fecha límite (línea vertical) */}
          <ReferenceLine
            x={fechaLimite}
            stroke="#5b8ba0"
            strokeDasharray="6 3"
            label={{
              value: 'Límite',
              fill: '#5b8ba0',
              fontSize: 11,
              position: 'top',
            }}
          />

          {/* Valor real (sólido, gold) */}
          <Line
            type="monotone"
            dataKey="valorReal"
            stroke="#d8b14a"
            strokeWidth={2.5}
            dot={false}
            fill="url(#realFill)"
            isAnimationActive={false}
          />

          {/* Plan (punteado, steel) */}
          <Line
            type="monotone"
            dataKey="valorPlan"
            stroke="#5b8ba0"
            strokeWidth={1.5}
            strokeDasharray="4 3"
            dot={false}
            isAnimationActive={false}
          />

          {/* Proyección (punteado, teal/coral según alcanzable) */}
          <Line
            type="monotone"
            dataKey="valorProyeccion"
            stroke={colorProyeccion}
            strokeWidth={2}
            strokeDasharray="4 3"
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Leyenda */}
      <div className="mt-3 flex items-center gap-4 text-label text-app-text-dim">
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: '#d8b14a' }} />
          Valor real
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-0.5 rounded-full shrink-0" style={{ backgroundColor: '#5b8ba0' }} />
          Plan original
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-0.5 rounded-full shrink-0" style={{ backgroundColor: colorProyeccion }} />
          Proyección
        </div>
      </div>
    </div>
  )
}
