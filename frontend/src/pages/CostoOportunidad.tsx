import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { useBenchmarkSeleccionado } from '../hooks/useBenchmarkSeleccionado'
import { getCostoOportunidad, type MonedaRiesgo } from '../api'
import { calcularDesde, formatUSD, formatARS, formatPctRatio, type PeriodoEvolucion } from '../utils'
import { qk } from '../api/queryClient'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Segmented from '../components/ui/Segmented'
import MetricTile from '../components/ui/MetricTile'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import BotonExportarCsv from '../components/ui/BotonExportarCsv'
import CostoOportunidadChart from '../components/charts/CostoOportunidadChart'
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

const OPCIONES_MONEDA: { value: MonedaRiesgo; label: string }[] = [
  { value: 'usd', label: 'USD (MEP)' },
  { value: 'ars_nominal', label: 'ARS' },
  { value: 'ars_real', label: 'ARS real (CER)' },
]

function fmtMoneda(v: number | null | undefined, moneda: MonedaRiesgo): string {
  if (v == null) return '—'
  return moneda === 'usd' ? formatUSD(v) : formatARS(v)
}

function fmtFecha(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' })
}

export default function CostoOportunidad() {
  const navigate = useNavigate()
  const { carteraSeleccionada } = useInversionesContext()
  const [periodo, setPeriodo] = useState<Periodo>('1Y')
  const [moneda, setMoneda] = useState<MonedaRiesgo>('usd')
  const { benchmarks, benchmarkSeleccionado, setBenchmarkSeleccionado } = useBenchmarkSeleccionado(carteraSeleccionada)

  const desde = calcularDesde(periodo)

  const query = useQuery({
    queryKey: qk.de('costo-oportunidad', carteraSeleccionada, moneda, benchmarkSeleccionado, periodo),
    queryFn: () => getCostoOportunidad(carteraSeleccionada, moneda, benchmarkSeleccionado, desde),
    enabled: benchmarkSeleccionado !== null,
  })
  const data = query.data ?? null

  const serieIndices = (data?.serie_indices ?? []).map(p => ({
    fecha: p.fecha,
    indice_cartera: p.indice_cartera,
    indice_referencia: p.indice_referencia,
  }))
  const serieValores = (data?.serie_valores ?? []).map(p => ({
    fecha: p.fecha,
    valor_cartera: p.valor_cartera,
    valor_referencia: p.valor_referencia,
    diferencia: p.diferencia,
  }))

  return (
    <div className="pb-4">
      <ScreenHeader title="Costo de oportunidad" onBack={() => navigate(-1)} />

      <div className="flex flex-col gap-2 mb-4">
        <Segmented options={OPCIONES_PERIODO} value={periodo} onChange={setPeriodo} />
        <Segmented options={OPCIONES_MONEDA} value={moneda} onChange={setMoneda} />
        {benchmarks.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {benchmarks.map(b => (
              <button
                key={b}
                onClick={() => setBenchmarkSeleccionado(b)}
                className={`px-2.5 py-1.5 rounded-lg text-caption font-semibold whitespace-nowrap ${
                  benchmarkSeleccionado === b
                    ? 'bg-app-accent-soft text-app-accent'
                    : 'bg-app-surface border border-app-border text-app-text-dim'
                }`}
              >
                {b}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Encuadre: siempre visible, antes que cualquier dato */}
      <Card className="mb-4">
        <div className="flex items-start gap-2">
          <Icon name="info" className="w-4 h-4 text-app-text-dim shrink-0 mt-0.5" />
          <div className="text-caption text-app-text-dim">
            <span className="font-semibold text-app-text">Esto es una comparación histórica.</span>{' '}
            Describe lo que ya ocurrió con los datos cargados. No es una recomendación ni una
            sugerencia de comprar, vender o cambiar de instrumento.
          </div>
        </div>
      </Card>

      <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
        {!benchmarkSeleccionado || !data || data.estado !== 'ok' ? (
          <EmptyState
            title={
              !benchmarkSeleccionado || data?.estado === 'sin_benchmark'
                ? 'Sin referencia elegida'
                : data?.estado === 'sin_movimientos'
                ? 'Sin movimientos'
                : 'Datos insuficientes'
            }
            description={
              !benchmarkSeleccionado || data?.estado === 'sin_benchmark'
                ? 'Elegí una referencia arriba, o configurá una para esta cartera en el Sheet.'
                : data?.estado === 'sin_movimientos'
                ? 'Esta cartera todavía no tiene movimientos cargados.'
                : 'No hay historia en común entre la cartera y la referencia para este período y esta moneda.'
            }
          />
        ) : (
          <div className="flex flex-col gap-5">
            {/* Frase principal */}
            <Card>
              <p className="text-caption text-app-text leading-relaxed">
                Durante el período seleccionado —del <b>{fmtFecha(data.periodo_desde)}</b> al{' '}
                <b>{fmtFecha(data.periodo_hasta)}</b>— la cartera tuvo{' '}
                <b className={data.resultado_cartera_pct != null && data.resultado_cartera_pct >= 0 ? 'text-app-pos' : 'text-app-neg'}>
                  {formatPctRatio(data.resultado_cartera_pct)}
                </b>{' '}
                y la referencia (<b>{data.referencia}</b>) tuvo{' '}
                <b className={data.resultado_referencia_pct != null && data.resultado_referencia_pct >= 0 ? 'text-app-pos' : 'text-app-neg'}>
                  {formatPctRatio(data.resultado_referencia_pct)}
                </b>
                . La diferencia fue de{' '}
                <b className={data.diferencia_pp != null && data.diferencia_pp >= 0 ? 'text-app-pos' : 'text-app-neg'}>
                  {data.diferencia_pp != null ? `${data.diferencia_pp >= 0 ? '+' : ''}${data.diferencia_pp.toFixed(1)} pp` : '—'}
                </b>
                . En dinero, al cierre del período la diferencia es de{' '}
                <b className={data.diferencia_monetaria != null && data.diferencia_monetaria >= 0 ? 'text-app-pos' : 'text-app-neg'}>
                  {fmtMoneda(data.diferencia_monetaria, moneda)}
                </b>
                .
              </p>
            </Card>

            {/* Tiles */}
            <div className="grid grid-cols-3 gap-2">
              <MetricTile
                label="Cartera — Resultado"
                value={formatPctRatio(data.resultado_cartera_pct)}
                tone={data.resultado_cartera_pct != null ? (data.resultado_cartera_pct >= 0 ? 'pos' : 'neg') : undefined}
              />
              <MetricTile
                label="Referencia — Resultado"
                value={formatPctRatio(data.resultado_referencia_pct)}
                tone={data.resultado_referencia_pct != null ? (data.resultado_referencia_pct >= 0 ? 'pos' : 'neg') : undefined}
              />
              <MetricTile
                label="Diferencia (cartera − referencia)"
                value={data.diferencia_pp != null ? `${data.diferencia_pp >= 0 ? '+' : ''}${data.diferencia_pp.toFixed(1)} pp` : '—'}
                tone={data.diferencia_pp != null ? (data.diferencia_pp >= 0 ? 'pos' : 'neg') : undefined}
              />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <MetricTile label="Valor de la cartera" value={fmtMoneda(data.valor_final_cartera, moneda)} />
              <MetricTile label="Valor siguiendo la referencia" value={fmtMoneda(data.valor_final_referencia, moneda)} />
              <MetricTile
                label="Diferencia"
                value={fmtMoneda(data.diferencia_monetaria, moneda)}
                tone={data.diferencia_monetaria != null ? (data.diferencia_monetaria >= 0 ? 'pos' : 'neg') : undefined}
                sub={`Mismo capital inicial (${fmtMoneda(data.valor_inicial, moneda)}) y los mismos aportes netos (${fmtMoneda(data.aportes_netos_periodo, moneda)})`}
              />
            </div>

            {/* Evolución acumulada (base 100) */}
            <div>
              <h3 className="text-body font-bold text-app-text mb-2">Evolución acumulada (base 100)</h3>
              <Card>
                <CostoOportunidadChart
                  serie={serieIndices}
                  dataKeyCartera="indice_cartera"
                  dataKeyReferencia="indice_referencia"
                  nombreReferencia={data.referencia ?? 'Referencia'}
                  formatValor={v => v.toFixed(1)}
                />
              </Card>
              <p className="text-label text-app-text-faint mt-1.5">
                Ambas líneas arrancan en 100 el {fmtFecha(data.periodo_desde)}. La distancia entre
                ellas es la diferencia porcentual acumulada.
              </p>
            </div>

            {/* Evolución en dinero */}
            <div>
              <h3 className="text-body font-bold text-app-text mb-2">Evolución en dinero</h3>
              <Card>
                <CostoOportunidadChart
                  serie={serieValores}
                  dataKeyCartera="valor_cartera"
                  dataKeyReferencia="valor_referencia"
                  nombreReferencia={data.referencia ?? 'Referencia'}
                  formatValor={v => fmtMoneda(v, moneda)}
                />
              </Card>
              <p className="text-label text-app-text-faint mt-1.5">
                Las dos líneas reciben el mismo capital inicial y los mismos aportes y retiros, en
                las mismas fechas.
              </p>
              <div className="mt-2">
                <BotonExportarCsv
                  nombre="costo-oportunidad"
                  encabezados={['Fecha', 'Valor cartera', 'Valor referencia', 'Diferencia']}
                  filas={() => serieValores.map(p => [p.fecha, p.valor_cartera, p.valor_referencia, p.diferencia])}
                />
              </div>
            </div>

            {/* Qué no dice esta comparación */}
            <Card>
              <h3 className="text-caption font-bold text-app-text mb-2">Qué no dice esta comparación</h3>
              <ul className="list-disc list-inside text-label text-app-text-dim space-y-1.5">
                <li>
                  Es una descripción de lo que ocurrió entre el {fmtFecha(data.periodo_desde)} y el{' '}
                  {fmtFecha(data.periodo_hasta)}, con los datos cargados hoy. No proyecta ni sugiere
                  nada sobre el futuro.
                </li>
                <li>
                  La referencia se sigue de forma teórica: sin comisiones, sin impuestos, sin
                  mínimos de operación y reinvirtiendo en el instante exacto de cada movimiento. Una
                  cartera real no se comporta así.
                </li>
                <li>
                  La referencia recibe exactamente los mismos aportes y retiros que la cartera. Si
                  hubieses operado distinto, los aportes también habrían sido otros.
                </li>
                <li>
                  El riesgo asumido no entra en la cuenta: dos resultados iguales pueden venir de
                  niveles de riesgo muy distintos. Para eso está la pantalla Riesgo.
                </li>
                <li>Cambiar el período, la moneda o la referencia cambia el resultado. Ninguna combinación es "la correcta".</li>
              </ul>
            </Card>

            {/* Advertencias de homogeneidad */}
            {data.advertencias.length > 0 && (
              <Card className="border-app-accent">
                <div className="flex items-center gap-1.5 mb-2">
                  <Icon name="alert" className="w-3.5 h-3.5 text-app-text-dim" />
                  <h3 className="text-caption font-bold text-app-text">Sobre la homogeneidad de esta comparación</h3>
                </div>
                <ul className="list-disc list-inside text-label text-app-text-dim space-y-1.5">
                  {data.advertencias.map((a, i) => <li key={i}>{a}</li>)}
                </ul>
              </Card>
            )}
          </div>
        )}
      </QueryBoundary>
    </div>
  )
}
