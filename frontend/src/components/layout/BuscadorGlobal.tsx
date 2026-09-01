import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../../context/InversionesContext'
import { TODAS_LAS_PANTALLAS } from '../../data/pantallas'
import { Icon } from '../icons/Icons'
import Modal from '../ui/Modal'

const MAX_POR_SECCION = 6

// Sin acentos y en minúsculas: buscar "exposicion" tiene que encontrar "Exposición".
function normalizar(texto: string): string {
  return texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
}

export default function BuscadorGlobal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const { rendimientoPorTicker } = useInversionesContext()
  const [consulta, setConsulta] = useState('')

  const q = normalizar(consulta.trim())

  // Los tickers ya están en el contexto: buscar no dispara ningún fetch.
  const tickers = useMemo(() => {
    if (!q) return []
    return rendimientoPorTicker
      .filter(it => normalizar(it.ticker).includes(q) || normalizar(it.nombre).includes(q))
      .slice(0, MAX_POR_SECCION)
  }, [rendimientoPorTicker, q])

  const pantallas = useMemo(() => {
    if (!q) return TODAS_LAS_PANTALLAS.slice(0, MAX_POR_SECCION)
    return TODAS_LAS_PANTALLAS
      .filter(p => normalizar(p.label).includes(q) || normalizar(p.desc).includes(q))
      .slice(0, MAX_POR_SECCION)
  }, [q])

  function ir(destino: string) {
    setConsulta('')
    onClose()
    navigate(destino)
  }

  const sinResultados = q !== '' && tickers.length === 0 && pantallas.length === 0

  return (
    <Modal open={open} onClose={onClose} title="Buscar">
      <div className="flex items-center gap-2 bg-app-surface-2 border border-app-border rounded-xl h-11 px-3 mb-3">
        <Icon name="search" className="w-4 h-4 text-app-text-dim" />
        <input
          autoFocus
          value={consulta}
          onChange={e => setConsulta(e.target.value)}
          placeholder="Ticker o pantalla…"
          aria-label="Buscar ticker o pantalla"
          className="flex-1 bg-transparent outline-none text-body text-app-text placeholder:text-app-text-dim"
        />
        {consulta && (
          <button onClick={() => setConsulta('')} aria-label="Limpiar búsqueda" className="text-app-text-dim">
            <Icon name="close" className="w-4 h-4" />
          </button>
        )}
      </div>

      {sinResultados && (
        <div className="py-8 text-center text-body text-app-text-dim">
          Nada coincide con “{consulta.trim()}”.
        </div>
      )}

      {tickers.length > 0 && (
        <div className="mb-4">
          <div className="text-label font-bold uppercase tracking-wide text-app-text-dim mb-1.5">Tickers</div>
          <div className="flex flex-col gap-1">
            {tickers.map(it => (
              <button
                key={it.ticker}
                onClick={() => ir(`/ticker/${encodeURIComponent(it.ticker)}`)}
                className="flex items-center gap-3 text-left px-3 py-2.5 rounded-xl bg-app-surface-2 border border-app-border"
              >
                <div className="w-8 h-8 rounded-lg bg-app-surface border border-app-border flex items-center justify-center font-mono text-label font-bold text-app-text shrink-0">
                  {it.ticker.slice(0, 4)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-body font-semibold text-app-text truncate">{it.ticker}</div>
                  <div className="text-caption text-app-text-dim truncate">{it.nombre}</div>
                </div>
                <Icon name="chevron" className="w-3.5 h-3.5 text-app-text-dim -rotate-90 shrink-0" />
              </button>
            ))}
          </div>
        </div>
      )}

      {pantallas.length > 0 && (
        <div>
          <div className="text-label font-bold uppercase tracking-wide text-app-text-dim mb-1.5">
            {q ? 'Pantallas' : 'Ir a'}
          </div>
          <div className="flex flex-col gap-1">
            {pantallas.map(p => (
              <button
                key={p.to}
                onClick={() => ir(p.to)}
                className="flex items-center gap-3 text-left px-3 py-2.5 rounded-xl bg-app-surface-2 border border-app-border"
              >
                <div className="w-8 h-8 rounded-lg bg-app-gold-soft text-app-gold flex items-center justify-center shrink-0">
                  <Icon name={p.icon} className="w-4 h-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-body font-semibold text-app-text truncate">{p.label}</div>
                  <div className="text-caption text-app-text-dim truncate">{p.desc}</div>
                </div>
                <Icon name="chevron" className="w-3.5 h-3.5 text-app-text-dim -rotate-90 shrink-0" />
              </button>
            ))}
          </div>
        </div>
      )}
    </Modal>
  )
}
