import type { ComparadorMejorOut } from '../../api'
import Card from '../ui/Card'
import InfoTooltip from '../../help/components/InfoTooltip'
import { Icon } from '../icons/Icons'

function formatPctSigned(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

/** "¿Qué estrategia obtuvo el mayor rendimiento?": nunca "la mejor para operar este instrumento",
 * el disclaimer literal viene del backend (`ComparadorMejorOut.disclaimer`) para que el texto no
 * se pueda desincronizar entre el motor y la pantalla. */
export default function PanelDiferenciaEstrategias({ mejor }: { mejor: ComparadorMejorOut | null }) {
  if (!mejor) {
    return (
      <Card>
        <div className="text-caption text-app-text-dim">
          Ninguna de las estrategias elegidas tiene datos suficientes para saber cuál rindió más.
        </div>
      </Card>
    )
  }

  return (
    <Card>
      <div className="flex items-center gap-1.5 mb-2">
        <span className="font-semibold text-caption text-app-text">¿Qué estrategia obtuvo el mayor rendimiento?</span>
        <InfoTooltip term="comparador_puntos_porcentuales" />
      </div>
      <p className="text-caption text-app-text leading-relaxed">
        <b>{mejor.nombre}</b> tuvo el mayor rendimiento del período elegido:{' '}
        <b className={mejor.retorno_total_pct >= 0 ? 'text-app-pos' : 'text-app-neg'}>
          {formatPctSigned(mejor.retorno_total_pct)}
        </b>
        {mejor.diferencia_pp != null && (
          <>
            {' '}— <b className={mejor.diferencia_pp >= 0 ? 'text-app-pos' : 'text-app-neg'}>
              {mejor.diferencia_pp >= 0 ? '+' : ''}{mejor.diferencia_pp.toFixed(2)} pp
            </b> contra la referencia.
          </>
        )}
      </p>
      <div className="flex items-start gap-1.5 mt-3 p-2.5 bg-app-surface-2 rounded-[9px] border border-app-border">
        <Icon name="alert" className="w-3.5 h-3.5 text-app-accent shrink-0 mt-0.5" />
        <p className="text-label text-app-text-dim">{mejor.disclaimer}</p>
      </div>
    </Card>
  )
}
