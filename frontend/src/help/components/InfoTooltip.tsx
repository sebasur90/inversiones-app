import { useState } from 'react'
import Modal from '../../components/ui/Modal'
import { Icon } from '../../components/icons/Icons'
import { HELP, type HelpKey } from '../content/index'

export default function InfoTooltip({ term, label, className = '' }: { term: HelpKey; label?: string; className?: string }) {
  const [open, setOpen] = useState(false)
  const entry = HELP[term]

  if (!entry) {
    console.warn(`InfoTooltip: no HelpContent found for term "${term}"`)
    return <span className={className}>{label ?? term}</span>
  }

  return (
    <span className={`inline-flex items-center gap-1 ${className}`}>
      {label ?? entry.title}
      <button
        type="button"
        aria-label={`Qué significa ${entry.title}`}
        onClick={e => {
          e.stopPropagation()
          setOpen(true)
        }}
        className="text-app-text-faint p-1.5 -m-1.5 shrink-0"
      >
        <Icon name="info" className="w-3.5 h-3.5" />
      </button>
      <Modal open={open} onClose={() => setOpen(false)} title={entry.title}>
        <div className="text-[13px] text-app-text-dim leading-relaxed space-y-3">
          {entry.shortDescription && <p>{entry.shortDescription}</p>}
          {entry.whyItMatters && (
            <div>
              <div className="font-semibold text-app-text mb-1">¿Por qué importa?</div>
              <p>{entry.whyItMatters}</p>
            </div>
          )}
          {entry.howItIsCalculated && (
            <div>
              <div className="font-semibold text-app-text mb-1">Cómo se calcula</div>
              <p>{entry.howItIsCalculated}</p>
            </div>
          )}
          {entry.howToInterpret && (
            <div>
              <div className="font-semibold text-app-text mb-1">Cómo interpretarlo</div>
              <p>{entry.howToInterpret}</p>
            </div>
          )}
          {entry.example && (
            <div>
              <div className="font-semibold text-app-text mb-1">Ejemplo</div>
              <p>{entry.example}</p>
            </div>
          )}
          {entry.limitations && (
            <div>
              <div className="font-semibold text-app-text mb-1">Limitaciones</div>
              <p>{entry.limitations}</p>
            </div>
          )}
          {entry.relatedTerms && entry.relatedTerms.length > 0 && (
            <div>
              <div className="font-semibold text-app-text mb-1">Ver también</div>
              <div className="flex flex-wrap gap-2">
                {entry.relatedTerms.map(relatedKey => {
                  const relatedEntry = HELP[relatedKey as HelpKey]
                  return relatedEntry ? (
                    <button
                      key={relatedKey}
                      onClick={() => {
                        setOpen(false)
                        // No-op por ahora: la navegación entre términos sería más compleja
                        // Este campo sirve principalmente para documentación
                      }}
                      className="text-xs px-2 py-1 rounded-md bg-app-surface border border-app-border text-app-text-secondary hover:text-app-text"
                    >
                      {relatedEntry.title}
                    </button>
                  ) : null
                })}
              </div>
            </div>
          )}
        </div>
      </Modal>
    </span>
  )
}
