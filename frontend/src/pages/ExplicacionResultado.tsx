import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getExplicacionResultado, type ExplicacionItem, type ExplicacionNoDisponible } from '../api'
import { calcularDesde, type PeriodoEvolucion } from '../utils'
import { qk } from '../api/queryClient'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Segmented from '../components/ui/Segmented'
import MetricTile from '../components/ui/MetricTile'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import InfoTooltip from '../help/components/InfoTooltip'
import type { HelpKey } from '../help/content/index'
import { Icon } from '../components/icons/Icons'

type Periodo = PeriodoEvolucion

const OPCIONES_PERIODO: { value: Periodo; label: string }[] = [
  { value: '1M', label: '1M' },
  { value: '3M', label: '3M' },
  { value: '6M', label: '6M' },
  { value: '1Y', label: '1A' },
  { value: '3Y', label: '3A' },
  { value: 'YTD', label: 'YTD' },
  { value: 'ALL', label: 'Todo' },
]

function toneClass(v: number | null | undefined): string {
  if (v == null) return 'text-app-text-dim'
  return v >= 0 ? 'text-app-pos' : 'text-app-neg'
}

function fmtMonto(v: number | null | undefined, esUSD: boolean): string {
  if (v == null) return 'No disponible'
  const abs = Math.abs(v)
  const signo = v < 0 ? '-' : v > 0 ? '+' : ''
  const prefijo = esUSD ? 'U$S' : '$'
  return `${signo}${prefijo} ${abs.toLocaleString('es-AR', { maximumFractionDigits: 0 })}`
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—'
  const signo = v >= 0 ? '+' : ''
  return `${signo}${v.toFixed(1)}%`
}

function ComponenteRow({ label, valor, esUSD, term }: { label: string; valor: number | null | undefined; esUSD: boolean; term?: HelpKey }) {
  return (
    <div className="flex justify-between text-label py-1">
      <span className="text-app-text-dim">{term ? <InfoTooltip term={term} label={label} /> : label}</span>
      <span className={`font-mono ${valor == null ? 'text-app-text-faint' : toneClass(valor)}`}>
        {valor == null ? 'No disponible' : fmtMonto(valor, esUSD)}
      </span>
    </div>
  )
}

function AtribucionBar({ item, maxAbs, esUSD }: { item: ExplicacionItem; maxAbs: number; esUSD: boolean }) {
  const pct = item.contribucion_pct
  const ancho = pct != null && maxAbs > 0 ? (Math.abs(pct) / maxAbs) * 100 : 0
  return (
    <div>
      <div className="flex justify-between items-baseline text-caption mb-1">
        <span className="text-app-text">
          {item.etiqueta}
          {item.n_no_disponibles ? <span className="text-app-text-faint text-label ml-1">({item.n_no_disponibles} sin datos)</span> : null}
        </span>
        <span className={`font-mono font-bold tabular-nums ${toneClass(pct)}`}>{fmtPct(pct)}</span>
      </div>
      <div className="h-1.5 rounded-full bg-app-surface-2 overflow-hidden mb-1">
        <div className={`h-full rounded-full ${(pct ?? 0) >= 0 ? 'bg-app-pos' : 'bg-app-neg'}`} style={{ width: `${ancho}%` }} />
      </div>
      <div className="flex justify-between text-label text-app-text-dim">
        <span>P&amp;L: {fmtMonto(item.pnl, esUSD)}</span>
      </div>
    </div>
  )
}

function RankingRow({ item, esUSD }: { item: ExplicacionItem; esUSD: boolean }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-app-border-soft last:border-b-0">
      <div className="min-w-0">
        <div className="text-caption font-semibold text-app-text truncate">{item.ticker}</div>
        <div className="text-label text-app-text-faint truncate">{item.nombre}</div>
      </div>
      <div className={`font-mono font-bold text-caption tabular-nums shrink-0 ml-2 ${toneClass(item.pnl)}`}>
        {fmtMonto(item.pnl, esUSD)}
      </div>
    </div>
  )
}

