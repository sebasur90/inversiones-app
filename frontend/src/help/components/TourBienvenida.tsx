import { useState } from 'react'
import Modal from '../../components/ui/Modal'
import Button from '../../components/ui/Button'
import { useInversionesContext } from '../../context/InversionesContext'
import { TOUR_BIENVENIDA } from '../content/tour'

/** Sobre `ui/Modal`: hereda el foco atrapado y el cierre con Escape/click afuera, que acá
 *  también cuenta como "saltear". */
export default function TourBienvenida() {
  const { tourAbierto, cerrarTour } = useInversionesContext()
  const [paso, setPaso] = useState(0)

  const total = TOUR_BIENVENIDA.length
  const esUltimo = paso === total - 1
  const actual = TOUR_BIENVENIDA[paso]

  function cerrarYReiniciar() {
    cerrarTour()
    // Con un pequeño delay para no ver el salto de paso mientras el modal todavía se cierra.
    setTimeout(() => setPaso(0), 300)
  }

  return (
    <Modal open={tourAbierto} onClose={cerrarYReiniciar} title="Bienvenida">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-1.5" role="tablist" aria-label="Progreso del tour">
          {TOUR_BIENVENIDA.map((_, i) => (
            <span
              key={i}
              className={`h-1.5 rounded-full transition-all ${i === paso ? 'w-5 bg-app-accent' : 'w-1.5 bg-app-border'}`}
            />
          ))}
        </div>
        <button type="button" onClick={cerrarYReiniciar} className="text-label font-semibold text-app-text-dim">
          Saltear
        </button>
      </div>

      <div className="text-center py-2 mb-2">
        <div className="text-metric-lg mb-3" aria-hidden="true">{actual.emoji}</div>
        <h3 className="font-display text-title font-semibold text-app-text mb-2">{actual.titulo}</h3>
        <p className="text-body text-app-text-dim leading-relaxed">{actual.texto}</p>
      </div>

      <div className="flex gap-2 mt-5">
        {paso > 0 && (
          <Button variant="outline" onClick={() => setPaso(p => p - 1)} className="flex-1">
            Atrás
          </Button>
        )}
        <Button onClick={() => (esUltimo ? cerrarYReiniciar() : setPaso(p => p + 1))} className="flex-1">
          {esUltimo ? 'Empezar' : 'Siguiente'}
        </Button>
      </div>
    </Modal>
  )
}
