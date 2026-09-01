import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  ComposedChart, Area, Line, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts'
import { useInversionesContext } from '../context/InversionesContext'
import { getEvolucionInversiones, getPatrimonioHistory, getPatrimonioSummary, type EvolucionPunto, type MovimientoInversion, type PatrimonioPunto, type PatrimonioSummaryOut } from '../api'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import EmptyState from '../components/ui/EmptyState'
import Modal from '../components/ui/Modal'
import { Icon } from '../components/icons/Icons'
import MetricTile from '../components/ui/MetricTile'
import InfoTooltip from '../help/components/InfoTooltip'
import ErrorBanner from '../help/components/ErrorBanner'
import { parseApiError, type ParsedApiError } from '../help/errors/apiErrors'
import PatrimonioMensualTable from '../components/tables/PatrimonioMensualTable'
import { calcularDesde, type PeriodoEvolucion } from '../utils'
import { qk } from '../api/queryClient'
import { Skeleton } from '../components/ui/Skeleton'

type Periodo = PeriodoEvolucion
type Vista = 'ars' | 'ars_real' | 'usd'
type TipoEvento = 'aporte' | 'retiro' | 'ingreso'

interface EventoPunto {
  fecha: string
  valor: number
  movimientos: MovimientoInversion[]
  tipo: TipoEvento | null
  cantidad: number
}

const OPCIONES_PERIODO: { value: Periodo; label: string }[] = [
  { value: '1M', label: '1M' },
  { value: '3M', label: '3M' },
  { value: '6M', label: '6M' },
  { value: '1Y', label: '1A' },
  { value: '3Y', label: '3A' },
  { value: 'YTD', label: 'YTD' },
  { value: 'ALL', label: 'Todo' },
]

const TIPO_LABELS: Record<string, string> = {
  compra: 'Compra',
  venta: 'Venta',
  dividendo: 'Dividendo',
  cupon: 'Cupón',
  amortizacion: 'Amortización',
}

const COLOR_EVENTO: Record<TipoEvento, string> = {
  aporte: '#4fd1ae',
  retiro: '#e2665a',
  ingreso: '#5b8ba0',
}

const LABEL_EVENTO: Record<TipoEvento, string> = {
  aporte: 'Aporte de capital',
  retiro: 'Retiro de capital',
  ingreso: 'Cobro de dividendo/cupón',
}

function tipoEvento(tipoMovimiento: string): TipoEvento | null {
  if (tipoMovimiento === 'compra') return 'aporte'
  if (tipoMovimiento === 'venta' || tipoMovimiento === 'amortizacion') return 'retiro'
  if (tipoMovimiento === 'dividendo' || tipoMovimiento === 'cupon') return 'ingreso'
  return null
}

function tipoPredominante(movs: MovimientoInversion[]): TipoEvento {
  const conteo: Record<TipoEvento, number> = { aporte: 0, retiro: 0, ingreso: 0 }
  for (const m of movs) {
    const t = tipoEvento(m.tipo_movimiento)
    if (t) conteo[t]++
  }
  return (Object.entries(conteo) as [TipoEvento, number][]).sort((a, b) => b[1] - a[1])[0][0]
}

function valorPorVista(p: EvolucionPunto, vista: Vista): number | null {
  return vista === 'ars' ? p.valor_ars : vista === 'usd' ? p.valor_usd : p.valor_ars_real
}

function capitalPorVista(p: EvolucionPunto, vista: Vista): number | null {
  return vista === 'ars' ? p.capital_aportado_ars : vista === 'usd' ? p.capital_aportado_usd : p.capital_aportado_ars_real
}

function formatCompact(v: number, esUSD: boolean): string {
  const abs = Math.abs(v)
  const signo = v < 0 ? '-' : ''
  if (esUSD) {
    if (abs >= 1_000_000) return `${signo}U$S ${(abs / 1_000_000).toFixed(1)}M`
    if (abs >= 1000) return `${signo}U$S ${(abs / 1000).toFixed(0)}K`
    return `${signo}U$S ${abs.toFixed(2)}`
  }
  if (abs >= 1_000_000) return `${signo}$${(abs / 1_000_000).toFixed(1)}M`
  if (abs >= 1000) return `${signo}$${(abs / 1000).toFixed(0)}K`
  return `${signo}$${abs.toFixed(0)}`
}

function formatMontoMovimiento(mov: MovimientoInversion): string {
  const monto = mov.cantidad != null ? mov.cantidad * mov.precio : mov.precio
  const valor = mov.moneda === 'USD' ? `U$S ${Math.abs(monto).toLocaleString('es-AR', { maximumFractionDigits: 2 })}` : `$${Math.abs(monto).toLocaleString('es-AR')}`
  return valor
}

