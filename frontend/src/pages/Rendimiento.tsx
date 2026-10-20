import { useQuery } from '@tanstack/react-query'
import { qk } from '../api/queryClient'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getPnlRealizadoNoRealizado, getRendimientoMensual, getPerformanceRelativa, getDescomposicionFx } from '../api'
import ScreenHeader from '../components/layout/ScreenHeader'
import EmptyState from '../components/ui/EmptyState'
import AvisoCalculo from '../components/inversiones/AvisoCalculo'
import { Icon } from '../components/icons/Icons'
import InfoTooltip from '../help/components/InfoTooltip'
import QueryBoundary from '../components/ui/QueryBoundary'
import RendimientoHero from '../components/rendimiento/RendimientoHero'
import GananciaOrigen from '../components/rendimiento/GananciaOrigen'
import ActivosVsDolar from '../components/rendimiento/ActivosVsDolar'
import { BenchmarkCard, AlternativasCard } from '../components/rendimiento/ContraElMercado'
import MesAMes from '../components/rendimiento/MesAMes'
import QuienAporto from '../components/rendimiento/QuienAporto'
import MetricasDetalladas from '../components/rendimiento/MetricasDetalladas'

function Seccion({ titulo, children }: { titulo: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="mb-5">
      <h2 className="text-strong font-bold text-app-text mb-2.5">{titulo}</h2>
      {children}
    </section>
  )
}

export default function Rendimiento() {
  const navigate = useNavigate()
  const { carteraSeleccionada, monedaSeleccionada, resumen } = useInversionesContext()

  const monedaBackend = monedaSeleccionada === 'ARS' ? 'ars_nominal' : 'usd'
  const rendimientoQuery = useQuery({
    queryKey: qk.de('rendimiento-detalle', carteraSeleccionada, monedaBackend),
    queryFn: async () => {
      const [pnl, mensual, perfRelativa, fx] = await Promise.all([
        getPnlRealizadoNoRealizado(carteraSeleccionada),
        getRendimientoMensual(carteraSeleccionada),
        getPerformanceRelativa(carteraSeleccionada, monedaBackend, null),
        getDescomposicionFx(carteraSeleccionada),
      ])
      return { pnl, mensual, perfRelativa, fx }
    },
  })

  const pnl = rendimientoQuery.data?.pnl ?? null
  const rendimientoMensual = rendimientoQuery.data?.mensual ?? null
  const perfRelativa = rendimientoQuery.data?.perfRelativa ?? null
  const descomposicionFx = rendimientoQuery.data?.fx ?? null

  const esARS = monedaSeleccionada === 'ARS'
  const c = pnl?.consolidado

  const realizado = c ? (esARS ? c.realizado_ars : c.realizado_usd) : null
  const noRealizado = c ? (esARS ? c.no_realizado_ars : c.no_realizado_usd) : null
  const ingresos = c ? (esARS ? c.ingresos_ars : c.ingresos_usd) : null
  const total = c ? (esARS ? c.total_ars : c.total_usd) : null

  return (
    <div className="pb-4">
      <ScreenHeader title="Rendimiento" onBack={() => navigate(-1)} />

      <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3">
        <button onClick={() => navigate('/patrimonio')} className="inline-flex items-center gap-1 text-label font-semibold text-app-text-dim">
          <Icon name="trend" className="w-3.5 h-3.5" /> Ver evolución del patrimonio
        </button>
        <button onClick={() => navigate('/riesgo')} className="inline-flex items-center gap-1 text-label font-semibold text-app-text-dim">
          <Icon name="alert" className="w-3.5 h-3.5" /> Ver métricas de riesgo
        </button>
      </div>

      <QueryBoundary
        isLoading={rendimientoQuery.isLoading}
        error={rendimientoQuery.error}
        onRetry={() => void rendimientoQuery.refetch()}
      >
      {!pnl || !resumen ? (
        <EmptyState title="Sin datos" description="No hay movimientos suficientes para calcular el rendimiento de esta cartera." />
      ) : (
        <>
          <RendimientoHero resumen={resumen} totalPnl={total} perfRelativa={perfRelativa} esARS={esARS} />

          <Seccion titulo="¿De dónde salió la ganancia?">
            <GananciaOrigen realizado={realizado} noRealizado={noRealizado} ingresos={ingresos} total={total} />
          </Seccion>

          {descomposicionFx && (
            <Seccion titulo="¿Ganaste por tus activos o por el dólar?">
              <ActivosVsDolar fx={descomposicionFx} />
            </Seccion>
          )}

          <Seccion titulo={<InfoTooltip term="benchmark" label="Contra el mercado" />}>
            <BenchmarkCard perf={perfRelativa} />
          </Seccion>

          <Seccion titulo="¿Y si hubieras hecho otra cosa con tu plata? (en pesos)">
            <AlternativasCard resumen={resumen} />
          </Seccion>

          <Seccion titulo={<InfoTooltip term="twr" label="Mes a mes" />}>
            {!rendimientoMensual || rendimientoMensual.meses.length === 0 ? (
              <EmptyState title="Sin historial mensual" description="No hay suficientes meses de actividad para armar el mapa de calor." />
            ) : (
              <MesAMes datos={rendimientoMensual} esARS={esARS} />
            )}
          </Seccion>

          <Seccion titulo="Quién aportó la ganancia">
            {pnl.por_ticker.length === 0 ? (
              <EmptyState title="Sin posiciones" description="No hay tickers con actividad para esta cartera." />
            ) : (
              <QuienAporto items={pnl.por_ticker} esARS={esARS} />
            )}
          </Seccion>

          <MetricasDetalladas resumen={resumen} medidaInicial={esARS ? 'ars' : 'usd'} />

          <AvisoCalculo
            className="mt-4"
            linkCalidad
            mensajes={[
              pnl.valuados_al_costo && pnl.valuados_al_costo.length > 0
                ? `${pnl.valuados_al_costo.join(', ')} sin cotización: se valúa${pnl.valuados_al_costo.length > 1 ? 'n' : ''} ` +
                  'al costo de compra, igual que en la pantalla principal, así que su "no realizado" no es un resultado de mercado.'
                : null,
            ]}
          />
        </>
      )}
      </QueryBoundary>
    </div>
  )
}
