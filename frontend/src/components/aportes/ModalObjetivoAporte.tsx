import { useState } from 'react'
import type { AporteObjetivo } from '../../api'
import Modal from '../ui/Modal'
import Button from '../ui/Button'
import { formatUSD } from '../../utils'
import { mesCorto } from './comun'

const ORIGEN_TEXTO: Record<string, string> = {
  promedio_12: 'tu promedio de los últimos 12 meses',
  promedio_6: 'tu promedio de los últimos 6 meses',
  promedio_3: 'tu promedio de los últimos 3 meses',
  promedio_historico: 'tu promedio histórico',
}

/** Alta/edición del objetivo mensual. Precarga el ritmo que el usuario ya demostró tener: la idea
 *  es que la meta salga de su propia historia y no de una cifra arbitraria.
 *
 *  Se monta sólo mientras está abierto (ver `AportesProgreso`): así el formulario se siembra de
 *  nuevo en cada apertura y no arrastra el monto de un objetivo que ya se borró. */
export default function ModalObjetivoAporte({
  objetivo,
  guardando,
  onGuardar,
  onEliminar,
  onCerrar,
}: {
  objetivo: AporteObjetivo
  guardando: boolean
  onGuardar: (monto: number, retroactivo: boolean) => void
  onEliminar: () => void
  onCerrar: () => void
}) {
  const inicial = objetivo.monto_usd ?? objetivo.sugerido_usd ?? 100
  const [monto, setMonto] = useState(String(inicial))
  const [retroactivo, setRetroactivo] = useState(objetivo.retroactivo)

  const valor = Number(monto.replace(',', '.'))
  const valido = Number.isFinite(valor) && valor > 0

  return (
    <Modal open onClose={onCerrar} title={objetivo.configurado ? 'Editar objetivo' : 'Definir objetivo mensual'}>
      <label className="block text-caption text-app-text-dim mb-1.5" htmlFor="objetivo-monto">
        ¿Cuánto querés aportar por mes?
      </label>
      <div className="flex items-center gap-2">
        <span className="text-body font-bold text-app-text-dim">USD</span>
        <input
          id="objetivo-monto"
          type="number"
          inputMode="decimal"
          min={1}
          step={10}
          value={monto}
          onChange={e => setMonto(e.target.value)}
          className="flex-1 h-11 px-3 rounded-2xl bg-app-surface-2 border border-app-border text-app-text font-mono text-body tabular-nums"
        />
      </div>

      {objetivo.sugerido_usd != null && !objetivo.configurado && (
        <button
          onClick={() => setMonto(String(objetivo.sugerido_usd))}
          className="mt-2 text-label font-semibold text-app-accent text-left"
        >
          Usar {formatUSD(objetivo.sugerido_usd)}
          {objetivo.sugerido_origen && ORIGEN_TEXTO[objetivo.sugerido_origen] && (
            <span className="text-app-text-faint font-normal"> · {ORIGEN_TEXTO[objetivo.sugerido_origen]}</span>
          )}
        </button>
      )}

      <label className="flex items-start gap-2 mt-4 text-caption text-app-text-dim">
        <input
          type="checkbox"
          checked={retroactivo}
          onChange={e => setRetroactivo(e.target.checked)}
          className="mt-0.5"
        />
        <span>
          Aplicarlo también a mi historial
          <span className="block text-label text-app-text-faint">
            Sin esto, el cumplimiento se mide desde{' '}
            {objetivo.fijado_en ? mesCorto(objetivo.fijado_en) : 'este mes'}: los meses anteriores
            no se dan por incumplidos, porque el objetivo todavía no existía.
          </span>
        </span>
      </label>

      <div className="flex gap-2 mt-5">
        <Button
          onClick={() => valido && onGuardar(valor, retroactivo)}
          disabled={!valido}
          loading={guardando}
          className="flex-1"
        >
          Guardar
        </Button>
        {objetivo.configurado && (
          <Button variant="danger" onClick={onEliminar} disabled={guardando}>
            Quitar
          </Button>
        )}
      </div>
    </Modal>
  )
}
