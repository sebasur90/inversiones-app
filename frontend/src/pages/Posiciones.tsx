import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import type { RendimientoPorTickerItem } from '../api'
import ScreenHeader from '../components/layout/ScreenHeader'
import PosicionRow from '../components/inversiones/PosicionRow'
import EmptyState from '../components/ui/EmptyState'
import IconButton from '../components/ui/IconButton'
import Segmented from '../components/ui/Segmented'
import InfoTooltip from '../help/components/InfoTooltip'
import { Icon } from '../components/icons/Icons'
import { descargarCSV, sufijoFechaHoy } from '../utils/csv'
import { esEstadoDeStopLoss, estadoAlerta, type EstadoAlerta } from '../utils/alertasPrecio'
import SkeletonPantalla from '../components/ui/Skeleton'

const COLUMNAS_POSICIONES = [
  'Ticker', 'Nombre', 'Cantidad Actual', 'Precio Promedio', 'Precio Actual',
  'Rendimiento USD %', 'Rendimiento ARS %', 'Rendimiento ARS Real %',
  'Valor Invertido (USD)', 'Valor Actual (USD)', 'Valor Invertido (ARS)', 'Valor Actual (ARS)',
  'Precio Objetivo', '% a Objetivo', 'Precio Stop Loss', '% a Stop Loss',
]

function filasPosiciones(items: RendimientoPorTickerItem[]) {
  const pct = (v: number | null | undefined) => (v != null ? (v * 100).toFixed(2) : '')
  return items.map(it => [
    it.ticker, it.nombre, it.cantidad_actual, it.precio_promedio, it.precio_actual,
    pct(it.rendimiento_simple_usd), pct(it.rendimiento_simple_ars), pct(it.rendimiento_simple_ars_real),
    it.valor_invertido_usd, it.valor_actual_usd, it.valor_invertido_ars, it.valor_actual_ars,
    it.precio_objetivo ?? '', pct(it.pct_a_objetivo), it.precio_stop_loss ?? '', pct(it.pct_a_stop_loss),
  ])
}

/** Filtro por alerta de precio. Se refleja en la query string para poder linkear desde el Resumen. */
type FiltroAlerta = 'todas' | 'con_alerta' | 'stop_loss' | 'objetivo'

const FILTROS: FiltroAlerta[] = ['todas', 'con_alerta', 'stop_loss', 'objetivo']

const ETIQUETA_FILTRO: Record<FiltroAlerta, string> = {
  todas: 'Todas',
  con_alerta: 'Con alerta',
  stop_loss: 'Stop loss',
  objetivo: 'Objetivo',
}

function parseFiltro(crudo: string | null): FiltroAlerta {
  return FILTROS.includes(crudo as FiltroAlerta) ? (crudo as FiltroAlerta) : 'todas'
}

function pasaFiltro(filtro: FiltroAlerta, estado: EstadoAlerta | null): boolean {
  if (filtro === 'todas') return true
  if (estado === null) return false
  if (filtro === 'con_alerta') return true
  return filtro === 'stop_loss' ? esEstadoDeStopLoss(estado) : !esEstadoDeStopLoss(estado)
}

export default function Posiciones() {
  const navigate = useNavigate()
  const { rendimientoPorTicker, carteraSeleccionada, monedaSeleccionada, umbralProximidad, loading } =
    useInversionesContext()
  const [busqueda, setBusqueda] = useState('')
  const [searchParams, setSearchParams] = useSearchParams()
  const filtro = parseFiltro(searchParams.get('alerta'))

  function cambiarFiltro(nuevo: FiltroAlerta) {
    // `replace`: cambiar de filtro no debería agregar una entrada al historial y obligar a
    // varios "atrás" para volver a la pantalla anterior.
    setSearchParams(nuevo === 'todas' ? {} : { alerta: nuevo }, { replace: true })
  }

  const alertaPorTicker = useMemo(() => {
    const mapa = new Map<string, EstadoAlerta>()
    for (const it of rendimientoPorTicker) {
      const estado = estadoAlerta(it, umbralProximidad)
      if (estado !== null) mapa.set(it.ticker, estado)
    }
    return mapa
  }, [rendimientoPorTicker, umbralProximidad])

  // Cuántas posiciones caen en cada filtro, para mostrarlo en la propia solapa y no obligar
  // a probarlas una por una.
  const conteoPorFiltro = useMemo(() => {
    const conteo: Record<FiltroAlerta, number> = { todas: rendimientoPorTicker.length, con_alerta: 0, stop_loss: 0, objetivo: 0 }
    for (const estado of alertaPorTicker.values()) {
      conteo.con_alerta += 1
      if (esEstadoDeStopLoss(estado)) conteo.stop_loss += 1
      else conteo.objetivo += 1
    }
    return conteo
  }, [rendimientoPorTicker.length, alertaPorTicker])

  const filtrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase()
    return rendimientoPorTicker.filter(it => {
      if (!pasaFiltro(filtro, alertaPorTicker.get(it.ticker) ?? null)) return false
      if (!q) return true
      return it.ticker.toLowerCase().includes(q) || it.nombre.toLowerCase().includes(q)
    })
  }, [rendimientoPorTicker, busqueda, filtro, alertaPorTicker])

  const opcionesFiltro = FILTROS.map(f => ({
    value: f,
    label: f === 'todas' ? ETIQUETA_FILTRO[f] : `${ETIQUETA_FILTRO[f]} · ${conteoPorFiltro[f]}`,
  }))

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
            className="flex-1 bg-transparent outline-none text-caption text-app-text placeholder:text-app-text-faint"
          />
        </div>
        <IconButton
          onClick={() =>
            descargarCSV(
              `inversiones-rendimiento-${carteraSeleccionada || 'consolidado'}-${sufijoFechaHoy()}`,
              COLUMNAS_POSICIONES,
              filasPosiciones(filtrados),
            )
          }
          aria-label="Exportar CSV"
          disabled={filtrados.length === 0}
        >
          <Icon name="download" className="w-4 h-4" />
        </IconButton>
      </div>

      <div className="flex items-center gap-1.5 mb-3">
        <div className="min-w-0 flex-1">
          <Segmented options={opcionesFiltro} value={filtro} onChange={cambiarFiltro} />
        </div>
        <InfoTooltip term="posiciones_filtro_alerta" />
      </div>

      {loading ? (
        <SkeletonPantalla />
      ) : filtrados.length === 0 ? (
        <EmptyState
          title={
            filtro === 'todas'
              ? 'No hay posiciones activas'
              : filtro === 'stop_loss'
                ? 'Ninguna posición cerca de su stop-loss'
                : filtro === 'objetivo'
                  ? 'Ninguna posición cerca de su objetivo'
                  : 'Ninguna posición cerca de su stop-loss ni de su objetivo'
          }
        />
      ) : (
        <div>
          {filtrados.map(item => (
            <PosicionRow
              key={item.ticker}
              item={item}
              moneda={monedaSeleccionada}
              alerta={alertaPorTicker.get(item.ticker) ?? null}
              onClick={() => navigate(`/ticker/${encodeURIComponent(item.ticker)}`)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
