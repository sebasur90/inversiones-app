import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

interface Punto {
  fecha: string
  propio: number
  mediana_pares: number | null
  pares: Record<string, number>
}

const COLOR_PROPIO = '#3b82f6'   // app-accent: el ticker siempre en azul
const COLOR_MEDIANA = '#94a3b8'  // app-text-dim, punteada: la referencia resumida
// Un color por par mostrado (como mucho 3 a la vez). Se asigna al prenderlo y lo conserva mientras
// esté visible: el color sigue al par, no a su posición en la lista.
const COLORES_PARES = ['#10b981', '#f59e0b', '#8b5cf6']
const MAX_PARES = COLORES_PARES.length
const CLAVE_MEDIANA = '__mediana'

const fechaCorta = (f: string) => {
  const [y, m] = f.split('-')
  return `${m}/${y.slice(2)}`
}

/**
 * Precio en USD del ticker vs. sus pares, todos con base 100 en la misma semana. Una sola escala
 * (índice), así que no hay doble eje: lo que se lee es qué línea terminó más arriba.
 *
 * Por default: con hasta 3 pares se ven todos, uno por uno; con más, la mediana (el par "del
 * medio" de cada semana) y los chips para sumar los que interesen.
 */
export default function FuerzaRelativaChart({ puntos, ticker, pares }: { puntos: Punto[]; ticker: string; pares: string[] }) {
  const disponibles = useMemo(
    () => pares.filter(p => puntos.some(pt => pt.pares[p] != null)),
    [pares, puntos],
  )
  const [verMediana, setVerMediana] = useState(disponibles.length > MAX_PARES)
  // par -> color, en el orden en que se prendieron
  const [visibles, setVisibles] = useState<Record<string, string>>(() =>
    disponibles.length <= MAX_PARES
      ? Object.fromEntries(disponibles.map((p, i) => [p, COLORES_PARES[i]]))
      : {},
  )

  if (puntos.length < 2) {
    return <div className="text-center py-8 text-app-text-dim text-caption">Todavía no hay serie semanal suficiente.</div>
  }

  function togglePar(p: string) {
    setVisibles(v => {
      if (v[p]) {
        const { [p]: _, ...resto } = v
        return resto
      }
      const usados = new Set(Object.values(v))
      const libre = COLORES_PARES.find(c => !usados.has(c))
      return libre ? { ...v, [p]: libre } : v
    })
  }

  const datos = puntos.map(pt => ({
    fecha: pt.fecha,
    [ticker]: pt.propio,
    [CLAVE_MEDIANA]: pt.mediana_pares,
    ...pt.pares,
  }))
  const ultimo = puntos[puntos.length - 1]
  const lleno = Object.keys(visibles).length >= MAX_PARES

  return (
    <div>
      <p className="text-caption text-app-text-dim mb-2">
        Cuánto subió o bajó el precio de cada uno en los últimos 12 meses, en dólares y arrancando todos en 100.
        Si la línea de {ticker} termina más arriba, le fue mejor que a esos pares.
      </p>

      <div className="flex flex-wrap gap-1.5 mb-2">
        <span className="inline-flex items-center gap-1.5 rounded-[9px] px-2.5 py-1.5 text-label font-bold bg-app-surface-2 border border-app-border text-app-text">
          <span className="inline-block w-3 h-0.5 rounded" style={{ background: COLOR_PROPIO }} />
          {ticker} <span className="font-mono text-app-text-dim">{ultimo.propio.toFixed(0)}</span>
        </span>
        {disponibles.length > 1 && (
          <button
            onClick={() => setVerMediana(m => !m)}
            aria-pressed={verMediana}
            className={`inline-flex items-center gap-1.5 rounded-[9px] px-2.5 py-1.5 text-label font-bold border ${
              verMediana ? 'bg-app-surface-2 border-app-border text-app-text' : 'bg-app-surface border-app-border text-app-text-faint'
            }`}
          >
            <span className="inline-block w-3 border-t-2 border-dashed" style={{ borderColor: verMediana ? COLOR_MEDIANA : 'transparent' }} />
            Mediana de pares
            {verMediana && ultimo.mediana_pares != null && <span className="font-mono text-app-text-dim">{ultimo.mediana_pares.toFixed(0)}</span>}
          </button>
        )}
        {disponibles.map(p => {
          const color = visibles[p]
          return (
            <button
              key={p}
              onClick={() => togglePar(p)}
              disabled={!color && lleno}
              aria-pressed={!!color}
              className={`inline-flex items-center gap-1.5 rounded-[9px] px-2.5 py-1.5 text-label font-bold border disabled:opacity-40 ${
                color ? 'bg-app-surface-2 border-app-border text-app-text' : 'bg-app-surface border-app-border text-app-text-faint'
              }`}
            >
              <span className="inline-block w-3 h-0.5 rounded" style={{ background: color ?? 'transparent' }} />
              {p}
              {color && ultimo.pares[p] != null && <span className="font-mono text-app-text-dim">{ultimo.pares[p].toFixed(0)}</span>}
            </button>
          )
        })}
      </div>
      {disponibles.length > MAX_PARES && (
        <div className="text-label text-app-text-faint mb-1">
          Tocá un par para verlo (hasta {MAX_PARES} a la vez). La mediana es, semana a semana, el valor del par del medio.
        </div>
      )}

      <ResponsiveContainer width="100%" height={210}>
        <LineChart data={datos} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
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
            formatter={(v: any, nombre: any) => [
              v != null ? Number(v).toFixed(1) : '—',
              nombre === CLAVE_MEDIANA ? 'Mediana de pares' : nombre,
            ]}
            cursor={{ stroke: 'rgba(255,255,255,0.2)' }}
          />
          {verMediana && (
            <Line
              type="monotone" dataKey={CLAVE_MEDIANA} stroke={COLOR_MEDIANA} strokeWidth={2} strokeDasharray="5 4"
              dot={false} activeDot={{ r: 4 }} connectNulls isAnimationActive={false}
            />
          )}
          {Object.entries(visibles).map(([p, color]) => (
            <Line
              key={p} type="monotone" dataKey={p} stroke={color} strokeWidth={2}
              dot={false} activeDot={{ r: 4 }} connectNulls isAnimationActive={false}
            />
          ))}
          <Line type="monotone" dataKey={ticker} stroke={COLOR_PROPIO} strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <div className="text-label text-app-text-faint mt-1">Base 100 = primer cierre semanal · en USD</div>
    </div>
  )
}
