import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import dayjs from 'dayjs'
import { useInversionesContext } from '../context/InversionesContext'
import { getFlujoCajaProyectado, type FlujoCajaProyectadoOut } from '../api'
import { formatARS, formatUSD } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import InfoTooltip from '../help/components/InfoTooltip'

const COLOR_CUPON = '#d8b14a'
const COLOR_AMORT = '#5b8ba0'

type Horizonte = '12' | '24' | '36'

const CONFIANZA_LABEL: Record<string, string> = {
  alta: 'Confianza alta',
  media: 'Confianza media',
  baja: 'Confianza baja',
}

const CONFIANZA_CLASE: Record<string, string> = {
  alta: 'bg-app-teal/15 text-app-teal',
  media: 'bg-app-gold-soft text-app-gold',
  baja: 'bg-app-coral/15 text-app-coral',
}

const METODO_LABEL: Record<string, string> = {
  bullet: 'Capital al vencimiento (estimado por precio)',
  amortizacion_inferida: 'Amortización inferida del historial',
  sin_estimacion: 'Sin estimación de capital',
}

function mesLabel(periodo: string): string {
  return dayjs(`${periodo}-01`).format('MMM YY')
}

export default function FlujoCaja() {
  const navigate = useNavigate()
  const { carteraSeleccionada, monedaSeleccionada, syncVersion } = useInversionesContext()
  const [datos, setDatos] = useState<FlujoCajaProyectadoOut | null>(null)
  const [horizonte, setHorizonte] = useState<Horizonte>('24')
  const [loading, setLoading] = useState(true)

  const esARS = monedaSeleccionada === 'ARS'
  const fmt = esARS ? formatARS : formatUSD

  useEffect(() => {
    let cancelado = false
    setLoading(true)
    getFlujoCajaProyectado(carteraSeleccionada, Number(horizonte))
      .then(data => {
        if (!cancelado) setDatos(data)
      })
      .catch(() => {
        if (!cancelado) setDatos(null)
      })
      .finally(() => {
        if (!cancelado) setLoading(false)
      })
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada, horizonte, syncVersion])

  const chartData = useMemo(() => {
    if (!datos) return []
    return datos.meses.map(m => ({
      periodo: m.periodo,
      cupones: esARS ? m.cupones_ars : m.cupones_usd,
      amortizaciones: esARS ? m.amortizaciones_ars : m.amortizaciones_usd,
      total: esARS ? m.total_ars : m.total_usd,
    }))
  }, [datos, esARS])

  const hayCobros = useMemo(() => chartData.some(d => d.total > 0), [chartData])

  return (
    <div className="pb-4">
      <ScreenHeader title="Flujo de caja proyectado" onBack={() => navigate(-1)} />

      <div className="px-4 pt-2 mb-3 flex items-center gap-2 text-[12px] text-app-text-dim">
        <span className="font-semibold text-app-text">Cómo se calcula</span>
        <InfoTooltip term="flujocaja_titulo" />
        <InfoTooltip term="flujocaja_inferido" />
      </div>

      <div className="px-4 mb-4">
        <Segmented<Horizonte>
          options={[
            { value: '12', label: '12 meses' },
            { value: '24', label: '24 meses' },
            { value: '36', label: '36 meses' },
          ]}
          value={horizonte}
          onChange={setHorizonte}
        />
      </div>

      {loading ? (
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      ) : !datos || (datos.instrumentos.length === 0 && datos.sin_proyeccion.length === 0) ? (
        <EmptyState
          title="Sin renta fija proyectable"
          description="No hay bonos, ON ni letras con tenencia activa y fecha de vencimiento en esta cartera."
        />
      ) : (
        <div className="px-4 flex flex-col gap-4">
          <Card>
            <div className="text-[10px] font-bold uppercase tracking-wide text-app-text-faint mb-1">
              Total a cobrar · próximos {datos.horizonte_meses} meses
            </div>
            <div className="font-mono text-[26px] font-bold text-app-text tabular-nums">
              {fmt(esARS ? datos.total_ars : datos.total_usd)}
            </div>
            <div className="text-[11.5px] text-app-text-dim mt-2 flex flex-wrap gap-x-4 gap-y-1">
              <span>
                <span className="inline-block w-2 h-2 rounded-sm mr-1.5 align-middle" style={{ background: COLOR_CUPON }} />
                Cupones {fmt(esARS ? datos.total_cupones_ars : datos.total_cupones_usd)}
              </span>
              <span>
                <span className="inline-block w-2 h-2 rounded-sm mr-1.5 align-middle" style={{ background: COLOR_AMORT }} />
                Amortizaciones {fmt(esARS ? datos.total_amortizaciones_ars : datos.total_amortizaciones_usd)}
              </span>
            </div>
            <div className="text-[11px] text-app-text-faint mt-2">
              Todo estimado a partir de tu historial de cobros. Tipo de cambio: MEP más reciente.
            </div>
          </Card>

          {hayCobros ? (
            <Card>
              <div className="text-[12px] font-semibold text-app-text mb-2">Cobros por mes</div>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={chartData} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#223028" />
                  <XAxis
                    dataKey="periodo"
                    stroke="#8ca39b"
                    tick={{ fontSize: 9, fill: '#8ca39b' }}
                    tickFormatter={mesLabel}
                    interval="preserveStartEnd"
                    minTickGap={12}
                  />
                  <YAxis
                    stroke="#8ca39b"
                    tick={{ fontSize: 10, fill: '#8ca39b' }}
                    width={54}
                    tickFormatter={v => (esARS ? `$${(v / 1000).toFixed(0)}k` : `U$S ${v}`)}
                  />
                  <Tooltip
                    contentStyle={{ background: '#17221e', border: '1px solid #223028', borderRadius: 10, fontSize: 12 }}
                    labelStyle={{ color: '#edf2ef' }}
                    cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                    labelFormatter={(v: string) => dayjs(`${v}-01`).format('MMMM YYYY')}
                    formatter={(value: number, name: string) => [fmt(value), name === 'cupones' ? 'Cupones' : 'Amortizaciones']}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 11, color: '#8ca39b', paddingTop: 8 }}
                    formatter={(v: string) => (v === 'cupones' ? 'Cupones' : 'Amortizaciones')}
                  />
                  <Bar dataKey="cupones" stackId="a" fill={COLOR_CUPON} />
                  <Bar dataKey="amortizaciones" stackId="a" fill={COLOR_AMORT} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          ) : (
            <Card>
              <div className="text-[12px] text-app-text-dim text-center py-6">
                No hay cobros proyectados dentro del horizonte elegido.
              </div>
            </Card>
          )}

          {datos.instrumentos.length > 0 && (
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2 px-0.5 flex items-center gap-2">
                Por instrumento
                <InfoTooltip term="flujocaja_confianza" />
              </div>
              <div className="flex flex-col gap-2">
                {datos.instrumentos.map(inst => (
                  <Card key={inst.ticker} className="!p-3.5">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-[13.5px] font-semibold text-app-text truncate">{inst.ticker}</div>
                        <div className="text-[11.5px] text-app-text-dim truncate">{inst.nombre}</div>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="font-mono text-[14px] font-bold text-app-text tabular-nums">
                          {fmt(esARS ? inst.total_proyectado_ars : inst.total_proyectado_usd)}
                        </div>
                        <div className="text-[10.5px] text-app-text-faint">{inst.cobros_proyectados} cobro{inst.cobros_proyectados !== 1 ? 's' : ''}</div>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5 mt-2.5">
                      {inst.periodicidad_label && (
                        <span className="text-[10.5px] px-1.5 py-0.5 rounded bg-app-surface-2 text-app-text-dim">
                          {inst.periodicidad_label}
                        </span>
                      )}
                      {inst.confianza && (
                        <span className={`text-[10.5px] px-1.5 py-0.5 rounded ${CONFIANZA_CLASE[inst.confianza] ?? 'bg-app-surface-2 text-app-text-dim'}`}>
                          {CONFIANZA_LABEL[inst.confianza] ?? inst.confianza}
                        </span>
                      )}
                      <span className="text-[10.5px] px-1.5 py-0.5 rounded bg-app-surface-2 text-app-text-dim">
                        {METODO_LABEL[inst.metodo_capital] ?? inst.metodo_capital}
                      </span>
                    </div>

                    <div className="text-[11.5px] text-app-text-dim mt-2 space-y-0.5">
                      <div>
                        Vence {dayjs(inst.fecha_vencimiento).format('DD/MM/YYYY')}
                        {inst.proximo_cobro && (
                          <>
                            {' · '}próximo cobro {dayjs(inst.proximo_cobro.fecha).format('DD/MM/YYYY')}
                            {' ('}
                            {inst.proximo_cobro.tipo === 'cupon' ? 'cupón' : 'amortización'}{' '}
                            {fmt(esARS ? inst.proximo_cobro.monto_ars : inst.proximo_cobro.monto_usd)}
                            {')'}
                          </>
                        )}
                      </div>
                      {inst.notas.map((n, i) => (
                        <div key={i} className="text-app-text-faint">— {n}</div>
                      ))}
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {datos.sin_proyeccion.length > 0 && (
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2 px-0.5">
                Sin proyección
              </div>
              <div className="flex flex-col gap-2">
                {datos.sin_proyeccion.map(item => (
                  <Card key={item.ticker} className="!p-3.5">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-[13px] font-semibold text-app-text truncate">{item.ticker}</div>
                        <div className="text-[11.5px] text-app-text-dim truncate">{item.nombre}</div>
                      </div>
                      <div className="text-[11px] text-app-text-faint shrink-0">
                        vence {dayjs(item.fecha_vencimiento).format('DD/MM/YYYY')}
                      </div>
                    </div>
                    <div className="text-[11.5px] text-app-text-faint mt-1.5">{item.motivo}</div>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
