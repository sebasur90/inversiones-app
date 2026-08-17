import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceDot, ResponsiveContainer } from 'recharts'
import { useInversionesContext } from '../context/InversionesContext'
import { getRiesgo, getBenchmarksDisponibles, getConfiguracionCartera, type RiesgoOut, type MonedaRiesgo, type PeriodoRetorno } from '../api'
import { formatPctRatio } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import Segmented from '../components/ui/Segmented'
import { Icon } from '../components/icons/Icons'
import InfoTerm from '../components/ui/InfoTerm'
import type { GlosarioKey } from '../data/glosario'

const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

const OPCIONES_VISTA: { value: MonedaRiesgo; label: string }[] = [
  { value: 'ars_nominal', label: 'ARS Nominal' },
  { value: 'ars_real', label: 'ARS Real (CER)' },
  { value: 'usd', label: 'USD (MEP)' },
]

function formatMesLabel(anio: number, mes: number): string {
  return `${MESES[mes - 1]} ${String(anio).slice(2)}`
}

function formatFechaEje(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return `${MESES[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`
}

function formatRatio(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toFixed(2)
}

function toneClass(v: number | null | undefined): string {
  if (v == null) return 'text-app-text'
  return v >= 0 ? 'text-app-teal' : 'text-app-coral'
}

function MetricCard({
  label,
  infoTerm,
  value,
  subtitulo,
  insuficiente,
  tone,
}: {
  label: string
  infoTerm: GlosarioKey
  value: string
  subtitulo?: string
  insuficiente?: boolean
  tone?: string
}) {
  return (
    <div className="bg-app-surface border border-app-border rounded-[13px] px-2.5 py-2.5">
      <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">
        <InfoTerm term={infoTerm} label={label} />
      </div>
      {insuficiente ? (
        <div className="text-[12px] text-app-text-faint">Datos insuficientes</div>
      ) : (
        <div className={`font-mono text-[14px] font-bold tabular-nums ${tone ?? 'text-app-text'}`}>{value}</div>
      )}
      {subtitulo && !insuficiente && <div className="text-[10px] text-app-text-dim mt-0.5">{subtitulo}</div>}
    </div>
  )
}

function PeriodoRow({ item }: { item: PeriodoRetorno }) {
  return (
    <div className="flex items-center justify-between bg-app-surface border border-app-border rounded-[13px] px-3.5 py-2 text-left">
      <div className="text-[12.5px] font-semibold text-app-text">{formatMesLabel(item.anio, item.mes)}</div>
      <div className={`font-mono font-bold text-[13px] tabular-nums ${toneClass(item.retorno)}`}>{formatPctRatio(item.retorno)}</div>
    </div>
  )
}

