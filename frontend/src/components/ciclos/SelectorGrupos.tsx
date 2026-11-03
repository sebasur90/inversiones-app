import { useMemo } from 'react'
import type { CicloGrupoCatalogo } from '../../api'
import { Icon } from '../icons/Icons'
import { ETIQUETA_TIPO } from './constantes'

interface Props {
  grupos: CicloGrupoCatalogo[]
  seleccion: string[]
  onChange: (ids: string[]) => void
  max: number
  placeholder?: string
}

/** Elegir grupos del catálogo: los elegidos como fichas removibles y un menú con el resto, agrupado por tipo. */
export default function SelectorGrupos({ grupos, seleccion, onChange, max, placeholder = 'Agregar un grupo…' }: Props) {
  const porId = useMemo(() => new Map(grupos.map(g => [g.id, g])), [grupos])
  const disponibles = useMemo(() => grupos.filter(g => g.activo && !seleccion.includes(g.id)), [grupos, seleccion])
  const tipos = useMemo(() => [...new Set(disponibles.map(g => g.tipo))], [disponibles])
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        {seleccion.map(id => (
          <span key={id} className="inline-flex items-center gap-1 rounded-lg bg-app-accent-soft px-2 py-1 text-caption font-semibold text-app-accent">
            {porId.get(id)?.nombre ?? id}
            <button type="button" aria-label={`Quitar ${porId.get(id)?.nombre ?? id}`} onClick={() => onChange(seleccion.filter(x => x !== id))} className="p-0.5">
              <Icon name="close" className="w-3 h-3" />
            </button>
          </span>
        ))}
        {seleccion.length === 0 && <span className="text-label text-app-text-faint">Ningún grupo elegido.</span>}
      </div>
      {seleccion.length < max && (
        <select
          aria-label={placeholder}
          value=""
          onChange={e => e.target.value && onChange([...seleccion, e.target.value])}
          className="h-11 w-full rounded-xl bg-app-surface border border-app-border px-3 text-body text-app-text"
        >
          <option value="">{placeholder}</option>
          {tipos.map(t => (
            <optgroup key={t} label={ETIQUETA_TIPO[t]}>
              {disponibles
                .filter(g => g.tipo === t)
                .map(g => (
                  <option key={g.id} value={g.id}>
                    {g.nombre}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      )}
    </div>
  )
}
