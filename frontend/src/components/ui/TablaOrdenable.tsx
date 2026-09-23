import { useMemo, useState, type ReactNode } from 'react'
import { Icon } from '../icons/Icons'

export interface ColumnaOrdenable<T> {
  key: string
  label: string
  align?: 'left' | 'right'
  valor: (fila: T) => string | number | null
  render?: (fila: T) => ReactNode
  ordenable?: boolean
}

interface Props<T> {
  columnas: ColumnaOrdenable<T>[]
  filas: T[]
  getKey: (fila: T) => string
  ordenInicial: { key: string; dir: 'asc' | 'desc' }
  onFilaClick?: (fila: T) => void
}

type Dir = 'asc' | 'desc'

function comparar(a: string | number | null, b: string | number | null, dir: Dir): number {
  // Los nulos siempre van al final, sin importar la dirección: no hay forma "correcta" de
  // ordenar un valor ausente, y ponerlo primero en 'desc' lo haría parecer el más relevante.
  if (a == null && b == null) return 0
  if (a == null) return 1
  if (b == null) return -1
  const signo = dir === 'asc' ? 1 : -1
  if (typeof a === 'number' && typeof b === 'number') return (a - b) * signo
  return String(a).localeCompare(String(b), 'es-AR') * signo
}

// Primer valor no nulo de la columna: define si la dirección "natural" al elegirla por primera
// vez es desc (numérica, como en un ranking) o asc (texto, alfabético).
function direccionNatural<T>(filas: T[], columna: ColumnaOrdenable<T>): Dir {
  for (const fila of filas) {
    const v = columna.valor(fila)
    if (v != null) return typeof v === 'number' ? 'desc' : 'asc'
  }
  return 'asc'
}

export default function TablaOrdenable<T>({ columnas, filas, getKey, ordenInicial, onFilaClick }: Props<T>) {
  const [orden, setOrden] = useState(ordenInicial)

  const filasOrdenadas = useMemo(() => {
    const columna = columnas.find(c => c.key === orden.key)
    if (!columna) return filas
    return [...filas].sort((a, b) => comparar(columna.valor(a), columna.valor(b), orden.dir))
  }, [filas, columnas, orden])

  function onHeaderClick(columna: ColumnaOrdenable<T>) {
    if (columna.ordenable === false) return
    setOrden(prev =>
      prev.key === columna.key
        ? { key: columna.key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key: columna.key, dir: direccionNatural(filas, columna) }
    )
  }

  return (
    <table className="w-full text-label border-separate border-spacing-0">
      <thead>
        <tr>
          {columnas.map((c, i) => {
            const activa = orden.key === c.key
            const align = c.align ?? (i === 0 ? 'left' : 'right')
            const ariaSort = activa ? (orden.dir === 'asc' ? 'ascending' : 'descending') : 'none'
            return (
              <th key={c.key} className={`pb-2 ${align === 'right' ? 'text-right' : 'text-left'}`} aria-sort={ariaSort}>
                {c.ordenable === false ? (
                  <span className="text-app-text-faint font-bold uppercase text-label">{c.label}</span>
                ) : (
                  <button
                    onClick={() => onHeaderClick(c)}
                    className={`inline-flex items-center gap-1 py-2.5 -my-2.5 px-2 -mx-2 font-bold uppercase text-label ${
                      activa ? 'text-app-text' : 'text-app-text-faint'
                    }`}
                  >
                    {c.label}
                    {activa && <Icon name={orden.dir === 'asc' ? 'up' : 'down'} className="w-3 h-3" />}
                  </button>
                )}
              </th>
            )
          })}
        </tr>
      </thead>
      <tbody>
        {filasOrdenadas.map(fila => (
          <tr
            key={getKey(fila)}
            onClick={onFilaClick ? () => onFilaClick(fila) : undefined}
            className={onFilaClick ? 'cursor-pointer active:bg-app-accent-soft' : undefined}
          >
            {columnas.map((c, i) => {
              const align = c.align ?? (i === 0 ? 'left' : 'right')
              return (
                <td key={c.key} className={`py-1.5 ${align === 'right' ? 'text-right' : 'text-left'}`}>
                  {c.render ? c.render(fila) : String(c.valor(fila) ?? '—')}
                </td>
              )
            })}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