export default function Riesgo() {
  const navigate = useNavigate()
  const { carteraSeleccionada } = useInversionesContext()
  const [vista, setVista] = useState<MonedaRiesgo>('usd')
  const [benchmarks, setBenchmarks] = useState<string[]>([])
  const [benchmarkSeleccionado, setBenchmarkSeleccionado] = useState<string | null>(null)
  const [riesgo, setRiesgo] = useState<RiesgoOut | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelado = false
    Promise.all([getBenchmarksDisponibles(), getConfiguracionCartera(carteraSeleccionada).catch(() => null)])
      .then(([data, config]) => {
        if (cancelado) return
        setBenchmarks(data)
        const preferido = config?.benchmark && data.includes(config.benchmark) ? config.benchmark : data[0] ?? null
        setBenchmarkSeleccionado(prev => prev ?? preferido)
      })
      .catch(() => {
        if (!cancelado) setBenchmarks([])
      })
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada])

  useEffect(() => {
    let cancelado = false
    setLoading(true)
    getRiesgo(carteraSeleccionada, vista, benchmarkSeleccionado)
      .then(data => {
        if (!cancelado) setRiesgo(data)
      })
      .catch(() => {
        if (!cancelado) setRiesgo(null)
      })
      .finally(() => {
        if (!cancelado) setLoading(false)
      })
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada, vista, benchmarkSeleccionado])

  const sinHistorialSuficiente = riesgo != null && riesgo.n_meses_historia === 0
  const serieDrawdown = riesgo?.drawdown.serie ?? []

  return (
    <div className="pb-4">
      <ScreenHeader title="Riesgo" onBack={() => navigate(-1)} />

      <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3">
        <button onClick={() => navigate('/rendimiento')} className="inline-flex items-center gap-1 text-[11px] font-semibold text-app-text-dim">
          <Icon name="trend" className="w-3.5 h-3.5" /> Ver rendimiento detallado
        </button>
        <button onClick={() => navigate('/contribucion')} className="inline-flex items-center gap-1 text-[11px] font-semibold text-app-text-dim">
          <Icon name="scale" className="w-3.5 h-3.5" /> Ver contribución y concentración
        </button>
      </div>

      <div className="mb-3">
        <Segmented options={OPCIONES_VISTA} value={vista} onChange={setVista} />
      </div>

      {benchmarks.length > 0 && (
        <div className="mb-3">
          <div className="text-[10px] text-app-text-faint uppercase tracking-wide mb-1.5">Benchmark para Sharpe</div>
          <Segmented
            options={benchmarks.map(b => ({ value: b, label: b }))}
            value={benchmarkSeleccionado ?? benchmarks[0]}
            onChange={setBenchmarkSeleccionado}
          />
        </div>
      )}

      {loading ? (
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      ) : !riesgo || sinHistorialSuficiente ? (
        <EmptyState title="Sin datos" description="No hay suficiente historial mensual para calcular métricas de riesgo de esta cartera." />
      ) : (
        <>
          <div className="text-[11px] text-app-text-dim mb-3">
            Basado en {riesgo.n_meses_historia} mes{riesgo.n_meses_historia === 1 ? '' : 'es'} de historial (frecuencia mensual).
          </div>

          <h3 className="text-[13.5px] font-bold text-app-text mb-2.5">
            <InfoTerm term="drawdown" label="Drawdown" />
          </h3>
          {serieDrawdown.length < 2 ? (
            <EmptyState title="Sin historial suficiente" description="Se necesitan al menos 2 meses con tenencia para graficar el drawdown." />
          ) : (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <AreaChart data={serieDrawdown} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
                  <defs>
                    <linearGradient id="ddFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#e2665a" stopOpacity={0} />
                      <stop offset="95%" stopColor="#e2665a" stopOpacity={0.35} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#223028" />
                  <XAxis
                    dataKey="fecha"
                    stroke="#8ca39b"
                    tick={{ fontSize: 10, fill: '#8ca39b' }}
                    tickFormatter={formatFechaEje}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    stroke="#8ca39b"
                    tick={{ fontSize: 10, fill: '#8ca39b' }}
                    width={44}
                    tickFormatter={v => `${(v * 100).toFixed(0)}%`}
                  />
                  <Tooltip
                    cursor={{ stroke: '#e2665a', strokeWidth: 1 }}
                    content={({ active, label, payload }) => {
                      if (!active || !payload || payload.length === 0) return null
                      return (
                        <div style={{ background: '#17221e', border: '1px solid #223028', borderRadius: 10, fontSize: 12, padding: '8px 10px' }}>
                          <div style={{ color: '#edf2ef', marginBottom: 4 }}>{formatFechaEje(String(label))}</div>
                          <div style={{ color: '#e2665a' }}>Drawdown: {formatPctRatio(Number(payload[0].value))}</div>
                        </div>
                      )
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="drawdown"
                    stroke="#e2665a"
                    strokeWidth={2}
                    fill="url(#ddFill)"
                    dot={false}
                    activeDot={{ r: 4, fill: '#e2665a' }}
                  />
                  {riesgo.drawdown.fecha_valle && riesgo.drawdown.maximo != null && (
                    <ReferenceDot
                      x={riesgo.drawdown.fecha_valle}
                      y={riesgo.drawdown.maximo}
                      r={5}
                      fill="#e2665a"
                      stroke="#0b1210"
                      strokeWidth={2}
                    />
                  )}
                </AreaChart>
              </ResponsiveContainer>
              <div className="text-[11px] text-app-text-dim mt-1.5">
                {riesgo.drawdown.en_recuperacion
                  ? 'Todavía no se recuperó del máximo drawdown.'
                  : riesgo.drawdown.tiempo_recuperacion_meses != null
                    ? `Se recuperó del máximo drawdown en ${riesgo.drawdown.tiempo_recuperacion_meses} mes${riesgo.drawdown.tiempo_recuperacion_meses === 1 ? '' : 'es'}.`
                    : null}
              </div>
            </>
          )}

          <div className="grid grid-cols-2 gap-2 my-4">
            <MetricCard
              label="Drawdown actual"
              infoTerm="drawdown"
              value={formatPctRatio(riesgo.drawdown.actual)}
              insuficiente={riesgo.drawdown.estado !== 'ok'}
              tone={toneClass(riesgo.drawdown.actual)}
            />
            <MetricCard
              label="Drawdown máximo"
              infoTerm="drawdown"
              value={formatPctRatio(riesgo.drawdown.maximo)}
              insuficiente={riesgo.drawdown.estado !== 'ok'}
              tone="text-app-coral"
            />
            <MetricCard
              label="Volatilidad anualizada"
              infoTerm="volatilidad"
              value={formatPctRatio(riesgo.volatilidad.anualizada)}
              insuficiente={riesgo.volatilidad.estado !== 'ok'}
            />
            <MetricCard
              label="Calmar"
              infoTerm="calmar"
              value={formatRatio(riesgo.calmar.valor)}
              insuficiente={riesgo.calmar.estado !== 'ok'}
              tone={toneClass(riesgo.calmar.valor)}
            />
            <MetricCard
              label="Sortino"
              infoTerm="sortino"
              value={formatRatio(riesgo.sortino.valor)}
              insuficiente={riesgo.sortino.estado !== 'ok' || riesgo.sortino.valor == null}
              tone={toneClass(riesgo.sortino.valor)}
            />
            <MetricCard
              label="Sharpe"
              infoTerm="sharpe"
              value={formatRatio(riesgo.sharpe.valor)}
              subtitulo={riesgo.sharpe.benchmark ? `vs. ${riesgo.sharpe.benchmark}` : undefined}
              insuficiente={riesgo.sharpe.estado !== 'ok'}
              tone={toneClass(riesgo.sharpe.valor)}
            />
          </div>

          {riesgo.frecuencia_positivos_negativos.estado === 'ok' && (
            <Card className="mb-4">
              <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">Meses positivos / negativos</div>
              <div className="text-[13px] text-app-text">
                <span className="text-app-teal font-bold">{formatPctRatio(riesgo.frecuencia_positivos_negativos.pct_positivos)}</span> positivos ·{' '}
                <span className="text-app-coral font-bold">{formatPctRatio(riesgo.frecuencia_positivos_negativos.pct_negativos)}</span> negativos
                <span className="text-app-text-dim"> ({riesgo.frecuencia_positivos_negativos.n_obs} meses)</span>
              </div>
            </Card>
          )}

          {(riesgo.mejores_periodos.length > 0 || riesgo.peores_periodos.length > 0) && (
            <>
              <h3 className="text-[13.5px] font-bold text-app-text mb-2.5">Mejores meses</h3>
              <div className="flex flex-col gap-1.5 mb-4">
                {riesgo.mejores_periodos.map(p => (
                  <PeriodoRow key={`mejor-${p.anio}-${p.mes}`} item={p} />
                ))}
              </div>
              <h3 className="text-[13.5px] font-bold text-app-text mb-2.5">Peores meses</h3>
              <div className="flex flex-col gap-1.5">
                {riesgo.peores_periodos.map(p => (
                  <PeriodoRow key={`peor-${p.anio}-${p.mes}`} item={p} />
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
