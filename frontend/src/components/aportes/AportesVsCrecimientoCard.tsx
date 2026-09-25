import { useQuery } from '@tanstack/react-query'
import { getPatrimonioSummary } from '../../api'
import { qk } from '../../api/queryClient'
import Card from '../ui/Card'
import InfoTooltip from '../../help/components/InfoTooltip'
import { formatUSD } from '../../utils'

/** Cuánto de tu patrimonio pusiste vos y cuánto lo pusieron las inversiones.
 *
 *  Reutiliza la descomposición de Patrimonio (`/patrimonio/summary`), que ya garantiza la
 *  identidad `valor = aportes + rendimiento + dividendos + otros ajustes`. Acá no se recalcula
 *  ningún rendimiento: sólo se muestra.
 *
 *  Es una segunda consulta y puede fallar sin arrastrar al resto de la pantalla: en ese caso la
 *  tarjeta no se dibuja. */
export default function AportesVsCrecimientoCard({ cartera }: { cartera: string | null }) {
  const query = useQuery({
    queryKey: qk.de('patrimonio-summary', cartera),
    queryFn: () => getPatrimonioSummary(cartera),
  })

  if (query.isLoading || query.error || !query.data) return null

  const { maximo, descomposicion } = query.data
  const patrimonio = maximo.valor_actual_usd
  if (patrimonio == null) return null

  const aportes = descomposicion.aportes_usd
  const resultado = descomposicion.rendimiento_usd + descomposicion.dividendos_usd
  const otros = descomposicion.otros_ajustes_usd

  // Proporción de la barra: se reparte sobre la suma de magnitudes para que un resultado
  // negativo no rompa el ancho.
  const total = Math.abs(aportes) + Math.abs(resultado)
  const anchoAportes = total > 0 ? (Math.abs(aportes) / total) * 100 : 100

  return (
    <Card className="mb-4">
      <h3 className="text-body font-bold text-app-text mb-1">
        <InfoTooltip term="aportes_vs_crecimiento" label="💎 Lo que pusiste vs. lo que creció" />
      </h3>
      <div className="font-mono text-metric font-bold tabular-nums text-app-text">
        {formatUSD(patrimonio)}
      </div>
      <div className="text-label text-app-text-faint mb-3">patrimonio actual</div>

      <div className="flex h-2 rounded-full overflow-hidden bg-app-surface-2 mb-2">
        <div className="bg-app-accent h-full" style={{ width: `${anchoAportes}%` }} />
        <div className={`h-full flex-1 ${resultado < 0 ? 'bg-app-neg' : 'bg-app-pos'}`} />
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex justify-between text-caption">
          <span className="text-app-text-dim">
            <span className="inline-block w-2 h-2 rounded-full bg-app-accent mr-1.5" aria-hidden="true" />
            Aportaste vos
          </span>
          <span className="font-mono font-bold tabular-nums text-app-text">{formatUSD(aportes)}</span>
        </div>
        <div className="flex justify-between text-caption">
          <span className="text-app-text-dim">
            <span
              className={`inline-block w-2 h-2 rounded-full mr-1.5 ${resultado < 0 ? 'bg-app-neg' : 'bg-app-pos'}`}
              aria-hidden="true"
            />
            Generaron las inversiones
          </span>
          <span
            className={`font-mono font-bold tabular-nums ${resultado < 0 ? 'text-app-neg' : 'text-app-pos'}`}
          >
            {formatUSD(resultado)}
          </span>
        </div>
        {Math.abs(otros) > 0.5 && (
          <div className="flex justify-between text-label">
            <span className="text-app-text-faint">Comisiones y otros ajustes</span>
            <span className="font-mono tabular-nums text-app-text-faint">{formatUSD(otros)}</span>
          </div>
        )}
      </div>

      <div className="text-label text-app-text-faint mt-3">
        Los aportes de esta tarjeta salen del cálculo de Patrimonio, que incluye todos los
        movimientos del período; puede diferir del total de arriba, que mide sólo capital nuevo.
      </div>
    </Card>
  )
}
