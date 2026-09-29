import type { ComparadorFilaOut } from '../../api'
import Card from '../ui/Card'
import EmptyState from '../ui/EmptyState'
import InfoTooltip from '../../help/components/InfoTooltip'

function fmtFecha(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' })
}

/** Tramos donde cada estrategia se separó más de la referencia, tal como los devuelve el backend
 * (ya agrupados por mes y limitados a los de mayor magnitud): no se recalcula nada acá. */
export default function DivergenciasEstrategias({ filas }: { filas: ComparadorFilaOut[] }) {
  const conDivergencias = filas.filter(f => f.divergencias.length > 0)

  if (conDivergencias.length === 0) {
    return (
      <EmptyState
        title="Sin tramos de divergencia"
        description="Ninguna estrategia se separó más de 2 puntos porcentuales de la referencia en un mismo mes."
      />
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-1.5">
        <InfoTooltip term="comparador_divergencias" />
      </div>
      {conDivergencias.map(f => (
        <Card key={String(f.estrategia_id ?? 'bh')}>
          <div className="font-semibold text-caption text-app-text mb-2">{f.nombre}</div>
          <div className="flex flex-col gap-2">
            {f.divergencias.map((t, i) => (
              <div key={i} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-label">
                <span className="text-app-text-dim">{fmtFecha(t.desde)} → {fmtFecha(t.hasta)}</span>
                <span className={`font-mono font-bold ${t.delta_pp >= 0 ? 'text-app-pos' : 'text-app-neg'}`}>
                  {t.delta_pp >= 0 ? '+' : ''}{t.delta_pp.toFixed(2)} pp
                </span>
                <span className="text-app-text-faint">
                  Invertida {t.invertida_pct.toFixed(0)}% · referencia invertida {t.invertida_referencia_pct.toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  )
}
