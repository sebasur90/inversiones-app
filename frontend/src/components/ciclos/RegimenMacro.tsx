import { useState } from 'react'
import type { CicloRegimen } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import { Icon } from '../icons/Icons'

const ETIQ: Record<string, string> = { acelerando: 'Acelera', desacelerando: 'Desacelera' }

/**
 * Régimen macroeconómico. Hoy no hay series macro globales confiables, así que la tarjeta lo dice y lista qué falta:
 * no se asigna un escenario supuesto. La estructura (los cuatro escenarios) queda lista para cuando haya datos.
 */
export default function RegimenMacro({ regimen }: { regimen: CicloRegimen }) {
  const [abierto, setAbierto] = useState(false)
  const disponible = regimen.estado !== 'no_disponible'
  return (
    <div className="rounded-xl border border-app-border bg-app-surface">
      <button
        type="button"
        onClick={() => setAbierto(a => !a)}
        aria-expanded={abierto}
        className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left"
      >
        <span className="flex flex-col">
          <span className="text-caption font-bold text-app-text">Régimen macroeconómico</span>
          <span className="text-label text-app-text-dim">
            {disponible ? regimen.escenario : 'No disponible: faltan series macro globales'}
          </span>
        </span>
        <Icon name="chevron" className={`w-4 h-4 text-app-text-faint transition-transform ${abierto ? 'rotate-180' : ''}`} />
      </button>
      {abierto && (
        <div className="px-3 pb-3 pt-1 border-t border-app-border flex flex-col gap-3">
          <p className="text-label text-app-text-dim">{regimen.aclaracion}</p>
          <div>
            <div className="text-label font-bold uppercase text-app-text-faint mb-1">
              Los cuatro <InfoTooltip term="ciclos_regimen" label="escenarios" />
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {regimen.escenarios.map(e => (
                <div key={e.id} className="rounded-lg border border-app-border px-2 py-1.5">
                  <div className="text-caption font-semibold text-app-text">{e.nombre}</div>
                  <div className="text-label text-app-text-faint">
                    Crecimiento: {ETIQ[e.crecimiento] ?? e.crecimiento}
                    <br />
                    Inflación: {ETIQ[e.inflacion] ?? e.inflacion}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="text-label font-bold uppercase text-app-text-faint mb-1">Qué falta</div>
            <ul className="list-disc pl-4 text-label text-app-text-dim space-y-0.5">
              {regimen.indicadores_necesarios.map(i => (
                <li key={i.id}>
                  <b className="text-app-text">{i.nombre}:</b> {i.motivo}
                </li>
              ))}
            </ul>
          </div>
          <p className="text-label text-app-text-faint">
            Hoy sólo hay {regimen.disponible_hoy.map(d => d.nombre).join(', ')} (Argentina). {regimen.proxima_etapa}
          </p>
        </div>
      )}
    </div>
  )
}
