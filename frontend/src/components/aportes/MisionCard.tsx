import type { AporteMision } from '../../api'
import Card from '../ui/Card'
import BarraProgreso from '../ui/BarraProgreso'
import InfoTooltip from '../../help/components/InfoTooltip'
import { formatUSD } from '../../utils'

/** Próximo paso concreto, siempre de comportamiento: sostener la racha o cumplir la meta que el
 *  propio usuario fijó. Nunca sugiere subir el aporte ni tomar más riesgo. */
export default function MisionCard({ mision }: { mision: AporteMision }) {
  const fmt = (v: number) => (mision.unidad === 'usd' ? formatUSD(v) : String(v))

  return (
    <Card className="mb-4 border-l-[3px] border-l-app-accent">
      <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">
        <InfoTooltip term="aportes_mision" label="Tu próxima misión" />
      </div>
      <div className="text-body font-bold text-app-text">🎯 {mision.titulo}</div>
      <div className="text-caption text-app-text-dim mt-0.5 mb-2.5">{mision.detalle}</div>
      <BarraProgreso pct={mision.progreso_pct} />
      <div className="flex justify-between text-label mt-1.5">
        <span className="font-mono tabular-nums text-app-text-dim">
          {fmt(mision.actual)} / {fmt(mision.objetivo)}
        </span>
        <span className="text-app-text-faint">{mision.por_que}</span>
      </div>
    </Card>
  )
}