function formatFechaLabel(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  const dia = d.getDate().toString().padStart(2, '0')
  const mes = (d.getMonth() + 1).toString().padStart(2, '0')
  return `${dia}/${mes}`
}

function formatFechaTooltip(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' })
}

const COLOR_POR_VISTA: Record<Vista, string> = {
  ars: '#d8b14a',
  ars_real: '#9c7aa0',
  usd: '#4fd1ae',
}

function EventoDot(props: any) {
  const { cx, cy, payload } = props
  if (cx == null || cy == null || payload.tipo == null) return <g />
  const color = COLOR_EVENTO[payload.tipo as TipoEvento]
  return (
    <g style={{ cursor: 'pointer' }}>
      <circle cx={cx} cy={cy} r={7} fill={color} stroke="#0b1210" strokeWidth={2} />
      {payload.cantidad > 1 && (
        <text x={cx} y={cy + 3} textAnchor="middle" fontSize={8} fontWeight={700} fill="#0b1210">
          {payload.cantidad}
        </text>
      )}
    </g>
  )
}

export default function Patrimonio() {
  const navigate = useNavigate()
  const { carteraSeleccionada, movimientos } = useInversionesContext()
  const [periodo, setPeriodo] = useState<Periodo>('1Y')
  const [vista, setVista] = useState<Vista>('ars')
  const [eventoSeleccionado, setEventoSeleccionado] = useState<EventoPunto | null>(null)

  const desde = calcularDesde(periodo)

  // Cuatro series: la del período elegido y la histórica completa, para evolución y para
  // patrimonio. Cada una con su clave, así cambiar de período no vuelve a pedir las
  // históricas (que no dependen del período).
  const evolucionQuery = useQuery({
    queryKey: qk.de('evolucion', carteraSeleccionada, periodo),
    queryFn: () => getEvolucionInversiones(carteraSeleccionada, desde),
  })
  const evolucionAllQuery = useQuery({
    queryKey: qk.de('evolucion', carteraSeleccionada, 'ALL'),
    queryFn: () => getEvolucionInversiones(carteraSeleccionada, undefined),
  })
  const summaryQuery = useQuery({
    queryKey: qk.de('patrimonio-summary', carteraSeleccionada, periodo),
    queryFn: () => getPatrimonioSummary(carteraSeleccionada, desde),
  })
  const historiaQuery = useQuery({
    queryKey: qk.de('patrimonio-history', carteraSeleccionada),
    queryFn: () => getPatrimonioHistory(carteraSeleccionada, undefined),
  })

  const puntos: EvolucionPunto[] = evolucionQuery.data?.puntos ?? []
  const puntosAll: EvolucionPunto[] = evolucionAllQuery.data?.puntos ?? []
  const patrimonioSummary: PatrimonioSummaryOut | null = summaryQuery.data ?? null
  const patrimonioHistoria: PatrimonioPunto[] = historiaQuery.data?.puntos ?? []
  const loading = evolucionQuery.isLoading
  const error: ParsedApiError | null =
    evolucionQuery.error ? parseApiError(evolucionQuery.error)
    : summaryQuery.error ? parseApiError(summaryQuery.error)
    : null

  const esUSD = vista === 'usd'
  type DatoGrafico = { fecha: string; valor: number; capitalAportado: number | null }
  const datosGrafico: DatoGrafico[] = puntos
    .map(p => ({
      fecha: p.fecha,
      valor: valorPorVista(p, vista),
      capitalAportado: capitalPorVista(p, vista),
    }))
    .filter((p): p is DatoGrafico => p.valor != null)

  const primerPunto = datosGrafico.length > 0 ? datosGrafico[0] : undefined
  const ultimoPunto = datosGrafico.length > 0 ? datosGrafico[datosGrafico.length - 1] : undefined
  const deltaAbs = primerPunto && ultimoPunto ? ultimoPunto.valor - primerPunto.valor : null
  const variacionPct =
    primerPunto && ultimoPunto && primerPunto.valor !== 0
      ? ((ultimoPunto.valor - primerPunto.valor) / Math.abs(primerPunto.valor)) * 100
      : null

  const hwm = puntosAll.reduce<number | null>((max, p) => {
    const v = valorPorVista(p, vista)
    if (v == null) return max
    return max == null ? v : Math.max(max, v)
  }, null)

  // Nota: Scatter comparte exactamente el mismo array/orden que Area y Line (un item por
  // punto del gráfico, con tipo=null cuando no hay evento) para no romper el eje X
  // categórico compartido de Recharts, que se calcula mal si un item pasa un `data` propio
  // con un subconjunto de categorías distinto al de los demás.
  const datosEventos = useMemo<EventoPunto[]>(() => {
    if (datosGrafico.length === 0) return []
    const fechasPuntos = datosGrafico.map(p => p.fecha)
    const primeraFecha = fechasPuntos[0]
    const ultimaFecha = fechasPuntos[fechasPuntos.length - 1]
    const eventosPorFecha = new Map<string, MovimientoInversion[]>()

    for (const mov of movimientos) {
      if (tipoEvento(mov.tipo_movimiento) == null) continue
      if (mov.fecha < primeraFecha || mov.fecha > ultimaFecha) continue
      let mejor = fechasPuntos[0]
      let mejorDiff = Infinity
      for (const f of fechasPuntos) {
        const diff = Math.abs(new Date(f).getTime() - new Date(mov.fecha).getTime())
        if (diff < mejorDiff) {
          mejorDiff = diff
          mejor = f
        }
      }
      const lista = eventosPorFecha.get(mejor) ?? []
      lista.push(mov)
      eventosPorFecha.set(mejor, lista)
    }

    return datosGrafico.map(p => {
      const movs = eventosPorFecha.get(p.fecha)
      if (!movs) return { fecha: p.fecha, valor: p.valor, movimientos: [], tipo: null, cantidad: 0 }
      return { fecha: p.fecha, valor: p.valor, movimientos: movs, tipo: tipoPredominante(movs), cantidad: movs.length }
    })
  }, [datosGrafico, movimientos])

  const colorLinea = COLOR_POR_VISTA[vista]

  const opcionesVista: { value: Vista; label: string }[] = [
    { value: 'ars', label: 'ARS Nominal' },
    { value: 'ars_real', label: 'ARS Real (CER)' },
    { value: 'usd', label: 'USD (MEP)' },
  ]

  return (
    <div className="pb-4">
      <ScreenHeader title="Patrimonio" onBack={() => navigate(-1)} />

      <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3">
        <button onClick={() => navigate('/rendimiento')} className="inline-flex items-center gap-1 text-label font-semibold text-app-text-dim">
          <Icon name="trend" className="w-3.5 h-3.5" /> Ver rendimiento detallado
        </button>
      </div>

      <ErrorBanner error={error} />

      <div className="mb-3">
        <Segmented options={OPCIONES_PERIODO} value={periodo} onChange={setPeriodo} />
      </div>
      <div className="mb-3">
        <Segmented options={opcionesVista} value={vista} onChange={setVista} />
      </div>

      {ultimoPunto && (
        <>
          <div className="flex items-start justify-between mb-3">
            <div>
              <div className="text-label text-app-text-faint uppercase tracking-wide mb-0.5">Valor actual</div>
              <div className="font-mono font-bold text-metric text-app-text tabular-nums">
                {formatCompact(ultimoPunto.valor, esUSD)}
              </div>
            </div>
            {deltaAbs != null && variacionPct != null && (
              <div className="text-right shrink-0 ml-4">
                <div className="text-label text-app-text-faint uppercase tracking-wide mb-0.5">Variación del período</div>
                <div className={`font-mono font-bold text-strong tabular-nums ${variacionPct >= 0 ? 'text-app-teal' : 'text-app-coral'}`}>
                  {variacionPct >= 0 ? '+' : ''}{formatCompact(deltaAbs, esUSD)} ({variacionPct >= 0 ? '+' : ''}{variacionPct.toFixed(1)}%)
                </div>
              </div>
            )}
          </div>
          {(() => {
            const valor = ultimoPunto?.valor ?? null
            const capital = ultimoPunto?.capitalAportado ?? null
            const ganancia = valor !== null && capital !== null ? valor - capital : null
            return ganancia !== null ? (
              <div className="text-label text-app-text-dim mb-3">
                Ganancia: <span className={ganancia >= 0 ? 'text-app-teal' : 'text-app-coral'}>{formatCompact(ganancia, esUSD)}</span>
              </div>
            ) : null
          })()}
        </>
      )}

      <div className="flex items-center gap-4 mb-2">
        <div className="flex items-center gap-1.5 text-label text-app-text-dim">
          <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: colorLinea }} />
          <InfoTooltip term="patrimonio_valor_mercado" label="Valor de mercado" />
        </div>
        <div className="flex items-center gap-1.5 text-label text-app-text-dim">
          <span className="w-2.5 h-0.5 rounded-full shrink-0" style={{ backgroundColor: '#8ca39b' }} />
          <InfoTooltip term="patrimonio_capital_aportado" label="Capital aportado" />
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-[260px] rounded-xl" />
      ) : datosGrafico.length === 0 ? (
        <EmptyState title="Sin datos para este período" description="Probá con un rango más amplio o revisá que la cartera tenga movimientos." />
      ) : (
        <>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={datosGrafico} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
              <defs>
                <linearGradient id="valorFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={colorLinea} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={colorLinea} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#223028" />
              <XAxis
                dataKey="fecha"
                stroke="#8ca39b"
                tick={{ fontSize: 10, fill: '#8ca39b' }}
                tickFormatter={formatFechaLabel}
                interval="preserveStartEnd"
              />
              <YAxis
                stroke="#8ca39b"
                tick={{ fontSize: 10, fill: '#8ca39b' }}
                width={62}
                tickFormatter={v => formatCompact(v, esUSD)}
              />
              <Tooltip
                cursor={{ stroke: colorLinea, strokeWidth: 1 }}
                content={({ active, label, payload }) => {
                  if (!active || !payload || payload.length === 0) return null
                  const vistos = new Set<string>()
                  const filas = payload.filter(item => {
                    const key = String(item.dataKey)
                    if (key !== 'valor' && key !== 'capitalAportado') return false
                    if (vistos.has(key)) return false
                    vistos.add(key)
                    return true
                  })
                  return (
                    <div style={{ background: '#17221e', border: '1px solid #223028', borderRadius: 10, fontSize: 12, padding: '8px 10px' }}>
                      <div style={{ color: '#edf2ef', marginBottom: 4 }}>{formatFechaTooltip(String(label))}</div>
                      {filas.map(item => (
                        <div key={String(item.dataKey)} style={{ color: item.dataKey === 'valor' ? colorLinea : '#8ca39b' }}>
                          {item.dataKey === 'valor' ? 'Valor de mercado' : 'Capital aportado'}: {formatCompact(Number(item.value), esUSD)}
                        </div>
                      ))}
                    </div>
                  )
                }}
              />
              {hwm != null && (
                <ReferenceLine
                  y={hwm}
                  stroke="#5e736a"
                  strokeDasharray="6 3"
                  label={{ value: 'Máximo histórico', position: 'insideTopLeft', fill: '#5e736a', fontSize: 10 }}
                />
              )}
              <Area
                type="stepAfter"
                dataKey="valor"
                stroke={colorLinea}
                strokeWidth={2}
                fill="url(#valorFill)"
                dot={false}
                activeDot={{ r: 5, fill: colorLinea }}
                connectNulls
              />
              <Line
                type="stepAfter"
                dataKey="capitalAportado"
                stroke="#8ca39b"
                strokeWidth={1.5}
                strokeDasharray="5 3"
                dot={false}
                activeDot={{ r: 4, fill: '#8ca39b' }}
                connectNulls
              />
              <Scatter
                data={datosEventos}
                dataKey="valor"
                shape={EventoDot}
                onClick={(payload: any) => {
                  const evento = payload as EventoPunto
                  if (evento.tipo != null) setEventoSeleccionado(evento)
                }}
              />
            </ComposedChart>
          </ResponsiveContainer>

          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
            {(Object.keys(LABEL_EVENTO) as TipoEvento[]).map(tipo => (
              <div key={tipo} className="flex items-center gap-1.5 text-label text-app-text-faint">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: COLOR_EVENTO[tipo] }} />
                {LABEL_EVENTO[tipo]}
              </div>
            ))}
          </div>
        </>
      )}

      {patrimonioSummary && (
        <>
          <div className="mt-6 mb-4">
            <div className="text-label text-app-text-faint uppercase tracking-wide font-semibold mb-2">Máximo histórico y drawdown</div>
            <div className="grid grid-cols-2 gap-2">
              <MetricTile
                label="Máximo histórico"
                infoTerm="maximoHistorico"
                value={formatCompact(vista === 'usd' ? (patrimonioSummary.maximo.valor_usd ?? 0) : (patrimonioSummary.maximo.valor_ars ?? 0), esUSD)}
                insuficiente={false}
              />
              {(() => {
                const drawdownNominal = vista === 'usd' ? (patrimonioSummary.maximo.drawdown_usd ?? 0) : (patrimonioSummary.maximo.drawdown_ars ?? 0)
                return (
                  <MetricTile
                    label="Drawdown nominal"
                    infoTerm="drawdown"
                    value={(drawdownNominal * 100).toFixed(1) + '%'}
                    insuficiente={false}
                    tone={drawdownNominal > 0.1 ? 'neg' : 'pos'}
                  />
                )
              })()}
            </div>
          </div>

          <div className="mt-6 mb-4">
            <div className="text-label text-app-text-faint uppercase tracking-wide font-semibold mb-2">Descomposición del período</div>
            <div className="space-y-2 text-label">
              <div className="flex justify-between">
                <span className="text-app-text-dim">
                  <InfoTooltip term="patrimonio_descomposicion_aportes" label="Aportes:" className="text-app-text-dim" />
                </span>
                <span className="text-app-text font-mono">{formatCompact(vista === 'usd' ? patrimonioSummary.descomposicion.aportes_usd : patrimonioSummary.descomposicion.aportes_ars, esUSD)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-app-text-dim">
                  <InfoTooltip term="patrimonio_descomposicion_rendimiento" label="Rendimiento:" className="text-app-text-dim" />
                </span>
                <span className={`font-mono ${(vista === 'usd' ? patrimonioSummary.descomposicion.rendimiento_usd : patrimonioSummary.descomposicion.rendimiento_ars) >= 0 ? 'text-app-teal' : 'text-app-coral'}`}>
                  {formatCompact(vista === 'usd' ? patrimonioSummary.descomposicion.rendimiento_usd : patrimonioSummary.descomposicion.rendimiento_ars, esUSD)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-app-text-dim">
                  <InfoTooltip term="ingresos" label="Dividendos:" className="text-app-text-dim" />
                </span>
                <span className="text-app-text font-mono">{formatCompact(vista === 'usd' ? patrimonioSummary.descomposicion.dividendos_usd : patrimonioSummary.descomposicion.dividendos_ars, esUSD)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-app-text-dim">
                  <InfoTooltip term="patrimonio_descomposicion_otros_ajustes" label="Otros ajustes (comisiones):" className="text-app-text-dim" />
                </span>
                <span className="text-app-text font-mono">{formatCompact(vista === 'usd' ? patrimonioSummary.descomposicion.otros_ajustes_usd : patrimonioSummary.descomposicion.otros_ajustes_ars, esUSD)}</span>
              </div>
              <div className="flex justify-between border-t border-app-border-soft pt-2 mt-2">
                <span className="text-app-text-dim font-semibold">
                  <InfoTooltip term="patrimonio_descomposicion_total" label="Total:" className="text-app-text-dim font-semibold" />
                </span>
                <span className="text-app-text font-mono font-bold">
                  {formatCompact(
                    (vista === 'usd'
                      ? patrimonioSummary.descomposicion.aportes_usd +
                        patrimonioSummary.descomposicion.rendimiento_usd +
                        patrimonioSummary.descomposicion.dividendos_usd +
                        patrimonioSummary.descomposicion.otros_ajustes_usd
                      : patrimonioSummary.descomposicion.aportes_ars +
                        patrimonioSummary.descomposicion.rendimiento_ars +
                        patrimonioSummary.descomposicion.dividendos_ars +
                        patrimonioSummary.descomposicion.otros_ajustes_ars),
                    esUSD
                  )}
                </span>
              </div>
            </div>
          </div>

          {patrimonioHistoria.length > 0 && (
            <div className="mt-6">
              <div className="text-label text-app-text-faint uppercase tracking-wide font-semibold mb-2">Tabla mensual</div>
              <PatrimonioMensualTable puntos={patrimonioHistoria} esUSD={esUSD} />
            </div>
          )}
        </>
      )}

      <Modal
        open={eventoSeleccionado != null}
        onClose={() => setEventoSeleccionado(null)}
        title={eventoSeleccionado ? formatFechaTooltip(eventoSeleccionado.fecha) : ''}
      >
        {eventoSeleccionado && (
          <div className="space-y-2">
            {eventoSeleccionado.movimientos.map(mov => {
              const tipo = tipoEvento(mov.tipo_movimiento)
              return (
                <div key={mov.id} className="flex items-center justify-between gap-2 py-2 border-b border-app-border-soft last:border-b-0">
                  <div>
                    <div className="text-caption font-semibold text-app-text">{TIPO_LABELS[mov.tipo_movimiento] ?? mov.tipo_movimiento}</div>
                    <div className="text-label text-app-text-dim">{mov.ticker}</div>
                  </div>
                  <div
                    className="font-mono text-caption font-bold tabular-nums"
                    style={{ color: tipo ? COLOR_EVENTO[tipo] : undefined }}
                  >
                    {tipo === 'retiro' ? '−' : '+'}{formatMontoMovimiento(mov)}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Modal>
    </div>
  )
}
