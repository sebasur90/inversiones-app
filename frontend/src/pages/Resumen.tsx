import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useInversionesContext } from '../context/InversionesContext'
import { getEvolucionInversiones, getDiagnostico, getCalidadDatos } from '../api'
import { qk } from '../api/queryClient'
import { Icon } from '../components/icons/Icons'
import ScreenHeader from '../components/layout/ScreenHeader'
import HeroValorCard from '../components/inversiones/HeroValorCard'
import KpiGrid from '../components/inversiones/KpiGrid'
import CarterasScroll from '../components/inversiones/CarterasScroll'
import PosicionRow from '../components/inversiones/PosicionRow'
import { estadoAlerta } from '../utils/alertasPrecio'
import RequiereAtencion from '../components/inversiones/RequiereAtencion'
import OportunidadesCompra from '../components/inversiones/OportunidadesCompra'
import EmptyState from '../components/ui/EmptyState'
import Card from '../components/ui/Card'
import ComparacionChart from '../components/charts/ComparacionChart'
import InfoTooltip from '../help/components/InfoTooltip'
import QueryBoundary from '../components/ui/QueryBoundary'
import SkeletonPantalla from '../components/ui/Skeleton'

export default function Resumen() {
  const navigate = useNavigate()
  const { carteras, carteraSeleccionada, setCarteraSeleccionada, monedaSeleccionada, resumen, rendimientoPorTicker, watchlist, umbralProximidad, loading } =
    useInversionesContext()

  // Sin `syncVersion` en las dependencias: sincronizar invalida la caché de queries y estas
  // tres se vuelven a pedir solas.
  const evolucionQuery = useQuery({
    queryKey: qk.evolucion(carteraSeleccionada),
    queryFn: () => getEvolucionInversiones(carteraSeleccionada),
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

  const topPosiciones = rendimientoPorTicker.slice(0, 5)

  return (
    <div className="pb-4">
      <ScreenHeader title="Resumen" />

      {loading ? (
        <SkeletonPantalla />
      ) : (
        <>
          <HeroValorCard resumen={resumen} moneda={monedaSeleccionada} evolucion={evolucion} />
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
            <RequiereAtencion
              diagnostico={diagnostico}
              calidad={calidad}
              posiciones={rendimientoPorTicker}
              umbralProximidad={umbralProximidad}
            />

            <OportunidadesCompra watchlist={watchlist} umbralProximidad={umbralProximidad} />

          {/* Los dos scores, en una fila: el detalle de lo que los mueve ya está arriba. */}
          <div className="grid grid-cols-2 gap-2 mb-4 mt-1">
            {diagnostico && (
              <button
                onClick={() => navigate('/diagnostico')}
                className="text-left bg-app-surface border border-app-border rounded-2xl p-3 hover:border-app-border-soft transition-colors"
              >
                <div className="text-label font-bold uppercase tracking-wide text-app-text-dim mb-0.5">Salud de cartera</div>
                <div className="font-display text-metric font-semibold text-app-text">
                  {diagnostico.salud.score_total !== null ? Math.round(diagnostico.salud.score_total) : '—'}
                  <span className="text-body text-app-text-dim">/100</span>
                </div>
                <div className="text-caption text-app-text-dim">
                  {diagnostico.hallazgos.length} hallazgo{diagnostico.hallazgos.length !== 1 ? 's' : ''}
                  <Icon name="chevron" className="w-3.5 h-3.5 inline-block -rotate-90 ml-0.5" />
                </div>
              </button>
            )}

            {calidad?.ultimo_sync && (
              <button
                onClick={() => navigate('/calidad-datos')}
                className="text-left bg-app-surface border border-app-border rounded-2xl p-3 hover:border-app-border-soft transition-colors"
              >
                <div className="text-label font-bold uppercase tracking-wide text-app-text-dim mb-0.5">Calidad de datos</div>
                <div className="font-display text-metric font-semibold text-app-text">
                  {calidad.ultimo_sync.health_score}
                  <span className="text-body text-app-text-dim">/100</span>
                </div>
                <div className="text-caption text-app-text-dim">
                  {calidad.issues.length} problema{calidad.issues.length !== 1 ? 's' : ''}
                  <Icon name="chevron" className="w-3.5 h-3.5 inline-block -rotate-90 ml-0.5" />
                </div>
              </button>
            )}
            </div>
          </QueryBoundary>

          <div className="flex items-center justify-between mb-2.5 mt-1">
            <h3 className="text-body font-bold text-app-text">Carteras</h3>
          </div>
          <CarterasScroll carteras={carteras} seleccionada={carteraSeleccionada} onSelect={setCarteraSeleccionada} />

          {/* Simulador de escenarios */}
          <button
            onClick={() => navigate('/simulador')}
            className="w-full text-left bg-app-surface border border-app-border rounded-2xl p-3.5 mb-4 mt-5 hover:border-app-gold/50 transition-colors"
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="text-caption font-semibold text-app-text">¿Qué pasaría si...?</div>
                <div className="text-label text-app-text-secondary mt-0.5">Simula escenarios sin tocar la cartera</div>
              </div>
              <Icon name="chevron" className="w-4 h-4 text-app-text-dim" />
            </div>
          </button>

          <h3 className="text-body font-bold text-app-text mb-2.5 mt-5">
            <InfoTooltip term="benchmark" label="Cartera vs. benchmarks (ARS)" />
          </h3>
          <Card>
            <ComparacionChart resumen={resumen} />
          </Card>

          <div className="flex items-center justify-between mb-1 mt-5">
            <h3 className="text-body font-bold text-app-text">Posiciones</h3>
            {rendimientoPorTicker.length > 5 && (
              <button onClick={() => navigate('/posiciones')} className="text-label font-semibold text-app-text-dim">
                Ver todas
              </button>
            )}
          </div>
          {topPosiciones.length === 0 ? (
            <EmptyState title="Sin posiciones activas" description="Todavía no hay tenencias para esta cartera." />
          ) : (
            <div>
              {topPosiciones.map(item => (
                <PosicionRow
                  key={item.ticker}
                  item={item}
                  moneda={monedaSeleccionada}
                  alerta={estadoAlerta(item, umbralProximidad)}
                  onClick={() => navigate(`/ticker/${encodeURIComponent(item.ticker)}`)}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
