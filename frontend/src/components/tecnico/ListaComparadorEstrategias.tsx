import { useMemo, useState } from 'react'
import type { ComparadorFilaOut } from '../../api'
import { formatARS, formatUSD, formatPrecio } from '../../utils'

const ETIQUETA_ESTADO: Record<string, string> = {
  sin_senales: 'Sin señales',
  datos_insuficientes: 'Datos insuficientes',
  warm_up_insuficiente: 'Warm-up insuficiente',
  definicion_invalida: 'Definición inválida',
}

type ClaveOrden = 'retorno_total_pct' | 'capital_final' | 'diferencia_pp' | 'max_drawdown_pct' | 'operaciones' | 'nombre'

const ORDENES: { value: ClaveOrden; label: string }[] = [
  { value: 'retorno_total_pct', label: 'Rendimiento' },
  { value: 'capital_final', label: 'Capital final' },
  { value: 'diferencia_pp', label: 'Diferencia vs. referencia' },
  { value: 'max_drawdown_pct', label: 'Drawdown (menor primero)' },
  { value: 'operaciones', label: 'Operaciones' },
  { value: 'nombre', label: 'Nombre' },
]

function valorOrden(f: ComparadorFilaOut, clave: ClaveOrden): string | number | null {
  switch (clave) {
    case 'retorno_total_pct': return f.retorno_total_pct
    case 'capital_final': return f.capital_final
    case 'diferencia_pp': return f.diferencia_pp
    // El drawdown llega negativo (una caída), así que "menor primero" es el más cercano a cero:
    // ordenamos por su magnitud para que el criterio se lea igual que la etiqueta.
    case 'max_drawdown_pct': return f.riesgo?.max_drawdown_pct != null ? Math.abs(f.riesgo.max_drawdown_pct) : null
    case 'operaciones': return f.riesgo?.operaciones ?? null
    case 'nombre': return f.nombre
  }
}

// El orden natural de cada criterio: de mayor a menor en los que "más es mejor", ascendente en
// drawdown (magnitud) y en el nombre.
const ASCENDENTE: Record<ClaveOrden, boolean> = {
  retorno_total_pct: false,
  capital_final: false,
  diferencia_pp: false,
  max_drawdown_pct: true,
  operaciones: false,
  nombre: true,
}

function comparar(a: string | number | null, b: string | number | null, asc: boolean): number {
  // Los nulos siempre al final: una fila sin dato no es "la mejor" ni "la peor".
  if (a == null && b == null) return 0
  if (a == null) return 1
  if (b == null) return -1
  const signo = asc ? 1 : -1
  if (typeof a === 'number' && typeof b === 'number') return (a - b) * signo
  return String(a).localeCompare(String(b), 'es-AR') * signo
}

function formatMoneda(v: number, moneda: string): string {
  if (moneda === 'ARS') return formatARS(v)
  if (moneda === 'USD') return formatUSD(v)
  return formatPrecio(v)
}

function claveFila(f: ComparadorFilaOut): string {
  return String(f.estrategia_id ?? 'bh')
}

function FilaComparador({ fila, posicion, moneda, onClick }: {
  fila: ComparadorFilaOut
  posicion: number
  moneda: string
  onClick?: () => void
}) {
  const r = fila.riesgo
  const motivo = ETIQUETA_ESTADO[fila.estado] ?? 'Sin datos'
  const hayNumeros = fila.retorno_total_pct != null

  return (
    <div
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } } : undefined}
      className={`bg-app-surface-2 border border-app-border rounded-xl px-3 py-2.5 ${
        onClick ? 'cursor-pointer active:bg-app-accent-soft' : ''
      }`}
    >
      <div className="flex items-baseline gap-2 min-w-0">
        <span className="text-label font-bold tabular-nums text-app-text-faint shrink-0">{posicion}</span>
        <span className="text-body font-semibold text-app-text truncate">{fila.nombre}</span>
        {fila.es_referencia && (
          <span className="text-label font-bold px-1.5 py-0.5 rounded bg-app-accent-soft text-app-accent shrink-0 ml-auto">
            referencia
          </span>
        )}
      </div>

      {hayNumeros ? (
        <>
          <div className="flex items-baseline justify-between gap-2 mt-1.5">
            <span className={`font-mono text-metric font-bold tabular-nums ${
              fila.retorno_total_pct! >= 0 ? 'text-app-pos' : 'text-app-neg'
            }`}>
              {fila.retorno_total_pct! >= 0 ? '+' : ''}{fila.retorno_total_pct!.toFixed(2)}%
            </span>
            {fila.diferencia_pp != null && (
              <span className={`font-mono text-caption tabular-nums ${
                fila.diferencia_pp >= 0 ? 'text-app-pos' : 'text-app-neg'
              }`}>
                {fila.diferencia_pp >= 0 ? '+' : ''}{fila.diferencia_pp.toFixed(2)} pp
              </span>
            )}
          </div>
          {fila.capital_final != null && (
            <div className="text-caption text-app-text-dim tabular-nums mt-0.5">
              {formatMoneda(fila.capital_final, moneda)} de capital final
            </div>
          )}
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1.5 pt-1.5 border-t border-app-border-soft text-label text-app-text-faint tabular-nums">
            <span>
              Drawdown{' '}
              <span className="text-app-text-dim">
                {r?.max_drawdown_pct != null ? `${r.max_drawdown_pct.toFixed(2)}%` : '—'}
              </span>
            </span>
            <span>
              Operaciones <span className="text-app-text-dim">{r?.operaciones ?? '—'}</span>
            </span>
          </div>
        </>
      ) : (
        // Sin número no inventamos un 0: la fila dice por qué no hay resultado.
        <div className="text-caption text-app-text-faint mt-1.5">{motivo}</div>
      )}
    </div>
  )
}

/** Comparativa de estrategias como lista de tarjetas.
 *
 * Reemplaza a la tabla de 6 columnas: el shell de la app mide como máximo 448px, así que esa
 * tabla nunca entraba y arrastraba la pantalla entera en horizontal. Acá cada estrategia ocupa
 * una tarjeta con el rendimiento como dato protagonista y el resto en líneas secundarias, y el
 * criterio de orden se elige con un selector en vez de tocando encabezados. */
export default function ListaComparadorEstrategias({
  filas, moneda, onFilaClick,
}: {
  filas: ComparadorFilaOut[]
  moneda: string
  onFilaClick?: (fila: ComparadorFilaOut) => void
}) {
  const [orden, setOrden] = useState<ClaveOrden>('retorno_total_pct')

  const filasOrdenadas = useMemo(
    () => [...filas].sort((a, b) => comparar(valorOrden(a, orden), valorOrden(b, orden), ASCENDENTE[orden])),
    [filas, orden],
  )

  return (
    <div>
      <div className="flex flex-col gap-2">
        {filasOrdenadas.map((f, i) => (
          <FilaComparador
            key={claveFila(f)} fila={f} posicion={i + 1} moneda={moneda}
            onClick={onFilaClick && f.estrategia_id != null ? () => onFilaClick(f) : undefined}
          />
        ))}
      </div>

      <div className="flex items-center gap-2 mt-3">
        <label htmlFor="orden-comparador" className="text-label font-bold uppercase text-app-text-faint shrink-0">
          Ordenar por
        </label>
        <select
          id="orden-comparador" value={orden} onChange={e => setOrden(e.target.value as ClaveOrden)}
          className="flex-1 min-w-0 h-9 rounded-lg bg-app-surface-2 border border-app-border px-2 text-caption text-app-text"
        >
          {ORDENES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>
    </div>
  )
}
