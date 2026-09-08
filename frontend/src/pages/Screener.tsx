import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  listarEstrategias, correrScreener,
  type ScreenerFilaOut, type OrigenScreener,
} from '../api'
import { qk } from '../api/queryClient'
import { usePreferencia } from '../hooks/usePreferencia'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Segmented from '../components/ui/Segmented'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import BotonExportarCsv from '../components/ui/BotonExportarCsv'
import InfoTooltip from '../help/components/InfoTooltip'
import { Icon } from '../components/icons/Icons'
import { formatARS, formatUSD, formatPrecio, formatPct } from '../utils'

const CLAVE_UMBRAL = 'inversiones-screener-umbral-pct'
const CLAVE_ESTRATEGIAS = 'inversiones-screener-estrategia-ids'
const UMBRALES_PCT = [1, 2, 3, 5, 10] as const

function formatMoneda(valor: number, moneda: string): string {
  if (moneda === 'ARS') return formatARS(valor)
  if (moneda === 'USD') return formatUSD(valor)
  return formatPrecio(valor)
}

const MOTIVO_LABEL: Record<string, string> = {
  entrada: 'Entrada',
  regla_salida: 'Regla de salida',
  stop_loss: 'Stop loss',
  take_profit: 'Take profit',
  trailing_stop: 'Trailing stop',
}

function claveFila(f: ScreenerFilaOut): string {
  return `${f.ticker}-${f.estrategia_id}-${f.motivo}`
}

