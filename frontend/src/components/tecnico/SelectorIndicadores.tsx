import {
  INDICADORES_UI, MAX_INDICADORES, claveIndicador, colorIndicador,
  type EspecIndicadorUi, type IndicadorActivo,
} from './indicadoresConfig'
import InfoTooltip from '../../help/components/InfoTooltip'
import type { HelpKey } from '../../help/content/index'
import { Icon } from '../icons/Icons'

const GRUPOS: { titulo: string; incluye: (e: EspecIndicadorUi) => boolean }[] = [
  { titulo: 'Sobre el precio', incluye: e => e.destino === 'precio' },
  { titulo: 'Paneles debajo del gráfico', incluye: e => e.destino !== 'precio' },
]

/** Lista de indicadores, agrupada por dónde se dibujan, con una línea que dice qué mide cada uno.
 * El interruptor de un indicador apagado agrega una instancia con los parámetros por defecto;
 * prendido, saca todas las de ese tipo. Prendido, debajo va una fila por instancia (con sus
 * inputs, su color y una cruz para sacarla) y un "+ otra" para sumar una segunda del mismo tipo
 * con otros parámetros (dos SMA de 50 y 200, por ejemplo). Los tipos sin parámetros (OBV) no se
 * duplican: serían la misma línea dos veces.
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
    <div className="flex flex-col gap-4">
      <p className={`text-label ${lleno ? 'text-app-warn' : 'text-app-text-dim'}`}>
        {activos.length} de {MAX_INDICADORES} en uso
        {lleno && ': sacá uno para sumar otro.'}
      </p>
      {GRUPOS.map(grupo => (
        <section key={grupo.titulo} className="flex flex-col">
          <h3 className="text-label font-bold uppercase tracking-wide text-app-text-dim pb-1">{grupo.titulo}</h3>
          {INDICADORES_UI.filter(grupo.incluye).map(espec => (
            <FilaIndicador
              key={espec.tipo} espec={espec} activos={activos} lleno={lleno} tieneVolumen={tieneVolumen}
              onAgregar={onAgregar} onQuitar={onQuitar} onQuitarTipo={onQuitarTipo} onCambiarParam={onCambiarParam}
            />
          ))}
        </section>
      ))}
    </div>
  )
}

function FilaIndicador({
  espec, activos, lleno, tieneVolumen, onAgregar, onQuitar, onQuitarTipo, onCambiarParam,
}: {
  espec: EspecIndicadorUi
  activos: IndicadorActivo[]
  lleno: boolean
  tieneVolumen: boolean
  onAgregar: (tipo: string) => void
  onQuitar: (id: number) => void
  onQuitarTipo: (tipo: string) => void
  onCambiarParam: (id: number, nombreParam: string, valor: number) => void
}) {
  const instancias = activos.filter(a => a.tipo === espec.tipo)
  const activo = instancias.length > 0
  const sinVolumen = !!espec.necesitaVolumen && !tieneVolumen
  const sinCupo = !activo && lleno
  const motivo = sinVolumen ? 'Este ticker no tiene datos de volumen.' : sinCupo ? `Máximo ${MAX_INDICADORES} a la vez.` : null

  return (
    <div className={`flex flex-col gap-2 py-2.5 border-b border-app-border ${sinVolumen ? 'opacity-50' : ''}`}>
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1 text-body font-semibold text-app-text">
            {espec.label}
            {instancias.length > 1 && <span className="text-label text-app-text-dim">×{instancias.length}</span>}
            {espec.ayuda && <InfoTooltip term={espec.ayuda as HelpKey} />}
          </div>
          <div className="text-label text-app-text-dim">{motivo ?? espec.descripcion}</div>
        </div>
        <button
          type="button" role="switch" aria-checked={activo} aria-label={espec.label}
          disabled={sinVolumen || sinCupo}
          onClick={() => (activo ? onQuitarTipo(espec.tipo) : onAgregar(espec.tipo))}
          className={`shrink-0 w-12 h-7 rounded-full p-[3px] flex transition-colors disabled:opacity-50 ${
            activo ? 'bg-app-accent justify-end' : 'bg-app-surface-2 border border-app-border justify-start'
          }`}
        >
          <span className="w-[22px] h-[22px] rounded-full bg-white" />
        </button>
      </div>

      {activo && espec.params.length > 0 && (
        <div className="flex flex-col gap-1.5">
          {instancias.map(a => (
            <div key={a.id} className="flex flex-wrap items-center gap-2">
              <span
                className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: colorIndicador(activos, a) }}
                title={claveIndicador(a.tipo, a.params)}
              />
              {espec.params.map(p => (
                <label key={p.nombre} className="flex items-center gap-1 text-label text-app-text-dim">
                  {p.label}
                  <input
                    type="number" inputMode="decimal" min={p.min} max={p.max} step={p.step ?? 1}
                    value={a.params[p.nombre] ?? p.default}
                    onChange={e => onCambiarParam(a.id, p.nombre, Number(e.target.value))}
                    className="w-16 h-8 bg-app-bg border border-app-border rounded-lg px-2 font-mono text-caption text-app-text"
                  />
                </label>
              ))}
              {instancias.length > 1 && (
                <button
                  type="button" onClick={() => onQuitar(a.id)}
                  aria-label={`Quitar ${claveIndicador(a.tipo, a.params)}`} title="Quitar esta instancia"
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-app-text-faint hover:text-app-text"
                >
                  <Icon name="close" className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          ))}
          <button
            type="button" onClick={() => onAgregar(espec.tipo)} disabled={lleno}
            title={lleno ? `Máximo ${MAX_INDICADORES} indicadores a la vez` : `Agregar otro ${espec.label} con otros parámetros`}
            className="self-start h-8 px-2.5 rounded-lg border border-dashed border-app-border text-label font-semibold text-app-text-dim disabled:opacity-50"
          >
            + otra
          </button>
        </div>
      )}
    </div>
  )
}
