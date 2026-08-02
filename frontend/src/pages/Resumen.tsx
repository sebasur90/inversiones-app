import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getEvolucionInversiones, type EvolucionPunto } from '../api'
import ScreenHeader from '../components/layout/ScreenHeader'
import HeroValorCard from '../components/inversiones/HeroValorCard'
import KpiGrid from '../components/inversiones/KpiGrid'
import CarterasScroll from '../components/inversiones/CarterasScroll'
import PosicionRow from '../components/inversiones/PosicionRow'
import EmptyState from '../components/ui/EmptyState'
import Card from '../components/ui/Card'
import ComparacionChart from '../components/charts/ComparacionChart'

export default function Resumen() {
  const navigate = useNavigate()
  const { carteras, carteraSeleccionada, setCarteraSeleccionada, monedaSeleccionada, resumen, rendimientoPorTicker, loading } =
    useInversionesContext()
  const [evolucion, setEvolucion] = useState<EvolucionPunto[]>([])

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

          <div className="flex items-center justify-between mb-2.5 mt-1">
            <h3 className="text-[13.5px] font-bold text-app-text">Carteras</h3>
          </div>
          <CarterasScroll carteras={carteras} seleccionada={carteraSeleccionada} onSelect={setCarteraSeleccionada} />

          <h3 className="text-[13.5px] font-bold text-app-text mb-2.5 mt-5">Cartera vs. benchmarks (ARS)</h3>
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
