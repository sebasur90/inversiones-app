import type { EscenarioVidaIn, TipoEscenarioVida } from '../../../api'
import InfoTooltip from '../../../help/components/InfoTooltip'
import type { HelpKey } from '../../../help/content/index'
import { CampoNumerico } from './VidaSupuestosForm'

interface Opcion {
  tipo: TipoEscenarioVida
  helpKey: HelpKey
  etiqueta: string
}

const OPCIONES: Opcion[] = [
  { tipo: 'aumentar_aporte', helpKey: 'vida_escenario_aumentar', etiqueta: 'Aumentar aporte mensual' },
  { tipo: 'disminuir_aporte', helpKey: 'vida_escenario_disminuir', etiqueta: 'Disminuir aporte mensual' },
  { tipo: 'dejar_de_aportar', helpKey: 'vida_escenario_dejar', etiqueta: 'Dejar de aportar' },
  { tipo: 'aporte_extraordinario', helpKey: 'vida_escenario_aporte_extra', etiqueta: 'Aporte extraordinario' },
  { tipo: 'retiro_extraordinario', helpKey: 'vida_escenario_retiro_extra', etiqueta: 'Retiro extraordinario' },
  { tipo: 'aumentar_aportes_anualmente', helpKey: 'vida_escenario_crecimiento_anual_aportes', etiqueta: 'Aumentar aportes cada año' },
]

const MAX_SELECCIONADOS = 5

interface Props {
  seleccionados: EscenarioVidaIn[]
  onChange: (next: EscenarioVidaIn[]) => void
  aporteMensualBase: number
  horizonteMeses: number
  moneda: 'USD' | 'ARS'
}

function CamposDeEscenario({
  tipo, spec, moneda, horizonteMeses, onCambiar,
}: {
  tipo: TipoEscenarioVida
  spec: EscenarioVidaIn
  moneda: 'USD' | 'ARS'
  horizonteMeses: number
  onCambiar: (campo: 'monto' | 'pct' | 'mes', valor: number | null) => void
}) {
  if (tipo === 'dejar_de_aportar') {
    return (
      <div className="text-label text-app-text-dim">
        Sin datos adicionales: el aporte pasa a 0 desde el mes 1.
      </div>
    )
  }

  if (tipo === 'aumentar_aporte' || tipo === 'disminuir_aporte') {
    return (
      <div className="flex items-center gap-2">
        <span className="text-label text-app-text-dim">Nuevo aporte mensual</span>
        <CampoNumerico
          valor={spec.monto ?? null}
          onCommit={n => onCambiar('monto', n !== null ? Math.max(0, n) : null)}
          placeholder="0"
          className="max-w-[7rem]"
        />
        <span className="text-label text-app-text-faint">{moneda}/mes</span>
      </div>
    )
  }

  if (tipo === 'aumentar_aportes_anualmente') {
    return (
      <div className="flex items-center gap-2">
        <span className="text-label text-app-text-dim">Aumento cada 12 meses</span>
        <CampoNumerico
          valor={spec.pct ?? null}
          onCommit={n => onCambiar('pct', n)}
          placeholder="0"
          className="max-w-[6rem]"
        />
        <span className="text-label text-app-text-faint">% anual</span>
      </div>
    )
  }

  // aporte_extraordinario | retiro_extraordinario
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-label text-app-text-dim">Monto</span>
      <CampoNumerico
        valor={spec.monto ?? null}
        onCommit={n => onCambiar('monto', n !== null ? Math.max(0, n) : null)}
        placeholder="0"
        className="max-w-[7rem]"
      />
      <span className="text-label text-app-text-faint">{moneda}</span>
      <span className="text-label text-app-text-dim ml-2">en el mes</span>
      <CampoNumerico
        valor={spec.mes ?? null}
        onCommit={n => onCambiar('mes', n !== null ? Math.min(horizonteMeses, Math.max(1, Math.round(n))) : null)}
        placeholder="1"
        className="max-w-[5rem]"
      />
      <span className="text-label text-app-text-faint">
        (año {Math.max(1, Math.ceil((spec.mes ?? 1) / 12))})
      </span>
    </div>
  )
}

