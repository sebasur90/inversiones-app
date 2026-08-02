import { useState } from 'react'
import { useInversionesContext } from '../../context/InversionesContext'
import { Icon } from '../icons/Icons'
import IconButton from '../ui/IconButton'
import Pill from '../ui/Pill'
import Modal from '../ui/Modal'

export default function ScreenHeader({ title, onBack }: { title: string; onBack?: () => void }) {
  const { carteras, carteraSeleccionada, setCarteraSeleccionada, monedaSeleccionada, setMonedaSeleccionada, syncing, triggerSync } =
    useInversionesContext()
  const [carteraModalOpen, setCarteraModalOpen] = useState(false)

  if (onBack) {
    return (
      <div className="flex items-center gap-3 mb-3.5">
        <IconButton onClick={onBack} aria-label="Volver">
          <Icon name="back" />
        </IconButton>
        <h1 className="font-display text-[19px] font-semibold text-app-text truncate">{title}</h1>
      </div>
    )
  }

  return (
    <>
      <div className="flex items-center justify-between gap-2 mb-3.5">
        <div className="flex items-center gap-2 min-w-0">
          <Pill onClick={() => setCarteraModalOpen(true)} className="max-w-[160px]">
            <span className="truncate">{carteraSeleccionada ?? 'Consolidado'}</span>
            <Icon name="chevron" className="w-3.5 h-3.5 text-app-text-dim" />
          </Pill>
          <div className="flex bg-app-surface border border-app-border rounded-[11px] p-[3px]">
            {(['USD', 'ARS'] as const).map(m => (
              <button
                key={m}
                onClick={() => setMonedaSeleccionada(m)}
                className={`px-2.5 py-1.5 rounded-lg text-[11.5px] font-bold ${
                  monedaSeleccionada === m ? 'bg-app-gold-soft text-app-gold' : 'text-app-text-dim'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
        <IconButton accent onClick={triggerSync} aria-label="Sincronizar">
          <Icon name="sync" className={`w-[18px] h-[18px] ${syncing ? 'animate-spin' : ''}`} />
        </IconButton>
      </div>

      <Modal open={carteraModalOpen} onClose={() => setCarteraModalOpen(false)} title="Elegir cartera">
        <div className="flex flex-col gap-1.5">
          <button
            onClick={() => {
              setCarteraSeleccionada(null)
              setCarteraModalOpen(false)
            }}
            className={`text-left px-3.5 py-3 rounded-xl text-[13.5px] font-semibold ${
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
              className={`text-left px-3.5 py-3 rounded-xl text-[13.5px] font-semibold ${
                carteraSeleccionada === c.nombre ? 'bg-app-gold-soft text-app-gold' : 'text-app-text bg-app-surface-2'
              }`}
            >
              {c.nombre}
            </button>
          ))}
        </div>
      </Modal>
    </>
  )
}
