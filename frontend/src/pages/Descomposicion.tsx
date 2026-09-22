import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getDescomposicion, type DescomposicionNodo } from '../api'
import { qk } from '../api/queryClient'
import { CHART_COLORS, formatARS, formatUSD } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import Donut from '../components/charts/Donut'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import SkeletonPantalla from '../components/ui/Skeleton'
import BotonExportarCsv from '../components/ui/BotonExportarCsv'
import { Icon } from '../components/icons/Icons'
import InfoTooltip from '../help/components/InfoTooltip'

type Unidad = 'pct' | 'ars' | 'usd'

const OPCIONES_UNIDAD: { value: Unidad; label: string }[] = [
  { value: 'pct', label: '%' },
  { value: 'ars', label: 'ARS' },
  { value: 'usd', label: 'USD' },
]

function formatValor(nodo: DescomposicionNodo, unidad: Unidad): string {
  if (unidad === 'pct') return `${nodo.porcentaje_padre.toFixed(1)}%`
  return unidad === 'ars' ? formatARS(nodo.valor_ars) : formatUSD(nodo.valor_usd)
}

/** Encuentra el nodo señalado por `ruta` (lista de claves, una por nivel) dentro del árbol. */
function ubicar(raiz: DescomposicionNodo[], ruta: string[]): { hijos: DescomposicionNodo[]; migas: DescomposicionNodo[] } {
  let hijos = raiz
  const migas: DescomposicionNodo[] = []
  for (const clave of ruta) {
    const nodo = hijos.find(n => n.clave === clave)
    if (!nodo) break
    migas.push(nodo)
    hijos = nodo.hijos
  }
  return { hijos, migas }
}

