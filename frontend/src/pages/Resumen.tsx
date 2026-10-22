import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useInversionesContext } from '../context/InversionesContext'
import { getEvolucionInversiones, getDiagnostico, getCalidadDatos } from '../api'
import { qk } from '../api/queryClient'
import { calcularDesde } from '../utils'
import { variacionDiaCartera } from '../utils/resumenCartera'
import { Icon } from '../components/icons/Icons'
import ScreenHeader from '../components/layout/ScreenHeader'
import HeroValorCard, { type PeriodoHero } from '../components/inversiones/HeroValorCard'
import KpiGrid from '../components/inversiones/KpiGrid'
import CarterasChips from '../components/inversiones/CarterasChips'
import PosicionRow from '../components/inversiones/PosicionRow'
import ParaMirarHoy from '../components/inversiones/ParaMirarHoy'
import EstadoGeneral from '../components/inversiones/EstadoGeneral'
import QueSeMovioHoy from '../components/inversiones/QueSeMovioHoy'
import { AlternativasCard } from '../components/rendimiento/ContraElMercado'
import { estadoAlerta } from '../utils/alertasPrecio'
import EmptyState from '../components/ui/EmptyState'
import InfoTooltip from '../help/components/InfoTooltip'
import QueryBoundary from '../components/ui/QueryBoundary'
import SkeletonPantalla from '../components/ui/Skeleton'

