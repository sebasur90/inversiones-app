import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getVencimientos, type VencimientoItem } from '../api'
import ScreenHeader from '../components/layout/ScreenHeader'
import VencimientoRow from '../components/inversiones/VencimientoRow'
import EmptyState from '../components/ui/EmptyState'

export default function Vencimientos() {
  const navigate = useNavigate()
  const { carteraSeleccionada, monedaSeleccionada } = useInversionesContext()
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
  }, [carteraSeleccionada])

  return (
    <div className="pb-4">
      <ScreenHeader title="Vencimientos" onBack={() => navigate(-1)} />

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
