import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CicloFilaSerie } from '../../api'
import { fechaCorta } from '../../utils/fechas'
import { COLORES_GRUPOS, fmtNum } from './constantes'

export interface SerieGrafico {
  id: string
  nombre: string
  rol?: 'grupo' | 'benchmark' | 'adicional'
}

const ADICIONALES = COLORES_GRUPOS.slice(1)

export function colorSerie(s: SerieGrafico, indiceAdicional: number): string {
  if (s.rol === 'grupo') return '#3b82f6'
  if (s.rol === 'benchmark') return '#94a3b8'
  return ADICIONALES[indiceAdicional % ADICIONALES.length]
}

const etiquetaFecha = (f: string) => {
  const [y, m] = f.split('-')
  return `${m}/${y.slice(2)}`
}

/** Líneas rebasadas a 100 en la primera fecha en que todas las series tienen dato (nada se rellena). */
export default function GraficoBase100({
  filas,
  series,
  alto = 260,
  linea100 = true,
}: {
  filas: CicloFilaSerie[]
  series: SerieGrafico[]
  alto?: number
  linea100?: boolean
}) {
  let adicional = 0
  const conColor = series.map(s => ({ ...s, color: colorSerie(s, s.rol === 'adicional' ? adicional++ : 0) }))
  return (
    <div>
      <ResponsiveContainer width="100%" height={alto}>
        <LineChart data={filas} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid stroke="#1c1f2a" strokeDasharray="3 3" />
          <XAxis dataKey="fecha" tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={etiquetaFecha} minTickGap={32} />
          <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} width={40} domain={['auto', 'auto']} tickFormatter={(v: number) => v.toFixed(0)} />
          {linea100 && <ReferenceLine y={100} stroke="#475569" strokeDasharray="4 3" />}
          <Tooltip
            contentStyle={{ background: '#171b26', border: '1px solid #1c1f2a', borderRadius: 10, fontSize: 12 }}
            labelFormatter={(f: string) => fechaCorta(f)}
            formatter={(v: number, nombre: string) => [fmtNum(v, 1), nombre]}
          />
          {conColor.map(s => (
            <Line
              key={s.id}
              type="monotone"
              dataKey={s.id}
              name={s.nombre}
              stroke={s.color}
              strokeWidth={s.rol === 'grupo' ? 2.2 : 1.6}
              strokeDasharray={s.rol === 'benchmark' ? '5 3' : undefined}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
        {conColor.map(s => (
          <span key={s.id} className="inline-flex items-center gap-1 text-label text-app-text-dim">
            <span aria-hidden="true" className="w-3 h-0.5 rounded" style={{ backgroundColor: s.color }} />
            {s.nombre}
          </span>
        ))}
      </div>
    </div>
  )
}
