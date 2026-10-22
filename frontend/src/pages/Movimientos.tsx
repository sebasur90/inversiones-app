import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import dayjs from 'dayjs'
import { diaMes } from '../utils/fechas'
import { useInversionesContext } from '../context/InversionesContext'
import ScreenHeader from '../components/layout/ScreenHeader'
import MovimientoRow from '../components/inversiones/MovimientoRow'
import Chip from '../components/ui/Chip'
import Button from '../components/ui/Button'
import CampoBusqueda from '../components/ui/CampoBusqueda'
import EmptyState from '../components/ui/EmptyState'
import BotonExportarCsv from '../components/ui/BotonExportarCsv'
import { Icon } from '../components/icons/Icons'
import SkeletonPantalla from '../components/ui/Skeleton'

const PILDORA =
  'min-h-10 px-3.5 rounded-full bg-app-surface border border-app-border hover:border-white/25 hover:bg-app-surface-2'

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
    return diaMes(fecha)
  }

  const hayFiltro = busqueda.trim() !== '' || !!tickerFiltro

  return (
    <div className="pb-4">
      <ScreenHeader title="Movimientos" />

      <div className="flex items-center justify-between gap-2 mb-3">
        <button
          onClick={() => navigate('/comisiones')}
          className={`group inline-flex items-center gap-2 text-caption font-semibold text-app-text-dim transition-[background-color,border-color,color,transform] duration-150 hover:text-app-text active:scale-[0.97] ${PILDORA}`}
        >
          <Icon name="dollar" className="w-4 h-4 text-app-warn" />
          Comisiones pagadas
          <Icon name="chevron" className="w-3.5 h-3.5 -rotate-90 text-app-text-faint transition-transform duration-150 group-hover:translate-x-0.5" />
        </button>
        {filtrados.length > 0 && (
          <BotonExportarCsv
            nombre="movimientos"
            className={PILDORA}
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

      <div className="flex mb-3">
        <CampoBusqueda value={busqueda} onChange={setBusqueda} placeholder="Buscar ticker o cartera…" ariaLabel="Buscar ticker o cartera" />
      </div>

      {tickerFiltro && (
        <div className="mb-3">
          <Chip onRemove={() => setSearchParams(p => { p.delete('ticker'); return p })}>{tickerFiltro}</Chip>
        </div>
      )}

      {loading ? (
        <SkeletonPantalla />
      ) : grupos.length === 0 ? (
        // Con filtro o búsqueda activos el vacío ofrece salida; sin ellos, la cartera no tiene
        // movimientos todavía.
        hayFiltro ? (
          <EmptyState
            ilustracion="lupa"
            emoji="📭"
            title="Sin movimientos"
            description="No hay movimientos que coincidan con el filtro."
            action={
              <Button
                variant="outline"
                icon={<Icon name="close" className="w-4 h-4" />}
                onClick={() => {
                  setBusqueda('')
                  if (tickerFiltro) setSearchParams(p => { p.delete('ticker'); return p })
                }}
              >
                Quitar filtros
              </Button>
            }
          />
        ) : (
          <EmptyState
            ilustracion="planta"
            emoji="🌱"
            title="Todavía no hay movimientos"
            description="Tus compras, ventas y cobros aparecen acá apenas los cargues en el Sheet."
          />
        )
      ) : (
        <div className="animate-fade-in">
          {grupos.map(grupo => (
            <section key={grupo.fecha} className="mt-4 first:mt-0" aria-label={labelFecha(grupo.fecha)}>
              <div className="flex items-center justify-between px-0.5 mb-2">
                <h2 className="inline-flex items-center gap-1.5 text-label font-bold uppercase tracking-wide text-app-text-dim">
                  <Icon name="calendarDays" className="w-3.5 h-3.5" />
                  {labelFecha(grupo.fecha)}
                </h2>
                <span className="text-label text-app-text-faint">
                  {grupo.items.length} movimiento{grupo.items.length !== 1 ? 's' : ''}
                </span>
              </div>
              <div className="bg-app-surface border border-app-border rounded-2xl px-1.5">
                {grupo.items.map(mov => (
                  <MovimientoRow key={mov.id} mov={mov} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
