import {
  INDICADORES_UI, MAX_INDICADORES, claveIndicador, colorIndicador, type IndicadorActivo,
} from './indicadoresConfig'
import InfoTooltip from '../../help/components/InfoTooltip'
import type { HelpKey } from '../../help/content/index'
import { Icon } from '../icons/Icons'

/** Chips por tipo de indicador. Tocar un chip apagado agrega una instancia con los parámetros por
 * defecto; tocarlo prendido saca todas las de ese tipo. Debajo del chip va una fila por instancia
 * (con sus inputs, su color y una cruz para sacarla) y un "+ otra" para sumar una segunda del
 * mismo tipo con otros parámetros (dos SMA de 50 y 200, por ejemplo). Los tipos sin parámetros
 * (OBV) no se duplican: serían la misma línea dos veces.
 *
 * Re-tildar un indicador ya pedido no dispara request nuevo: la clave de react-query en
 * `AnalisisTecnico` ya incluye la lista ordenada y sin repetidos de claves. */
export default function SelectorIndicadores({
  activos, onAgregar, onQuitar, onQuitarTipo, onCambiarParam, tieneVolumen,
}: {
  activos: IndicadorActivo[]
  onAgregar: (tipo: string) => void
  onQuitar: (id: number) => void
  onQuitarTipo: (tipo: string) => void
  onCambiarParam: (id: number, nombreParam: string, valor: number) => void
  tieneVolumen: boolean
}) {
  const lleno = activos.length >= MAX_INDICADORES
  return (
    <div className="flex flex-wrap gap-2.5">
      {INDICADORES_UI.map(espec => {
        const instancias = activos.filter(a => a.tipo === espec.tipo)
        const activo = instancias.length > 0
        const deshabilitado = !!espec.necesitaVolumen && !tieneVolumen
        const sinCupo = !activo && lleno
        return (
          <div key={espec.tipo} className={`flex flex-col gap-1 ${deshabilitado ? 'opacity-40' : ''}`}>
            <button
              disabled={deshabilitado || sinCupo}
              onClick={() => (activo ? onQuitarTipo(espec.tipo) : onAgregar(espec.tipo))}
              title={
                deshabilitado ? 'Este ticker no tiene datos de volumen'
                : sinCupo ? `Máximo ${MAX_INDICADORES} indicadores a la vez`
                : undefined
              }
              className={`font-semibold text-caption px-2.5 py-1.5 rounded-[10px] border transition-colors whitespace-nowrap disabled:opacity-60 ${
                activo ? 'border-app-accent text-app-accent bg-app-accent-soft' : 'border-app-border text-app-text-dim bg-app-surface'
              }`}
            >
              {espec.label}
              {instancias.length > 1 && <span className="ml-1 text-label opacity-80">×{instancias.length}</span>}
            </button>
            {activo && espec.params.length > 0 && instancias.map(a => (
              <div key={a.id} className="flex flex-wrap items-center gap-1.5 pl-0.5">
                <span
                  className="w-2 h-2 rounded-full shrink-0" style={{ background: colorIndicador(activos, a) }}
                  title={claveIndicador(a.tipo, a.params)}
                />
                {espec.params.map(p => (
                  <label key={p.nombre} className="flex items-center gap-1 text-label text-app-text-dim">
                    {p.label}
                    <input
                      type="number" min={p.min} max={p.max} step={p.step ?? 1}
                      value={a.params[p.nombre] ?? p.default}
                      onChange={e => onCambiarParam(a.id, p.nombre, Number(e.target.value))}
                      className="w-14 bg-app-surface-2 border border-app-border rounded px-1 py-0.5 font-mono text-label text-app-text"
                    />
                  </label>
                ))}
                {instancias.length > 1 && (
                  <button
                    type="button" onClick={() => onQuitar(a.id)}
                    aria-label={`Quitar ${claveIndicador(a.tipo, a.params)}`} title="Quitar esta instancia"
                    className="text-app-text-faint hover:text-app-text w-4 h-4 flex items-center justify-center"
                  >
                    <Icon name="close" className="w-3 h-3" />
                  </button>
                )}
              </div>
            ))}
            {activo && espec.params.length > 0 && (
              <button
                type="button" onClick={() => onAgregar(espec.tipo)} disabled={lleno}
                title={lleno ? `Máximo ${MAX_INDICADORES} indicadores a la vez` : `Agregar otro ${espec.label} con otros parámetros`}
                className="self-start pl-0.5 text-label text-app-text-faint underline disabled:no-underline disabled:opacity-50"
              >
                + otra
              </button>
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
