import InfoTooltip from './InfoTooltip'
import type { HelpKey } from '../content/index'
import { ESCENARIO_PARAM_LIMITS } from '../errors/escenarioLimits'

interface FormHelpProps {
  term: HelpKey
  label: string
  fieldKey?: string
  className?: string
}

export default function FormHelp({ term, label, fieldKey, className = '' }: FormHelpProps) {
  const limits = fieldKey ? ESCENARIO_PARAM_LIMITS[fieldKey] : null

  return (
    <div className={className}>
      <label className="block text-xs font-semibold text-app-text mb-2">
        <InfoTooltip term={term} label={label} />
      </label>
      {limits && (
        <div className="text-[11px] text-app-text-dim mb-2 px-2 py-1.5 bg-app-surface/50 rounded border border-app-border/30">
          {limits.min !== undefined && limits.max !== undefined
            ? `Rango: ${limits.min} a ${limits.max} ${limits.unit}`
            : limits.min !== undefined
              ? `Mínimo: ${limits.min} ${limits.unit}`
              : `Máximo: ${limits.max} ${limits.unit}`}
        </div>
      )}
    </div>
  )
}