export default function Resumen() {
  const navigate = useNavigate()
  const { carteras, carteraSeleccionada, setCarteraSeleccionada, monedaSeleccionada, resumen, rendimientoPorTicker, watchlist, umbralProximidad, loading } =
    useInversionesContext()
  const [periodo, setPeriodo] = useState<PeriodoHero>('ALL')

  // Sin `syncVersion` en las dependencias: sincronizar invalida la caché de queries y estas
  // se vuelven a pedir solas. La serie del gráfico usa la misma clave que Patrimonio
  // (`evolucion` + cartera + período), así que cambiar de período acá y allá comparte caché.
  const evolucionQuery = useQuery({
    queryKey: qk.de('evolucion', carteraSeleccionada, periodo),
    queryFn: () => getEvolucionInversiones(carteraSeleccionada, calcularDesde(periodo)),
    // Al cambiar de período se sigue viendo la serie anterior (atenuada) en vez de un hueco.
    placeholderData: keepPreviousData,
  })
  const diagnosticoQuery = useQuery({
    queryKey: qk.diagnostico(carteraSeleccionada),
    queryFn: () => getDiagnostico(carteraSeleccionada),
  })
  const calidadQuery = useQuery({
    queryKey: qk.calidadDatos,
    queryFn: () => getCalidadDatos(),
  })

  const evolucion = evolucionQuery.data?.puntos ?? []
  const diagnostico = diagnosticoQuery.data ?? null
  const calidad = calidadQuery.data ?? null

  const variacionDia = useMemo(
    () => variacionDiaCartera(rendimientoPorTicker, monedaSeleccionada),
    [rendimientoPorTicker, monedaSeleccionada],
  )

  const topPosiciones = rendimientoPorTicker.slice(0, 5)
  // El peso se mide contra el mismo total que muestra el valor de arriba, no contra la suma de las
  // filas: si alguna posición quedó afuera del total, las barras no inventan un 100% distinto.
  const valorTotal = monedaSeleccionada === 'ARS' ? resumen?.valor_actual_ars : resumen?.valor_actual_usd

  return (
    <div className="pb-4">
      <ScreenHeader title="Resumen" />
      <CarterasChips carteras={carteras} seleccionada={carteraSeleccionada} onSelect={setCarteraSeleccionada} />

      {loading ? (
        <SkeletonPantalla />
      ) : (
        <>
          <HeroValorCard
            resumen={resumen}
            moneda={monedaSeleccionada}
            evolucion={evolucion}
            periodo={periodo}
            onPeriodo={setPeriodo}
            cargandoSerie={evolucionQuery.isFetching}
            variacionDia={variacionDia}
          />
          <KpiGrid resumen={resumen} moneda={monedaSeleccionada} />

          <QueryBoundary
            isLoading={diagnosticoQuery.isLoading || calidadQuery.isLoading}
            error={diagnosticoQuery.error ?? calidadQuery.error}
            onRetry={() => {
              void diagnosticoQuery.refetch()
              void calidadQuery.refetch()
            }}
            fallback={null}
          >
            <ParaMirarHoy
              diagnostico={diagnostico}
              calidad={calidad}
              posiciones={rendimientoPorTicker}
              watchlist={watchlist}
              umbralProximidad={umbralProximidad}
            />
            <EstadoGeneral diagnostico={diagnostico} calidad={calidad} />
          </QueryBoundary>

          <QueSeMovioHoy variacionDia={variacionDia} moneda={monedaSeleccionada} />

          <div className="flex items-center justify-between mb-1">
            <h3 className="text-strong font-bold text-app-text">Tus posiciones</h3>
            {rendimientoPorTicker.length > 5 && (
              <button
                onClick={() => navigate('/posiciones')}
                className="group inline-flex items-center gap-0.5 min-h-9 text-body font-semibold text-app-accent transition-colors duration-150 hover:text-blue-300"
              >
                Ver las {rendimientoPorTicker.length}
                <Icon name="chevron" className="w-3.5 h-3.5 -rotate-90 transition-transform duration-150 group-hover:translate-x-0.5" />
              </button>
            )}
          </div>
          {topPosiciones.length === 0 ? (
            <EmptyState
              ilustracion="planta"
              emoji="🌱"
              title="Sin posiciones activas"
              description="Todavía no hay tenencias para esta cartera. Cuando cargues una compra en el Sheet, aparece acá."
            />
          ) : (
            <div className="bg-app-surface border border-app-border rounded-2xl px-3.5">
              {topPosiciones.map(item => {
                const valor = monedaSeleccionada === 'ARS' ? item.valor_actual_ars : item.valor_actual_usd
                return (
                  <PosicionRow
                    key={item.ticker}
                    item={item}
                    moneda={monedaSeleccionada}
                    alerta={estadoAlerta(item, umbralProximidad)}
                    peso={valorTotal && valorTotal > 0 ? valor / valorTotal : null}
                    onClick={() => navigate(`/ticker/${encodeURIComponent(item.ticker)}`)}
                  />
                )
              })}
            </div>
          )}

          <h3 className="text-strong font-bold text-app-text mb-2 mt-5">
            <InfoTooltip term="benchmark" label="Contra el mercado (en pesos)" />
          </h3>
          {resumen && <AlternativasCard resumen={resumen} conConclusion />}
          <button
            onClick={() => navigate('/benchmarks-comparacion')}
            className="group inline-flex items-center gap-1 min-h-9 mt-1 text-body font-semibold text-app-accent transition-colors duration-150 hover:text-blue-300"
          >
            Comparar con más referencias
            <Icon name="chevron" className="w-3.5 h-3.5 -rotate-90 transition-transform duration-150 group-hover:translate-x-0.5" />
          </button>

          {/* Simulador de escenarios */}
          <button
            onClick={() => navigate('/simulador')}
            className="group w-full text-left bg-app-surface border border-dashed border-app-border rounded-2xl p-3.5 mt-4 transition-[border-color,box-shadow,transform] duration-150 hover:border-app-accent/50 hover:shadow-[0_6px_24px_-12px_rgba(59,130,246,0.45)] hover:-translate-y-px active:translate-y-0 active:scale-[0.99]"
          >
            <div className="flex items-center gap-3.5">
              {/* Ilustración decorativa: una serie que se bifurca en dos escenarios. */}
              <svg viewBox="0 0 64 64" aria-hidden="true" className="w-14 h-14 shrink-0 rounded-[14px] bg-app-surface-2">
                <path d="M10 46L22 36l8 4 14-16" fill="none" stroke="#3b82f6" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M44 24l10-6" fill="none" stroke="#3b82f6" strokeWidth="2.5" strokeLinecap="round" strokeDasharray="2 4" />
                <path d="M44 24l10 10" fill="none" stroke="#f59e0b" strokeWidth="2.5" strokeLinecap="round" strokeDasharray="2 4" />
                <circle cx="44" cy="24" r="3.5" fill="#0a0e18" stroke="#f8fafc" strokeWidth="2" />
              </svg>
              <div className="flex-1 min-w-0">
                <div className="text-caption font-semibold text-app-text">
                  ¿Qué pasaría si...? <span aria-hidden="true">🔮</span>
                </div>
                <div className="text-label text-app-text-dim mt-0.5">Simula escenarios sin tocar la cartera</div>
              </div>
              <Icon
                name="chevron"
                className="w-4 h-4 -rotate-90 text-app-text-dim transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-app-text"
              />
            </div>
          </button>
        </>
      )}
    </div>
  )
}
