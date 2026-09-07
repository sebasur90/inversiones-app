import { useRef, useState } from 'react'
import type { BarraOut, CurvaPuntoOut, IndicadorDsl, SenalOut } from '../../api'
import { useEscalaX } from './useEscalaX'
import { useAnchoContenedor } from './useAnchoContenedor'
import { manejadoresPuntero } from './crosshair'
import { trazoDeSerie } from './trazo'
import PanelPrecio, { type OverlayPrecio } from './PanelPrecio'
import PanelIndicador from './PanelIndicador'
import PanelVolumen from './PanelVolumen'
import { ESPEC_POR_TIPO, claveIndicador } from './indicadoresConfig'

/** Colores para distinguir varios overlays del mismo tipo sobre el precio (p.ej. las dos medias
 * del cruce de medias, que en `indicadoresConfig` comparten color). */
const PALETA_OVERLAY = ['#d8b14a', '#5b8ba0', '#9c7aa0', '#4fd1ae', '#e2a13a']
const COLOR_ESTRATEGIA = '#d8b14a'
const COLOR_BUYHOLD = '#8ca39b'
const COLOR_GRID = '#223028'
const COLOR_EJE = '#8ca39b'

/**
 * Gráfico del resultado de un backtest: velas del precio + indicadores de la estrategia (medias,
 * RSI, MACD…) + flechas de entrada/salida (`senales`) + curva de rendimiento vs. buy & hold, todo
 * sobre la misma escala X para que el crosshair quede alineado entre paneles.
 *
 * Las series (`indicadoresSeries`, `curvaEquity`, `curvaBuyHold`) vienen del backtest ya alineadas
 * 1:1 con `barras` y con `senales[].indice`, así que no hay que realinear por fecha.
 */
export default function GraficoBacktest({
  barras: barrasRaw, indicadoresSeries: indicadoresRaw, dslIndicadores, senales: senalesRaw,
  primeraBarraEvaluable, curvaEquity: curvaEquityRaw, curvaBuyHold: curvaBuyHoldRaw,
  indiceDesde = 0, moneda, tieneVelas, tieneVolumen,
}: {
  barras: BarraOut[]
  indicadoresSeries: Record<string, Record<string, (number | null)[]>>
  dslIndicadores: IndicadorDsl[]
  senales: SenalOut[]
  primeraBarraEvaluable?: number | null
  curvaEquity: CurvaPuntoOut[]
  curvaBuyHold: CurvaPuntoOut[]
  indiceDesde?: number
  moneda?: string
  tieneVelas: boolean
  tieneVolumen: boolean
}) {
  // Recorta el warm-up de indicadores previo a `desde` (puede ser cientos de ruedas para MM200),
  // reindexando señales y `primera_barra_evaluable` para que sigan alineadas con `barras`.
  const off = Math.max(0, Math.min(indiceDesde, Math.max(0, barrasRaw.length - 2)))
  const barras = off ? barrasRaw.slice(off) : barrasRaw
  const curvaEquity = off ? curvaEquityRaw.slice(off) : curvaEquityRaw
  const curvaBuyHold = off ? curvaBuyHoldRaw.slice(off) : curvaBuyHoldRaw
  const senales = off ? senalesRaw.filter(s => s.indice >= off).map(s => ({ ...s, indice: s.indice - off })) : senalesRaw
  const indicadoresSeries: Record<string, Record<string, (number | null)[]>> = off
    ? Object.fromEntries(
        Object.entries(indicadoresRaw).map(([id, series]) => [
          id, Object.fromEntries(Object.entries(series).map(([k, v]) => [k, v.slice(off)])),
        ]),
      )
    : indicadoresRaw
  const pbe = primeraBarraEvaluable != null && primeraBarraEvaluable > off ? primeraBarraEvaluable - off : undefined

  const [containerRef, ancho] = useAnchoContenedor<HTMLDivElement>(280)
  const escalaX = useEscalaX(barras.length, ancho)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)

  const overlaysPrecio: OverlayPrecio[] = []
  const overlaysVolumen: { clave: string; color: string; series: Record<string, (number | null)[]> }[] = []
  const panelesOsciladores: { tipo: string; clave: string; series: Record<string, (number | null)[]> }[] = []

  dslIndicadores.forEach((ind, i) => {
    const espec = ESPEC_POR_TIPO[ind.tipo]
    const series = indicadoresSeries[ind.id]
    if (!espec || !series) return
    const clave = claveIndicador(ind.tipo, ind.params)
    if (espec.destino === 'precio') {
      overlaysPrecio.push({ clave, tipo: ind.tipo, color: PALETA_OVERLAY[i % PALETA_OVERLAY.length], series })
    } else if (espec.destino === 'volumen') {
      overlaysVolumen.push({ clave, color: PALETA_OVERLAY[i % PALETA_OVERLAY.length], series })
    } else {
      panelesOsciladores.push({ tipo: ind.tipo, clave, series })
    }
  })

  const barraHover = hoverIndex != null ? barras[hoverIndex] : undefined
  const equityHover = hoverIndex != null ? curvaEquity[hoverIndex]?.valor : undefined
  const buyHoldHover = hoverIndex != null ? curvaBuyHold[hoverIndex]?.valor : undefined

  return (
    <div ref={containerRef} className="w-full">
      <div className="text-label text-app-text-dim font-mono tabular-nums h-4 truncate mb-1">
        {barraHover
          ? `${barraHover.fecha} · ${moneda ? moneda + ' ' : ''}O ${barraHover.apertura?.toFixed(2) ?? '—'} A ${barraHover.maximo?.toFixed(2) ?? '—'} B ${barraHover.minimo?.toFixed(2) ?? '—'} C ${barraHover.cierre.toFixed(2)}`
          : ' '}
      </div>

      {(overlaysPrecio.length > 0 || senales.length > 0) && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-1.5 text-label text-app-text-dim">
          {overlaysPrecio.map(o => (
            <span key={o.clave} className="inline-flex items-center gap-1">
              <span className="inline-block w-3 h-0.5 rounded" style={{ background: o.color }} />
              {o.clave}
            </span>
          ))}
          {senales.length > 0 && (
            <>
              <span className="inline-flex items-center gap-1"><span style={{ color: '#4fd1ae' }}>▲</span> compra</span>
              <span className="inline-flex items-center gap-1"><span style={{ color: '#e2665a' }}>▼</span> venta</span>
            </>
          )}
        </div>
      )}

      <PanelPrecio
        barras={barras} escalaX={escalaX} alto={240} tieneVelas={tieneVelas} moneda={moneda}
        overlays={overlaysPrecio} senales={senales} primeraBarraEvaluable={pbe}
        hoverIndex={hoverIndex} onHover={setHoverIndex}
      />

      {panelesOsciladores.map(p => (
        <div key={p.clave} className="mt-2">
          <PanelIndicador
            tipo={p.tipo} clave={p.clave} series={p.series} escalaX={escalaX}
            alto={90} hoverIndex={hoverIndex} onHover={setHoverIndex}
          />
        </div>
      ))}

      <div className="mt-2">
        <div className="flex items-center justify-between text-label text-app-text-faint px-1 mb-0.5">
          <span>Rendimiento vs. buy &amp; hold (base 100)</span>
          <span className="font-mono tabular-nums">
            {equityHover != null
              ? `Estrategia ${equityHover.toFixed(1)} · B&H ${buyHoldHover?.toFixed(1) ?? '—'}`
              : ''}
          </span>
        </div>
        <PanelEquity
          curvaEquity={curvaEquity} curvaBuyHold={curvaBuyHold} escalaX={escalaX} alto={110}
          hoverIndex={hoverIndex} onHover={setHoverIndex}
        />
      </div>

      {tieneVolumen && (
        <div className="mt-2">
          <PanelVolumen
            barras={barras} overlays={overlaysVolumen} escalaX={escalaX}
            alto={70} hoverIndex={hoverIndex} onHover={setHoverIndex}
          />
        </div>
      )}
    </div>
  )
}

