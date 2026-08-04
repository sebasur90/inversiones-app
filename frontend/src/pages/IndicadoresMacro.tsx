import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { getIndicesMercado, type IndicesMercadoOut } from '../api'
import { formatPct } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import EmptyState from '../components/ui/EmptyState'
import { Icon } from '../components/icons/Icons'

type Vista = 'cer' | 'mep'

function formatIndice(v: number): string {
  return v.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatFechaLabel(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  const mes = (d.getMonth() + 1).toString().padStart(2, '0')
  const anio = d.getFullYear().toString().slice(2)
  return `${mes}/${anio}`
}

function formatFechaTooltip(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' })
}

const OPCIONES: { value: Vista; label: string }[] = [
  { value: 'cer', label: 'CER' },
  { value: 'mep', label: 'MEP' },
]

export default function IndicadoresMacro() {
  const navigate = useNavigate()
  const [datos, setDatos] = useState<IndicesMercadoOut | null>(null)
  const [vista, setVista] = useState<Vista>('cer')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getIndicesMercado()
      .then(setDatos)
      .catch(() => setDatos(null))
      .finally(() => setLoading(false))
  }, [])

  const datosGrafico = (datos?.puntos ?? [])
    .map(p => ({ fecha: p.fecha, valor: vista === 'cer' ? p.cer : p.mep }))
    .filter(p => p.valor != null) as { fecha: string; valor: number }[]

  const colorLinea = vista === 'cer' ? '#9c7aa0' : '#4fd1ae'
  const variacion = vista === 'cer' ? datos?.variacion_cer_pct : datos?.variacion_mep_pct
  const positivo = (variacion ?? 0) >= 0
  const ultimoPunto = datosGrafico.length > 0 ? datosGrafico[datosGrafico.length - 1] : undefined

  if (loading) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Indicadores macro" onBack={() => navigate(-1)} />
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      </div>
    )
  }

  if (!datos || datos.puntos.length === 0) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Indicadores macro" onBack={() => navigate(-1)} />
        <EmptyState title="Sin índices cargados" description="Sincronizá el sheet para ver la evolución de CER y MEP." />
      </div>
    )
  }

  return (
    <div className="pb-4">
      <ScreenHeader title="Indicadores macro" onBack={() => navigate(-1)} />

      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="font-semibold text-[15px] text-app-text">{vista.toUpperCase()}</div>
          <div className="text-[11.5px] text-app-text-dim">Índice / tipo de cambio (Sheet)</div>
        </div>
        {ultimoPunto && (
          <div className="text-right shrink-0 ml-4">
            <div className="text-[10px] text-app-text-faint uppercase tracking-wide mb-0.5">Último registro</div>
            <div className="font-mono font-bold text-[15px] text-app-text tabular-nums">{formatIndice(ultimoPunto.valor)}</div>
            {variacion != null && (
              <div className={`inline-flex items-center gap-0.5 font-mono text-[11px] font-bold mt-0.5 tabular-nums ${positivo ? 'text-app-teal' : 'text-app-coral'}`}>
                <Icon name={positivo ? 'up' : 'down'} className="w-2.5 h-2.5" />
                {formatPct(variacion)}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="mb-3">
        <Segmented options={OPCIONES} value={vista} onChange={setVista} />
      </div>

      {datosGrafico.length === 0 ? (
        <div className="h-[220px] flex items-center justify-center text-app-text-dim text-[12.5px]">
          Sin datos para esta vista
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
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
              tickFormatter={formatIndice}
            />
            <Tooltip
              contentStyle={{ background: '#17221e', border: '1px solid #223028', borderRadius: 10, fontSize: 12 }}
              labelStyle={{ color: '#edf2ef' }}
              formatter={(v: number) => [formatIndice(v), vista.toUpperCase()]}
              labelFormatter={formatFechaTooltip}
              cursor={{ stroke: colorLinea, strokeWidth: 1 }}
            />
            <Line
              type="monotone"
              dataKey="valor"
              stroke={colorLinea}
              strokeWidth={2}
              dot={{ r: 3.5, fill: colorLinea, strokeWidth: 0 }}
              activeDot={{ r: 5, fill: colorLinea }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      <div className="mt-2 text-[10.5px] text-app-text-dim">
        {datosGrafico.length} registro{datosGrafico.length !== 1 ? 's' : ''} cargados
        {ultimoPunto && ` · hasta ${formatFechaTooltip(ultimoPunto.fecha)}`}
      </div>
    </div>
  )
}
