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
import { EscenarioSimulacionOut } from '../../api'

interface EscenarioProyeccionChartProps {
  resultado: EscenarioSimulacionOut
}

const COLORES = {
  actual: '#8ca39b',
  base: '#d8b14a',
  alcista: '#4fd1ae',
  bajista: '#e2665a',
  crisis: '#a94a4a',
  personalizado: '#5b8ba0',
}

export default function EscenarioProyeccionChart({ resultado }: EscenarioProyeccionChartProps) {
  // Construir datos para el gráfico
  // Todos los escenarios tienen la misma cantidad de puntos (mismo horizonte)
  const data = resultado.resultados[0]?.puntos.map((punto, idx) => {
    const row: any = {
      mes: punto.mes,
      fecha: punto.fecha,
    }

    // Agregar valor de cada escenario
    resultado.resultados.forEach(res => {
      const p = res.puntos[idx]
      row[res.nombre] = p?.valor_usd || 0
    })

    return row
  }) || []

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 40 }}>
        <CartesianGrid stroke="#223028" strokeDasharray="3 3" />
        <XAxis
          dataKey="fecha"
          tick={{ fontSize: 10 }}
          stroke="#8ca39b"
          tickFormatter={(date: string) => {
            const d = new Date(date)
            return `${d.getMonth() + 1}/${d.getFullYear().toString().slice(-2)}`
          }}
          interval={Math.floor(data.length / 6)}
        />
        <YAxis
          tick={{ fontSize: 10 }}
          stroke="#8ca39b"
          tickFormatter={(val) => `$${(val / 1000).toFixed(0)}k`}
        />
        <Tooltip
          contentStyle={{
            background: '#17221e',
            border: '1px solid #223028',
            borderRadius: 10,
            fontSize: 12,
          }}
          labelStyle={{ color: '#ccc' }}
          formatter={(val: any) => `$${(val as number).toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
          labelFormatter={(label) => {
            if (typeof label === 'string') {
              const d = new Date(label)
              return d.toLocaleDateString('es-ES')
            }
            return label
          }}
        />

        {/* Línea actual de referencia (punteada) */}
        <ReferenceLine
          y={resultado.actual_valor_usd}
          stroke="#8ca39b"
          strokeDasharray="5 5"
          label={{
            value: 'Actual',
            position: 'insideTopLeft',
            offset: 10,
            fontSize: 10,
            fill: '#8ca39b',
          }}
        />

        {/* Líneas por escenario */}
        {resultado.resultados.map((esc, idx) => (
          <Line
            key={idx}
            type="monotone"
            dataKey={esc.nombre}
            stroke={COLORES[esc.tipo_preset as keyof typeof COLORES] || '#ccc'}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        ))}

        <Legend
          wrapperStyle={{ fontSize: 11, paddingTop: 15 }}
          iconType="line"
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