export default function VidaEscenarioSelector({
  seleccionados, onChange, aporteMensualBase, horizonteMeses, moneda,
}: Props) {
  const estaActivo = (tipo: TipoEscenarioVida) => seleccionados.some(s => s.tipo === tipo)
  const spec = (tipo: TipoEscenarioVida) => seleccionados.find(s => s.tipo === tipo)

  const toggle = (tipo: TipoEscenarioVida) => {
    if (estaActivo(tipo)) {
      onChange(seleccionados.filter(s => s.tipo !== tipo))
      return
    }
    if (seleccionados.length >= MAX_SELECCIONADOS) return

    const mesDefault = Math.max(1, Math.min(horizonteMeses, Math.round(horizonteMeses / 2)))
    let nuevo: EscenarioVidaIn
    switch (tipo) {
      case 'aumentar_aporte':
        nuevo = { tipo, monto: Math.round((aporteMensualBase || 100) * 1.5) }
        break
      case 'disminuir_aporte':
        nuevo = { tipo, monto: Math.round((aporteMensualBase || 100) * 0.5) }
        break
      case 'aporte_extraordinario':
        nuevo = { tipo, monto: 1000, mes: mesDefault }
        break
      case 'retiro_extraordinario':
        nuevo = { tipo, monto: 1000, mes: mesDefault }
        break
      case 'aumentar_aportes_anualmente':
        nuevo = { tipo, pct: 10 }
        break
      default:
        nuevo = { tipo }
    }
    onChange([...seleccionados, nuevo])
  }

  const actualizar = (tipo: TipoEscenarioVida, campo: 'monto' | 'pct' | 'mes', valor: number | null) => {
    onChange(seleccionados.map(s => (s.tipo === tipo ? { ...s, [campo]: valor } : s)))
  }

  return (
    <div className="space-y-3">
      <div>
        <span className="inline-flex items-center gap-1.5 bg-app-surface-2 text-app-text-dim rounded-[9px] px-2.5 py-1.5 text-label font-bold border border-app-border">
          <InfoTooltip term="vida_escenario_continuar" label="Continuar igual" />
          <span className="text-app-text-faint font-normal">· base, siempre incluido</span>
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {OPCIONES.map(op => {
          const activo = estaActivo(op.tipo)
          return (
            <button
              key={op.tipo}
              onClick={() => toggle(op.tipo)}
              disabled={!activo && seleccionados.length >= MAX_SELECCIONADOS}
              className={`text-label font-semibold px-2.5 py-1.5 rounded-[9px] border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                activo
                  ? 'bg-app-accent-soft text-app-accent border-app-accent/40'
                  : 'bg-app-surface text-app-text-dim border-app-border'
              }`}
            >
              {op.etiqueta}
            </button>
          )
        })}
      </div>

      {seleccionados.length >= MAX_SELECCIONADOS && (
        <div className="text-label text-app-text-faint">
          Máximo {MAX_SELECCIONADOS} escenarios además de "Continuar igual". Quitá alguno para agregar otro.
        </div>
      )}

      {seleccionados.length > 0 && (
        <div className="space-y-2">
          {OPCIONES.filter(op => estaActivo(op.tipo)).map(op => {
            const s = spec(op.tipo)!
            return (
              <div key={op.tipo} className="bg-app-surface-2 border border-app-border rounded-[11px] p-2.5">
                <div className="text-xs font-semibold text-app-text mb-1.5">
                  <InfoTooltip term={op.helpKey} label={op.etiqueta} />
                </div>
                <CamposDeEscenario
                  tipo={op.tipo}
                  spec={s}
                  moneda={moneda}
                  horizonteMeses={horizonteMeses}
                  onCambiar={(campo, valor) => actualizar(op.tipo, campo, valor)}
                />
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
