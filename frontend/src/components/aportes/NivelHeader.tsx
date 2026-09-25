import type { AporteNivelConstancia, AporteRachas } from '../../api'
import Card from '../ui/Card'
import BarraProgreso from '../ui/BarraProgreso'
import InfoTooltip from '../../help/components/InfoTooltip'
import { meses } from './comun'

/** Cabecera de progreso: racha en curso, nivel alcanzado y qué falta para el siguiente.
 *
 *  El nivel se muestra siempre junto a sus motivos: la idea es que se pueda leer "estoy acá
 *  porque llevo X meses aportando", nunca un puntaje sin explicación. */
export default function NivelHeader({ nivel, rachas }: { nivel: AporteNivelConstancia; rachas: AporteRachas }) {
  const racha = rachas.aportando_actual.meses
  const sig = nivel.siguiente

  return (
    <Card className="mb-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">
            <InfoTooltip term="aportes_nivel" label="Tu constancia" />
          </div>
          <div className="font-mono text-metric-lg font-bold tabular-nums text-app-text">
            {racha > 0 ? <>🔥 {meses(racha)}</> : <span className="text-app-text-dim">Sin racha activa</span>}
          </div>
          <div className="text-caption text-app-text-dim mt-0.5">
            {racha > 0 ? 'consecutivos aportando' : 'Un aporte este mes la vuelve a arrancar'}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-metric" aria-hidden="true">{nivel.emoji}</div>
          <div className="text-caption font-bold text-app-text">{nivel.nombre}</div>
          <div className="text-label text-app-text-faint">
            Nivel {nivel.orden} de {nivel.total_niveles}
          </div>
        </div>
      </div>

      {nivel.sello_objetivo && (
        <div className="mt-2 inline-flex items-center gap-1 rounded-full bg-app-pos-soft px-2 py-0.5 text-label font-semibold text-app-pos">
          🎯 {nivel.sello_objetivo.etiqueta} · {meses(nivel.sello_objetivo.meses)}
        </div>
      )}

      <ul className="mt-3 flex flex-col gap-0.5">
        {nivel.motivos.map(m => (
          <li key={m} className="text-caption text-app-text-dim">· {m}</li>
        ))}
      </ul>

      {sig && (
        <div className="mt-3 pt-3 border-t border-app-border">
          <div className="flex justify-between items-baseline text-caption mb-1.5">
            <span className="text-app-text">
              Siguiente: <span className="font-semibold">{sig.emoji} {sig.nombre}</span>
            </span>
            <span className="font-mono text-app-text-dim tabular-nums">{sig.progreso_pct.toFixed(0)}%</span>
          </div>
          <BarraProgreso pct={sig.progreso_pct} />
          <div className="text-label text-app-text-dim mt-1.5">{sig.falta_texto}</div>
          <div className="mt-2 flex flex-col gap-1">
            {sig.requisitos.filter(r => r.objetivo > 0).map(r => (
              <div key={r.clave} className="flex justify-between text-label">
                <span className={r.cumple ? 'text-app-text-faint' : 'text-app-text-dim'}>
                  {r.cumple ? '✓' : '○'} {r.etiqueta}
                </span>
                <span className="font-mono tabular-nums text-app-text-dim">
                  {r.actual} / {r.objetivo}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}
