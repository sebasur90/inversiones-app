import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getCiclosTasas, type CicloCambioPp, type CicloPendienteCurva, type CicloTasa } from '../../api'
import { qk } from '../../api/queryClient'
import InfoTooltip from '../../help/components/InfoTooltip'
import { fechaCorta } from '../../utils/fechas'
import Card from '../ui/Card'
import QueryBoundary from '../ui/QueryBoundary'
import Segmented from '../ui/Segmented'
import PieDatos from './PieDatos'
import { fmtNum } from './constantes'

const ANIOS = [
  { value: '1', label: '1A' },
  { value: '5', label: '5A' },
  { value: '10', label: '10A' },
  { value: '20', label: 'Todo' },
]

// El color identifica a la serie (plazo), nunca "bueno" o "malo": una tasa que sube no es ni lo uno ni lo otro.
const COLOR_TASA: Record<string, string> = { 'tasa-3m': '#22d3ee', 'tasa-5a': '#a78bfa', 'tasa-10a': '#fbbf24', 'tasa-30a': '#60a5fa' }
const PERIODOS_CAMBIO = ['1M', '3M', '6M', '1A']

function fmtPp(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `${v > 0 ? '+' : ''}${fmtNum(v, 2)} pp`
}

function fmtNivel(v: number | null | undefined): string {
  return v == null ? '—' : `${fmtNum(v, 2)}%`
}

function Cambios({ cambios }: { cambios: Record<string, CicloCambioPp> }) {
  return (
    <div className="grid grid-cols-4 gap-1 mt-1.5">
      {PERIODOS_CAMBIO.map(p => (
        <div key={p} title={cambios[p]?.motivo ?? undefined}>
          <div className="text-label text-app-text-faint">{p}</div>
          <div className="font-mono tabular-nums text-caption font-semibold text-app-text">{fmtPp(cambios[p]?.pp)}</div>
        </div>
      ))}
    </div>
  )
}

function TarjetaTasa({ t }: { t: CicloTasa }) {
  return (
    <li className="rounded-xl border border-app-border bg-app-surface-2 px-3 py-2.5">
      <div className="flex items-center gap-1.5">
        <span aria-hidden="true" className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: COLOR_TASA[t.id] ?? '#94a3b8' }} />
        <span className="text-caption font-semibold text-app-text">{t.nombre}</span>
      </div>
      {t.nivel == null ? (
        <p className="text-caption text-app-text-dim mt-1">Sin datos: {t.motivo}</p>
      ) : (
        <>
          <div className="font-mono tabular-nums text-strong font-bold text-app-text mt-0.5">{fmtNivel(t.nivel)}</div>
          <Cambios cambios={t.cambios} />
          <p className="text-label text-app-text-faint mt-1">
            Rango del período: {fmtNivel(t.minimo)} a {fmtNivel(t.maximo)}
            {t.estado === 'desactualizado' && t.fecha ? ` · último dato del ${fechaCorta(t.fecha)}` : ''}
          </p>
        </>
      )}
    </li>
  )
}

function TarjetaPendiente({ p }: { p: CicloPendienteCurva }) {
  return (
    <li className="rounded-xl border border-app-border bg-app-surface-2 px-3 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-caption font-semibold text-app-text">{p.nombre}</span>
        {p.invertida != null && (
          <span className={`rounded-md px-1.5 py-0.5 text-label font-bold ${p.invertida ? 'bg-app-warn/15 text-app-warn' : 'bg-app-surface text-app-text-dim border border-app-border'}`}>
            {p.invertida ? 'Curva invertida' : 'Curva normal'}
          </span>
        )}
      </div>
      {p.valor_pp == null ? (
        <p className="text-caption text-app-text-dim mt-1">Sin datos de alguna de las dos tasas.</p>
      ) : (
        <>
          <div className="font-mono tabular-nums text-strong font-bold text-app-text mt-0.5">{fmtPp(p.valor_pp)}</div>
          <Cambios cambios={p.cambios} />
          <p className="text-label text-app-text-faint mt-1">
            Estuvo invertida {p.semanas_invertida_52} de las últimas {p.semanas_52} semanas.
          </p>
        </>
      )}
    </li>
  )
}

const EJE = { fontSize: 10, fill: '#94a3b8' }
const TOOLTIP = { background: '#171b26', border: '1px solid #1c1f2a', borderRadius: 10, fontSize: 12 }

/**
 * Tasas del Tesoro de EE.UU.: nivel, cambios en puntos porcentuales, forma de la curva y pendientes. Describe los datos;
 * una curva invertida no es un pronóstico y nada acá dice qué hacer.
 */
