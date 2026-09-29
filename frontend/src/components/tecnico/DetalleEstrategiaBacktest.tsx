import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { qk } from '../../api/queryClient'
import { backtestEstrategia, type EstrategiaOut, type VarianteSerie } from '../../api'
import QueryBoundary from '../ui/QueryBoundary'
import { Skeleton } from '../ui/Skeleton'
import EmptyState from '../ui/EmptyState'
import GraficoBacktest from './GraficoBacktest'
import GraficoFullscreen from './GraficoFullscreen'
import TablaOperaciones from './TablaOperaciones'

/**
 * Detalle de una estrategia del comparador: corre el backtest **existente** (mismo endpoint que
 * `/analisis-tecnico`) sólo para tener con qué dibujar velas + indicadores + señales + niveles de
 * riesgo (`GraficoBacktest`, el "calendario de señales"). No es la fuente de los números de la
 * tabla/tarjetas del comparador -esos ya vienen calculados con el eje de fechas común-, es nomás la
 * vista de una estrategia puntual. Mismo patrón que `Screener.tsx` → `DetalleDisparo.tsx`.
 */
export default function DetalleEstrategiaBacktest({
  ticker, estrategia, desde, hasta, variante,
}: {
  ticker: string
  estrategia: EstrategiaOut
  desde?: string
  hasta?: string
  variante: VarianteSerie
}) {
  const [fullscreen, setFullscreen] = useState(false)
  const query = useQuery({
    queryKey: qk.de('comparador-detalle-estrategia', ticker, estrategia.id, desde, hasta, variante),
    queryFn: () => backtestEstrategia(ticker, estrategia.definicion, desde, hasta, variante),
  })

  return (
    <QueryBoundary
      isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}
      fallback={<Skeleton className="h-[240px] rounded-xl" />}
    >
      {query.data && query.data.barras.length === 0 ? (
        <EmptyState title="Sin datos para graficar" description="No hay serie suficiente en este ticker y período." />
      ) : query.data ? (
        <div className="flex flex-col gap-3">
          <GraficoBacktest
            barras={query.data.barras} indicadoresSeries={query.data.indicadores}
            dslIndicadores={estrategia.definicion.indicadores}
            senales={query.data.senales} operaciones={query.data.operaciones}
            primeraBarraEvaluable={query.data.primera_barra_evaluable}
            curvaEquity={query.data.curva_equity} curvaBuyHold={query.data.curva_buy_hold}
            indiceDesde={query.data.indice_desde} moneda={query.data.moneda}
            tieneVelas={query.data.barras.some(b => b.apertura != null)}
            tieneVolumen={query.data.barras.some(b => b.volumen != null)}
            onToggleFullscreen={() => setFullscreen(true)}
          />
          <GraficoFullscreen open={fullscreen} onClose={() => setFullscreen(false)} title={`${ticker} · ${estrategia.nombre}`}>
            <GraficoBacktest
              barras={query.data.barras} indicadoresSeries={query.data.indicadores}
              dslIndicadores={estrategia.definicion.indicadores}
              senales={query.data.senales} operaciones={query.data.operaciones}
              primeraBarraEvaluable={query.data.primera_barra_evaluable}
              curvaEquity={query.data.curva_equity} curvaBuyHold={query.data.curva_buy_hold}
              indiceDesde={query.data.indice_desde} moneda={query.data.moneda}
              tieneVelas={query.data.barras.some(b => b.apertura != null)}
              tieneVolumen={query.data.barras.some(b => b.volumen != null)}
              fullscreen onToggleFullscreen={() => setFullscreen(false)}
            />
          </GraficoFullscreen>
          <TablaOperaciones ticker={ticker} operaciones={query.data.operaciones} />
        </div>
      ) : null}
    </QueryBoundary>
  )
}
