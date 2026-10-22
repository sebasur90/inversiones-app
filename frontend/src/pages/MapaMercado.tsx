import { useMemo, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getMapaMercado, type MapaMercadoItem } from '../api'
import { qk } from '../api/queryClient'
import {
  construirArbol,
  formatCapitalizacion,
  GRADIENTE_LEYENDA,
  TOPE_COLOR,
  ubicar,
  variacionDe,
  type Eje,
  type Periodo,
  type TamanoRect,
} from '../utils/mapaMercado'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import Modal from '../components/ui/Modal'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import SkeletonPantalla from '../components/ui/Skeleton'
import VariacionDia from '../components/ui/VariacionDia'
import MapaCalor from '../components/charts/MapaCalor'
import InfoTooltip from '../help/components/InfoTooltip'

const PERIODOS: { value: Periodo; label: string }[] = [
  { value: '1d', label: '1D' },
  { value: '1s', label: '1S' },
  { value: '1m', label: '1M' },
  { value: '1a', label: '1A' },
]
const EJES: { value: Eje; label: string }[] = [
  { value: 'sector', label: 'Sector' },
  { value: 'region', label: 'Región' },
  { value: 'tamano', label: 'Tamaño empresa' },
  { value: 'tipo', label: 'Tipo' },
]
const TAMANOS: { value: TamanoRect; label: string }[] = [
  { value: 'cap', label: 'Capitalización' },
  { value: 'cartera', label: 'Mi cartera' },
  { value: 'parejo', label: 'Parejo' },
]
const ETIQUETA_PERIODO: Record<Periodo, string> = {
  '1d': 'último día',
  '1s': 'última semana',
  '1m': 'último mes',
  '1a': 'último año',
}

function Fila({ titulo, info, children }: { titulo: string; info?: Parameters<typeof InfoTooltip>[0]['term']; children: ReactNode }) {
  return (
    <div className="mb-2.5">
      <div className="mb-1 flex items-center gap-1 text-label font-semibold uppercase tracking-wide text-app-text-faint">
        {titulo}
        {info && <InfoTooltip term={info} label="" />}
      </div>
      {children}
    </div>
  )
}

function FichaEmisor({ item, onVerTicker }: { item: MapaMercadoItem; onVerTicker: () => void }) {
  const detalleClasif = [item.tipo, item.sector, item.industria].filter(Boolean).join(' · ')
  const ubicacion = [item.pais, item.region].filter(Boolean).join(' · ')
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        {item.tiene_logo && (
          <img
            src={`/api/inversiones/logos/${encodeURIComponent(item.ticker_base)}.png`}
            alt=""
            className="h-10 w-10 shrink-0 rounded-full bg-white/90 object-contain"
            onError={e => {
              e.currentTarget.style.display = 'none'
            }}
          />
        )}
        <div className="min-w-0">
        <div className="font-mono text-strong font-bold text-app-text">{item.ticker}</div>
        {detalleClasif && <div className="text-caption text-app-text-dim">{detalleClasif}</div>}
        {ubicacion && <div className="text-caption text-app-text-dim">{ubicacion}</div>}
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2 rounded-xl bg-app-surface-2 p-3">
        {(['1d', '1s', '1m', '1a'] as Periodo[]).map(p => (
          <div key={p} className="flex flex-col items-center gap-0.5">
            <span className="text-label text-app-text-faint">{p.toUpperCase()}</span>
            <VariacionDia pct={variacionDe(item, p)} />
          </div>
        ))}
      </div>
      {item.moneda_variacion === 'ARS' && (
        <p className="text-caption text-app-warn">
          Esta variación está en pesos: faltó el dólar MEP para llevarla a dólares.
        </p>
      )}

      <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-caption">
        <div>
          <dt className="text-app-text-faint">Tamaño</dt>
          <dd className="text-app-text">{item.tamano_empresa}</dd>
        </div>
        <div>
          <dt className="text-app-text-faint">Capitalización</dt>
          <dd className="font-mono tabular-nums text-app-text">{formatCapitalizacion(item.market_cap_usd)}</dd>
        </div>
        {item.en_cartera && (
          <div>
            <dt className="text-app-text-faint">En tu cartera</dt>
            <dd className="font-mono tabular-nums text-app-text">
              {item.peso_cartera != null ? `${item.peso_cartera.toFixed(1)}%` : 'Sí'}
            </dd>
          </div>
        )}
        {item.en_watchlist && (
          <div>
            <dt className="text-app-text-faint">Watchlist</dt>
            <dd className="text-app-text">La seguís</dd>
          </div>
        )}
      </dl>

      <button
        onClick={onVerTicker}
        className="rounded-xl bg-app-accent px-4 py-2.5 text-strong font-semibold text-white"
      >
        Ver {item.ticker}
      </button>
    </div>
  )
}

