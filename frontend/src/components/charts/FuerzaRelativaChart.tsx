import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

interface Punto {
  fecha: string
  propio: number
  mediana_pares: number | null
}

const COLOR_PROPIO = '#3b82f6'   // app-accent
const COLOR_PARES = '#94a3b8'    // app-text-dim: la referencia, recesiva y punteada

const fechaCorta = (f: string) => {
  const [y, m] = f.split('-')
  return `${m}/${y.slice(2)}`
}

/**
 * Precio del ticker vs. la mediana de sus pares, ambos en USD y con base 100 en el primer
 * cierre semanal. Una sola escala (índice), así que no hay doble eje: lo que se lee es cuál de
 * las dos líneas terminó más arriba.
 */
export default function FuerzaRelativaChart({ puntos, ticker }: { puntos: Punto[]; ticker: string }) {
  if (puntos.length < 2) {
    return <div className="text-center py-8 text-app-text-dim text-caption">Todavía no hay serie semanal suficiente.</div>
  }
  const ultimo = puntos[puntos.length - 1]

  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mb-2 text-caption">
        <span className="inline-flex items-center gap-1.5 text-app-text">
          <span className="inline-block w-4 h-0.5 rounded" style={{ background: COLOR_PROPIO }} />
          {ticker} <span className="font-mono text-app-text-dim">{ultimo.propio.toFixed(0)}</span>
        </span>
        <span className="inline-flex items-center gap-1.5 text-app-text">
          <span className="inline-block w-4 border-t-2 border-dashed" style={{ borderColor: COLOR_PARES }} />
          Mediana de pares{' '}
          <span className="font-mono text-app-text-dim">
            {ultimo.mediana_pares != null ? ultimo.mediana_pares.toFixed(0) : '—'}
          </span>
        </span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={puntos} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
          <XAxis
            dataKey="fecha" tickFormatter={fechaCorta} minTickGap={28}
            tick={{ fontSize: 10, fill: '#7c8798' }} stroke="rgba(255,255,255,0.07)" tickLine={false}
          />
          <YAxis
            width={34} tick={{ fontSize: 10, fill: '#7c8798' }} stroke="rgba(255,255,255,0.07)"
            tickLine={false} axisLine={false} domain={['auto', 'auto']}
          />
          <ReferenceLine y={100} stroke="rgba(255,255,255,0.15)" />
          <Tooltip
            contentStyle={{ background: '#171b26', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 10, fontSize: 12 }}
            labelStyle={{ color: '#f8fafc' }}
            itemStyle={{ color: '#f8fafc' }}
            labelFormatter={(f: any) => `Semana del ${String(f).split('-').reverse().join('/')}`}
            formatter={(v: any, nombre: any) => [v != null ? Number(v).toFixed(1) : '—', nombre === 'propio' ? ticker : 'Mediana de pares']}
            cursor={{ stroke: 'rgba(255,255,255,0.2)' }}
          />
          <Line type="monotone" dataKey="propio" stroke={COLOR_PROPIO} strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
          <Line
            type="monotone" dataKey="mediana_pares" stroke={COLOR_PARES} strokeWidth={2} strokeDasharray="5 4"
            dot={false} activeDot={{ r: 4 }} connectNulls isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <div className="text-label text-app-text-faint mt-1">Base 100 = primer cierre semanal · en USD</div>
    </div>
  )
}
