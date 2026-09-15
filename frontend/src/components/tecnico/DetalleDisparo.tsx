import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { qk } from '../../api/queryClient'
import {
  backtestEstrategia,
  type EstrategiaOut, type ScreenerCondicionOut, type ScreenerFilaOut,
} from '../../api'
import Segmented from '../ui/Segmented'
import EmptyState from '../ui/EmptyState'
import QueryBoundary from '../ui/QueryBoundary'
import { Skeleton } from '../ui/Skeleton'
import { Icon } from '../icons/Icons'
import InfoTooltip from '../../help/components/InfoTooltip'
import { calcularDesde, formatARS, formatPct, formatPrecio, formatUSD, type PeriodoEvolucion } from '../../utils'
import GraficoBacktest from './GraficoBacktest'
import type { GatilloPrecio } from './PanelPrecio'

/** Compartido con `Screener.tsx`: la fila del acordeón y el encabezado de este panel usan las
 * mismas etiquetas de motivo. */
export const MOTIVO_LABEL: Record<string, string> = {
  entrada: 'Entrada',
  regla_salida: 'Regla de salida',
  stop_loss: 'Stop loss',
  take_profit: 'Take profit',
  trailing_stop: 'Trailing stop',
}

export function formatMoneda(valor: number, moneda: string): string {
  if (moneda === 'ARS') return formatARS(valor)
  if (moneda === 'USD') return formatUSD(valor)
  return formatPrecio(valor)
}

/** Desglose ✓/✗ de una fila del screener: lo usa tanto el acordeón de `Screener.tsx` como este
 * panel, con la misma fila. */
export function ListaCondiciones({ condiciones }: { condiciones: ScreenerCondicionOut[] }) {
  if (condiciones.length === 0) return null
  return (
    <div className="flex flex-col gap-1">
      <div className="text-label text-app-text-dim">
        <InfoTooltip term="screener_condiciones" label="Condiciones" />
      </div>
      {condiciones.map((c, i) => (
        <div key={i} className="flex items-center gap-1.5 text-label">
          <Icon
            name={c.cumple ? 'check' : 'close'}
            className={`w-3 h-3 shrink-0 ${c.cumple ? 'text-app-pos' : 'text-app-text-faint'}`}
          />
          <span className="font-mono text-app-text-dim truncate">
            {c.izq_etiqueta} {c.izq_valor != null && `(${formatPrecio(c.izq_valor)})`} {c.op} {c.der_etiqueta}
            {c.der_valor != null && ` (${formatPrecio(c.der_valor)})`}
          </span>
        </div>
      ))}
    </div>
  )
}

const PERIODOS: PeriodoEvolucion[] = ['1M', '3M', '6M', '1Y', '3Y', 'YTD', 'ALL']

/**
 * Contenido del panel a pantalla completa "por qué puede disparar": corre un backtest de la
 * estrategia sobre el ticker sólo para tener con qué dibujar (velas, indicadores, señales
 * históricas, niveles de riesgo) y le suma la capa de gatillo con el nivel que calculó el
 * screener.
 *
 * Los números que se muestran (distancia, precio gatillo, condiciones) son siempre los de `fila`
 * -tal como los calculó el screener sobre toda la serie disponible-, nunca recalculados acá: este
 * backtest corre sobre una ventana más corta (el período elegido + warm-up), así que un indicador
 * recursivo (EMA/RSI/MACD/ATR) puede diferir en el último decimal. El backtest sólo aporta el
 * dibujo, no los números.
 */
export default function DetalleDisparo({
  fila, estrategia,
}: {
  fila: ScreenerFilaOut
  estrategia: EstrategiaOut | undefined
}) {
  const [periodo, setPeriodo] = useState<PeriodoEvolucion>('1Y')
  const desde = calcularDesde(periodo)

  const backtestQuery = useQuery({
    queryKey: qk.de('screener-disparo', fila.ticker, fila.estrategia_id, periodo),
    queryFn: () => backtestEstrategia(fila.ticker, estrategia!.definicion, desde, undefined, fila.variante),
    enabled: estrategia != null,
  })

  if (!estrategia) {
    return (
      <EmptyState
        title="Estrategia no encontrada"
        description="Esta estrategia se borró o se modificó después del escaneo. Volvé a escanear para verla de nuevo."
      />
    )
  }

  const resultado = backtestQuery.data
  const gatillo: GatilloPrecio = {
    precio: fila.precio_gatillo,
    precioActual: fila.precio_actual,
    distanciaPct: fila.distancia_pct,
    tipo: fila.tipo,
    motivo: fila.motivo,
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-1.5">
            <span
              className={`rounded-md px-1.5 py-0.5 text-label font-bold border ${
                fila.tipo === 'compra'
                  ? 'border-app-pos/40 text-app-pos bg-app-pos-soft'
                  : 'border-app-neg/40 text-app-neg bg-app-neg-soft'
              }`}
            >
              {fila.tipo === 'compra' ? '▲' : '▼'} {fila.tipo}
            </span>
            <span className="text-caption text-app-text-dim">{MOTIVO_LABEL[fila.motivo] ?? fila.motivo}</span>
          </div>
          <div className="mt-1">
            <InfoTooltip term="screener_grafico_gatillo" label="Cómo leer este gráfico" className="text-label text-app-text-dim" />
          </div>
        </div>
        <Segmented options={PERIODOS.map(p => ({ value: p, label: p }))} value={periodo} onChange={setPeriodo} />
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-label text-app-text-dim">
        <span>
          Precio actual <span className="font-mono font-bold text-app-text">{formatMoneda(fila.precio_actual, fila.moneda)}</span>
        </span>
        <span className="inline-flex items-center gap-0.5">
          Precio gatillo
          <InfoTooltip term="screener_precio_gatillo" />
          <span className="font-mono font-bold text-app-text">{formatMoneda(fila.precio_gatillo, fila.moneda)}</span>
        </span>
        <span className="inline-flex items-center gap-0.5">
          Distancia
          <InfoTooltip term="screener_distancia" />
          <span className="font-mono font-bold text-app-text">{formatPct(fila.distancia_pct)}</span>
        </span>
        {fila.posicion_abierta && fila.retorno_abierta_pct != null && (
          <span>
            Posición abierta <span className="font-mono font-bold text-app-text">{formatPct(fila.retorno_abierta_pct)}</span>
          </span>
        )}
      </div>

      <QueryBoundary
        isLoading={backtestQuery.isLoading} error={backtestQuery.error}
        onRetry={() => void backtestQuery.refetch()} fallback={<Skeleton className="h-[240px] rounded-xl" />}
      >
        {resultado && resultado.barras.length === 0 ? (
          <EmptyState title="Sin serie suficiente" description="Todavía no hay datos históricos para graficar este ticker." />
        ) : resultado ? (
          <GraficoBacktest
            barras={resultado.barras} indicadoresSeries={resultado.indicadores}
            dslIndicadores={estrategia.definicion.indicadores}
            senales={resultado.senales} operaciones={resultado.operaciones}
            primeraBarraEvaluable={resultado.primera_barra_evaluable}
            curvaEquity={resultado.curva_equity} curvaBuyHold={resultado.curva_buy_hold}
            indiceDesde={resultado.indice_desde} moneda={resultado.moneda}
            tieneVelas={resultado.barras.some(b => b.apertura != null)}
            tieneVolumen={resultado.barras.some(b => b.volumen != null)}
            gatillo={gatillo} mostrarEquity={false}
            fullscreen
          />
        ) : null}
      </QueryBoundary>

      <ListaCondiciones condiciones={fila.condiciones} />
    </div>
  )
}
