import InfoTooltip from '../../help/components/InfoTooltip'
import { CUADRANTES, INFO_CUADRANTE } from './constantes'

/** Qué significa cada cuadrante, siempre a la vista junto al gráfico. */
export default function LeyendaCuadrantes() {
  return (
    <div className="grid grid-cols-2 gap-2">
      {CUADRANTES.map(c => {
        const info = INFO_CUADRANTE[c]
        return (
          <div key={c} className="rounded-xl border border-app-border bg-app-surface px-2.5 py-2">
            <div className="flex items-center gap-1.5 text-caption font-bold" style={{ color: info.color }}>
              <span aria-hidden="true" className="w-2 h-2 rounded-full" style={{ backgroundColor: info.color }} />
              <InfoTooltip term={info.termino} label={info.nombre} />
            </div>
            <div className="text-label text-app-text-dim mt-0.5">{info.frase}</div>
          </div>
        )
      })}
    </div>
  )
}
