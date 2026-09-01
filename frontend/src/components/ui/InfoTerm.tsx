import { useState } from 'react'
import Modal from './Modal'
import { Icon } from '../icons/Icons'
import { HELP, type HelpKey } from '../../help/content/index'

export default function InfoTerm({ term, label, className = '' }: { term: HelpKey; label?: string; className?: string }) {
  const [open, setOpen] = useState(false)
  const entry = HELP[term]
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
        <p className="text-body text-app-text-dim leading-relaxed">{entry.shortDescription}</p>
      </Modal>
    </span>
  )
}