function PanelEquity({
  curvaEquity, curvaBuyHold, escalaX, alto, hoverIndex, onHover,
}: {
  curvaEquity: CurvaPuntoOut[]
  curvaBuyHold: CurvaPuntoOut[]
  escalaX: ReturnType<typeof useEscalaX>
  alto: number
  hoverIndex: number | null
  onHover: (i: number | null) => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const handlers = manejadoresPuntero(svgRef, escalaX, onHover)

  const est = curvaEquity.map(p => p.valor)
  const bh = curvaBuyHold.map(p => p.valor)
  const todos = [...est, ...bh].filter((v): v is number => Number.isFinite(v))
  const minV = todos.length ? Math.min(...todos, 100) : 0
  const maxV = todos.length ? Math.max(...todos, 100) : 1
  const pad = (maxV - minV) * 0.08 || 1
  const y0 = minV - pad
  const y1 = maxV + pad
  const yDeValor = (v: number) => alto - ((v - y0) / (y1 - y0 || 1)) * alto

  return (
    <svg ref={svgRef} width={escalaX.ancho} height={alto} className="block touch-none select-none" {...handlers}>
      <line x1={0} x2={escalaX.ancho} y1={yDeValor(100)} y2={yDeValor(100)} stroke={COLOR_GRID} strokeDasharray="3 3" />
      <path d={trazoDeSerie(bh, escalaX, yDeValor)} fill="none" stroke={COLOR_BUYHOLD} strokeWidth={1.5} strokeDasharray="4 3" />
      <path d={trazoDeSerie(est, escalaX, yDeValor)} fill="none" stroke={COLOR_ESTRATEGIA} strokeWidth={2} />
      {hoverIndex != null && (
        <line x1={escalaX.xDeIndice(hoverIndex)} x2={escalaX.xDeIndice(hoverIndex)} y1={0} y2={alto} stroke={COLOR_EJE} strokeOpacity={0.5} />
      )}
    </svg>
  )
}
