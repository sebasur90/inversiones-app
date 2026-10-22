import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import type { ExposicionItem } from '../api'
import { CHART_COLORS } from '../utils'
import { useFormatoFijo } from '../hooks/useFormatoMoneda'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import Donut from '../components/charts/Donut'
import EmptyState from '../components/ui/EmptyState'
import AvisosValuacion from '../components/inversiones/AvisosValuacion'
import TituloSeccion from '../components/ui/TituloSeccion'
import BotonAcceso from '../components/ui/BotonAcceso'
import InfoTooltip from '../help/components/InfoTooltip'
import SkeletonPantalla from '../components/ui/Skeleton'

function bucketizeTop10(items: ExposicionItem[]): ExposicionItem[] {
  if (items.length <= 10) return items
  const top = items.slice(0, 10)
  const resto = items.slice(10)
  return [
    ...top,
    {
      etiqueta: 'Otros',
      valor_usd: resto.reduce((acc, i) => acc + i.valor_usd, 0),
      valor_ars: resto.reduce((acc, i) => acc + i.valor_ars, 0),
      porcentaje: resto.reduce((acc, i) => acc + i.porcentaje, 0),
    },
  ]
}

export default function Exposicion() {
  const navigate = useNavigate()
  const { exposicion, monedaSeleccionada, loading } = useInversionesContext()
  const [ejeActivo, setEjeActivo] = useState<string | null>(null)
  const esARS = monedaSeleccionada === 'ARS'
  const { monto: formatMoneda } = useFormatoFijo(esARS ? 'ARS' : 'USD')

  const eje = useMemo(() => {
    if (exposicion.ejes.length === 0) return null
    return exposicion.ejes.find(e => e.eje === ejeActivo) ?? exposicion.ejes[0]
  }, [exposicion.ejes, ejeActivo])

  const items = useMemo(() => {
    if (!eje) return []
    const base = eje.eje === 'Ticker' ? bucketizeTop10(eje.items) : eje.items
    return [...base].sort((a, b) => b.porcentaje - a.porcentaje)
  }, [eje])

  const total = items.reduce((acc, i) => acc + (esARS ? i.valor_ars : i.valor_usd), 0)

  return (
    <div className="pb-4">
      <ScreenHeader title="Exposición" />

      <div className="flex flex-wrap gap-2 mb-4">
        <BotonAcceso icono="pie" onClick={() => navigate('/descomposicion')}>Descomposición jerárquica</BotonAcceso>
        <span className="inline-flex items-center gap-1">
          <BotonAcceso icono="calendar" colorIcono="text-app-warn" onClick={() => navigate('/vencimientos')}>Calendario de vencimientos</BotonAcceso>
          <InfoTooltip term="exposicion_vencimientos" />
        </span>
        <span className="inline-flex items-center gap-1">
          <BotonAcceso icono="scale" colorIcono="text-app-violet" onClick={() => navigate('/contribucion')}>Contribución y concentración</BotonAcceso>
          <InfoTooltip term="exposicion_contribucion_concentracion" />
        </span>
      </div>

      {loading ? (
        <SkeletonPantalla />
      ) : exposicion.ejes.length === 0 ? (
        <EmptyState ilustracion="planta" emoji="🌱" title="Sin exposición para mostrar" description="Sincronizá tu Sheet o elegí otra cartera." />
      ) : (
        <>
          <div className="flex items-center gap-2 mb-3">
            <div className="flex-1">
              <Segmented
                options={exposicion.ejes.map(e => ({ value: e.eje, label: e.eje }))}
                value={eje?.eje ?? exposicion.ejes[0].eje}
                onChange={setEjeActivo}
              />
            </div>
            <InfoTooltip term="exposicion_eje" />
          </div>

          <div className="my-4">
            <Donut
              slices={items.map(i => ({ etiqueta: i.etiqueta, porcentaje: i.porcentaje }))}
              centerLabel="Total"
              centerValue={formatMoneda(total)}
            />
          </div>

          <TituloSeccion icono="list" tono="accent" className="mb-2.5">
            <span className="inline-flex items-center gap-1.5">Detalle <InfoTooltip term="exposicion_porcentaje" /></span>
          </TituloSeccion>
          <div className="animate-fade-in flex flex-col gap-3.5 bg-app-surface border border-app-border rounded-2xl p-4">
            {items.map((item, i) => {
              const color = CHART_COLORS[i % CHART_COLORS.length]
              return (
                <div key={item.etiqueta}>
                  <div className="flex justify-between items-center gap-3 text-caption mb-1.5">
                    <div className="flex items-center gap-2 min-w-0">
                      <span aria-hidden="true" className="w-2.5 h-2.5 rounded-[3px] shrink-0" style={{ background: color }} />
                      <span className="text-app-text truncate">{item.etiqueta}</span>
                      {item.etiqueta === 'Otros' && <InfoTooltip term="exposicion_ticker_top10" />}
                    </div>
                    <div className="flex items-baseline gap-2 shrink-0">
                      <span className="font-mono font-bold text-app-text tabular-nums">{formatMoneda(esARS ? item.valor_ars : item.valor_usd)}</span>
                      <span className="font-mono text-label text-app-text-dim tabular-nums w-10 text-right">{item.porcentaje.toFixed(1).replace('.', ',')}%</span>
                    </div>
                  </div>
                  <div className="h-1.5 rounded-full bg-app-surface-2 overflow-hidden">
                    <div className="h-full rounded-full transition-[width] duration-200" style={{ width: `${item.porcentaje}%`, background: color }} />
                  </div>
                </div>
              )
            })}
          </div>

          <AvisosValuacion avisos={exposicion.avisos} moneda={esARS ? 'ARS' : 'USD'} />
        </>
      )}
    </div>
  )
}
