import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getEvolucionInversiones, getDiagnostico, getCalidadDatos, type EvolucionPunto, type DiagnosticoOut, type CalidadDatosOut } from '../api'
import { Icon } from '../components/icons/Icons'
import ScreenHeader from '../components/layout/ScreenHeader'
import HeroValorCard from '../components/inversiones/HeroValorCard'
import KpiGrid from '../components/inversiones/KpiGrid'
import CarterasScroll from '../components/inversiones/CarterasScroll'
import PosicionRow from '../components/inversiones/PosicionRow'
import EmptyState from '../components/ui/EmptyState'
import Card from '../components/ui/Card'
import ComparacionChart from '../components/charts/ComparacionChart'
import InfoTerm from '../components/ui/InfoTerm'

export default function Resumen() {
  const navigate = useNavigate()
  const { carteras, carteraSeleccionada, setCarteraSeleccionada, monedaSeleccionada, resumen, rendimientoPorTicker, loading } =
    useInversionesContext()
  const [evolucion, setEvolucion] = useState<EvolucionPunto[]>([])
  const [diagnostico, setDiagnostico] = useState<DiagnosticoOut | null>(null)
  const [calidad, setCalidad] = useState<CalidadDatosOut | null>(null)

  useEffect(() => {
    let cancelado = false
    getEvolucionInversiones(carteraSeleccionada)
      .then(out => {
        if (!cancelado) setEvolucion(out.puntos)
      })
      .catch(() => {
        if (!cancelado) setEvolucion([])
      })
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada])

  useEffect(() => {
    let cancelado = false
    getDiagnostico(carteraSeleccionada)
      .then(d => {
        if (!cancelado) setDiagnostico(d)
      })
      .catch(() => {
        if (!cancelado) setDiagnostico(null)
      })
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada])

  useEffect(() => {
    let cancelado = false
    getCalidadDatos()
      .then(c => {
        if (!cancelado) setCalidad(c)
      })
      .catch(() => {
        if (!cancelado) setCalidad(null)
      })
    return () => {
      cancelado = true
    }
  }, [])

  const topPosiciones = rendimientoPorTicker.slice(0, 5)

  return (
    <div className="pb-4">
      <ScreenHeader title="Resumen" />

      {loading ? (
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      ) : (
        <>
          <HeroValorCard resumen={resumen} moneda={monedaSeleccionada} evolucion={evolucion} />
          <KpiGrid resumen={resumen} moneda={monedaSeleccionada} />

          {diagnostico && (
            <button
              onClick={() => navigate('/diagnostico')}
              className="w-full text-left bg-app-surface border border-app-border rounded-2xl p-3.5 mb-4 mt-1 flex items-center justify-between gap-3 hover:border-app-border-soft transition-colors"
            >
              <div>
                <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-0.5">Salud de cartera</div>
                <div className="font-display text-[22px] font-semibold text-app-text">
                  {diagnostico.salud.score_total !== null ? Math.round(diagnostico.salud.score_total) : '—'}
                  <span className="text-[13px] text-app-text-dim">/100</span>
                </div>
              </div>
              <div className="text-right">
                <div className="text-[11.5px] font-semibold text-app-text-dim">
                  {diagnostico.hallazgos.length} hallazgo{diagnostico.hallazgos.length !== 1 ? 's' : ''}
                </div>
                <Icon name="chevron" className="w-4 h-4 text-app-text-dim inline-block mt-1" />
              </div>
            </button>
          )}

          {calidad?.ultimo_sync && (
            <button
              onClick={() => navigate('/calidad-datos')}
              className="w-full text-left bg-app-surface border border-app-border rounded-2xl p-3.5 mb-4 flex items-center justify-between gap-3 hover:border-app-border-soft transition-colors"
            >
              <div>
                <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-0.5">Calidad de datos</div>
                <div className="font-display text-[22px] font-semibold text-app-text">
                  {calidad.ultimo_sync.health_score}
                  <span className="text-[13px] text-app-text-dim">/100</span>
                </div>
              </div>
              <div className="text-right">
                <div className="text-[11.5px] font-semibold text-app-text-dim">
                  {calidad.issues.length} problema{calidad.issues.length !== 1 ? 's' : ''}
                </div>
                <Icon name="chevron" className="w-4 h-4 text-app-text-dim inline-block mt-1" />
              </div>
            </button>
          )}

          <div className="flex items-center justify-between mb-2.5 mt-1">
            <h3 className="text-[13.5px] font-bold text-app-text">Carteras</h3>
          </div>
          <CarterasScroll carteras={carteras} seleccionada={carteraSeleccionada} onSelect={setCarteraSeleccionada} />

          <h3 className="text-[13.5px] font-bold text-app-text mb-2.5 mt-5">
            <InfoTerm term="benchmark" label="Cartera vs. benchmarks (ARS)" />
          </h3>
          <Card>
            <ComparacionChart resumen={resumen} />
          </Card>

          <div className="flex items-center justify-between mb-1 mt-5">
            <h3 className="text-[13.5px] font-bold text-app-text">Posiciones</h3>
            {rendimientoPorTicker.length > 5 && (
              <button onClick={() => navigate('/posiciones')} className="text-[11px] font-semibold text-app-text-dim">
                Ver todas
              </button>
            )}
          </div>
          {topPosiciones.length === 0 ? (
            <EmptyState title="Sin posiciones activas" description="Todavía no hay tenencias para esta cartera." />
          ) : (
            <div>
              {topPosiciones.map(item => (
                <PosicionRow key={item.ticker} item={item} moneda={monedaSeleccionada} onClick={() => navigate(`/ticker/${encodeURIComponent(item.ticker)}`)} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
