import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  actualizarClasificacionLote, getEstadoClasificacion, getValuacionLista,
  type ClaveDimension, type LecturaValuacion, type UniversoValuacion, type ValuacionItem,
} from '../api'
import { qk } from '../api/queryClient'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Segmented from '../components/ui/Segmented'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import InfoTooltip from '../help/components/InfoTooltip'
import {
  EstadoDimension, LECTURAS_ORDEN, LecturaBadge, ORDEN_NIVEL_CONFIANZA, TEXTO_LECTURA_CORTO,
} from '../components/valuacion/comun'

const UNIVERSOS: { value: UniversoValuacion; label: string }[] = [
  { value: 'cartera', label: 'Mi cartera' },
  { value: 'watchlist', label: 'Watchlist' },
  { value: 'catalogo', label: 'Todo el catálogo' },
]
const PAGINA = 60

/** Orden de la lista: un criterio explícito a la vez, nunca una mezcla opaca. */
type Orden = 'nombre' | 'baratas' | 'calidad' | 'crecimiento' | 'confianza'
const ORDENES: { value: Orden; label: string }[] = [
  { value: 'nombre', label: 'Nombre' },
  { value: 'baratas', label: 'Más baratas' },
  { value: 'calidad', label: 'Mejor calidad' },
  { value: 'crecimiento', label: 'Más crecimiento' },
  { value: 'confianza', label: 'Más confianza' },
]
const DIMENSION_DE_ORDEN: Partial<Record<Orden, ClaveDimension>> = {
  baratas: 'valuacion', calidad: 'calidad', crecimiento: 'crecimiento',
}
// Se muestran en la tarjeta (la valuación ya es el badge de arriba).
const DIMENSIONES_TARJETA: { clave: ClaveDimension; label: string }[] = [
  { clave: 'calidad', label: 'Calidad' },
  { clave: 'crecimiento', label: 'Crecimiento' },
  { clave: 'solidez', label: 'Solidez' },
  { clave: 'confianza', label: 'Confianza en los datos' },
]

function dimension(item: ValuacionItem, clave: ClaveDimension) {
  return item.dimensiones.find(d => d.clave === clave)
}

function valorOrden(item: ValuacionItem, orden: Orden): number | null {
  if (orden === 'confianza') {
    const d = dimension(item, 'confianza')
    return d ? ORDEN_NIVEL_CONFIANZA[d.estado.toLowerCase().replace(' ', '_')] ?? null : null
  }
  const clave = DIMENSION_DE_ORDEN[orden]
  return clave ? dimension(item, clave)?.percentil ?? null : null
}

function ordenar(items: ValuacionItem[], orden: Orden): ValuacionItem[] {
  if (orden === 'nombre') return items
  // Sin dato va siempre al final: no es "lo peor", es lo que no se puede comparar.
  return [...items].sort((a, b) => {
    const va = valorOrden(a, orden)
    const vb = valorOrden(b, orden)
    if (va == null && vb == null) return a.ticker.localeCompare(b.ticker)
    if (va == null) return 1
    if (vb == null) return -1
    return vb - va || a.ticker.localeCompare(b.ticker)
  })
}

function FiltroChip({ activo, onClick, children }: { activo: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`shrink-0 rounded-[9px] px-2.5 py-1.5 text-label font-bold border transition-colors ${
        activo ? 'bg-app-accent-soft text-app-accent border-app-accent/40' : 'bg-app-surface-2 text-app-text-dim border-app-border'
      }`}
    >
      {children}
    </button>
  )
}

function Tarjeta({ item, onClick }: { item: ValuacionItem; onClick: () => void }) {
  const detalle = [item.tipo, item.region, item.sector].filter(Boolean).join(' · ')
  return (
    <button onClick={onClick} className="w-full text-left bg-app-surface border border-app-border rounded-2xl p-3.5 mb-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-body font-bold text-app-text">{item.ticker}</span>
            {item.en_cartera && <span className="text-label font-bold text-app-accent">en cartera</span>}
            {!item.en_cartera && item.en_watchlist && <span className="text-label font-bold text-app-text-dim">watchlist</span>}
          </div>
          <div className="text-label text-app-text-dim truncate">{item.nombre ?? detalle}</div>
        </div>
        <LecturaBadge lectura={item.lectura} />
      </div>
      {detalle && item.nombre && <div className="text-label text-app-text-faint mt-1 truncate">{detalle}</div>}
      {item.estado_datos === 'ok' && (
        <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 mt-2.5">
          {DIMENSIONES_TARJETA.map(({ clave, label }) => {
            const d = dimension(item, clave)
            if (!d || d.nivel === 'no_aplica') return null
            return (
              <div key={clave} className="min-w-0">
                <div className="text-label text-app-text-faint truncate">{label}</div>
                <EstadoDimension nivel={d.nivel} estado={d.estado} />
              </div>
            )
          })}
        </div>
      )}
      {item.frases.length > 0 ? (
        <ul className="mt-2 flex flex-col gap-1">
          {item.frases.map(f => <li key={f} className="text-caption text-app-text">{f}</li>)}
        </ul>
      ) : (
        <div className="text-caption text-app-text-dim mt-2">
          {item.estado_datos === 'ok' ? 'Pocos pares con datos para comparar.' : 'Datos pendientes: la app los baja de a poco.'}
        </div>
      )}
      {item.fecha_dato && (
        <div className="text-label text-app-text-faint mt-2">Datos del {item.fecha_dato.split('-').reverse().join('/')}</div>
      )}
    </button>
  )
}

