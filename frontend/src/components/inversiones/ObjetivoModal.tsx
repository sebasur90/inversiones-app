import { useEffect, useState } from 'react'
import type { ObjetivoInversion, ObjetivoInversionPayload } from '../../api'
import Modal from '../ui/Modal'
import Button from '../ui/Button'

const EMOJIS = ['🎯', '🚗', '🪑', '🏠', '✈️', '💻', '📱', '🎓', '🏖️', '💰', '🛒', '🏋️', '🎸', '📷', '🚀']

export default function ObjetivoModal({
  open,
  objetivo,
  onGuardar,
  onCancelar,
}: {
  open: boolean
  objetivo: ObjetivoInversion | null
  onGuardar: (payload: ObjetivoInversionPayload) => Promise<void>
  onCancelar: () => void
}) {
  const [icono, setIcono] = useState('🎯')
  const [nombre, setNombre] = useState('')
  const [montoUsd, setMontoUsd] = useState('')
  const [mes, setMes] = useState('')
  const [loading, setLoading] = useState(false)
  const [errorNombre, setErrorNombre] = useState(false)

  useEffect(() => {
    if (!open) return
    setIcono(objetivo?.icono ?? '🎯')
    setNombre(objetivo?.nombre ?? '')
    setMontoUsd(objetivo ? String(objetivo.monto_usd) : '')
    setMes(objetivo ? objetivo.fecha_limite.slice(0, 7) : '')
    setErrorNombre(false)
  }, [open, objetivo])

  const handleSubmit = async () => {
    if (!nombre.trim() || !montoUsd || !mes) {
      setErrorNombre(!nombre.trim())
      return
    }
    setLoading(true)
    try {
      await onGuardar({
        nombre: nombre.trim(),
        icono,
        monto_usd: Number(montoUsd),
        fecha_limite: `${mes}-01`,
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal open={open} onClose={onCancelar} title={objetivo ? 'Editar objetivo' : 'Nuevo objetivo'}>
      <div className="flex flex-col gap-4">
        <div>
          <label className="block text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2">Ícono</label>
          <div className="flex flex-wrap gap-1.5">
            {EMOJIS.map(e => (
              <button
                key={e}
                type="button"
                onClick={() => setIcono(e)}
                className={`w-9 h-9 rounded-lg text-[19px] flex items-center justify-center border ${
                  icono === e ? 'bg-app-gold-soft border-app-gold/50' : 'border-transparent'
                }`}
              >
                {e}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2">Nombre</label>
          <input
            value={nombre}
            onChange={e => setNombre(e.target.value)}
            placeholder="ej: Fondo de emergencia"
            className={`w-full h-11 rounded-xl bg-app-surface-2 border px-3.5 text-[13.5px] text-app-text outline-none focus:border-app-gold/60 ${
              errorNombre ? 'border-app-coral' : 'border-app-border'
            }`}
          />
          {errorNombre && <p className="text-[11px] text-app-coral mt-1">Ingresá un nombre</p>}
        </div>

        <div className="flex gap-3">
          <div className="flex-1">
            <label className="block text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2">Monto (USD)</label>
            <input
              type="number"
              min={1}
              value={montoUsd}
              onChange={e => setMontoUsd(e.target.value)}
              className="w-full h-11 rounded-xl bg-app-surface-2 border border-app-border px-3.5 text-[13.5px] text-app-text outline-none focus:border-app-gold/60 tabular-nums"
            />
          </div>
          <div className="flex-1">
            <label className="block text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2">Fecha límite</label>
            <input
              type="month"
              value={mes}
              onChange={e => setMes(e.target.value)}
              className="w-full h-11 rounded-xl bg-app-surface-2 border border-app-border px-3.5 text-[13.5px] text-app-text outline-none focus:border-app-gold/60"
            />
          </div>
        </div>

        <div className="flex gap-2 mt-1">
          <Button variant="outline" onClick={onCancelar} className="flex-1">
            Cancelar
          </Button>
          <Button onClick={handleSubmit} loading={loading} className="flex-1">
            Guardar
          </Button>
        </div>
      </div>
    </Modal>
  )
}
