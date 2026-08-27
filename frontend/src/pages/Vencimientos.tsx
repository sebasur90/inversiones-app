import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getVencimientos, type VencimientoItem } from '../api'
import ScreenHeader from '../components/layout/ScreenHeader'
import VencimientoRow from '../components/inversiones/VencimientoRow'
import EmptyState from '../components/ui/EmptyState'
import InfoTooltip from '../help/components/InfoTooltip'

export default function Vencimientos() {
  const navigate = useNavigate()
  const { carteraSeleccionada, monedaSeleccionada, syncVersion } = useInversionesContext()
  const [items, setItems] = useState<VencimientoItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelado = false
    setLoading(true)
    getVencimientos(carteraSeleccionada)
      .then(data => {
        if (!cancelado) setItems(data)
      })
      .catch(() => {
        if (!cancelado) setItems([])
      })
      .finally(() => {
        if (!cancelado) setLoading(false)
      })
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada, syncVersion])

  return (
    <div className="pb-4">
      <ScreenHeader title="Vencimientos" onBack={() => navigate(-1)} />

      <div className="px-4 mb-4 pt-2">
        <div className="text-[12px] text-app-text-dim space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-app-text">Días restantes</span>
            <InfoTooltip term="vencimientos_dias_restantes" />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-app-text">Fecha de vencimiento</span>
            <InfoTooltip term="vencimientos_fecha_vencimiento" />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-app-text">Valor actual</span>
            <InfoTooltip term="vencimientos_valor_actual" />
          </div>
        </div>
      </div>

      {loading ? (
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      ) : items.length === 0 ? (
        <EmptyState title="Sin vencimientos" description="No hay instrumentos con fecha de vencimiento en esta cartera." />
      ) : (
        <div>
          {items.map(item => (
            <VencimientoRow key={item.ticker} item={item} moneda={monedaSeleccionada} />
          ))}
        </div>
      )}
    </div>
  )
}