export default function MapaMercado() {
  const navigate = useNavigate()
  const [periodo, setPeriodo] = useState<Periodo>('1d')
  const [eje, setEje] = useState<Eje>('sector')
  const [tamano, setTamano] = useState<TamanoRect>('cap')
  const [soloMio, setSoloMio] = useState(false)
  const [ruta, setRuta] = useState<string[]>([])
  const [elegido, setElegido] = useState<MapaMercadoItem | null>(null)

  const query = useQuery({ queryKey: qk.de('mapa-mercado'), queryFn: getMapaMercado })
  const data = query.data ?? null

  const items = useMemo(
    () => (data ? data.items.filter(i => !soloMio || i.en_cartera || i.en_watchlist) : []),
    [data, soloMio],
  )
  const arbol = useMemo(() => construirArbol(items, eje, periodo, tamano), [items, eje, periodo, tamano])
  const { nodo: visible, migas } = useMemo(() => ubicar(arbol, ruta), [arbol, ruta])
  // Si el grupo al que se había entrado ya no existe (cambió el tamaño o el filtro), `ubicar` vuelve
  // a la raíz: la ruta efectiva es la de las migas, no la guardada.
  const rutaEfectiva = migas.map(m => m.clave)

  const cambiarEje = (e: Eje) => {
    setEje(e)
    setRuta([])
  }
  const cambiarSoloMio = () => {
    setSoloMio(v => !v)
    setRuta([])
  }

  const ocultosPorPeso = tamano === 'cartera' ? items.filter(i => !i.peso_cartera).length : 0
  const sinContenido = !arbol.hijos?.length

  return (
    <div className="pb-4">
      <ScreenHeader title="Mapa de mercado" />

      <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
        {!data ? (
          <SkeletonPantalla />
        ) : data.items.length === 0 ? (
          <EmptyState
            title="Todavía no hay datos del mercado"
            description="La descarga corre sola después del cierre de EE.UU., y la clasificación se completa de a poco. Volvé más tarde."
          />
        ) : (
          <>
            <Fila titulo="Variación de">
              <Segmented options={PERIODOS} value={periodo} onChange={setPeriodo} />
            </Fila>
            <Fila titulo="Agrupar por" info="mapa_agrupar">
              <Segmented options={EJES} value={eje} onChange={cambiarEje} />
            </Fila>
            <Fila titulo="Tamaño del rectángulo" info="mapa_tamano">
              <Segmented options={TAMANOS} value={tamano} onChange={setTamano} />
            </Fila>
            <label className="mb-3 flex items-center gap-2 text-caption text-app-text">
              <input type="checkbox" checked={soloMio} onChange={cambiarSoloMio} className="h-4 w-4 accent-[#3b82f6]" />
              Sólo lo mío (cartera y watchlist)
            </label>

            <div className="mb-2 flex flex-wrap items-center gap-1 text-caption">
              <button
                onClick={() => setRuta([])}
                className={`font-semibold ${migas.length === 0 ? 'text-app-text' : 'text-app-text-dim'}`}
              >
                Mercado
              </button>
              {migas.map((m, i) => (
                <span key={m.clave} className="flex items-center gap-1">
                  <span className="text-app-text-faint">›</span>
                  <button
                    onClick={() => setRuta(rutaEfectiva.slice(0, i + 1))}
                    className={`font-semibold ${i === migas.length - 1 ? 'text-app-text' : 'text-app-text-dim'}`}
                  >
                    {m.etiqueta}
                  </button>
                </span>
              ))}
            </div>

            {sinContenido ? (
              <EmptyState
                title={soloMio || tamano === 'cartera' ? 'No hay nada tuyo para mostrar' : 'Nada para mostrar'}
                description={
                  soloMio || tamano === 'cartera'
                    ? 'Ningún emisor de tu cartera o watchlist está en el mapa todavía. Probá sacar el filtro o elegir otro tamaño.'
                    : 'Probá con otro agrupamiento.'
                }
              />
            ) : (
              <MapaCalor
                visible={visible}
                periodo={periodo}
                onElegirGrupo={clave => setRuta([...rutaEfectiva, clave])}
                onElegirItem={setElegido}
              />
            )}

            <div className="mt-2.5">
              <div className="h-2 rounded-full" style={{ background: GRADIENTE_LEYENDA }} />
              <div className="mt-1 flex justify-between font-mono text-label tabular-nums text-app-text-faint">
                <span>−{(TOPE_COLOR[periodo] * 100).toFixed(0)}%</span>
                <span>0%</span>
                <span>+{(TOPE_COLOR[periodo] * 100).toFixed(0)}%</span>
              </div>
            </div>

            <div className="mt-3 flex flex-col gap-1 text-caption text-app-text-dim">
              <p>
                Variación del {ETIQUETA_PERIODO[periodo]}, en dólares.{' '}
                <span className="inline-flex items-center gap-1">
                  <span className="inline-block h-2.5 w-2.5 rounded-sm ring-2 ring-inset ring-white" /> en tu cartera
                  <span className="ml-1 inline-block h-2.5 w-2.5 rounded-sm ring-2 ring-inset ring-app-accent" /> en tu watchlist
                </span>
              </p>
              <p>
                {data.cobertura.con_variacion} de {data.cobertura.total} emisores con variación · {data.cobertura.con_logo} con logo
                {data.actualizado ? ` · actualizado ${new Date(data.actualizado + 'Z').toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' })}` : ''}.
              </p>
              {ocultosPorPeso > 0 && (
                <p>Con "Mi cartera" sólo se dibujan tus posiciones: {ocultosPorPeso} emisores sin tenencia quedan afuera.</p>
              )}
              {data.avisos.map(a => (
                <p key={a} className="text-app-warn">{a}</p>
              ))}
            </div>
          </>
        )}
      </QueryBoundary>

      <Modal open={elegido != null} onClose={() => setElegido(null)} title={elegido?.nombre ?? elegido?.ticker ?? ''}>
        {elegido && (
          <FichaEmisor
            item={elegido}
            onVerTicker={() => navigate(`/ticker/${encodeURIComponent(elegido.ticker)}`)}
          />
        )}
      </Modal>
    </div>
  )
}
