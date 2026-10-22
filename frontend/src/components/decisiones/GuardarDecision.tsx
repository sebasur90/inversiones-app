import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { crearDecision, type CrearDecisionIn } from '../../api'
import { qk } from '../../api/queryClient'
import { parseApiError } from '../../help/errors/apiErrors'
import ErrorBanner from '../../help/components/ErrorBanner'
import Button from '../ui/Button'
import Modal from '../ui/Modal'

export const ACCIONES_OPORTUNIDAD: { value: string; label: string }[] = [
  { value: 'profundizar', label: 'Profundizar el análisis' },
  { value: 'esperar_tecnica', label: 'Esperar una condición técnica' },
  { value: 'esperar_valoracion', label: 'Esperar un mejor precio' },
  { value: 'entrar_ahora', label: 'Entrar ahora' },
  { value: 'escalonada', label: 'Entrada escalonada' },
  { value: 'elegir_alternativa', label: 'Elegir una alternativa' },
  { value: 'descartar', label: 'Descartar por ahora' },
  { value: 'ninguna', label: 'Sólo registrar el análisis' },
]

export const ACCIONES_POSICION: { value: string; label: string }[] = [
  { value: 'mantener', label: 'Mantener' },
  { value: 'aumentar', label: 'Aumentar' },
  { value: 'reducir', label: 'Reducir' },
  { value: 'salir', label: 'Salir' },
  { value: 'reasignar', label: 'Reasignar a una alternativa' },
  { value: 'ninguna', label: 'Sólo registrar el análisis' },
]

export const TEXTO_ACCION: Record<string, string> = Object.fromEntries(
  [...ACCIONES_OPORTUNIDAD, ...ACCIONES_POSICION].map(a => [a.value, a.label]),
)

/**
 * Guardar una decisión. El servidor vuelve a correr el análisis y congela su resultado: acá sólo se elige qué
 * se decidió, la nota y cuándo revisarlo. "La llevé a cabo" lo marca el usuario: una simulación no se asume.
 */
export default function GuardarDecision({ abierto, onClose, modo, ticker, cartera, con, alternativas, accionInicial }: {
  abierto: boolean; onClose: () => void; modo: 'oportunidad' | 'posicion'; ticker: string; cartera: string | null
  con: string[]; alternativas: string[]; accionInicial?: string
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const acciones = modo === 'posicion' ? ACCIONES_POSICION : ACCIONES_OPORTUNIDAD
  const [accion, setAccion] = useState(accionInicial ?? acciones[0].value)
  const [nota, setNota] = useState('')
  const [dias, setDias] = useState('')
  const [ejecutada, setEjecutada] = useState(false)
  const [alternativa, setAlternativa] = useState(alternativas[0] ?? '')
  const pideAlternativa = accion === 'elegir_alternativa' || accion === 'reasignar'
  const guardar = useMutation({
    mutationFn: () => {
      const body: CrearDecisionIn = {
        modo, ticker, accion_elegida: accion, cartera, con, nota: nota.trim() || null, ejecutada,
        revisar_en_dias: dias ? Number(dias) : null, alternativa_elegida: pideAlternativa ? alternativa : null,
      }
      return crearDecision(body)
    },
    onSuccess: d => {
      void queryClient.invalidateQueries({ queryKey: qk.de('decisiones') })
      void queryClient.invalidateQueries({ queryKey: qk.de('decisiones-pendientes') })
      onClose()
      navigate(`/decisiones/${d.id}`)
    },
  })

  return (
    <Modal open={abierto} onClose={onClose} title={`Guardar decisión sobre ${ticker}`}>
      <div className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-label font-bold uppercase text-app-text-faint">Qué decidiste</span>
          <select value={accion} onChange={e => setAccion(e.target.value)}
                  className="h-11 px-3 rounded-xl bg-app-surface-2 border border-app-border text-body text-app-text">
            {acciones.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
          </select>
        </label>
        {pideAlternativa && (
          <label className="flex flex-col gap-1">
            <span className="text-label font-bold uppercase text-app-text-faint">Alternativa</span>
            {alternativas.length ? (
              <select value={alternativa} onChange={e => setAlternativa(e.target.value)}
                      className="h-11 px-3 rounded-xl bg-app-surface-2 border border-app-border text-body text-app-text">
                {alternativas.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
            ) : <span className="text-caption text-app-text-dim">No hay alternativas analizadas.</span>}
          </label>
        )}
        <label className="flex flex-col gap-1">
          <span className="text-label font-bold uppercase text-app-text-faint">Tu tesis o motivo (opcional)</span>
          <textarea value={nota} onChange={e => setNota(e.target.value)} maxLength={2000} rows={3}
                    className="px-3 py-2 rounded-xl bg-app-surface-2 border border-app-border text-body text-app-text" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-label font-bold uppercase text-app-text-faint">Revisar en (días)</span>
          <input inputMode="numeric" value={dias} onChange={e => setDias(e.target.value.replace(/\D/g, ''))}
                 placeholder="Por defecto según tu horizonte (30 / 90 / 180)"
                 className="h-11 px-3 rounded-xl bg-app-surface-2 border border-app-border text-body text-app-text" />
        </label>
        <label className="flex items-center gap-2 text-caption text-app-text">
          <input type="checkbox" checked={ejecutada} onChange={e => setEjecutada(e.target.checked)} />
          Ya la llevé a cabo (la registré en la planilla)
        </label>
        <p className="text-label text-app-text-faint">
          Se guarda lo que la app concluye hoy, con la fecha de los datos y la versión de las reglas. No se registra ningún movimiento.
        </p>
        {guardar.error && <ErrorBanner error={parseApiError(guardar.error)} />}
        <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={pideAlternativa && !alternativa}>
          Guardar decisión
        </Button>
      </div>
    </Modal>
  )
}
