import { useRef, useState } from 'react'
import type { CarteraInfo } from '../../api'

const CARD_WIDTH = 132
const CARD_GAP = 10

export default function CarterasScroll({
  carteras,
  seleccionada,
  onSelect,
}: {
  carteras: CarteraInfo[]
  seleccionada: string | null
  onSelect: (nombre: string) => void
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [activeIndex, setActiveIndex] = useState(0)

  if (carteras.length === 0) return null

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const idx = Math.round(el.scrollLeft / (CARD_WIDTH + CARD_GAP))
    setActiveIndex(Math.max(0, Math.min(idx, carteras.length - 1)))
  }

  return (
    <div>
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex gap-2.5 overflow-x-auto no-scrollbar pb-1 -mx-0.5 px-0.5 snap-x snap-mandatory"
      >
        {carteras.map(c => (
          <button
            key={c.nombre}
            onClick={() => onSelect(c.nombre)}
            className={`shrink-0 w-[132px] text-left rounded-[14px] p-3 border transition-colors snap-center ${
              seleccionada === c.nombre ? 'bg-app-gold-soft border-app-gold/40' : 'bg-app-surface border-app-border'
            }`}
          >
            <div className="text-caption font-bold text-app-text-dim mb-1.5 truncate">{c.nombre}</div>
            <div className="font-mono text-label text-app-text-dim tabular-nums">
              {c.ultimo_sync ? `sync ${new Date(c.ultimo_sync).toLocaleDateString('es-AR')}` : 'sin sync'}
            </div>
          </button>
        ))}
      </div>
      {carteras.length > 1 && (
        <div className="flex items-center justify-center gap-1.5 mt-2">
          {carteras.map((c, i) => (
            <span
              key={c.nombre}
              className={`h-1.5 rounded-full transition-all ${
                i === activeIndex ? 'w-4 bg-app-gold' : 'w-1.5 bg-app-border'
              }`}
            />
          ))}
        </div>
      )}
    </div>
  )
}
