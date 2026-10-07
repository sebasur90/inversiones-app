import { useQuery } from '@tanstack/react-query'
import { getAlertas } from '../../api'
import type { AlertaPrecioOut } from '../../api'
import type { Moneda } from '../../utils/formatoMonto'
import { qk } from '../../api/queryClient'
import { fechaHora } from '../../utils/fechas'
import { formatMonto } from '../../utils/formatoMonto'
import { useMontosOcultos } from '../../utils/privacidad'
import {
  COLOR_ACCION, ETIQUETA_ACCION, esAvisoDeSenal, etiquetaOrigen, etiquetaRegla,
} from '../../utils/avisosTelegram'
import EmptyState from '../ui/EmptyState'
import QueryBoundary from '../ui/QueryBoundary'
import { SkeletonFilas } from '../ui/Skeleton'

function moneda(aviso: AlertaPrecioOut): Moneda {
  return aviso.moneda === 'ARS' ? 'ARS' : 'USD'
}

function Fila({ aviso }: { aviso: AlertaPrecioOut }) {
  const ocultos = useMontosOcultos()
  const divisa = moneda(aviso)
  const esSenal = esAvisoDeSenal(aviso.tipo)

  return (
    <div className="py-2.5 border-b border-app-border-soft last:border-b-0">
      <div className="flex items-baseline justify-between gap-2">
        <div className="min-w-0">
          <span className="text-body font-semibold text-app-text">{aviso.ticker}</span>
          <span className={`text-label font-bold ml-2 ${COLOR_ACCION[aviso.accion]}`}>
            {ETIQUETA_ACCION[aviso.accion]}
          </span>
        </div>
        <span className="text-caption text-app-text-dim shrink-0">
          {aviso.emitida_en ? fechaHora(aviso.emitida_en) : '—'}
        </span>
      </div>

      <div className="text-caption text-app-text-dim mt-0.5">
        {etiquetaRegla(aviso)} · {etiquetaOrigen(aviso)}
      </div>

      <div className="text-caption text-app-text mt-0.5">
        {esSenal
          ? `cierre${aviso.senal_fecha ? ` del ${aviso.senal_fecha}` : ''}: ${formatMonto(aviso.precio_disparo, divisa, ocultos)}`
          : `${formatMonto(aviso.precio_disparo, divisa, ocultos)} vs. ${formatMonto(aviso.nivel, divisa, ocultos)}`}
        {aviso.resultado_pct !== null && (
          <span className={aviso.resultado_pct >= 0 ? 'text-app-pos ml-2' : 'text-app-neg ml-2'}>
            {aviso.resultado_pct >= 0 ? '+' : ''}
            {aviso.resultado_pct.toFixed(1)}%
          </span>
        )}
      </div>

      {!aviso.entregada && (
        <div className="text-caption text-app-neg mt-0.5">
          Sin entregar; se reintenta en la próxima evaluación.
        </div>
      )}
    </div>
  )
}

/**
 * Los últimos avisos que el servidor mandó al celular.
 *
 * Sale de las mismas filas que generaron el mensaje de Telegram (`alertas_analytics.listar`), así
 * que la app y el celular no pueden contar cosas distintas. Los avisos silenciados por la
 * configuración no figuran: no se emitieron.
 */
export default function HistorialAvisos({ limite = 20 }: { limite?: number }) {
  const query = useQuery({
    queryKey: qk.de('alertas-historial', limite),
    queryFn: () => getAlertas(limite),
  })

  return (
    <QueryBoundary
      isLoading={query.isLoading}
      error={query.error}
      onRetry={() => void query.refetch()}
      fallback={<SkeletonFilas filas={3} />}
    >
      {query.data && query.data.length === 0 ? (
        <EmptyState
          title="Todavía no se mandó ningún aviso"
          description="Cuando una posición cruce su stop-loss o su objetivo, un ticker de la watchlist entre en zona de compra, o dispare una estrategia habilitada, el aviso va a aparecer acá."
        />
      ) : (
        <div>{query.data?.map(aviso => <Fila key={`${aviso.ticker}-${aviso.tipo}-${aviso.cartera ?? ''}`} aviso={aviso} />)}</div>
      )}
    </QueryBoundary>
  )
}
