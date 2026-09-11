import { INDICADORES_UI } from './indicadoresConfig'
import InfoTooltip from '../../help/components/InfoTooltip'
import type { HelpKey } from '../../help/content/index'

/** Chips activables/desactivables por tipo de indicador, con inputs numéricos inline para sus
 * parámetros cuando está activo. Re-tildar un indicador ya pedido no dispara request nuevo: la
 * clave de react-query en `AnalisisTecnico` ya incluye la lista ordenada de claves. */
export default function SelectorIndicadores({
  activos, onToggle, onCambiarParam, tieneVolumen,
}: {
  activos: Record<string, Record<string, number>>
  onToggle: (tipo: string) => void
  onCambiarParam: (tipo: string, nombreParam: string, valor: number) => void
  tieneVolumen: boolean
}) {
  return (
    <div className="flex flex-wrap gap-2.5">
      {INDICADORES_UI.map(espec => {
        const activo = espec.tipo in activos
        const deshabilitado = !!espec.necesitaVolumen && !tieneVolumen
        return (
          <div key={espec.tipo} className={`flex flex-col gap-1 ${deshabilitado ? 'opacity-40' : ''}`}>
            <button
              disabled={deshabilitado}
              onClick={() => onToggle(espec.tipo)}
              title={deshabilitado ? 'Este ticker no tiene datos de volumen' : undefined}
              className={`font-semibold text-caption px-2.5 py-1.5 rounded-[10px] border transition-colors whitespace-nowrap ${
                activo ? 'border-app-accent text-app-accent bg-app-accent-soft' : 'border-app-border text-app-text-dim bg-app-surface'
              }`}
            >
              {espec.label}
            </button>
            {activo && espec.params.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pl-0.5">
                {espec.params.map(p => (
                  <label key={p.nombre} className="flex items-center gap-1 text-label text-app-text-dim">
                    {p.label}
                    <input
                      type="number" min={p.min} max={p.max} step={p.step ?? 1}
                      value={activos[espec.tipo]?.[p.nombre] ?? p.default}
                      onChange={e => onCambiarParam(espec.tipo, p.nombre, Number(e.target.value))}
                      className="w-14 bg-app-surface-2 border border-app-border rounded px-1 py-0.5 font-mono text-label text-app-text"
                    />
                  </label>
                ))}
              </div>
            )}
            {activo && espec.ayuda && (
              <div className="pl-0.5 text-label text-app-text-faint">
                <InfoTooltip term={espec.ayuda as HelpKey} />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
