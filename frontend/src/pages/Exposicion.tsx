import { useMemo, useState } from 'react'
import { useInversionesContext } from '../context/InversionesContext'
import type { ExposicionItem } from '../api'
import { CHART_COLORS, formatARS, formatUSD } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import Donut from '../components/charts/Donut'
import EmptyState from '../components/ui/EmptyState'

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
  const { exposicion, monedaSeleccionada, loading } = useInversionesContext()
  const [ejeActivo, setEjeActivo] = useState<string | null>(null)
  const esARS = monedaSeleccionada === 'ARS'
  const formatMoneda = esARS ? formatARS : formatUSD

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

      {loading ? (
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      ) : exposicion.ejes.length === 0 ? (
        <EmptyState title="Sin exposición para mostrar" description="Sincronizá tu Sheet o elegí otra cartera." />
      ) : (
        <>
          <Segmented
            options={exposicion.ejes.map(e => ({ value: e.eje, label: e.eje }))}
            value={eje?.eje ?? exposicion.ejes[0].eje}
            onChange={setEjeActivo}
          />

          <div className="my-4">
            <Donut
              slices={items.map(i => ({ etiqueta: i.etiqueta, porcentaje: i.porcentaje }))}
              centerLabel="Total"
              centerValue={formatMoneda(total)}
            />
          </div>

          <h3 className="text-[13.5px] font-bold text-app-text mb-2.5">Detalle</h3>
          <div className="flex flex-col gap-2.5">
            {items.map((item, i) => (
              <div key={item.etiqueta}>
                <div className="flex justify-between items-baseline text-[11.5px] mb-1.5">
                  <span className="text-app-text">{item.etiqueta}</span>
                  <span className="font-mono font-bold text-app-text tabular-nums">{formatMoneda(esARS ? item.valor_ars : item.valor_usd)}</span>
                </div>
                <div className="h-1.5 rounded-full bg-app-surface-2 overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${item.porcentaje}%`, background: CHART_COLORS[i % CHART_COLORS.length] }}
                  />
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