export default function TasasInteres() {
  const [anios, setAnios] = useState('5')
  const query = useQuery({ queryKey: qk.de('ciclos-tasas', anios), queryFn: () => getCiclosTasas(Number(anios)) })
  const d = query.data
  const tasasConDatos = d?.tasas.filter(t => t.nivel != null) ?? []
  const pendienteGrafico = d?.pendientes.find(p => p.estado === 'ok')

  return (
    <div className="flex flex-col gap-3">
      <Segmented options={ANIOS} value={anios} onChange={setAnios} />
      <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()} fallback={<p className="text-caption text-app-text-dim">Cargando…</p>}>
        {!d || d.estado !== 'ok' ? (
          <p className="text-caption text-app-text-dim">{d?.motivo ?? 'Sin datos de tasas.'}</p>
        ) : (
          <>
            <p className="text-caption text-app-text-dim">
              Rendimiento anual de los bonos del Tesoro de EE.UU. <InfoTooltip term="ciclos_tasas" /> Los cambios van en <InfoTooltip term="ciclos_puntos_porcentuales" label="puntos porcentuales" />.
            </p>
            <ul className="grid grid-cols-1 min-[380px]:grid-cols-2 gap-2">
              {d.tasas.map(t => (
                <TarjetaTasa key={t.id} t={t} />
              ))}
            </ul>

            <Card>
              <div className="text-label font-bold uppercase text-app-text-faint mb-1">Nivel de cada tasa (% anual)</div>
              <ResponsiveContainer width="100%" height={210}>
                <LineChart data={d.filas} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
                  <CartesianGrid stroke="#1c1f2a" strokeDasharray="3 3" />
                  <XAxis dataKey="fecha" tick={EJE} tickFormatter={(f: string) => `${f.slice(5, 7)}/${f.slice(2, 4)}`} minTickGap={32} />
                  <YAxis tick={EJE} width={34} domain={['auto', 'auto']} tickFormatter={(v: number) => v.toFixed(0)} />
                  <Tooltip contentStyle={TOOLTIP} labelFormatter={(f: string) => fechaCorta(f)} formatter={(v: number, n: string) => [fmtNivel(v), n]} />
                  {tasasConDatos.map(t => (
                    <Line key={t.id} type="monotone" dataKey={t.id} name={t.nombre} stroke={COLOR_TASA[t.id] ?? '#94a3b8'} strokeWidth={1.8} dot={false} isAnimationActive={false} connectNulls />
                  ))}
                </LineChart>
              </ResponsiveContainer>
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-label text-app-text-dim mt-1">
                {tasasConDatos.map(t => (
                  <span key={t.id} className="inline-flex items-center gap-1">
                    <span aria-hidden="true" className="w-3 h-0.5" style={{ backgroundColor: COLOR_TASA[t.id] ?? '#94a3b8' }} />
                    {t.nombre.replace('Tesoro EE.UU. a ', '')}
                  </span>
                ))}
              </div>
            </Card>

            <div>
              <div className="text-label font-bold uppercase text-app-text-faint mb-1.5">
                Pendiente de la curva <InfoTooltip term="ciclos_pendiente_curva" />
              </div>
              <ul className="grid grid-cols-1 min-[380px]:grid-cols-2 gap-2">
                {d.pendientes.map(p => (
                  <TarjetaPendiente key={p.id} p={p} />
                ))}
              </ul>
            </div>

            {pendienteGrafico && (
              <Card>
                <div className="text-label font-bold uppercase text-app-text-faint mb-1">{pendienteGrafico.nombre} (pp) · bajo cero = curva invertida</div>
                <ResponsiveContainer width="100%" height={170}>
                  <LineChart data={d.filas} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
                    <CartesianGrid stroke="#1c1f2a" strokeDasharray="3 3" />
                    <XAxis dataKey="fecha" tick={EJE} tickFormatter={(f: string) => `${f.slice(5, 7)}/${f.slice(2, 4)}`} minTickGap={32} />
                    <YAxis tick={EJE} width={34} domain={['auto', 'auto']} tickFormatter={(v: number) => v.toFixed(1)} />
                    <ReferenceLine y={0} stroke="#64748b" />
                    <Tooltip contentStyle={TOOLTIP} labelFormatter={(f: string) => fechaCorta(f)} formatter={(v: number) => [fmtPp(v), pendienteGrafico.nombre]} />
                    <Line type="monotone" dataKey={`pendiente:${pendienteGrafico.id}`} name={pendienteGrafico.nombre} stroke="#10b981" strokeWidth={1.8} dot={false} isAnimationActive={false} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              </Card>
            )}

            {d.curva.length > 1 && (
              <div className="rounded-xl border border-app-border px-3 py-2.5">
                <div className="text-label font-bold uppercase text-app-text-faint mb-1.5">Forma de la curva hoy y hace un año</div>
                <div className="grid grid-cols-[auto,1fr,1fr] gap-x-3 gap-y-0.5 text-label">
                  <span className="text-app-text-faint">Plazo</span>
                  <span className="text-app-text-faint text-right">Hoy</span>
                  <span className="text-app-text-faint text-right">Hace 1 año</span>
                  {d.curva.map(c => (
                    <div key={c.id} className="contents">
                      <span className="text-app-text-dim">{c.nombre.replace('Tesoro EE.UU. a ', '')}</span>
                      <span className="font-mono tabular-nums text-right text-app-text font-semibold">{fmtNivel(c.nivel)}</span>
                      <span className="font-mono tabular-nums text-right text-app-text-dim">{fmtNivel(c.hace_un_anio)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <p className="text-label text-app-text-faint">{d.lectura}</p>
            <PieDatos meta={d.meta} />
          </>
        )}
      </QueryBoundary>
    </div>
  )
}
