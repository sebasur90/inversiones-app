import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { useInversionesContext } from '../context/InversionesContext'
import { getEvolucionInversiones, type EvolucionPunto } from '../api'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import EmptyState from '../components/ui/EmptyState'
import { Icon } from '../components/icons/Icons'

type Periodo = '1M' | '3M' | '1Y' | 'YTD' | 'ALL'
type Vista = 'ars' | 'ars_real' | 'usd'

const OPCIONES_PERIODO: { value: Periodo; label: string }[] = [
  { value: '1M', label: '1M' },
  { value: '3M', label: '3M' },
  { value: '1Y', label: '1Y' },
  { value: 'YTD', label: 'YTD' },
  { value: 'ALL', label: 'ALL' },
]

function calcularDesde(periodo: Periodo): string | undefined {
  const hoy = new Date()
  if (periodo === 'ALL') return undefined
  if (periodo === 'YTD') return `${hoy.getFullYear()}-01-01`
  const d = new Date(hoy)
  if (periodo === '1M') d.setMonth(d.getMonth() - 1)
  if (periodo === '3M') d.setMonth(d.getMonth() - 3)
  if (periodo === '1Y') d.setFullYear(d.getFullYear() - 1)
  return d.toISOString().slice(0, 10)
}

function formatCompact(v: number, esUSD: boolean): string {
  const abs = Math.abs(v)
  if (esUSD) {
    if (abs >= 1_000_000) return `U$S ${(v / 1_000_000).toFixed(1)}M`
    if (abs >= 1000) return `U$S ${(v / 1000).toFixed(0)}K`
    return `U$S ${v.toFixed(2)}`
  }
  if (abs >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
  if (abs >= 1000) return `$${(v / 1000).toFixed(0)}K`
  return `$${v.toFixed(0)}`
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

export default function Patrimonio() {
  const navigate = useNavigate()
  const { carteraSeleccionada } = useInversionesContext()
  const [periodo, setPeriodo] = useState<Periodo>('1Y')
  const [vista, setVista] = useState<Vista>('ars')
  const [puntos, setPuntos] = useState<EvolucionPunto[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelado = false
    setLoading(true)
    getEvolucionInversiones(carteraSeleccionada, calcularDesde(periodo))
      .then(data => {
        if (!cancelado) setPuntos(data.puntos)
      })
      .catch(() => {
        if (!cancelado) setPuntos([])
      })
      .finally(() => {
        if (!cancelado) setLoading(false)
      })
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada, periodo])

  const esUSD = vista === 'usd'
  const datosGrafico = puntos
    .map(p => ({
      fecha: p.fecha,
      valor: vista === 'ars' ? p.valor_ars : vista === 'usd' ? p.valor_usd : p.valor_ars_real,
    }))
    .filter(p => p.valor != null) as { fecha: string; valor: number }[]

  const primerPunto = datosGrafico.length > 0 ? datosGrafico[0] : undefined
  const ultimoPunto = datosGrafico.length > 0 ? datosGrafico[datosGrafico.length - 1] : undefined
  const variacionPct =
    primerPunto && ultimoPunto && primerPunto.valor !== 0
      ? ((ultimoPunto.valor - primerPunto.valor) / Math.abs(primerPunto.valor)) * 100
      : null

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
        <button onClick={() => navigate('/rendimiento')} className="inline-flex items-center gap-1 text-[11px] font-semibold text-app-text-dim">
          <Icon name="trend" className="w-3.5 h-3.5" /> Ver rendimiento detallado
        </button>
      </div>

      <div className="mb-3">
        <Segmented options={OPCIONES_PERIODO} value={periodo} onChange={setPeriodo} />
      </div>
      <div className="mb-3">
        <Segmented options={opcionesVista} value={vista} onChange={setVista} />
      </div>

      {ultimoPunto && (
        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="text-[10px] text-app-text-faint uppercase tracking-wide mb-0.5">Valor actual</div>
            <div className="font-mono font-bold text-[22px] text-app-text tabular-nums">
              {formatCompact(ultimoPunto.valor, esUSD)}
            </div>
          </div>
          {variacionPct != null && (
            <div className="text-right shrink-0 ml-4">
              <div className="text-[10px] text-app-text-faint uppercase tracking-wide mb-0.5">Variación del período</div>
              <div className={`font-mono font-bold text-[15px] tabular-nums ${variacionPct >= 0 ? 'text-app-teal' : 'text-app-coral'}`}>
                {variacionPct >= 0 ? '+' : ''}{variacionPct.toFixed(1)}%
              </div>
            </div>
          )}
        </div>
      )}

      {loading ? (
        <div className="h-[260px] flex items-center justify-center text-app-text-dim text-[12.5px]">Cargando…</div>
      ) : datosGrafico.length === 0 ? (
        <EmptyState title="Sin datos para este período" description="Probá con un rango más amplio o revisá que la cartera tenga movimientos." />
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={datosGrafico} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
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
              contentStyle={{ background: '#17221e', border: '1px solid #223028', borderRadius: 10, fontSize: 12 }}
              labelStyle={{ color: '#edf2ef' }}
              formatter={(v: number) => [formatCompact(v, esUSD), 'Valor']}
              labelFormatter={formatFechaTooltip}
              cursor={{ stroke: colorLinea, strokeWidth: 1 }}
            />
            <Line
              type="monotone"
              dataKey="valor"
              stroke={colorLinea}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5, fill: colorLinea }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
