import { useQuery } from '@tanstack/react-query'
import { qk } from '../api/queryClient'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getPnlRealizadoNoRealizado, getRendimientoMensual, getPerformanceRelativa, getDescomposicionFx } from '../api'
import { formatARS, formatUSD, formatPctRatio } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import ComparacionChart from '../components/charts/ComparacionChart'
import RendimientoHeatmap from '../components/charts/RendimientoHeatmap'
import DescomposicionFxChart from '../components/charts/DescomposicionFxChart'
import { Icon } from '../components/icons/Icons'
import MetricTile from '../components/ui/MetricTile'
import InfoTerm from '../components/ui/InfoTerm'
import type { HelpKey } from '../help/content/index'
import SkeletonPantalla from '../components/ui/Skeleton'
import QueryBoundary from '../components/ui/QueryBoundary'

function toneClass(v: number | null | undefined): string {
  if (v == null) return 'text-app-text'
  return v >= 0 ? 'text-app-teal' : 'text-app-coral'
}

function toneFor(v: number | null | undefined): 'pos' | 'neg' | undefined {
  if (v == null) return undefined
  return v >= 0 ? 'pos' : 'neg'
}

export default function Rendimiento() {
  const navigate = useNavigate()
  const { carteraSeleccionada, monedaSeleccionada, resumen } = useInversionesContext()

  const monedaBackend = monedaSeleccionada === 'ARS' ? 'ars_nominal' : 'usd'
  const rendimientoQuery = useQuery({
    queryKey: qk.de('rendimiento-detalle', carteraSeleccionada, monedaBackend),
    queryFn: async () => {
      const [pnl, mensual, perfRelativa, fx] = await Promise.all([
        getPnlRealizadoNoRealizado(carteraSeleccionada),
        getRendimientoMensual(carteraSeleccionada),
        getPerformanceRelativa(carteraSeleccionada, monedaBackend, null),
        getDescomposicionFx(carteraSeleccionada),
      ])
      return { pnl, mensual, perfRelativa, fx }
    },
  })

  const pnl = rendimientoQuery.data?.pnl ?? null
  const rendimientoMensual = rendimientoQuery.data?.mensual ?? null
  const perfRelativa = rendimientoQuery.data?.perfRelativa ?? null
  const descomposicionFx = rendimientoQuery.data?.fx ?? null
  const loading = rendimientoQuery.isLoading

  const esARS = monedaSeleccionada === 'ARS'
  const formatMoneda = esARS ? formatARS : formatUSD
  const c = pnl?.consolidado

  const realizado = c ? (esARS ? c.realizado_ars : c.realizado_usd) : null
  const noRealizado = c ? (esARS ? c.no_realizado_ars : c.no_realizado_usd) : null
  const ingresos = c ? (esARS ? c.ingresos_ars : c.ingresos_usd) : null
  const total = c ? (esARS ? c.total_ars : c.total_usd) : null

  // XIRR pondera por cuánta plata había invertida en cada momento, TWR no: la diferencia entre
  // ambas es el efecto de CUÁNDO aportaste/retiraste, aislado de cómo rindió la estrategia.
  // Sólo vale restarlas en la misma unidad: el XIRR sale anualizado y el TWR es acumulado del
  // período, así que se usa `xirr_*_periodo` (el XIRR llevado a base acumulada por el backend).
  const diff = (a: number | null | undefined, b: number | null | undefined) =>
    a != null && b != null ? a - b : null

  const filas: { label: string; infoTerm: HelpKey; valores: (number | null | undefined)[] }[] = resumen
    ? [
        { label: 'Simple (período)', infoTerm: 'simple', valores: [resumen.rendimiento_simple_ars, resumen.rendimiento_simple_ars_real, resumen.rendimiento_simple_usd] },
        { label: 'TIR (XIRR) anualizada', infoTerm: 'xirr', valores: [resumen.xirr_ars, resumen.xirr_ars_real, resumen.xirr_usd] },
        { label: 'TIR (XIRR) del período', infoTerm: 'xirrPeriodo', valores: [resumen.xirr_ars_periodo, resumen.xirr_ars_real_periodo, resumen.xirr_usd_periodo] },
        { label: 'TWRR del período', infoTerm: 'twr', valores: [resumen.twr_ars, resumen.twr_ars_real, resumen.twr_usd] },
        { label: 'TWRR sin comisiones', infoTerm: 'twrBruto', valores: [resumen.twr_ars_bruto, null, resumen.twr_usd_bruto] },
        {
          label: 'Costo de operar',
          infoTerm: 'costoOperar',
          valores: [
            diff(resumen.twr_ars, resumen.twr_ars_bruto),
            null,
            diff(resumen.twr_usd, resumen.twr_usd_bruto),
          ],
        },
        {
          label: 'Efecto de tus aportes',
          infoTerm: 'efectoAportes',
          valores: [
            diff(resumen.xirr_ars_periodo, resumen.twr_ars),
            diff(resumen.xirr_ars_real_periodo, resumen.twr_ars_real),
            diff(resumen.xirr_usd_periodo, resumen.twr_usd),
          ],
        },
      ]
    : []

  return (
    <div className="pb-4">
      <ScreenHeader title="Rendimiento" onBack={() => navigate(-1)} />

      <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3">
        <button onClick={() => navigate('/patrimonio')} className="inline-flex items-center gap-1 text-label font-semibold text-app-text-dim">
          <Icon name="trend" className="w-3.5 h-3.5" /> Ver evolución del patrimonio
        </button>
        <button onClick={() => navigate('/riesgo')} className="inline-flex items-center gap-1 text-label font-semibold text-app-text-dim">
          <Icon name="alert" className="w-3.5 h-3.5" /> Ver métricas de riesgo
        </button>
      </div>

      <QueryBoundary
        isLoading={loading}
        error={rendimientoQuery.error}
        onRetry={() => void rendimientoQuery.refetch()}
      >
      {!pnl || !resumen ? (
        <EmptyState title="Sin datos" description="No hay movimientos suficientes para calcular el rendimiento de esta cartera." />
      ) : (
        <>
          {descomposicionFx && descomposicionFx.estado === 'ok' ? (
            <>
              <h3 className="text-body font-bold text-app-text mb-2.5">¿Ganaste por los activos o por el dólar?</h3>
              <Card className="mb-4">
                <div className="grid grid-cols-2 gap-2 mb-4">
                  <MetricTile
                    label="Retorno ARS"
                    infoTerm="rendimiento_ars"
                    value={formatPctRatio(descomposicionFx.retorno_total_ars_pct)}
                    tone={toneFor(descomposicionFx.retorno_total_ars_pct)}
                  />
                  <MetricTile
                    label="Retorno USD"
                    infoTerm="rendimiento_usd"
                    value={formatPctRatio(descomposicionFx.retorno_activo_pct)}
                    tone={toneFor(descomposicionFx.retorno_activo_pct)}
                  />
                </div>
                <DescomposicionFxChart
                  retornoTotalArs={descomposicionFx.retorno_total_ars_pct}
                  retornoActivo={descomposicionFx.retorno_activo_pct}
                  efectoFx={descomposicionFx.efecto_fx_pct}
                  esARS={esARS}
                />
                <div className="mt-4 p-3 bg-app-surface rounded-[9px] border border-app-border">
                  <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">
                    Efecto dólar
                  </div>
                  <div className={`font-mono text-strong font-bold tabular-nums mb-2 ${toneFor(descomposicionFx.efecto_fx_pct) === 'pos' ? 'text-app-teal' : 'text-app-coral'}`}>
                    {descomposicionFx.efecto_fx_pct !== null ? (descomposicionFx.efecto_fx_pct >= 0 ? '+' : '') + formatPctRatio(descomposicionFx.efecto_fx_pct) : 'N/A'}
                  </div>
                  <div className="text-label text-app-text-dim">
                    Parte de la variación en ARS proviene del cambio del tipo de cambio.
                  </div>
                  {descomposicionFx.mep_aproximado && (
                    <div className="mt-2 text-label text-app-text-dim italic">
                      ⚠ Datos de MEP desactualizados o estimados
                    </div>
                  )}
                  {!descomposicionFx.identidad_verificada && (
                    <div className="mt-2 text-label text-app-text-dim italic">
                      ⚠ La descomposición no se verifica exactamente (puede deberse a operaciones particulares)
                    </div>
                  )}
                </div>
              </Card>
            </>
          ) : descomposicionFx ? (
            <>
              <h3 className="text-body font-bold text-app-text mb-2.5">Descomposición FX</h3>
              <Card className="mb-4">
                <EmptyState
                  title="Descomposición no disponible"
                  description={
                    descomposicionFx.estado === 'mep_faltante'
                      ? 'No hay datos de MEP suficientes para este período.'
                      : 'No hay suficiente historial para descomponer el rendimiento.'
                  }
                />
              </Card>
            </>
          ) : null}

          <h3 className="text-body font-bold text-app-text mb-2.5">P&amp;L realizado vs. no realizado</h3>
          <div className="grid grid-cols-2 gap-2 mb-2">
            <MetricTile label="Realizado (ventas)" infoTerm="realizado" value={formatMoneda(realizado)} tone={toneFor(realizado)} />
            <MetricTile label="No realizado (en cartera)" infoTerm="noRealizado" value={formatMoneda(noRealizado)} tone={toneFor(noRealizado)} />
          </div>
          <div className="grid grid-cols-2 gap-2 mb-4">
            <MetricTile label="Ingresos (div./cupones)" infoTerm="ingresos" value={formatMoneda(ingresos)} tone={toneFor(ingresos)} />
            <MetricTile label="Total" value={formatMoneda(total)} tone={toneFor(total)} />
          </div>

          <h3 className="text-body font-bold text-app-text mb-2.5">Rendimiento: nominal vs. real vs. USD</h3>
          <Card className="mb-4 overflow-x-auto">
            <table className="w-full text-caption">
              <thead>
                <tr>
                  <th className="text-left text-app-text-faint font-bold uppercase text-label pb-2">&nbsp;</th>
                  <th className="text-right text-app-text-faint font-bold uppercase text-label pb-2 px-1.5">ARS Nominal</th>
                  <th className="text-right text-app-text-faint font-bold uppercase text-label pb-2 px-1.5">
                    <InfoTerm term="cer" label="ARS Real (CER)" className="justify-end" />
                  </th>
                  <th className="text-right text-app-text-faint font-bold uppercase text-label pb-2 px-1.5">
                    <InfoTerm term="mep" label="USD (MEP)" className="justify-end" />
                  </th>
                </tr>
              </thead>
              <tbody>
                {filas.map(fila => (
                  <tr key={fila.label} className="border-t border-app-border">
                    <td className="py-2 font-semibold text-app-text">
                      <InfoTerm term={fila.infoTerm} label={fila.label} />
                    </td>
                    {fila.valores.map((v, i) => (
                      <td key={i} className={`py-2 px-1.5 text-right font-mono font-bold tabular-nums ${toneClass(v)}`}>
                        {formatPctRatio(v)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {resumen.dias_periodo > 0 && (
              <div className="mt-2 text-label text-app-text-dim">
                «Del período» = los {resumen.dias_periodo} días desde tu primer movimiento hasta hoy.
                La TIR anualizada extrapola ese tramo a 12 meses, por eso es mucho más grande cuando el
                historial es corto.
              </div>
            )}
          </Card>

          <h3 className="text-body font-bold text-app-text mb-2.5">
            <InfoTerm term="twr" label="Mapa de calor: rendimiento mensual" />
          </h3>
          {!rendimientoMensual || rendimientoMensual.meses.length === 0 ? (
            <EmptyState title="Sin historial mensual" description="No hay suficientes meses de actividad para armar el mapa de calor." />
          ) : (
            <RendimientoHeatmap meses={rendimientoMensual.meses} anios={rendimientoMensual.anios} esARS={esARS} />
          )}

          <h3 className="text-body font-bold text-app-text mb-2.5">
            <InfoTerm term="benchmark" label="Performance vs benchmark" />
          </h3>
          {perfRelativa?.estado === 'ok' ? (
            <Card className="mb-4">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <div className="text-label text-app-text-faint uppercase tracking-wide mb-0.5">Benchmark</div>
                  <div className="text-body font-semibold text-app-text">{perfRelativa.benchmark_usado}</div>
                </div>
                <div className="text-right">
                  <div className="text-label text-app-text-faint uppercase tracking-wide mb-0.5">Cartera vs Benchmark</div>
                  <div className={`font-mono font-bold text-strong tabular-nums ${(perfRelativa.delta_pp ?? 0) >= 0 ? 'text-app-teal' : 'text-app-coral'}`}>
                    {(perfRelativa.delta_pp ?? 0) >= 0 ? '+' : ''}{perfRelativa.delta_pp?.toFixed(1)}%
                  </div>
                </div>
              </div>
              <div className="text-label text-app-text-dim mb-3">
                {(perfRelativa.retorno_cartera_pct ?? 0) >= (perfRelativa.retorno_benchmark_pct ?? 0) ? 'Superaste el benchmark' : 'Quedaste por debajo del benchmark'}
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => navigate('/performance-relativa')}
                  className="inline-flex items-center gap-1 text-label font-semibold text-app-text-dim hover:text-app-text"
                >
                  <Icon name="trend" className="w-3.5 h-3.5" /> Ver comparación completa
                </button>
                <button
                  onClick={() => navigate('/benchmarks-comparacion')}
                  className="inline-flex items-center gap-1 text-label font-semibold text-app-text-dim hover:text-app-text"
                >
                  <Icon name="trend" className="w-3.5 h-3.5" /> Comparar benchmarks
                </button>
              </div>
            </Card>
          ) : (
            <Card className="mb-4">
              <EmptyState title="Sin benchmark" description="No hay benchmark configurado para esta cartera." />
            </Card>
          )}

          <h3 className="text-body font-bold text-app-text mb-2.5">
            <InfoTerm term="benchmark" label="Cartera vs. benchmarks (ARS)" />
          </h3>
          <Card className="mb-4">
            <ComparacionChart resumen={resumen} />
          </Card>

          <h3 className="text-body font-bold text-app-text mb-2.5">P&amp;L por ticker</h3>
          {pnl.por_ticker.length === 0 ? (
            <EmptyState title="Sin posiciones" description="No hay tickers con actividad para esta cartera." />
          ) : (
            <div className="flex flex-col gap-1.5">
              {pnl.por_ticker.map(item => {
                const itemRealizado = esARS ? item.realizado_ars : item.realizado_usd
                const itemNoRealizado = esARS ? item.no_realizado_ars : item.no_realizado_usd
                const itemTotal = esARS ? item.total_ars : item.total_usd
                return (
                  <button
                    key={item.ticker}
                    onClick={() => navigate(`/ticker/${encodeURIComponent(item.ticker)}`)}
                    className="flex items-center justify-between bg-app-surface border border-app-border rounded-[13px] px-3.5 py-2.5 text-left"
                  >
                    <div className="min-w-0">
                      <div className="font-semibold text-body text-app-text">{item.ticker}</div>
                      <div className="text-label text-app-text-dim truncate">{item.nombre}</div>
                    </div>
                    <div className="text-right shrink-0 ml-3">
                      <div className={`font-mono font-bold text-body tabular-nums ${toneClass(itemTotal)}`}>
                        {formatMoneda(itemTotal)}
                      </div>
                      <div className="text-label text-app-text-dim tabular-nums">
                        Real. {formatMoneda(itemRealizado)} · No real. {formatMoneda(itemNoRealizado)}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </>
      )}
      </QueryBoundary>
    </div>
  )
}
