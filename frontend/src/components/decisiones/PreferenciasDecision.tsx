import { useEffect, useState, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { guardarPreferenciasDecision, type PreferenciasDecision, type PreferenciasDecisionOut } from '../../api'
import { qk } from '../../api/queryClient'
import { parseApiError } from '../../help/errors/apiErrors'
import ErrorBanner from '../../help/components/ErrorBanner'
import InfoTooltip from '../../help/components/InfoTooltip'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import Segmented from '../ui/Segmented'

const DIMS: { clave: string; nombre: string }[] = [
  { clave: 'fundamentales', nombre: 'Fundamentales' }, { clave: 'valoracion', nombre: 'Valoración' },
  { clave: 'riesgo', nombre: 'Riesgo' }, { clave: 'tecnico', nombre: 'Técnico' }, { clave: 'encaje', nombre: 'Encaje' },
]

/** Preferencias de análisis: se guardan en el servidor porque cada decisión las congela y el aviso las usa. */
export default function PreferenciasDecisionModal({ abierto, onClose, actuales }: {
  abierto: boolean; onClose: () => void; actuales: PreferenciasDecisionOut
}) {
  const queryClient = useQueryClient()
  const [p, setP] = useState<PreferenciasDecision>(actuales)
  const [pesosPropios, setPesosPropios] = useState(actuales.pesos != null)
  useEffect(() => { setP(actuales); setPesosPropios(actuales.pesos != null) }, [actuales])
  const tabla = actuales.pesos_tabla[p.enfoque]?.[p.horizonte] ?? {}
  const pesos = p.pesos ?? tabla

  const guardar = useMutation({
    mutationFn: () => guardarPreferenciasDecision({ ...p, pesos: pesosPropios ? pesos : null }),
    onSuccess: datos => {
      queryClient.setQueryData(qk.de('decisiones-preferencias'), datos)
      void queryClient.invalidateQueries({ queryKey: qk.de('decision-analisis') })
      void queryClient.invalidateQueries({ queryKey: qk.de('decisiones-explorar') })
      void queryClient.invalidateQueries({ queryKey: qk.de('decision-posicion') })
      onClose()
    },
  })

  const set = <K extends keyof PreferenciasDecision>(k: K, v: PreferenciasDecision[K]) => setP(prev => ({ ...prev, [k]: v }))

  return (
    <Modal open={abierto} onClose={onClose} title="Preferencias de análisis">
      <div className="flex flex-col gap-3">
        <Campo titulo="Horizonte">
          <Segmented options={[{ value: 'corto', label: 'Corto' }, { value: 'mediano', label: 'Mediano' }, { value: 'largo', label: 'Largo' }]}
                     value={p.horizonte} onChange={v => set('horizonte', v)} />
        </Campo>
        <Campo titulo="Objetivo">
          <Segmented options={[{ value: 'crecimiento', label: 'Crecimiento' }, { value: 'valor', label: 'Valoración' },
            { value: 'ingresos', label: 'Ingresos' }, { value: 'diversificacion', label: 'Diversificar' }]}
                     value={p.objetivo} onChange={v => set('objetivo', v)} />
        </Campo>
        <Campo titulo="Enfoque">
          <Segmented options={[{ value: 'fundamental', label: 'Fundamental' }, { value: 'tecnico', label: 'Técnico' }, { value: 'combinado', label: 'Combinado' }]}
                     value={p.enfoque} onChange={v => set('enfoque', v)} />
        </Campo>
        <Campo titulo="Tolerancia al riesgo">
          <Segmented options={[{ value: 'sin', label: 'Sin definir' }, { value: 'baja', label: 'Baja' }, { value: 'media', label: 'Media' }, { value: 'alta', label: 'Alta' }]}
                     value={p.tolerancia ?? 'sin'} onChange={v => set('tolerancia', v === 'sin' ? null : v as 'baja' | 'media' | 'alta')} />
        </Campo>
        <Campo titulo="Moneda de referencia">
          <Segmented options={[{ value: 'USD', label: 'USD' }, { value: 'ARS', label: 'ARS' }]} value={p.moneda} onChange={v => set('moneda', v)} />
        </Campo>
        <Campo titulo="Universo para explorar">
          <Segmented options={[{ value: 'catalogo', label: 'Todo el catálogo' }, { value: 'watchlist', label: 'Watchlist' }, { value: 'cartera', label: 'Mi cartera' }]}
                     value={p.universo} onChange={v => set('universo', v)} />
        </Campo>
        <Campo titulo="Excluir sectores (separados por coma)">
          <input value={(p.excluir.sectores ?? []).join(', ')}
                 onChange={e => set('excluir', { ...p.excluir, sectores: e.target.value.split(',').map(x => x.trim()).filter(Boolean) })}
                 className="h-11 px-3 rounded-xl bg-app-surface-2 border border-app-border text-body text-app-text" />
        </Campo>
        <Campo titulo="Excluir tickers (separados por coma)">
          <input value={(p.excluir.tickers ?? []).join(', ')}
                 onChange={e => set('excluir', { ...p.excluir, tickers: e.target.value.split(',').map(x => x.trim().toUpperCase()).filter(Boolean) })}
                 className="h-11 px-3 rounded-xl bg-app-surface-2 border border-app-border text-body text-app-text" />
        </Campo>
        <div>
          <div className="flex items-center justify-between">
            <span className="text-label font-bold uppercase text-app-text-faint flex items-center gap-1">
              Pesos <InfoTooltip term="decisiones_pesos" label="" />
            </span>
            <label className="flex items-center gap-1.5 text-caption text-app-text">
              <input type="checkbox" checked={pesosPropios} onChange={e => { setPesosPropios(e.target.checked); set('pesos', e.target.checked ? { ...tabla } : null) }} />
              Usar los míos
            </label>
          </div>
          <div className="grid grid-cols-5 gap-1.5 mt-1.5">
            {DIMS.map(d => (
              <label key={d.clave} className="flex flex-col items-center gap-1">
                <span className="text-label text-app-text-dim truncate w-full text-center">{d.nombre}</span>
                <input inputMode="numeric" disabled={!pesosPropios} value={pesos[d.clave] ?? 0}
                       onChange={e => set('pesos', { ...pesos, [d.clave]: Math.min(100, Number(e.target.value.replace(/\D/g, '') || 0)) })}
                       className="w-full h-10 text-center rounded-lg bg-app-surface-2 border border-app-border text-body text-app-text disabled:opacity-60" />
              </label>
            ))}
          </div>
          <p className="text-label text-app-text-faint mt-1">
            Los pesos por defecto dependen del enfoque y el horizonte. Son una decisión de diseño, no una verdad financiera.
          </p>
        </div>
        {guardar.error && <ErrorBanner error={parseApiError(guardar.error)} />}
        <Button onClick={() => guardar.mutate()} loading={guardar.isPending}>Guardar preferencias</Button>
      </div>
    </Modal>
  )
}

function Campo({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-label font-bold uppercase text-app-text-faint">{titulo}</span>
      {children}
    </div>
  )
}
