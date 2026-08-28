import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { getIndicesMercado, type IndicesMercadoOut } from '../api'
import { formatPct } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import EmptyState from '../components/ui/EmptyState'
import { Icon } from '../components/icons/Icons'
import InfoTooltip from '../help/components/InfoTooltip'
import { useInversionesContext } from '../context/InversionesContext'

type Vista = 'cer' | 'mep' | 'riesgo_pais' | 'inflacion'

function formatIndice(v: number): string {
  return v.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatEntero(v: number): string {
  return Math.round(v).toLocaleString('es-AR')
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
  { value: 'riesgo_pais', label: 'Riesgo país' },
  { value: 'inflacion', label: 'Inflación' },
]

const META: Record<Vista, { titulo: string; sub: string; color: string; formato: (v: number) => string; unidad: string }> = {
  cer: { titulo: 'CER', sub: 'Índice de inflación (Sheet + API)', color: '#9c7aa0', formato: formatIndice, unidad: '' },
  mep: { titulo: 'MEP', sub: 'Dólar bolsa (Sheet + API)', color: '#4fd1ae', formato: formatIndice, unidad: '$' },
  riesgo_pais: { titulo: 'Riesgo país', sub: 'EMBI+ Argentina (ArgentinaDatos)', color: '#e0a15f', formato: formatEntero, unidad: 'pb' },
  inflacion: { titulo: 'Inflación mensual', sub: 'Variación % mes a mes (INDEC)', color: '#d97b6c', formato: (v: number) => formatPct(v), unidad: '%' },
}

export default function IndicadoresMacro() {
  const { syncVersion } = useInversionesContext()
  const navigate = useNavigate()
  const [datos, setDatos] = useState<IndicesMercadoOut | null>(null)
  const [vista, setVista] = useState<Vista>('cer')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getIndicesMercado()
      .then(setDatos)
      .catch(() => setDatos(null))
      .finally(() => setLoading(false))
  }, [syncVersion])

  const meta = META[vista]
  const esInflacion = vista === 'inflacion'

  const datosGrafico = useMemo(() => {
    if (!datos) return [] as { fecha: string; valor: number }[]
    if (esInflacion) {
      return datos.inflacion_mensual.map(p => ({ fecha: p.fecha, valor: p.valor_pct }))
    }
    return datos.puntos
      .map(p => ({ fecha: p.fecha, valor: vista === 'cer' ? p.cer : vista === 'mep' ? p.mep : p.riesgo_pais }))
      .filter(p => p.valor != null) as { fecha: string; valor: number }[]
  }, [datos, vista, esInflacion])

  const variacion = vista === 'cer'
    ? datos?.variacion_cer_pct
    : vista === 'mep'
      ? datos?.variacion_mep_pct
      : vista === 'riesgo_pais'
        ? datos?.variacion_riesgo_pais_pct
        : null
  const positivo = (variacion ?? 0) >= 0
  const ultimoPunto = datosGrafico.length > 0 ? datosGrafico[datosGrafico.length - 1] : undefined

  const hayAlgo = datos && (datos.puntos.length > 0 || datos.inflacion_mensual.length > 0)

  if (loading) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Indicadores macro" onBack={() => navigate(-1)} />
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      </div>
    )
  }

  if (!hayAlgo) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Indicadores macro" onBack={() => navigate(-1)} />
        <EmptyState title="Sin indicadores cargados" description="Sincronizá el sheet para ver CER, MEP, riesgo país e inflación." />
      </div>
    )
  }

  return (
    <div className="pb-4">
      <ScreenHeader title="Indicadores macro" onBack={() => navigate(-1)} />

      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="font-semibold text-[15px] text-app-text">{meta.titulo}</div>
          <div className="text-[11.5px] text-app-text-dim">{meta.sub}</div>
        </div>
        {ultimoPunto && (
          <div className="text-right shrink-0 ml-4">
            <div className="text-[10px] text-app-text-faint uppercase tracking-wide mb-0.5 flex items-center justify-end gap-1.5">
              <span>Último registro</span>
              <InfoTooltip term="precios_ultimo_registro" />
            </div>
            <div className="font-mono font-bold text-[15px] text-app-text tabular-nums">
              {meta.formato(ultimoPunto.valor)}{meta.unidad && !esInflacion ? ` ${meta.unidad}` : ''}
            </div>
            {!esInflacion && variacion != null && (
              <div className={`inline-flex items-center gap-0.5 font-mono text-[11px] font-bold mt-0.5 tabular-nums ${positivo ? 'text-app-teal' : 'text-app-coral'}`}>
                <Icon name={positivo ? 'up' : 'down'} className="w-2.5 h-2.5" />
                {formatPct(variacion)}
                <div className="ml-0.5">
                  <InfoTooltip term="indicadoresmacro_variacion" />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="px-4 mb-4 pt-2">
        <div className="text-[12px] text-app-text-dim space-y-1.5 mb-3">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-app-text">CER</span>
            <InfoTooltip term="cer" />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-app-text">MEP</span>
            <InfoTooltip term="mep" />
          </div>
          <div className="text-[11.5px]">
            <span className="font-semibold text-app-text">Riesgo país</span>: sobretasa que paga
            la deuda argentina vs. la de EE. UU., en puntos básicos (100 pb = 1%).
          </div>
        </div>
      </div>

      <div className="mb-3">
        <Segmented options={OPCIONES} value={vista} onChange={setVista} />
      </div>

      {datosGrafico.length === 0 ? (
        <div className="h-[220px] flex items-center justify-center text-app-text-dim text-[12.5px]">
          {esInflacion
            ? 'Sin serie de inflación. Requiere el benchmark "Inflación (INDEC)" (se completa vía API).'
            : vista === 'riesgo_pais'
              ? 'Sin serie de riesgo país. Se completa automáticamente vía API en el próximo sync.'
              : 'Sin datos para esta vista'}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          {esInflacion ? (
            <BarChart data={datosGrafico} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#223028" />
              <XAxis dataKey="fecha" stroke="#8ca39b" tick={{ fontSize: 10, fill: '#8ca39b' }} tickFormatter={formatFechaLabel} interval="preserveStartEnd" />
              <YAxis stroke="#8ca39b" tick={{ fontSize: 10, fill: '#8ca39b' }} width={44} tickFormatter={(v: number) => `${v}%`} />
              <Tooltip
                contentStyle={{ background: '#17221e', border: '1px solid #223028', borderRadius: 10, fontSize: 12 }}
                labelStyle={{ color: '#edf2ef' }}
                formatter={(v: number) => [formatPct(v), 'Inflación']}
                labelFormatter={formatFechaTooltip}
                cursor={{ fill: 'rgba(255,255,255,0.04)' }}
              />
              <Bar dataKey="valor" fill={meta.color} radius={[3, 3, 0, 0]} />
            </BarChart>
          ) : (
            <LineChart data={datosGrafico} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#223028" />
              <XAxis dataKey="fecha" stroke="#8ca39b" tick={{ fontSize: 10, fill: '#8ca39b' }} tickFormatter={formatFechaLabel} interval="preserveStartEnd" />
              <YAxis stroke="#8ca39b" tick={{ fontSize: 10, fill: '#8ca39b' }} width={62} tickFormatter={vista === 'riesgo_pais' ? formatEntero : formatIndice} />
              <Tooltip
                contentStyle={{ background: '#17221e', border: '1px solid #223028', borderRadius: 10, fontSize: 12 }}
                labelStyle={{ color: '#edf2ef' }}
                formatter={(v: number) => [meta.formato(v), meta.titulo]}
                labelFormatter={formatFechaTooltip}
                cursor={{ stroke: meta.color, strokeWidth: 1 }}
              />
              <Line
                type="monotone"
                dataKey="valor"
                stroke={meta.color}
                strokeWidth={2}
                dot={{ r: 3.5, fill: meta.color, strokeWidth: 0 }}
                activeDot={{ r: 5, fill: meta.color }}
                connectNulls
              />
            </LineChart>
          )}
        </ResponsiveContainer>
      )}

      <div className="mt-2 text-[10.5px] text-app-text-dim">
        {datosGrafico.length} registro{datosGrafico.length !== 1 ? 's' : ''}
        {ultimoPunto && ` · hasta ${formatFechaTooltip(ultimoPunto.fecha)}`}
      </div>
    </div>
  )
}
