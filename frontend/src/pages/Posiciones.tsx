import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import type { RendimientoPorTickerItem } from '../api'
import ScreenHeader from '../components/layout/ScreenHeader'
import PosicionRow from '../components/inversiones/PosicionRow'
import EmptyState from '../components/ui/EmptyState'
import IconButton from '../components/ui/IconButton'
import { Icon } from '../components/icons/Icons'

function exportarCSV(items: RendimientoPorTickerItem[], cartera: string | null) {
  const headers = [
    'Ticker', 'Nombre', 'Cantidad Actual', 'Precio Promedio', 'Precio Actual',
    'Rendimiento USD %', 'Rendimiento ARS %', 'Rendimiento ARS Real %',
    'Valor Invertido (USD)', 'Valor Actual (USD)', 'Valor Invertido (ARS)', 'Valor Actual (ARS)',
  ]
  const rows = items.map(it => [
    it.ticker, it.nombre, it.cantidad_actual, it.precio_promedio, it.precio_actual,
    it.rendimiento_simple_usd != null ? (it.rendimiento_simple_usd * 100).toFixed(2) : '',
    it.rendimiento_simple_ars != null ? (it.rendimiento_simple_ars * 100).toFixed(2) : '',
    it.rendimiento_simple_ars_real != null ? (it.rendimiento_simple_ars_real * 100).toFixed(2) : '',
    it.valor_invertido_usd, it.valor_actual_usd, it.valor_invertido_ars, it.valor_actual_ars,
  ])
  const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const fecha = new Date().toISOString().slice(0, 10)
  a.download = `inversiones-rendimiento-${cartera || 'consolidado'}-${fecha}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export default function Posiciones() {
  const navigate = useNavigate()
  const { rendimientoPorTicker, carteraSeleccionada, monedaSeleccionada, loading } = useInversionesContext()
  const [busqueda, setBusqueda] = useState('')

  const filtrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase()
    if (!q) return rendimientoPorTicker
    return rendimientoPorTicker.filter(it => it.ticker.toLowerCase().includes(q) || it.nombre.toLowerCase().includes(q))
  }, [rendimientoPorTicker, busqueda])

  return (
    <div className="pb-4">
      <ScreenHeader title="Posiciones" onBack={() => navigate(-1)} />

      <div className="flex items-center gap-2 mb-3">
        <div className="flex-1 flex items-center gap-2 bg-app-surface border border-app-border rounded-xl h-10 px-3">
          <Icon name="search" className="w-4 h-4 text-app-text-faint" />
          <input
            value={busqueda}
            onChange={e => setBusqueda(e.target.value)}
            placeholder="Buscar ticker o nombre…"
            className="flex-1 bg-transparent outline-none text-[12.5px] text-app-text placeholder:text-app-text-faint"
          />
        </div>
        <IconButton onClick={() => exportarCSV(filtrados, carteraSeleccionada)} aria-label="Exportar CSV" disabled={filtrados.length === 0}>
          <Icon name="download" className="w-4 h-4" />
        </IconButton>
      </div>

      {loading ? (
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      ) : filtrados.length === 0 ? (
        <EmptyState title="No hay posiciones activas" />
      ) : (
        <div>
          {filtrados.map(item => (
            <PosicionRow key={item.ticker} item={item} moneda={monedaSeleccionada} onClick={() => navigate(`/ticker/${encodeURIComponent(item.ticker)}`)} />
          ))}
        </div>
      )}
    </div>
  )
}
