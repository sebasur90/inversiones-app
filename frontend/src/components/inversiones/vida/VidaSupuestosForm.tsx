import { useState } from 'react'
import Segmented from '../../ui/Segmented'
import type { SupuestosVidaIn } from '../../../api'
import FormHelp from '../../../help/components/FormHelp'

const NUM_COMPLETO = /^-?\d+(\.\d+)?$/
const HORIZONTES_ANIOS: number[] = [5, 10, 20, 30]

interface CampoNumericoProps {
  valor: number | null
  onCommit: (n: number | null) => void
  placeholder?: string
  permitirNegativo?: boolean
  className?: string
}

/** Input de texto con draft crudo (permite tipear "-" o borrar antes de un dígito completo),
 * el mismo patrón que `VariacionPorInstrumento` en `EscenarioConfigPanel.tsx`. */
export function CampoNumerico({ valor, onCommit, placeholder, className = '' }: CampoNumericoProps) {
  const [draft, setDraft] = useState<string | null>(null)

  const mostrado = draft ?? (valor !== null && valor !== undefined ? String(valor) : '')

  const onInput = (raw: string) => {
    setDraft(raw)
    const t = raw.trim()
    if (t === '') onCommit(null)
    else if (NUM_COMPLETO.test(t)) onCommit(parseFloat(t))
  }

  const onBlur = () => {
    const t = (draft ?? '').trim()
    if (t !== '' && NUM_COMPLETO.test(t)) onCommit(parseFloat(t))
    else if (t === '') onCommit(null)
    setDraft(null)
  }

  return (
    <input
      type="text"
      inputMode="decimal"
      value={mostrado}
      placeholder={placeholder}
      onChange={e => onInput(e.target.value)}
      onBlur={onBlur}
      className={`w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-accent/60 tabular-nums ${className}`}
    />
  )
}

interface VidaSupuestosFormProps {
  supuestos: SupuestosVidaIn
  onChange: <K extends keyof SupuestosVidaIn>(campo: K, valor: SupuestosVidaIn[K]) => void
  onRestaurarDefaults?: () => void
  hayDefaults: boolean
}

export default function VidaSupuestosForm({
  supuestos, onChange, onRestaurarDefaults, hayDefaults,
}: VidaSupuestosFormProps) {
  const anios = Math.max(1, Math.round(supuestos.horizonte_meses / 12))

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <FormHelp term="vida_patrimonio_inicial" label="Patrimonio inicial" />
        <FormHelp term="vida_aporte_mensual" label="Aporte mensual" />
      </div>
      <div className="grid grid-cols-2 gap-3 -mt-2">
        <CampoNumerico
          valor={supuestos.patrimonio_inicial}
          onCommit={n => onChange('patrimonio_inicial', Math.max(0, n ?? 0))}
          placeholder="0"
        />
        <CampoNumerico
          valor={supuestos.aporte_mensual}
          onCommit={n => onChange('aporte_mensual', Math.max(0, n ?? 0))}
          placeholder="0"
        />
      </div>

      {onRestaurarDefaults && hayDefaults && (
        <button
          onClick={onRestaurarDefaults}
          className="text-label font-semibold text-app-accent"
        >
          Volver a mis datos
        </button>
      )}

      <div>
        <FormHelp term="vida_crecimiento_anual" label="Crecimiento esperado anual" fieldKey="crecimiento_anual_pct" />
        <div className="flex items-center gap-2 -mt-2">
          <CampoNumerico
            valor={supuestos.crecimiento_anual_pct}
            onCommit={n => onChange('crecimiento_anual_pct', n ?? 0)}
            placeholder="0"
            className="max-w-[7rem]"
          />
          <span className="text-xs text-app-text-dim">% anual</span>
        </div>
      </div>

      <div>
        <FormHelp term="vida_inflacion" label="Inflación esperada anual (opcional)" fieldKey="inflacion_anual_pct" />
        <div className="flex items-center gap-2 -mt-2">
          <CampoNumerico
            valor={supuestos.inflacion_anual_pct ?? null}
            onCommit={n => onChange('inflacion_anual_pct', n)}
            placeholder="sin cargar"
            className="max-w-[7rem]"
          />
          <span className="text-xs text-app-text-dim">% anual, "en plata de hoy"</span>
        </div>
      </div>

      <div>
        <FormHelp term="vida_horizonte" label="Horizonte" />
        <div className="-mt-2">
          <Segmented<string>
            options={HORIZONTES_ANIOS.map(a => ({ value: String(a), label: `${a} años` }))}
            value={String(anios)}
            onChange={v => onChange('horizonte_meses', Number(v) * 12)}
          />
        </div>
      </div>

      <div>
        <FormHelp term="vida_moneda" label="Moneda" />
        <div className="-mt-2">
          <Segmented<'USD' | 'ARS'>
            options={[{ value: 'USD', label: 'USD' }, { value: 'ARS', label: 'ARS' }]}
            value={supuestos.moneda}
            onChange={v => onChange('moneda', v)}
          />
        </div>
        <div className="text-label text-app-text-faint mt-1.5">
          Es sólo una unidad de cuenta: no convierte nada. Cargá todos los montos en la misma moneda.
        </div>
      </div>
    </div>
  )
}
