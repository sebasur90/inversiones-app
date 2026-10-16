import { useState } from 'react'
import type { ClaveDimension, DiagnosticoEmpresa, DimensionDiagnostico } from '../../api'
import type { HelpKey } from '../../help/content/index'
import Card from '../ui/Card'
import InfoTooltip from '../../help/components/InfoTooltip'
import { Icon } from '../icons/Icons'
import { EstadoDimension, OrigenTag, TONO_FRASE } from './comun'

const AYUDA: Record<ClaveDimension, HelpKey> = {
  valuacion: 'diagnostico_familias',
  calidad: 'diagnostico_calidad',
  crecimiento: 'diagnostico_crecimiento',
  solidez: 'diagnostico_solidez',
  confianza: 'diagnostico_confianza',
}

const TEXTO_BANDA = { mejor: 'más barata', peor: 'más cara', media: 'en el medio' } as const

function Fila({ dim, abierta, onToggle }: { dim: DimensionDiagnostico; abierta: boolean; onToggle: () => void }) {
  const hayDetalle = dim.nivel !== 'no_aplica'
  return (
    <div className="border-b border-app-border last:border-b-0 py-3">
      <button
        onClick={hayDetalle ? onToggle : undefined}
        className="w-full flex items-center justify-between gap-2 text-left"
        aria-expanded={hayDetalle ? abierta : undefined}
        disabled={!hayDetalle}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1 mb-0.5">
            <span className="text-label font-bold uppercase tracking-wide text-app-text-dim">{dim.nombre}</span>
            <InfoTooltip term={AYUDA[dim.clave]} label="" />
          </div>
          <EstadoDimension nivel={dim.nivel} estado={dim.estado} />
        </div>
        {hayDetalle && (
          <Icon name="chevron" className={`w-3.5 h-3.5 text-app-text-dim shrink-0 transition-transform ${abierta ? 'rotate-0' : '-rotate-90'}`} />
        )}
      </button>

      {!hayDetalle && <div className="text-caption text-app-text-faint mt-1">{dim.resumen}</div>}

      {abierta && hayDetalle && (
        <div className="mt-2.5 flex flex-col gap-2.5">
          <div className="text-caption text-app-text-dim">{dim.resumen}</div>

          {dim.votos.length > 0 && dim.clave === 'valuacion' && (
            <div>
              <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">Cómo votó cada familia</div>
              <ul className="flex flex-col gap-0.5">
                {dim.votos.map(v => (
                  <li key={v.familia} className="text-caption text-app-text-dim flex flex-wrap gap-x-1.5">
                    <span className="text-app-text font-semibold">{v.nombre}:</span>
                    <span>{v.banda === 'media' ? 'en el medio' : TEXTO_BANDA[v.banda]}</span>
                    {v.solo_apoya && <span className="text-app-text-faint">(suma, no decide solo)</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Las razones de valuación son las frases de la tarjeta de lectura: no se repiten acá. */}
          {dim.razones.length > 0 && dim.clave !== 'valuacion' && (
            <div className="flex flex-col gap-2">
              {dim.razones.map((r, i) => (
                <div key={i} className={`border-l-2 pl-2.5 ${TONO_FRASE[r.tono]}`}>
                  <div className="text-caption text-app-text flex flex-wrap items-center gap-1.5">
                    <span>{r.texto}</span>
                    {r.origen !== 'observado' && <OrigenTag origen={r.origen} />}
                  </div>
                  {r.regla && <div className="text-label text-app-text-faint">Regla: {r.regla}</div>}
                </div>
              ))}
            </div>
          )}

          <div className="bg-app-surface-2 rounded-xl p-2.5">
            <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">¿Cómo se decide?</div>
            <div className="text-caption text-app-text-dim">{dim.regla}</div>
          </div>

          {dim.faltantes.length > 0 && (
            <div>
              <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">Qué falta para estar más seguro</div>
              <ul className="flex flex-col gap-0.5">
                {dim.faltantes.map(f => (
                  <li key={f} className="text-caption text-app-text-dim flex gap-1.5">
                    <span aria-hidden="true">·</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** Las cinco preguntas por separado, sin puntaje único: estado en palabras, razones, regla y lo que falta. */
export default function DiagnosticoCard({ diagnostico, fechaDato }: { diagnostico: DiagnosticoEmpresa; fechaDato: string | null }) {
  const [abierta, setAbierta] = useState<string | null>(null)
  const baja = diagnostico.confianza === 'baja'
  return (
    <Card>
      <div className="flex items-start justify-between gap-2 mb-1">
        <div className="text-strong font-bold text-app-text flex items-center gap-1">
          Diagnóstico <InfoTooltip term="diagnostico_que_es" label="" />
        </div>
        <InfoTooltip term="diagnostico_origen" label="Dato · estimación · calculado" />
      </div>
      <div className="text-label text-app-text-faint mb-1">
        {fechaDato ? `Datos de Yahoo del ${fechaDato.split('-').reverse().join('/')}. ` : ''}
        Las conclusiones las calcula la app con reglas visibles.
      </div>
      {baja && (
        <div className="flex gap-1.5 items-start text-caption text-app-warn mt-1">
          <Icon name="alert" className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          Confianza baja en los datos: tomá estas conclusiones con mucha cautela.
        </div>
      )}
      <div className="mt-1">
        {diagnostico.dimensiones.map(d => (
          <Fila key={d.clave} dim={d} abierta={abierta === d.clave} onToggle={() => setAbierta(abierta === d.clave ? null : d.clave)} />
        ))}
      </div>
    </Card>
  )
}
