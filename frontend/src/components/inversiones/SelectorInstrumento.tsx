import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { buscarCatalogo, type CatalogoInstrumentoOut } from '../../api'
import { qk } from '../../api/queryClient'
import { Icon } from '../icons/Icons'
import { SkeletonFilas } from '../ui/Skeleton'

/** El orden de los chips: de más a menos usado, no alfabético. */
const TIPOS = ['Acción', 'CEDEAR', 'Bono', 'ON', 'Letra', 'FCI'] as const

export default function SelectorInstrumento({
  onElegir,
  yaSeguidos,
  deshabilitado,
}: {
  onElegir: (instrumento: CatalogoInstrumentoOut) => void
  /** Tickers que ya están en la watchlist: se muestran, pero no se pueden volver a agregar. */
  yaSeguidos: Set<string>
  deshabilitado?: boolean
}) {
  const [texto, setTexto] = useState('')
  const [tipo, setTipo] = useState('')
  const [consulta, setConsulta] = useState('')

  // Debounce: el catálogo son ~2.300 instrumentos servidos desde un archivo, pero sin esto cada
  // tecla dispara un request y las respuestas pueden llegar desordenadas.
  useEffect(() => {
    const t = setTimeout(() => setConsulta(texto.trim()), 250)
    return () => clearTimeout(t)
  }, [texto])

  const busqueda = useQuery({
    queryKey: qk.catalogo(consulta, tipo),
    queryFn: () => buscarCatalogo(consulta, tipo),
  })

  const conteos = busqueda.data?.conteos_por_tipo ?? {}
  const items = useMemo(() => busqueda.data?.items ?? [], [busqueda.data])
  const total = busqueda.data?.total ?? 0

  return (
    <div className="flex flex-col gap-3">
      <label className="flex items-center gap-2 h-11 px-3 rounded-2xl bg-app-surface-2 border border-app-border">
        <Icon name="search" className="w-4 h-4 text-app-text-dim" />
        <input
          autoFocus
          value={texto}
          onChange={e => setTexto(e.target.value)}
          placeholder="Ticker o nombre (AL30, Apple, Aluar…)"
          className="flex-1 min-w-0 bg-transparent text-body text-app-text placeholder:text-app-text-dim outline-none"
        />
        {texto && (
          <button onClick={() => setTexto('')} aria-label="Limpiar búsqueda" className="flex items-center">
            <Icon name="close" className="w-4 h-4 text-app-text-dim" />
          </button>
        )}
      </label>

      <div className="flex gap-1.5 overflow-x-auto -mx-1 px-1 pb-0.5">
        <ChipTipo activo={tipo === ''} onClick={() => setTipo('')}>
          Todos
        </ChipTipo>
        {TIPOS.map(t => (
          <ChipTipo key={t} activo={tipo === t} onClick={() => setTipo(tipo === t ? '' : t)}>
            {t} · {conteos[t] ?? 0}
          </ChipTipo>
        ))}
      </div>

      <div className="min-h-[260px] max-h-[48vh] overflow-y-auto -mx-1 px-1">
        {busqueda.isLoading ? (
          <SkeletonFilas filas={5} />
        ) : busqueda.error ? (
          <p className="text-caption text-app-neg py-6 text-center">
            No se pudo leer el catálogo de instrumentos.
          </p>
        ) : items.length === 0 ? (
          <p className="text-caption text-app-text-dim py-6 text-center">
            {consulta ? `Sin resultados para "${consulta}"` : 'No hay instrumentos en el catálogo.'}
          </p>
        ) : (
          <>
            {items.map(item => {
              const seguido = yaSeguidos.has(item.simbolo)
              return (
                <button
                  key={item.simbolo}
                  disabled={seguido || deshabilitado}
                  onClick={() => onElegir(item)}
                  className="w-full flex items-center gap-2.5 py-2.5 border-b border-app-border-soft last:border-b-0 text-left disabled:opacity-45"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="font-mono text-caption font-bold text-app-text truncate">
                        {item.simbolo}
                      </span>
                      <span className="shrink-0 rounded-md px-1.5 py-0.5 text-label font-bold bg-app-surface-2 text-app-text-dim">
                        {item.tipo}
                      </span>
                    </div>
                    <div className="text-label text-app-text-dim truncate mt-0.5">
                      {item.descripcion}
                    </div>
                  </div>
                  {seguido ? (
                    <span className="shrink-0 text-label font-bold text-app-text-dim">Ya la seguís</span>
                  ) : (
                    <Icon name="plus" className="w-4 h-4 text-app-accent shrink-0" />
                  )}
                </button>
              )
            })}
            {total > items.length && (
              <p className="text-label text-app-text-dim py-3 text-center">
                {total - items.length} resultados más. Afiná la búsqueda.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function ChipTipo({
  activo,
  onClick,
  children,
}: {
  activo: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={`shrink-0 rounded-[9px] px-2.5 py-1.5 text-label font-bold border transition-colors ${
        activo
          ? 'bg-app-accent-soft text-app-accent border-app-accent/40'
          : 'bg-app-surface-2 text-app-text-dim border-app-border'
      }`}
    >
      {children}
    </button>
  )
}