export default function ValuacionPares() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const universoParam = searchParams.get('universo') as UniversoValuacion | null
  const universo: UniversoValuacion = UNIVERSOS.some(u => u.value === universoParam) ? universoParam! : 'cartera'

  const [lectura, setLectura] = useState<LecturaValuacion | null>(null)
  const [region, setRegion] = useState<string | null>(null)
  const [tipo, setTipo] = useState<string | null>(null)
  const [orden, setOrden] = useState<Orden>('nombre')
  const [soloCalidad, setSoloCalidad] = useState(false)
  const [soloSolidas, setSoloSolidas] = useState(false)
  const [soloConfiables, setSoloConfiables] = useState(false)
  const [visibles, setVisibles] = useState(PAGINA)

  const lista = useQuery({
    queryKey: qk.de('valuacion-lista', universo),
    queryFn: () => getValuacionLista(universo),
  })
  const estado = useQuery({ queryKey: qk.de('clasificacion-estado'), queryFn: getEstadoClasificacion })
  const lote = useMutation({
    mutationFn: actualizarClasificacionLote,
    onSuccess: () => {
      // La corrida tarda unos minutos: se vuelve a mirar el estado un rato después.
      setTimeout(() => void queryClient.invalidateQueries(), 60_000)
    },
  })

  const items = lista.data?.items ?? []
  const regiones = useMemo(() => [...new Set(items.map(i => i.region).filter(Boolean) as string[])].sort(), [items])
  const tipos = useMemo(() => [...new Set(items.map(i => i.tipo).filter(Boolean) as string[])].sort(), [items])
  const filtrados = ordenar(items.filter(i =>
    (!lectura || i.lectura === lectura) && (!region || i.region === region) && (!tipo || i.tipo === tipo)
    && (!soloCalidad || dimension(i, 'calidad')?.estado === 'Alta')
    && (!soloSolidas || dimension(i, 'solidez')?.estado === 'Sólida')
    && (!soloConfiables || dimension(i, 'confianza')?.estado === 'Alta')), orden)
  const conteos = useMemo(() => {
    const c: Partial<Record<LecturaValuacion, number>> = {}
    for (const i of items) {
      if ((!region || i.region === region) && (!tipo || i.tipo === tipo)) c[i.lectura] = (c[i.lectura] ?? 0) + 1
    }
    return c
  }, [items, region, tipo])

  function cambiarUniverso(u: UniversoValuacion) {
    setSearchParams(u === 'cartera' ? {} : { universo: u }, { replace: true })
    setLectura(null)
    setRegion(null)
    setTipo(null)
    setSoloCalidad(false)
    setSoloSolidas(false)
    setSoloConfiables(false)
    setVisibles(PAGINA)
  }

  const cob = estado.data?.cobertura

  return (
    <div className="pb-4">
      <ScreenHeader title="Valuación vs. pares" onBack={() => navigate(-1)} />

      <div className="mb-3">
        <InfoTooltip term="valuacion_que_es" label="Qué muestra esta pantalla" />
      </div>

      {cob && (
        <Card className="mb-3">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="text-caption text-app-text">
                <span className="font-bold">{cob.con_datos}</span> de {cob.aptos} emisores con datos
                {cob.propios > 0 && <span className="text-app-text-dim"> · lo tuyo: {cob.propios_con_datos}/{cob.propios}</span>}
              </div>
              <div className="text-label text-app-text-faint">
                {estado.data?.horas_programadas
                  ? `Se completa sola de a poco (a las ${estado.data.horas_programadas.split(',').join(' y ')} h).`
                  : 'La descarga automática está apagada en este servidor.'}
                {estado.data?.ultima_corrida?.rate_limited ? ' Yahoo limitó la última corrida.' : ''}
              </div>
            </div>
            {cob.pendientes > 0 && (
              <button
                onClick={() => lote.mutate()}
                disabled={lote.isPending || lote.isSuccess}
                className="shrink-0 text-caption font-bold text-app-accent disabled:text-app-text-faint"
              >
                {lote.isSuccess ? 'Bajando…' : 'Bajar ahora'}
              </button>
            )}
          </div>
          <div className="h-1.5 rounded-full bg-app-surface-2 mt-2 overflow-hidden" aria-hidden="true">
            <div className="h-full bg-app-accent rounded-full" style={{ width: `${cob.cobertura_pct}%` }} />
          </div>
        </Card>
      )}

      <div className="mb-3">
        <Segmented options={UNIVERSOS} value={universo} onChange={cambiarUniverso} />
      </div>

      <div className="flex gap-1.5 overflow-x-auto no-scrollbar -mx-1 px-1 pb-1 mb-1.5">
        <FiltroChip activo={lectura === null} onClick={() => setLectura(null)}>Todas</FiltroChip>
        {LECTURAS_ORDEN.filter(l => conteos[l]).map(l => (
          <FiltroChip key={l} activo={lectura === l} onClick={() => setLectura(lectura === l ? null : l)}>
            {TEXTO_LECTURA_CORTO[l]} · {conteos[l]}
          </FiltroChip>
        ))}
      </div>
      {(regiones.length > 1 || tipos.length > 1) && (
        <div className="flex gap-1.5 overflow-x-auto no-scrollbar -mx-1 px-1 pb-1 mb-3">
          {regiones.length > 1 && regiones.map(r => (
            <FiltroChip key={r} activo={region === r} onClick={() => setRegion(region === r ? null : r)}>{r}</FiltroChip>
          ))}
          {tipos.length > 1 && tipos.map(t => (
            <FiltroChip key={t} activo={tipo === t} onClick={() => setTipo(tipo === t ? null : t)}>{t}</FiltroChip>
          ))}
        </div>
      )}

      <div className="flex gap-1.5 overflow-x-auto no-scrollbar -mx-1 px-1 pb-1 mb-1.5">
        <FiltroChip activo={soloCalidad} onClick={() => setSoloCalidad(v => !v)}>Calidad alta</FiltroChip>
        <FiltroChip activo={soloSolidas} onClick={() => setSoloSolidas(v => !v)}>Solidez sólida</FiltroChip>
        <FiltroChip activo={soloConfiables} onClick={() => setSoloConfiables(v => !v)}>Confianza alta</FiltroChip>
      </div>
      <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar -mx-1 px-1 pb-1 mb-3">
        <span className="shrink-0 text-label font-bold text-app-text-faint">Ordenar por</span>
        {ORDENES.map(o => (
          <FiltroChip key={o.value} activo={orden === o.value} onClick={() => setOrden(o.value)}>{o.label}</FiltroChip>
        ))}
      </div>

      <QueryBoundary isLoading={lista.isLoading} error={lista.error} onRetry={() => void lista.refetch()}>
        {filtrados.length === 0 ? (
          <EmptyState
            title={items.length === 0 ? 'Todavía no hay nada para comparar' : 'Nada con esos filtros'}
            description={
              items.length === 0
                ? universo === 'catalogo'
                  ? 'Los datos de Yahoo se bajan de a poco; en unos días está todo el catálogo.'
                  : 'Esta lista muestra acciones, CEDEARs y ETFs. Los bonos y FCI todavía no se comparan.'
                : 'Probá sacando algún filtro.'
            }
          />
        ) : (
          <>
            {filtrados.slice(0, visibles).map(item => (
              <Tarjeta
                key={item.ticker}
                item={item}
                onClick={() => navigate(`/ticker/${encodeURIComponent(item.ticker)}?tab=pares`)}
              />
            ))}
            {filtrados.length > visibles && (
              <button onClick={() => setVisibles(v => v + PAGINA)} className="w-full py-3 text-caption font-bold text-app-accent">
                Ver {Math.min(PAGINA, filtrados.length - visibles)} más de {filtrados.length - visibles}
              </button>
            )}
          </>
        )}
      </QueryBoundary>

      <p className="text-label text-app-text-faint text-center mt-3">
        Sirve para encontrar candidatos para mirar, no es una recomendación de compra o venta: algo puede estar barato por una buena razón.
      </p>
    </div>
  )
}
