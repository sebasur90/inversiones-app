import { useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import type { ComparadorFilaOut } from '../../api'
import { CHART_COLORS, formatARS, formatUSD, formatPrecio } from '../../utils'

type Fila = { fecha: string } & Record<string, string | number | null>

function claveFila(f: ComparadorFilaOut): string {
  return String(f.estrategia_id ?? 'bh')
}

function formatMoneda(v: number, moneda: string): string {
  if (moneda === 'ARS') return formatARS(v)
  if (moneda === 'USD') return formatUSD(v)
  return formatPrecio(v)
}

/**
 * Evolución del capital inicial por estrategia (Recharts multi-serie), con leyenda interactiva:
 * no hay un patrón de `<Legend>` con `onClick` en el repo (los 9 `<Legend>` existentes son sólo
 * informativos) — el patrón vivo son chips externos que togglean qué `<Line>` se renderiza
 * (`pages/Comparador.tsx`), que es el que se sigue acá.
 */
export default function GraficoComparadorCapital({
  fechas, filas, moneda, capitalInicial,
}: {
  fechas: string[]
  filas: ComparadorFilaOut[]
  moneda: string
  capitalInicial: number
}) {
  const [activas, setActivas] = useState<Set<string>>(() => new Set(filas.map(claveFila)))

  const datos: Fila[] = fechas.map((fecha, i) => {
    const fila: Fila = { fecha }
    for (const f of filas) {
      const valorBase100 = f.curva[i]
      fila[claveFila(f)] = valorBase100 != null ? (valorBase100 / 100) * capitalInicial : null
    }
    return fila
  })

  function toggle(clave: string) {
    setActivas(prev => {
      const next = new Set(prev)
      if (next.has(clave)) next.delete(clave)
      else next.add(clave)
      return next
    })
  }

  function formatFechaLabel(iso: string): string {
    const d = new Date(iso + 'T00:00:00')
    return `${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getFullYear().toString().slice(2)}`
  }

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {filas.map((f, i) => {
          const clave = claveFila(f)
          const activa = activas.has(clave)
          return (
            <button
              key={clave}
              onClick={() => toggle(clave)}
              aria-pressed={activa}
              className={`inline-flex items-center gap-1.5 text-label font-semibold px-2.5 py-1.5 rounded-lg border transition-opacity ${
                activa ? 'border-app-border bg-app-surface text-app-text' : 'border-app-border-soft bg-transparent text-app-text-faint opacity-50'
              }`}
            >
              <span className="inline-block w-2.5 h-2.5 rounded-full shrink-0" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
              <span className="truncate max-w-[140px]">{f.nombre}</span>
            </button>
          )
        })}
      </div>

      {datos.length === 0 ? (
        <div className="h-[260px] flex items-center justify-center text-app-text-dim text-caption">Sin datos para graficar</div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={datos} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1c1f2a" />
            <XAxis
              dataKey="fecha" stroke="#94a3b8" tick={{ fontSize: 10, fill: '#94a3b8' }}
              tickFormatter={formatFechaLabel} interval="preserveStartEnd"
            />
            <YAxis
              stroke="#94a3b8" tick={{ fontSize: 10, fill: '#94a3b8' }} width={72}
              tickFormatter={v => formatMoneda(v as number, moneda)}
            />
            <Tooltip
              contentStyle={{ background: '#171b26', border: '1px solid #1c1f2a', borderRadius: 10, fontSize: 12 }}
              labelStyle={{ color: '#f8fafc' }}
              formatter={(v: number, name: string) => [
                formatMoneda(v, moneda), filas.find(f => claveFila(f) === name)?.nombre ?? name,
              ]}
            />
            {filas.map((f, i) => {
              const clave = claveFila(f)
              if (!activas.has(clave)) return null
              return (
                <Line
                  key={clave} type="monotone" dataKey={clave}
                  stroke={CHART_COLORS[i % CHART_COLORS.length]} strokeWidth={2}
                  // dot={{ r: 0 }} en vez de `false`: con pocos puntos Recharts fuerza igual un
                  // punto visible (gotcha documentado en `components/charts/AportesChart.tsx`).
                  dot={{ r: 0, fillOpacity: 0, strokeOpacity: 0 }}
                  connectNulls
                />
              )
            })}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
