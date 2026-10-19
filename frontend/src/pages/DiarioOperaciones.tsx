import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getDiarioOperaciones, type DiarioOperacionOut } from '../api'
import { qk } from '../api/queryClient'
import { useFormatoFijo } from '../hooks/useFormatoMoneda'
import { formatMonedaCruda, type Moneda } from '../utils/formatoMonto'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import Segmented from '../components/ui/Segmented'
import EmptyState from '../components/ui/EmptyState'
import QueryBoundary from '../components/ui/QueryBoundary'
import { Skeleton } from '../components/ui/Skeleton'
import InfoTooltip from '../help/components/InfoTooltip'
import { COLOR_COMPRA_PROPIA, colorResultado, textoContexto } from '../components/tecnico/operacionesPropias'
import { fechaCorta, formatoPct } from '../components/tecnico/formatoEjes'

type FiltroTipo = 'todas' | 'compra' | 'venta'

const OPCIONES_TIPO: { value: FiltroTipo; label: string }[] = [
  { value: 'todas', label: 'Todas' }, { value: 'compra', label: 'Compras' }, { value: 'venta', label: 'Ventas' },
]

const NOMBRE_TIPO: Record<DiarioOperacionOut['tipo'], string> = {
  compra: 'Compra', venta: 'Venta', amortizacion: 'Amortización',
}

/**
 * El diario de lo que hiciste: cada compra y venta con el contexto de mercado de ese día (RSI,
 * distancia a la media de 200 ruedas, posición en el rango anual) y, para las ventas, qué pasó
 * después. Arriba, un resumen en palabras de cómo operás; abajo, la lista filtrable, y cada fila
 * lleva al gráfico técnico del ticker. Los resultados en dinero pasan por el modo privacidad; los
 * porcentajes y los indicadores se ven siempre.
 */
export default function DiarioOperaciones() {
  const navigate = useNavigate()
  const fmt = useFormatoFijo('USD')
  const [tipo, setTipo] = useState<FiltroTipo>('todas')
  const [ticker, setTicker] = useState<string | null>(null)

  const query = useQuery({ queryKey: qk.de('diario-operaciones'), queryFn: getDiarioOperaciones })
  const datos = query.data

  const tickers = useMemo(
    () => [...new Set((datos?.operaciones ?? []).map(o => o.ticker))].sort(),
    [datos],
  )
  const filtradas = useMemo(
    () => (datos?.operaciones ?? []).filter(o =>
      (tipo === 'todas' || o.tipo === tipo) && (ticker == null || o.ticker === ticker)),
    [datos, tipo, ticker],
  )

  return (
    <div className="pb-4">
      <ScreenHeader title="Diario de operaciones" onBack={() => navigate(-1)} />

      <QueryBoundary
        isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}
        fallback={<Skeleton className="h-[240px] rounded-xl" />}
      >
        {datos && datos.operaciones.length === 0 ? (
          <EmptyState title="Todavía no hay operaciones" description="Cuando registres compras o ventas van a aparecer acá, con el contexto de mercado de cada una." />
        ) : datos ? (
          <div className="flex flex-col gap-3">
            <Card>
              <div className="flex items-center gap-1 text-label font-bold text-app-text-dim uppercase mb-2">
                Cómo operás
                <InfoTooltip term="diario_como_operas" />
              </div>
              {datos.frases.length > 0 ? (
                <ul className="flex flex-col gap-1.5 text-caption text-app-text list-disc pl-4">
                  {datos.frases.map(f => <li key={f}>{f}</li>)}
                </ul>
              ) : (
                <p className="text-caption text-app-text-dim">
                  Todavía son pocas operaciones para sacar conclusiones: hacen falta al menos tres con datos de mercado.
                </p>
              )}
              <p className="mt-2 text-label text-app-text-faint">
                {datos.resumen.n_compras} compras y {datos.resumen.n_ventas} ventas. El contexto sale de la serie de referencia
                de cada ticker (para un CEDEAR, la acción en dólares).
              </p>
            </Card>

            <div className="flex flex-col gap-2">
              <Segmented options={OPCIONES_TIPO} value={tipo} onChange={setTipo} />
              <div className="flex gap-2 overflow-x-auto no-scrollbar -mx-4 px-4">
                {[null, ...tickers].map(t => (
                  <button
                    key={t ?? 'todos'} type="button" onClick={() => setTicker(t)}
                    className={`shrink-0 font-semibold text-caption px-3 py-1.5 rounded-[10px] border transition-colors ${
                      t === ticker ? 'bg-app-accent-soft border-app-accent text-app-accent' : 'bg-app-surface border-app-border text-app-text-dim'
                    }`}
                  >
                    {t ?? 'Todos'}
                  </button>
                ))}
              </div>
            </div>

            {filtradas.length === 0 ? (
              <p className="text-caption text-app-text-dim py-4 text-center">Ninguna operación con ese filtro.</p>
            ) : (
              <div className="flex flex-col divide-y divide-app-border rounded-xl bg-app-surface-2">
                {filtradas.map((o, i) => (
                  <Fila
                    key={`${o.ticker}-${o.fecha}-${o.tipo}-${i}`} op={o}
                    resultado={o.resultado_usd != null ? fmt.montoConSigno(o.resultado_usd) : null}
                    onAbrir={() => navigate(`/analisis-tecnico?ticker=${encodeURIComponent(o.ticker)}`)}
                  />
                ))}
              </div>
            )}

            {datos.tickers_sin_serie.length > 0 && (
              <p className="text-label text-app-text-dim">
                Sin serie de precios para calcular el contexto de: {datos.tickers_sin_serie.join(', ')}.
              </p>
            )}
          </div>
        ) : null}
      </QueryBoundary>
    </div>
  )
}

function Fila({ op, resultado, onAbrir }: { op: DiarioOperacionOut; resultado: string | null; onAbrir: () => void }) {
  const color = op.tipo === 'compra' ? COLOR_COMPRA_PROPIA : colorResultado(op.resultado_usd)
  const moneda: Moneda = op.moneda === 'USD' ? 'USD' : 'ARS'
  const contexto = textoContexto(op)
  return (
    <button type="button" onClick={onAbrir} className="flex items-start justify-between gap-3 px-3 py-2.5 text-left">
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="text-caption font-semibold text-app-text">{op.ticker}</span>
          <span className="text-label font-semibold" style={{ color }}>
            {op.tipo === 'compra' ? '▲' : op.tipo === 'venta' ? '▼' : '▽'} {NOMBRE_TIPO[op.tipo]}
          </span>
          <span className="text-label text-app-text-faint font-mono tabular-nums">{fechaCorta(op.fecha)}</span>
        </div>
        <div className="text-label text-app-text-dim font-mono tabular-nums">
          {op.cantidad} a {formatMonedaCruda(op.precio, moneda)}
        </div>
        {contexto && <div className="text-label text-app-text-dim font-mono tabular-nums mt-0.5">{contexto}</div>}
      </div>
      {(resultado != null || op.resultado_pct != null) && (
        <div className="shrink-0 text-right font-mono tabular-nums" style={{ color }}>
          {resultado != null && <div className="text-caption font-semibold">{resultado}</div>}
          {op.resultado_pct != null && <div className="text-label">{formatoPct(op.resultado_pct)}</div>}
        </div>
      )}
    </button>
  )
}