export default function Screener() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const origenParam = searchParams.get('origen')
  const origen: OrigenScreener = origenParam === 'cartera' || origenParam === 'watchlist' ? origenParam : 'todos'

  const [umbralPct, setUmbralPct] = usePreferencia<number>(
    CLAVE_UMBRAL, 3,
    crudo => {
      const n = Number(crudo)
      return (UMBRALES_PCT as readonly number[]).includes(n) ? n : null
    },
    n => String(n),
  )
  const [estrategiaIds, setEstrategiaIds] = usePreferencia<number[]>(
    CLAVE_ESTRATEGIAS, [],
    crudo => {
      try {
        const arr = JSON.parse(crudo)
        return Array.isArray(arr) && arr.every(x => typeof x === 'number') ? arr : null
      } catch {
        return null
      }
    },
    arr => JSON.stringify(arr),
  )

  const [expandida, setExpandida] = useState<string | null>(null)
  const [haEscaneado, setHaEscaneado] = useState(false)

  const estrategiasQuery = useQuery({ queryKey: qk.de('estrategias'), queryFn: () => listarEstrategias() })
  const estrategias = estrategiasQuery.data ?? []

  const idsOrdenados = useMemo(() => [...estrategiaIds].sort((a, b) => a - b), [estrategiaIds])

  const scanQuery = useQuery({
    queryKey: qk.de('screener', idsOrdenados, umbralPct, origen),
    queryFn: () => correrScreener({ estrategia_ids: idsOrdenados, umbral_pct: umbralPct, origen }),
    enabled: false,
  })

  function escanear() {
    setHaEscaneado(true)
    void scanQuery.refetch()
  }

  function toggleEstrategia(id: number) {
    setEstrategiaIds(estrategiaIds.includes(id) ? estrategiaIds.filter(x => x !== id) : [...estrategiaIds, id])
  }

  function cambiarOrigen(nuevo: OrigenScreener) {
    setSearchParams(nuevo === 'todos' ? {} : { origen: nuevo }, { replace: true })
  }

  const filas = scanQuery.data?.filas ?? []

  return (
    <div className="pb-4">
      <ScreenHeader title="Screener" onBack={() => navigate(-1)} />

      <Card className="mb-3 flex flex-col gap-3">
        <div>
          <div className="text-label font-bold text-app-text-dim uppercase mb-1.5">Estrategias</div>
          {estrategiasQuery.isLoading ? (
            <div className="text-caption text-app-text-dim">Cargando…</div>
          ) : estrategias.length === 0 ? (
            <div className="text-caption text-app-text-dim">
              No hay estrategias guardadas. Creá una desde Análisis técnico.
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              <button
                onClick={() => setEstrategiaIds([])}
                className={`text-label font-bold px-2.5 py-1.5 rounded-lg border ${
                  estrategiaIds.length === 0
                    ? 'bg-app-gold-soft text-app-gold border-app-gold/40'
                    : 'bg-app-surface text-app-text-dim border-app-border'
                }`}
              >
                Todas
              </button>
              {estrategias.map(e => (
                <button
                  key={e.id}
                  onClick={() => toggleEstrategia(e.id)}
                  className={`text-label font-bold px-2.5 py-1.5 rounded-lg border truncate max-w-[160px] ${
                    estrategiaIds.includes(e.id)
                      ? 'bg-app-gold-soft text-app-gold border-app-gold/40'
                      : 'bg-app-surface text-app-text-dim border-app-border'
                  }`}
                >
                  {e.nombre}
                </button>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="text-label font-bold text-app-text-dim uppercase mb-1.5">Universo</div>
          <Segmented
            options={[
              { value: 'todos' as const, label: 'Todos' },
              { value: 'cartera' as const, label: 'Cartera' },
              { value: 'watchlist' as const, label: 'Watchlist' },
            ]}
            value={origen}
            onChange={cambiarOrigen}
          />
        </div>

        <div>
          <div className="flex items-center gap-1 text-label font-bold text-app-text-dim uppercase mb-1.5">
            Umbral de proximidad
            <InfoTooltip term="screener_umbral" />
          </div>
          <Segmented
            options={UMBRALES_PCT.map(n => ({ value: String(n), label: `±${n}%` }))}
            value={String(umbralPct)}
            onChange={v => setUmbralPct(Number(v))}
          />
        </div>

        <Button onClick={escanear} disabled={scanQuery.isFetching} loading={scanQuery.isFetching} icon={<Icon name="search" className="w-4 h-4" />}>
          {scanQuery.isFetching ? 'Escaneando…' : 'Escanear'}
        </Button>
      </Card>

      {!haEscaneado ? (
        <EmptyState
          title="Todavía no escaneaste"
          description="Elegí estrategias y un umbral, y tocá Escanear para ver qué tickers están cerca de disparar."
        />
      ) : (
        <QueryBoundary isLoading={scanQuery.isLoading} error={scanQuery.error} onRetry={escanear}>
          {scanQuery.data && (
            <>
              <div className="flex items-center justify-between mb-2">
                <div className="text-label text-app-text-dim">
                  {scanQuery.data.tickers_evaluados} tickers · {scanQuery.data.pares_evaluados} pares evaluados
                </div>
                {filas.length > 0 && (
                  <BotonExportarCsv
                    nombre="screener"
                    encabezados={['Ticker', 'Nombre', 'Estrategia', 'Tipo', 'Motivo', 'Distancia %', 'Precio actual', 'Precio gatillo']}
                    filas={() => filas.map(f => [
                      f.ticker, f.nombre, f.estrategia_nombre, f.tipo, f.motivo,
                      f.distancia_pct, f.precio_actual, f.precio_gatillo,
                    ])}
                  />
                )}
              </div>

              {scanQuery.data.advertencias.includes('universo_truncado') && (
                <div className="text-label text-app-gold mb-2">
                  Se alcanzó el máximo de pares evaluables: algunos pares pueden haber quedado afuera.
                </div>
              )}

              {filas.length === 0 ? (
                <EmptyState
                  title="Ninguna estrategia está cerca de disparar"
                  description={`Nada quedó dentro de ±${scanQuery.data.umbral_pct}%. Probá un umbral más amplio.`}
                />
              ) : (
                <div>
                  {filas.map(f => {
                    const key = claveFila(f)
                    const abierta = expandida === key
                    const avatarClase = f.dispara_ahora
                      ? 'border-app-gold/40 text-app-gold'
                      : f.tipo === 'compra'
                        ? 'border-app-teal/40 text-app-teal'
                        : 'border-app-coral/40 text-app-coral'
                    return (
                      <div key={key} className="border-b border-app-border-soft last:border-b-0">
                        <button
                          onClick={() => setExpandida(abierta ? null : key)}
                          className="w-full flex items-center gap-2.5 py-2.5 text-left"
                        >
                          <div className={`w-9 h-9 rounded-[11px] bg-app-surface-2 border flex items-center justify-center font-mono text-label font-bold shrink-0 ${avatarClase}`}>
                            {f.ticker.slice(0, 4)}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5 min-w-0">
                              <div className="text-caption font-bold text-app-text truncate">{f.nombre}</div>
                              <span
                                className={`shrink-0 rounded-md px-1.5 py-0.5 text-label font-bold border ${
                                  f.tipo === 'compra'
                                    ? 'border-app-teal/40 text-app-teal bg-app-teal-soft'
                                    : 'border-app-coral/40 text-app-coral bg-app-coral-soft'
                                }`}
                              >
                                {f.tipo === 'compra' ? '▲' : '▼'} {f.tipo}
                              </span>
                            </div>
                            <div className="text-label text-app-text-dim mt-0.5 truncate">
                              {f.estrategia_nombre} · {MOTIVO_LABEL[f.motivo] ?? f.motivo}
                            </div>
                          </div>
                          <div className="text-right shrink-0">
                            <div className="flex items-center justify-end gap-0.5 font-mono text-caption font-bold text-app-text tabular-nums">
                              {formatPct(f.distancia_pct)}
                              <InfoTooltip term="screener_distancia" />
                            </div>
                            <div className="text-label text-app-text-dim mt-0.5 tabular-nums">
                              {formatMoneda(f.precio_actual, f.moneda)}
                            </div>
                          </div>
                          <Icon
                            name="chevron"
                            className={`w-3.5 h-3.5 text-app-text-dim shrink-0 transition-transform ${abierta ? 'rotate-0' : '-rotate-90'}`}
                          />
                        </button>

                        {abierta && (
                          <div className="pb-3 pl-11 flex flex-col gap-2">
                            <div className="flex items-center gap-1 text-label text-app-text-dim">
                              <span className="inline-flex items-center gap-0.5">
                                Precio gatillo
                                <InfoTooltip term="screener_precio_gatillo" />
                              </span>
                              <span className="font-mono font-bold text-app-text">{formatMoneda(f.precio_gatillo, f.moneda)}</span>
                            </div>
                            {f.posicion_abierta && f.retorno_abierta_pct != null && (
                              <div className="text-label text-app-text-dim">
                                Posición abierta desde la entrada: <span className="font-mono font-bold text-app-text">{formatPct(f.retorno_abierta_pct)}</span>
                              </div>
                            )}
                            {f.condiciones.length > 0 && (
                              <div className="flex flex-col gap-1">
                                {f.condiciones.map((c, i) => (
                                  <div key={i} className="flex items-center gap-1.5 text-label">
                                    <Icon
                                      name={c.cumple ? 'check' : 'close'}
                                      className={`w-3 h-3 shrink-0 ${c.cumple ? 'text-app-teal' : 'text-app-text-faint'}`}
                                    />
                                    <span className="font-mono text-app-text-dim truncate">
                                      {c.izq_etiqueta} {c.izq_valor != null && `(${formatPrecio(c.izq_valor)})`} {c.op} {c.der_etiqueta}
                                      {c.der_valor != null && ` (${formatPrecio(c.der_valor)})`}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </QueryBoundary>
      )}
    </div>
  )
}