export default function Descomposicion() {
  const navigate = useNavigate()
  const { carteraSeleccionada } = useInversionesContext()
  const [unidad, setUnidad] = useState<Unidad>('pct')
  const [ruta, setRuta] = useState<string[]>([])

  // El toggle ARS/USD del header (moneda "de referencia" de la cartera) se ignora a
  // propósito: acá manda el selector local %/ARS/USD, que además incluye la vista porcentual.
  const descomposicionQuery = useQuery({
    queryKey: qk.de('descomposicion', carteraSeleccionada),
    queryFn: () => getDescomposicion(carteraSeleccionada),
  })
  const data = descomposicionQuery.data ?? null

  const { hijos, migas } = useMemo(() => {
    if (!data) return { hijos: [] as DescomposicionNodo[], migas: [] as DescomposicionNodo[] }
    return ubicar(data.raiz, ruta)
  }, [data, ruta])

  // Si `ruta` quedó apuntando a un nodo que ya no existe (cambio de cartera), volver a la raíz.
  const rutaValida = migas.length === ruta.length
  const nodoActual = rutaValida ? migas[migas.length - 1] ?? null : null
  const nivelActual = nodoActual?.nivel ?? data?.niveles[0] ?? 'Familia'

  const totalNivel = nodoActual
    ? (unidad === 'usd' ? nodoActual.valor_usd : unidad === 'ars' ? nodoActual.valor_ars : 100)
    : (unidad === 'usd' ? data?.total_usd ?? 0 : unidad === 'ars' ? data?.total_ars ?? 0 : 100)

  const formatTotal = () => {
    if (unidad === 'pct') return '100%'
    return unidad === 'ars' ? formatARS(totalNivel) : formatUSD(totalNivel)
  }

  const irARaiz = () => setRuta([])
  const irAMiga = (i: number) => setRuta(ruta.slice(0, i + 1))
  const entrarA = (nodo: DescomposicionNodo) => {
    if (nodo.nivel === 'Ticker') {
      navigate(`/ticker/${encodeURIComponent(nodo.etiqueta)}`)
      return
    }
    if (nodo.hijos.length > 0) setRuta([...ruta, nodo.clave])
  }

  const hijosOrdenados = useMemo(() => [...hijos].sort((a, b) => b.valor_usd - a.valor_usd), [hijos])

  return (
    <div className="pb-4">
      <ScreenHeader title="Descomposición de cartera" />

      <QueryBoundary
        isLoading={descomposicionQuery.isLoading}
        error={descomposicionQuery.error}
        onRetry={() => void descomposicionQuery.refetch()}
      >
        {!data ? (
          <SkeletonPantalla />
        ) : data.raiz.length === 0 ? (
          <EmptyState title="Sin posiciones para descomponer" description="Sincronizá tu Sheet o elegí otra cartera." />
        ) : (
          <>
            {/* Breadcrumb */}
            <div className="flex items-center gap-1 flex-wrap text-caption mb-2.5">
              <button
                onClick={irARaiz}
                className={`font-semibold ${ruta.length === 0 ? 'text-app-text' : 'text-app-text-dim'}`}
              >
                Cartera
              </button>
              {migas.map((nodo, i) => (
                <span key={nodo.clave} className="flex items-center gap-1">
                  <span className="text-app-text-faint">›</span>
                  <button
                    onClick={() => irAMiga(i)}
                    className={`font-semibold ${i === migas.length - 1 ? 'text-app-text' : 'text-app-text-dim'}`}
                  >
                    {nodo.etiqueta}
                  </button>
                </span>
              ))}
            </div>

            <div className="flex items-center gap-2 mb-3">
              <div className="flex-1">
                <Segmented options={OPCIONES_UNIDAD} value={unidad} onChange={setUnidad} />
              </div>
              <InfoTooltip term="descomposicion_unidad" label="" />
            </div>

            <div className="my-4">
              <Donut
                slices={hijosOrdenados.map(n => ({ etiqueta: n.etiqueta, porcentaje: n.porcentaje_padre }))}
                centerLabel={nodoActual ? nodoActual.etiqueta : 'Total'}
                centerValue={formatTotal()}
              />
            </div>

            <div className="flex items-center gap-2 mb-2.5">
              <h3 className="text-body font-bold text-app-text">
                {nivelActual === 'Familia' ? 'Por familia' : nodoActual ? `Dentro de ${nodoActual.etiqueta}` : 'Detalle'}
              </h3>
              <InfoTooltip term="descomposicion_nivel" label="" />
              <div className="flex-1" />
              <BotonExportarCsv
                nombre={`descomposicion-${nivelActual.toLowerCase()}`}
                encabezados={['Categoría', 'Nivel', '%', 'Valor USD', 'Valor ARS', 'Instrumentos']}
                filas={() => hijosOrdenados.map(n => [n.etiqueta, n.nivel, n.porcentaje_padre, n.valor_usd, n.valor_ars, n.instrumentos])}
              />
            </div>

            <div className="flex flex-col gap-2.5">
              {hijosOrdenados.map((nodo, i) => (
                <button
                  key={nodo.clave}
                  onClick={() => entrarA(nodo)}
                  disabled={nodo.hijos.length === 0 && nodo.nivel !== 'Ticker'}
                  className="text-left w-full disabled:cursor-default"
                >
                  <div className="flex justify-between items-baseline text-caption mb-1.5">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className={`truncate ${nodo.sin_clasificar ? 'text-app-text-faint italic' : 'text-app-text'}`}>
                        {nodo.etiqueta}
                      </span>
                      {nodo.sin_clasificar && <InfoTooltip term="descomposicion_sin_clasificar" />}
                      {nodo.nivel === 'Ticker' && nodo.tipo_instrumento && (
                        <span className="shrink-0 text-label font-semibold text-app-text-dim bg-app-surface-2 rounded px-1.5 py-0.5">
                          {nodo.tipo_instrumento}
                        </span>
                      )}
                      <span className="shrink-0 text-label text-app-text-faint">
                        {nodo.instrumentos} instr.
                      </span>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <span className="font-mono font-bold text-app-text tabular-nums">
                        {formatValor(nodo, unidad)}
                      </span>
                      {(nodo.hijos.length > 0 || nodo.nivel === 'Ticker') && (
                        <Icon name="chevron" className="w-3.5 h-3.5 text-app-text-dim -rotate-90" />
                      )}
                    </div>
                  </div>
                  <div className="h-1.5 rounded-full bg-app-surface-2 overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${nodo.porcentaje_padre}%`,
                        background: nodo.sin_clasificar ? '#6b7280' : CHART_COLORS[i % CHART_COLORS.length],
                        opacity: nodo.sin_clasificar ? 0.5 : 1,
                      }}
                    />
                  </div>
                </button>
              ))}
            </div>

            {data.posiciones_sin_precio.length > 0 && (
              <div className="mt-4 flex items-center gap-1.5 text-label text-app-text-faint">
                <Icon name="alert" className="w-3.5 h-3.5 shrink-0" />
                <span>
                  {data.posiciones_sin_precio.length} posición{data.posiciones_sin_precio.length !== 1 ? 'es' : ''} sin
                  precio no incluida{data.posiciones_sin_precio.length !== 1 ? 's' : ''} ({data.posiciones_sin_precio.join(', ')}).{' '}
                  <button onClick={() => navigate('/calidad-datos')} className="font-semibold text-app-accent">
                    Ver calidad de datos
                  </button>
                </span>
              </div>
            )}
          </>
        )}
      </QueryBoundary>
    </div>
  )
}
