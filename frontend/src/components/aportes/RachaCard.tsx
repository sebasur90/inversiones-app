import dayjs from 'dayjs'
import type { AporteMesItem, AporteRachas } from '../../api'
import Card from '../ui/Card'
import InfoTooltip from '../../help/components/InfoTooltip'
import { formatUSD } from '../../utils'
import { mesCorto, meses } from './comun'

/** Racha de aportes con la tira de los últimos 12 meses.
 *
 *  La marca nunca es sólo color: cada mes lleva ✓ / ○ y su `title`, para que se entienda sin
 *  distinguir verde de gris. */
export default function RachaCard({ rachas, serie }: { rachas: AporteRachas; serie: AporteMesItem[] }) {
  const ultimos = serie.filter(s => !s.futuro).slice(-12)
  const actual = rachas.aportando_actual
  const record = rachas.aportando_record

  return (
    <Card className="mb-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-body font-bold text-app-text">
          <InfoTooltip term="aportes_racha" label="Tu racha" />
        </h3>
        <span className="font-mono text-title font-bold tabular-nums text-app-pos">
          {actual.meses > 0 ? `🔥 ${actual.meses}` : '—'}
        </span>
      </div>

      <div className="flex gap-1 mb-3" role="list">
        {ultimos.map(m => {
          const etiqueta = `${dayjs(`${m.mes}-01`).format('MMMM YYYY')}: ${
            m.con_aporte ? formatUSD(m.neto_usd) : 'sin aporte'
          }${m.en_curso ? ' (mes en curso)' : ''}`
          return (
            <div key={m.mes} className="flex-1 flex flex-col items-center gap-1" role="listitem" title={etiqueta}>
              <div
                className={`w-full h-7 rounded-md flex items-center justify-center text-label font-bold ${
                  m.con_aporte
                    ? 'bg-app-pos-soft text-app-pos'
                    : m.en_curso
                      ? 'bg-app-surface-2 text-app-text-faint border border-dashed border-app-border'
                      : 'bg-app-surface-2 text-app-text-faint'
                }`}
                aria-label={etiqueta}
              >
                {m.con_aporte ? '✓' : '○'}
              </div>
              <span className="text-label text-app-text-faint">
                {dayjs(`${m.mes}-01`).format('MMM')[0].toUpperCase()}
              </span>
            </div>
          )
        })}
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-caption">
        <div className="flex justify-between">
          <span className="text-app-text-dim">Mejor racha</span>
          <span className="font-mono tabular-nums text-app-text">{record.meses > 0 ? meses(record.meses) : '—'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-app-text-dim">Sin aportar</span>
          <span className="font-mono tabular-nums text-app-text">
            {rachas.meses_sin_aportar_ultimos_12} de {rachas.meses_considerados_ultimos_12}
          </span>
        </div>
      </div>
      {record.meses > 0 && (
        <div className="text-label text-app-text-faint mt-2">
          Tu mejor racha va de {mesCorto(record.desde)} a {mesCorto(record.hasta)}
          {actual.meses >= record.meses && actual.meses > 0 && ' — y es la que estás corriendo ahora'}
        </div>
      )}
    </Card>
  )
}
