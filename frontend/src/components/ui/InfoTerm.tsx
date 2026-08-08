import { useState } from 'react'
import Modal from './Modal'
import { Icon } from '../icons/Icons'
import { GLOSARIO, type GlosarioKey } from '../../data/glosario'

export default function InfoTerm({ term, label, className = '' }: { term: GlosarioKey; label?: string; className?: string }) {
  const [open, setOpen] = useState(false)
  const entry = GLOSARIO[term]
  return (
    <span className={`inline-flex items-center gap-1 ${className}`}>
      {label ?? entry.titulo}
      <button
        type="button"
        aria-label={`Qué significa ${entry.titulo}`}
        onClick={e => {
          e.stopPropagation()
          setOpen(true)
        }}
        className="text-app-text-faint p-1.5 -m-1.5 shrink-0"
      >
        <Icon name="info" className="w-3.5 h-3.5" />
      </button>
      <Modal open={open} onClose={() => setOpen(false)} title={entry.titulo}>
        <p className="text-[13px] text-app-text-dim leading-relaxed">{entry.texto}</p>
      </Modal>
    </span>
  )
}
