import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

interface Punto {
  fecha: string
  /** Cierre semanal en USD, sin normalizar. */
  propio: number
  pares: Record<string, number>
}

const COLOR_PROPIO = '#3b82f6'   // app-accent: el ticker siempre en azul
const COLOR_MEDIANA = '#94a3b8'  // app-text-dim, punteada: la referencia resumida
// Un color por par mostrado (como mucho 3 a la vez). Se asigna al prenderlo y lo conserva mientras
// esté visible: el color sigue al par, no a su posición en la lista.
const COLORES_PARES = ['#10b981', '#f59e0b', '#8b5cf6']
const MAX_PARES = COLORES_PARES.length
const CLAVE_MEDIANA = '__mediana'

const ATAJOS: { label: string; meses: number }[] = [
  { label: '1M', meses: 1 }, { label: '3M', meses: 3 }, { label: '6M', meses: 6 },
  { label: '1A', meses: 12 }, { label: '3A', meses: 36 }, { label: '5A', meses: 60 },
]

const fechaCorta = (f: string) => {
  const [y, m] = f.split('-')
  return `${m}/${y.slice(2)}`
}
const fechaLarga = (f: string) => f.split('-').reverse().join('/')
const pct = (v: number | null | undefined) =>
  v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toLocaleString('es-AR', { maximumFractionDigits: 1, minimumFractionDigits: 1 })}%`

function mediana(xs: number[]): number | null {
  if (xs.length === 0) return null
  const s = [...xs].sort((a, b) => a - b)
  const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

/** El primer punto en o después de `fecha` (la serie es semanal: una fecha elegida a mano casi
 *  nunca cae justo en un cierre). */
function indiceDesde(puntos: Punto[], fecha: string): number {
  const i = puntos.findIndex(p => p.fecha >= fecha)
  return i === -1 ? Math.max(puntos.length - 2, 0) : Math.min(i, puntos.length - 2)
}

function restarMeses(iso: string, meses: number): string {
  const d = new Date(`${iso}T00:00:00`)
  d.setMonth(d.getMonth() - meses)
  return d.toISOString().slice(0, 10)
}

/**
 * Precio en USD del ticker vs. sus pares, re-basado a 100 en la fecha que elija el usuario: un
 * atajo (1M…5A), una fecha puntual o tocando el gráfico. Sirve para preguntas como "desde el piso
 * de la última baja, ¿quién se recuperó mejor?". Una sola escala (índice): no hay doble eje.
 *
 * Por default: últimos 12 meses; con hasta 3 pares se ven todos, con más la mediana y chips para
 * sumar los que interesen. La mediana se calcula acá, sobre la fecha base elegida.
 */
export default function FuerzaRelativaChart({ puntos, ticker, pares }: { puntos: Punto[]; ticker: string; pares: string[] }) {
  const primera = puntos[0]?.fecha ?? ''
  const ultima = puntos[puntos.length - 1]?.fecha ?? ''
  const disponibles = useMemo(
    () => pares.filter(p => puntos.some(pt => pt.pares[p] != null)),
    [pares, puntos],
  )
  const [base, setBase] = useState(() => (ultima ? restarMeses(ultima, 12) : ''))
  const [verMediana, setVerMediana] = useState(disponibles.length > MAX_PARES)
  const [visibles, setVisibles] = useState<Record<string, string>>(() =>
    disponibles.length <= MAX_PARES
      ? Object.fromEntries(disponibles.map((p, i) => [p, COLORES_PARES[i]]))
      : {},
  )

  const tramo = useMemo(() => {
    if (puntos.length < 2) return null
    const i0 = indiceDesde(puntos, base)
    const p0 = puntos[i0]
    // Un par sin cotización en la fecha base (todavía no listaba) queda afuera: no hay desde dónde medirlo.
    const conBase = disponibles.filter(p => p0.pares[p] != null)
    const filas = puntos.slice(i0).map(pt => {
      const fila: Record<string, number | string | null> = {
        fecha: pt.fecha,
        [ticker]: (pt.propio / p0.propio) * 100,
      }
      const vals: number[] = []
      for (const p of conBase) {
        if (pt.pares[p] != null) {
          const v = (pt.pares[p] / p0.pares[p]) * 100
          fila[p] = v
          vals.push(v)
        }
      }
      fila[CLAVE_MEDIANA] = mediana(vals)
      return fila
    })
    const fin = filas[filas.length - 1]
    const rendPropio = (fin[ticker] as number) - 100
    const rendPares = Object.fromEntries(
      conBase.filter(p => fin[p] != null).map(p => [p, (fin[p] as number) - 100]),
    ) as Record<string, number>
    const rendMediana = fin[CLAVE_MEDIANA] != null ? (fin[CLAVE_MEDIANA] as number) - 100 : null
    return { desde: p0.fecha, filas, conBase, rendPropio, rendPares, rendMediana }
  }, [puntos, base, disponibles, ticker])

  if (!tramo) {
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

  const lleno = Object.keys(visibles).length >= MAX_PARES
  const comparables = Object.values(tramo.rendPares)
  const superados = comparables.filter(r => tramo.rendPropio > r).length
  const atajoActivo = ATAJOS.find(a => indiceDesde(puntos, restarMeses(ultima, a.meses)) === indiceDesde(puntos, base))

  return (
    <div>
      <p className="text-caption text-app-text-dim mb-2">
        Cuánto subió o bajó el precio de cada uno desde la fecha que elijas, en dólares y arrancando todos en 100.
        Elegí un atajo, una fecha, o tocá el gráfico en el punto desde el que querés medir (por ejemplo, el piso de una baja).
      </p>

      <div className="flex flex-wrap items-center gap-1.5 mb-2">
        {ATAJOS.filter(a => restarMeses(ultima, a.meses) >= primera || a.meses === 1).map(a => (
          <button
            key={a.label}
            onClick={() => setBase(restarMeses(ultima, a.meses))}
            className={`rounded-[9px] px-2.5 py-1.5 text-label font-bold border ${
              atajoActivo?.label === a.label
                ? 'bg-app-accent-soft text-app-accent border-app-accent/40'
                : 'bg-app-surface-2 text-app-text-dim border-app-border'
            }`}
          >
            {a.label}
          </button>
        ))}
        <button
          onClick={() => setBase(primera)}
          className={`rounded-[9px] px-2.5 py-1.5 text-label font-bold border ${
            indiceDesde(puntos, base) === 0
              ? 'bg-app-accent-soft text-app-accent border-app-accent/40'
              : 'bg-app-surface-2 text-app-text-dim border-app-border'
          }`}
        >
          Máx
        </button>
        <label className="inline-flex items-center gap-1.5 text-label text-app-text-dim">
          Desde
          <input
            type="date"
            value={tramo.desde}
            min={primera}
            max={puntos[puntos.length - 2]?.fecha}
            onChange={e => e.target.value && setBase(e.target.value)}
            className="h-8 px-2 rounded-lg bg-app-surface-2 border border-app-border text-label text-app-text"
          />
        </label>
      </div>

      <div className="text-caption text-app-text mb-2">
        Desde el {fechaLarga(tramo.desde)}: <span className="font-bold">{ticker} {pct(tramo.rendPropio)}</span>
        {tramo.rendMediana != null && comparables.length > 1 && (
          <span className="text-app-text-dim"> · mediana de pares {pct(tramo.rendMediana)}</span>
        )}
        {comparables.length > 0 && (
          <span className="text-app-text-dim"> · le fue mejor que a {superados} de {comparables.length} {comparables.length === 1 ? 'par' : 'pares'}</span>
        )}
      </div>

      <div className="flex flex-wrap gap-1.5 mb-2">
        {tramo.conBase.length > 1 && (
          <button
            onClick={() => setVerMediana(m => !m)}
            aria-pressed={verMediana}
            className={`inline-flex items-center gap-1.5 rounded-[9px] px-2.5 py-1.5 text-label font-bold border ${
              verMediana ? 'bg-app-surface-2 border-app-border text-app-text' : 'bg-app-surface border-app-border text-app-text-faint'
            }`}
          >
            <span className="inline-block w-3 border-t-2 border-dashed" style={{ borderColor: verMediana ? COLOR_MEDIANA : 'transparent' }} />
            Mediana {verMediana && <span className="font-mono text-app-text-dim">{pct(tramo.rendMediana)}</span>}
          </button>
        )}
        {disponibles.map(p => {
          const color = visibles[p]
          const sinBase = !tramo.conBase.includes(p)
          return (
            <button
              key={p}
              onClick={() => togglePar(p)}
              disabled={sinBase || (!color && lleno)}
              aria-pressed={!!color}
              title={sinBase ? 'No cotizaba en la fecha elegida' : undefined}
              className={`inline-flex items-center gap-1.5 rounded-[9px] px-2.5 py-1.5 text-label font-bold border disabled:opacity-40 ${
                color && !sinBase ? 'bg-app-surface-2 border-app-border text-app-text' : 'bg-app-surface border-app-border text-app-text-faint'
              }`}
            >
              <span className="inline-block w-3 h-0.5 rounded" style={{ background: color && !sinBase ? color : 'transparent' }} />
              {p}
              <span className="font-mono text-app-text-dim">{sinBase ? 's/d' : pct(tramo.rendPares[p])}</span>
            </button>
          )
        })}
      </div>
      {disponibles.length > MAX_PARES && (
        <div className="text-label text-app-text-faint mb-1">
          Tocá un par para verlo (hasta {MAX_PARES} a la vez). La mediana es, semana a semana, el valor del par del medio.
        </div>
      )}

      <ResponsiveContainer width="100%" height={220}>
        <LineChart
          data={tramo.filas}
          margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
          onClick={(e: any) => {
            if (e?.activeLabel && e.activeLabel !== tramo.desde && e.activeLabel < ultima) setBase(String(e.activeLabel))
          }}
        >
          <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
          <XAxis
            dataKey="fecha" tickFormatter={fechaCorta} minTickGap={28}
            tick={{ fontSize: 10, fill: '#7c8798' }} stroke="rgba(255,255,255,0.07)" tickLine={false}
          />
          <YAxis
            width={34} tick={{ fontSize: 10, fill: '#7c8798' }} stroke="rgba(255,255,255,0.07)"
            tickLine={false} axisLine={false} domain={['auto', 'auto']}
            tickFormatter={(v: number) => v.toFixed(0)}
          />
          <ReferenceLine y={100} stroke="rgba(255,255,255,0.15)" />
          <Tooltip
            contentStyle={{ background: '#171b26', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 10, fontSize: 12 }}
            labelStyle={{ color: '#f8fafc' }}
            itemStyle={{ color: '#f8fafc' }}
            labelFormatter={(f: any) => `Semana del ${fechaLarga(String(f))} · tocá para medir desde acá`}
            formatter={(v: any, nombre: any) => [
              v != null ? pct(Number(v) - 100) : '—',
              nombre === CLAVE_MEDIANA ? 'Mediana de pares' : nombre,
            ]}
            cursor={{ stroke: 'rgba(255,255,255,0.2)' }}
          />
          {verMediana && tramo.conBase.length > 1 && (
            <Line
              type="monotone" dataKey={CLAVE_MEDIANA} stroke={COLOR_MEDIANA} strokeWidth={2} strokeDasharray="5 4"
              dot={false} activeDot={{ r: 4 }} connectNulls isAnimationActive={false}
            />
          )}
          {Object.entries(visibles).filter(([p]) => tramo.conBase.includes(p)).map(([p, color]) => (
            <Line
              key={p} type="monotone" dataKey={p} stroke={color} strokeWidth={2}
              dot={false} activeDot={{ r: 4 }} connectNulls isAnimationActive={false}
            />
          ))}
          <Line type="monotone" dataKey={ticker} stroke={COLOR_PROPIO} strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <div className="text-label text-app-text-faint mt-1">
        Base 100 = cierre de la semana del {fechaLarga(tramo.desde)} · en USD · historia disponible desde {fechaLarga(primera)}
      </div>
    </div>
  )
}