function NoDisponibleRow({ item }: { item: ExplicacionNoDisponible }) {
  return (
    <div className="flex items-center justify-between py-1.5 text-label">
      <span className="text-app-text">{item.ticker} — {item.nombre}</span>
      <span className="text-app-text-faint">{item.motivo}</span>
    </div>
  )
}

export default function ExplicacionResultado() {
  const navigate = useNavigate()
  const { carteraSeleccionada, monedaSeleccionada } = useInversionesContext()
  const [periodo, setPeriodo] = useState<Periodo>('1Y')

  const esUSD = monedaSeleccionada === 'USD'
  const moneda = esUSD ? 'usd' : 'ars'
  const desde = calcularDesde(periodo)

  const query = useQuery({
    queryKey: qk.de('explicacion-resultado', carteraSeleccionada, periodo, moneda),
    queryFn: () => getExplicacionResultado(carteraSeleccionada, desde, moneda),
  })
  const data = query.data ?? null

  const porTipo = data?.por_tipo ?? []
  const maxAbsTipo = Math.max(1e-9, ...porTipo.map(it => Math.abs(it.contribucion_pct ?? 0)))

  return (
    <div className="pb-4">
      <ScreenHeader title="¿Por qué ganó o perdió?" onBack={() => navigate(-1)} />

      <div className="mb-3">
        <Segmented options={OPCIONES_PERIODO} value={periodo} onChange={setPeriodo} />
      </div>

      <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
        {!data || data.estado === 'sin_datos' ? (
          <EmptyState title="Sin movimientos" description="Esta cartera todavía no tiene movimientos cargados en este período." />
        ) : (
          <div className="flex flex-col gap-5">
            {/* 1. Resultado total */}
            <div>
              <h3 className="text-body font-bold text-app-text mb-2.5">
                <InfoTooltip term="explicacion_que_es" label="Resultado total" />
              </h3>
              <div className="grid grid-cols-2 gap-2 mb-3">
                <MetricTile label="Rendimiento del período" value={fmtPct(data.resultado.twr_pct)} tone={data.resultado.twr_pct != null ? (data.resultado.twr_pct >= 0 ? 'pos' : 'neg') : undefined} />
                <MetricTile label="P&L" value={fmtMonto(data.resultado.pnl, esUSD)} tone={data.resultado.pnl != null ? (data.resultado.pnl >= 0 ? 'pos' : 'neg') : undefined} />
                <MetricTile label="Aportes" value={fmtMonto(data.resultado.aportes, esUSD)} />
                <MetricTile label="Retiros" value={fmtMonto(data.resultado.retiros, esUSD)} />
              </div>
              {data.resultado.amortizaciones != null && Math.abs(data.resultado.amortizaciones) > 0.5 && (
                <div className="text-label text-app-text-dim mb-2">
                  <InfoTooltip term="explicacion_amortizaciones" label="Amortizaciones cobradas (capital devuelto, no ganancia)" />:{' '}
                  <span className="font-mono">{fmtMonto(data.resultado.amortizaciones, esUSD)}</span>
                </div>
              )}

              {data.por_mercado.length > 0 && (
                <Card className="mb-2">
                  <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1.5">Resultado por mercado</div>
                  {data.por_mercado.map(it => (
                    <div key={it.etiqueta} className="flex justify-between text-caption py-1">
                      <span className="text-app-text">{it.etiqueta}</span>
                      <span className={`font-mono ${toneClass(it.pnl)}`}>{fmtMonto(it.pnl, esUSD)}</span>
                    </div>
                  ))}
                </Card>
              )}
            </div>

            {/* 2. Atribución por tipo */}
            {porTipo.length > 0 && (
              <div>
                <h3 className="text-body font-bold text-app-text mb-2.5">Atribución por tipo</h3>
                <div className="flex flex-col gap-3">
                  {porTipo.map(it => (
                    <AtribucionBar key={it.etiqueta} item={it} maxAbs={maxAbsTipo} esUSD={esUSD} />
                  ))}
                </div>
              </div>
            )}

            {/* 3. Principales contribuyentes */}
            <div>
              <h3 className="text-body font-bold text-app-text mb-2.5">Principales contribuyentes</h3>
              {data.contribuyentes.length === 0 ? (
                <div className="text-label text-app-text-faint">Ninguna posición aportó ganancia en este período.</div>
              ) : (
                <Card>{data.contribuyentes.map(it => <RankingRow key={it.ticker} item={it} esUSD={esUSD} />)}</Card>
              )}
            </div>

            {/* 4. Principales detractores */}
            <div>
              <h3 className="text-body font-bold text-app-text mb-2.5">Principales detractores</h3>
              {data.detractores.length === 0 ? (
                <div className="text-label text-app-text-faint">Ninguna posición restó en este período.</div>
              ) : (
                <Card>{data.detractores.map(it => <RankingRow key={it.ticker} item={it} esUSD={esUSD} />)}</Card>
              )}
            </div>

            {/* 5. Descomposición del resultado */}
            <div>
              <h3 className="text-body font-bold text-app-text mb-2.5">De dónde viene el resultado</h3>
              <Card>
                <ComponenteRow label="Movimiento de precio" valor={data.componentes.precio} esUSD={esUSD} term="explicacion_precio" />
                <ComponenteRow label="Dividendos" valor={data.componentes.dividendos} esUSD={esUSD} term="explicacion_dividendos_cupones" />
                <ComponenteRow label="Cupones" valor={data.componentes.cupones} esUSD={esUSD} />
                <ComponenteRow label="Comisiones" valor={data.componentes.comisiones} esUSD={esUSD} term="explicacion_comisiones" />
              </Card>

              <div className="mt-3">
                <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1.5">
                  <InfoTooltip term="explicacion_efecto_mep" label="Efecto moneda / MEP" />
                </div>
                {data.fx.estado === 'no_aplica' ? (
                  <div className="text-label text-app-text-faint">
                    No aplica en la vista USD: el tipo de cambio ya está incorporado en el precio en dólares de cada activo. Cambiá a ARS para verlo.
                  </div>
                ) : data.fx.estado === 'no_disponible' ? (
                  <div className="text-label text-app-text-faint">No disponible: falta el tipo de cambio (MEP) para este período.</div>
                ) : (
                  <Card>
                    <ComponenteRow label="Resultado de los activos (en dólares, a MEP de hoy)" valor={data.fx.resultado_activos_ars} esUSD={false} />
                    <ComponenteRow label="Efecto del movimiento del dólar (MEP)" valor={data.fx.efecto_mep_ars} esUSD={false} />
                  </Card>
                )}
              </div>

              {data.no_disponibles.length > 0 && (
                <div className="mt-3">
                  <div className="flex items-center gap-1 mb-1.5">
                    <Icon name="alert" className="w-3.5 h-3.5 text-app-text-dim" />
                    <span className="text-label font-bold uppercase tracking-wide text-app-text-faint">
                      <InfoTooltip term="explicacion_no_disponible" label="No disponible" />
                    </span>
                  </div>
                  <Card>{data.no_disponibles.map(it => <NoDisponibleRow key={it.ticker} item={it} />)}</Card>
                </div>
              )}
            </div>

            {/* 6. Explicación para principiantes */}
            <div>
              <h3 className="text-body font-bold text-app-text mb-2.5">En criollo</h3>
              <Card>
                <div className="text-caption text-app-text font-semibold mb-1.5">{data.explicacion.titulo}</div>
                {data.explicacion.frases.length > 0 && (
                  <ul className="list-disc list-inside text-caption text-app-text-dim space-y-1">
                    {data.explicacion.frases.map((f, i) => <li key={i}>{f}</li>)}
                  </ul>
                )}
              </Card>
            </div>

            {data.advertencias.length > 0 && (
              <div className="text-label text-app-text-faint text-center px-4">
                {data.advertencias.join(' · ')}
              </div>
            )}
          </div>
        )}
      </QueryBoundary>
    </div>
  )
}
