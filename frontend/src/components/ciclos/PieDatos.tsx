import { useState } from 'react'
import type { CiclosMeta } from '../../api'
import InfoTooltip from '../../help/components/InfoTooltip'
import { Icon } from '../icons/Icons'
import { fechaCorta, fechaHora } from '../../utils/fechas'

const TIPO_REND: Record<string, string> = {
  total: 'Retorno total (con dividendos y distribuciones)',
  precio: 'Retorno de precio',
  mixto: 'Mixto: hay grupos de retorno total y de precio',
}

/**
 * De dónde sale lo que se ve: fuente, fechas, período, moneda, tipo de rendimiento, benchmark y limitaciones. Las
 * advertencias (comparaciones que no son homogéneas, datos faltantes) están siempre visibles; el resto, plegado.
 */
export default function PieDatos({ meta }: { meta: CiclosMeta }) {
  const [abierto, setAbierto] = useState(false)
  const filas: [string, string][] = [
    ['Fuente', meta.fuente],
    ['Último dato', meta.ultima_fecha_datos ? fechaCorta(meta.ultima_fecha_datos) : 'sin datos'],
    ['Última actualización de la app', meta.ultima_actualizacion ? fechaHora(meta.ultima_actualizacion) : 'todavía no descargó datos'],
    ['Período', meta.periodo.desde && meta.periodo.hasta ? `${fechaCorta(meta.periodo.desde)} → ${fechaCorta(meta.periodo.hasta)}` : '—'],
    ['Moneda', meta.moneda],
    ['Tipo de rendimiento', meta.tipo_rendimiento ? TIPO_REND[meta.tipo_rendimiento] ?? meta.tipo_rendimiento : '—'],
    ['Referencia', meta.benchmark ? `${meta.benchmark.nombre}${meta.benchmark.proxy ? ` (${meta.benchmark.proxy})` : ''}` : 'ninguna'],
  ]
  return (
    <div className="flex flex-col gap-2">
      {meta.advertencias.length > 0 && (
        <div role="note" className="rounded-xl border border-app-warn/30 bg-app-warn/10 px-3 py-2">
          {meta.advertencias.map(a => (
            <div key={a} className="flex items-start gap-1.5 text-caption text-app-text-dim">
              <Icon name="alert" className="w-3.5 h-3.5 text-app-warn mt-0.5" />
              <span>{a}</span>
            </div>
          ))}
        </div>
      )}
      <div className="rounded-xl border border-app-border bg-app-surface">
        <button
          type="button"
          onClick={() => setAbierto(a => !a)}
          aria-expanded={abierto}
          className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-caption font-semibold text-app-text-dim"
        >
          <span className="inline-flex items-center gap-1.5">
            <Icon name="info" className="w-3.5 h-3.5" />
            Datos de este análisis
          </span>
          <Icon name="chevron" className={`w-3.5 h-3.5 transition-transform ${abierto ? 'rotate-180' : ''}`} />
        </button>
        {abierto && (
          <div className="px-3 pb-3 flex flex-col gap-2 border-t border-app-border pt-2">
            <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-label">
              {filas.map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-app-text-faint font-semibold">{k}</dt>
                  <dd className="text-app-text-dim">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="text-label text-app-text-dim">
              <div className="font-semibold text-app-text mb-0.5">Limitaciones</div>
              <ul className="list-disc pl-4 space-y-0.5">
                {meta.limitaciones.map(l => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
            </div>
            <div className="text-label text-app-text-faint">
              Qué es un <InfoTooltip term="ciclos_proxy" label="proxy" />, el <InfoTooltip term="ciclos_retorno_total" label="tipo de retorno" /> y la{' '}
              <InfoTooltip term="ciclos_moneda" label="moneda" />.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
