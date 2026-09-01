import { useState } from 'react'
import { useInversionesContext } from '../../context/InversionesContext'
import { Icon } from '../icons/Icons'
import IconButton from '../ui/IconButton'
import Pill from '../ui/Pill'
import Modal from '../ui/Modal'
import BuscadorGlobal from './BuscadorGlobal'
import { calcularFrescura, type NivelFrescura } from '../../utils/frescura'

const COLOR_FRESCURA: Record<NivelFrescura, string> = {
  fresco: 'text-app-text-dim',
  tibio: 'text-app-gold',
  viejo: 'text-app-coral',
  desconocido: 'text-app-coral',
}

export default function ScreenHeader({ title, onBack }: { title: string; onBack?: () => void }) {
  const {
    carteras, carteraSeleccionada, setCarteraSeleccionada,
    monedaSeleccionada, setMonedaSeleccionada,
    syncing, triggerSync, ultimoSync,
  } = useInversionesContext()
  const [carteraModalOpen, setCarteraModalOpen] = useState(false)
  const [buscadorOpen, setBuscadorOpen] = useState(false)

  if (onBack) {
    return (
      <div className="flex items-center gap-3 mb-3.5">
        <IconButton onClick={onBack} aria-label="Volver">
          <Icon name="back" />
        </IconButton>
        <h1 className="font-display text-heading font-semibold text-app-text truncate">{title}</h1>
      </div>
    )
  }

  const frescura = calcularFrescura(ultimoSync)

  return (
    <>
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-2 min-w-0">
          <Pill onClick={() => setCarteraModalOpen(true)} className="max-w-[150px]">
            <span className="truncate">{carteraSeleccionada ?? 'Consolidado'}</span>
            <Icon name="chevron" className="w-3.5 h-3.5 text-app-text-dim" />
          </Pill>
          <div className="flex bg-app-surface border border-app-border rounded-[11px] p-[3px]">
            {(['USD', 'ARS'] as const).map(m => (
              <button
                key={m}
                onClick={() => setMonedaSeleccionada(m)}
                aria-pressed={monedaSeleccionada === m}
                className={`px-2.5 py-1.5 rounded-lg text-caption font-bold ${
                  monedaSeleccionada === m ? 'bg-app-gold-soft text-app-gold' : 'text-app-text-dim'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <IconButton onClick={() => setBuscadorOpen(true)} aria-label="Buscar ticker o pantalla">
            <Icon name="search" className="w-[18px] h-[18px]" />
          </IconButton>
          <IconButton accent onClick={triggerSync} disabled={syncing} aria-label="Sincronizar con el Sheet">
            <Icon name="sync" className={`w-[18px] h-[18px] ${syncing ? 'animate-spin' : ''}`} />
          </IconButton>
        </div>
      </div>

      {/* Frescura de los datos: sin esto no había forma de saber si los números son de hoy
          o de la semana pasada sin entrar a Calidad de datos. */}
      <button
        onClick={triggerSync}
        disabled={syncing}
        className={`text-caption mb-3 ${COLOR_FRESCURA[frescura.nivel]} disabled:opacity-60`}
      >
        {syncing ? 'Sincronizando…' : `Datos ${frescura.etiqueta}`}
      </button>

      <Modal open={carteraModalOpen} onClose={() => setCarteraModalOpen(false)} title="Elegir cartera">
        <div className="flex flex-col gap-1.5">
          <button
            onClick={() => {
              setCarteraSeleccionada(null)
              setCarteraModalOpen(false)
            }}
            className={`text-left px-3.5 py-3 rounded-xl text-body font-semibold ${
              carteraSeleccionada === null ? 'bg-app-gold-soft text-app-gold' : 'text-app-text bg-app-surface-2'
            }`}
          >
            Consolidado
          </button>
          {carteras.map(c => (
            <button
              key={c.nombre}
              onClick={() => {
                setCarteraSeleccionada(c.nombre)
                setCarteraModalOpen(false)
              }}
              className={`text-left px-3.5 py-3 rounded-xl text-body font-semibold ${
                carteraSeleccionada === c.nombre ? 'bg-app-gold-soft text-app-gold' : 'text-app-text bg-app-surface-2'
              }`}
            >
              {c.nombre}
            </button>
          ))}
        </div>
      </Modal>

      <BuscadorGlobal open={buscadorOpen} onClose={() => setBuscadorOpen(false)} />
    </>
  )
}
