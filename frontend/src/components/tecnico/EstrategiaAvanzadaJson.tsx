import type { EjecucionDsl, EstrategiaDsl, RiesgoDsl } from '../../api'
import Segmented from '../ui/Segmented'
import InfoTooltip from '../../help/components/InfoTooltip'

const RIESGO_CAMPOS = [
  ['stop_loss_pct', 'Stop loss %'],
  ['take_profit_pct', 'Take profit %'],
  ['trailing_stop_pct', 'Trailing stop %'],
  ['max_barras', 'Máx. barras en posición'],
] as const

/** Editor de una estrategia cuyas condiciones el editor visual **no** puede representar (`no`,
 * `entre`, `subiendo`, anidamiento). Muestra las condiciones como JSON de solo lectura y deja
 * editar sólo riesgo y ejecución — lo único que se puede tocar sin pérdida, y justo lo que uno
 * quiere retocar después de importar. Emite `{ ...dsl, riesgo, ejecucion }`: **nunca** reconstruye
 * `entrada` / `salida`.
 *
 * Limitación conocida (fuera de alcance): el Segmented de "Precio de ejecución" fija
 * `demora_barras` a 0/1, así que un DSL importado con `demora_barras: 3` se conserva sólo mientras
 * no toques ese control. */
export default function EstrategiaAvanzadaJson({
  dsl, onCambiar, onEditarIgual, erroresValidacion,
}: {
  dsl: EstrategiaDsl
  onCambiar: (dsl: EstrategiaDsl) => void
  onEditarIgual?: () => void
  erroresValidacion?: string[]
}) {
  const riesgo: RiesgoDsl = dsl.riesgo ?? { stop_loss_pct: null, take_profit_pct: null, trailing_stop_pct: null, max_barras: null }
  const ejecucion: EjecucionDsl = dsl.ejecucion ?? { lado: 'long', comision_pct: 0, precio_ejecucion: 'cierre', demora_barras: 0 }

  const emitirRiesgo = (parche: Partial<RiesgoDsl>) => onCambiar({ ...dsl, riesgo: { ...riesgo, ...parche } })
  const emitirEjecucion = (parche: Partial<EjecucionDsl>) => onCambiar({ ...dsl, ejecucion: { ...ejecucion, ...parche } })

  const condicionesJson = JSON.stringify(
    { indicadores: dsl.indicadores, entrada: dsl.entrada, salida: dsl.salida ?? null },
    null, 2,
  )

  return (
    <div className="flex flex-col gap-3">
      {erroresValidacion && erroresValidacion.length > 0 && (
        <div className="bg-app-coral-soft border border-app-coral/40 rounded-xl px-3 py-2 text-caption text-app-coral">
          {erroresValidacion.map((e, i) => <div key={i}>{e}</div>)}
        </div>
      )}

      <div className="bg-app-surface border border-app-border rounded-2xl p-3">
        <div className="font-semibold text-caption text-app-text mb-1">Condiciones (avanzadas)</div>
        <p className="text-label text-app-text-dim mb-2">
          Esta estrategia usa condiciones que el editor visual no puede representar (por ejemplo
          <span className="font-mono"> no</span>, <span className="font-mono">entre</span>,
          <span className="font-mono"> subiendo</span> o anidamiento). Se muestran como JSON de solo
          lectura. El backtest y el guardado funcionan normalmente; también podés editar el riesgo y
          la ejecución acá abajo.
        </p>
        <pre className="text-label font-mono text-app-text-dim bg-app-surface-2 border border-app-border rounded-lg p-2 overflow-x-auto max-h-72">
          {condicionesJson}
        </pre>
        {onEditarIgual && (
          <button
            onClick={() => {
              if (window.confirm('Pasar al editor visual descarta las condiciones avanzadas (no, entre, subiendo, anidamiento). ¿Continuar?')) {
                onEditarIgual()
              }
            }}
            className="mt-2 text-label font-semibold text-app-coral"
          >
            Editar igual (se pierden las condiciones avanzadas)
          </button>
        )}
      </div>

      <div className="bg-app-surface border border-app-border rounded-2xl p-3">
        <div className="font-semibold text-caption text-app-text mb-2">Riesgo</div>
        <div className="grid grid-cols-2 gap-2">
          {RIESGO_CAMPOS.map(([campo, label]) => (
            <label key={campo} className="flex flex-col gap-1 text-label text-app-text-dim">
              {label}
              <input
                type="number"
                value={riesgo[campo] ?? ''}
                onChange={e => emitirRiesgo({ [campo]: e.target.value === '' ? null : Number(e.target.value) })}
                placeholder="—"
                className="bg-app-surface-2 border border-app-border rounded-lg px-2 py-1.5 font-mono text-caption text-app-text"
              />
            </label>
          ))}
        </div>
      </div>

      <div className="bg-app-surface border border-app-border rounded-2xl p-3">
        <div className="font-semibold text-caption text-app-text mb-2">Ejecución</div>
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-label text-app-text-dim">
            Comisión por lado (%)
            <input
              type="number" min={0} max={5} step={0.1} value={ejecucion.comision_pct}
              onChange={e => emitirEjecucion({ comision_pct: Number(e.target.value) })}
              className="w-24 bg-app-surface-2 border border-app-border rounded-lg px-2 py-1.5 font-mono text-caption text-app-text"
            />
          </label>
          <div>
            <div className="flex items-center gap-1 text-label text-app-text-dim mb-1">
              Precio de ejecución
              <InfoTooltip term="analisis_tecnico_precio_ejecucion" />
            </div>
            <Segmented
              options={[
                { value: 'cierre', label: 'Cierre' },
                { value: 'apertura_siguiente', label: 'Apertura siguiente (sin lookahead)' },
              ]}
              value={ejecucion.precio_ejecucion}
              onChange={v => emitirEjecucion({ precio_ejecucion: v as EjecucionDsl['precio_ejecucion'], demora_barras: v === 'apertura_siguiente' ? 1 : 0 })}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
