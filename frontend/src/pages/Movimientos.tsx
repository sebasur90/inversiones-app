import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import dayjs from 'dayjs'
import { useInversionesContext } from '../context/InversionesContext'
import ScreenHeader from '../components/layout/ScreenHeader'
import MovimientoRow from '../components/inversiones/MovimientoRow'
import Chip from '../components/ui/Chip'
import EmptyState from '../components/ui/EmptyState'
import BotonExportarCsv from '../components/ui/BotonExportarCsv'
import { Icon } from '../components/icons/Icons'
import SkeletonPantalla from '../components/ui/Skeleton'

export default function Movimientos() {
  const navigate = useNavigate()
  const { movimientos, loading } = useInversionesContext()
  const [searchParams, setSearchParams] = useSearchParams()
  const tickerFiltro = searchParams.get('ticker')
  const [busqueda, setBusqueda] = useState('')

  const filtrados = useMemo(
    () =>
      movimientos.filter(
        m =>
          (!tickerFiltro || m.ticker === tickerFiltro) &&
          (!busqueda || m.ticker.toLowerCase().includes(busqueda.toLowerCase()) || m.cartera.toLowerCase().includes(busqueda.toLowerCase())),
      ),
    [movimientos, tickerFiltro, busqueda],
  )

  const grupos = useMemo(() => {
    const out: { fecha: string; items: typeof filtrados }[] = []
    for (const m of filtrados) {
      const ultimo = out[out.length - 1]
      if (ultimo && ultimo.fecha === m.fecha) {
        ultimo.items.push(m)
      } else {
        out.push({ fecha: m.fecha, items: [m] })
      }
    }
    return out
  }, [filtrados])

  const labelFecha = (fecha: string) => {
    const d = dayjs(fecha)
    if (d.isSame(dayjs(), 'day')) return 'Hoy'
    return d.format('D MMM')
  }

  return (
    <div className="pb-4">
      <ScreenHeader title="Movimientos" />

      <div className="flex items-center justify-between gap-3 mb-3">
        <button onClick={() => navigate('/comisiones')} className="inline-flex items-center gap-1 text-label font-semibold text-app-text-dim">
          Ver comisiones pagadas →
        </button>
        {filtrados.length > 0 && (
          <BotonExportarCsv
            nombre="movimientos"
            encabezados={['Fecha', 'Cartera', 'Ticker', 'Tipo', 'Cantidad', 'Precio', 'Moneda', 'Comisión']}
            filas={() =>
              filtrados.map(m => [
                m.fecha, m.cartera, m.ticker, m.tipo_movimiento,
                m.cantidad, m.precio, m.moneda, m.comision,
              ])
            }
          />
        )}
      </div>

      <div className="flex items-center gap-2 bg-app-surface border border-app-border rounded-xl h-10 px-3 mb-3">
        <Icon name="search" className="w-4 h-4 text-app-text-faint" />
        <input
          value={busqueda}
          onChange={e => setBusqueda(e.target.value)}
          placeholder="Buscar ticker o cartera…"
          className="flex-1 bg-transparent outline-none text-caption text-app-text placeholder:text-app-text-faint"
        />
      </div>

      {tickerFiltro && (
        <div className="mb-3">
          <Chip onRemove={() => setSearchParams(p => { p.delete('ticker'); return p })}>{tickerFiltro}</Chip>
        </div>
      )}

      {loading ? (
        <SkeletonPantalla />
      ) : grupos.length === 0 ? (
        <EmptyState title="Sin movimientos" description="No hay movimientos que coincidan con el filtro." />
      ) : (
        grupos.map(grupo => (
          <div key={grupo.fecha}>
            <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mt-3.5 mb-1">{labelFecha(grupo.fecha)}</div>
            {grupo.items.map(mov => (
              <MovimientoRow key={mov.id} mov={mov} />
            ))}
          </div>
        ))
      )}
    </div>
  )
}
