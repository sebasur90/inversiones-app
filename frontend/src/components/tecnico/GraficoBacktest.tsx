import { useRef, useState } from 'react'
import type { BarraOut, CurvaPuntoOut, IndicadorDsl, OperacionOut, SenalOut } from '../../api'
import { useEscalaX } from './useEscalaX'
import { useVentanaVisible } from './useVentanaVisible'
import { useAnchoContenedor } from './useAnchoContenedor'
import { manejadoresPuntero } from './crosshair'
import { trazoDeSerie, valoresVisibles } from './trazo'
import PanelPrecio, { type OverlayPrecio } from './PanelPrecio'
import PanelIndicador from './PanelIndicador'
import PanelVolumen from './PanelVolumen'
import { ESPEC_POR_TIPO, claveIndicador } from './indicadoresConfig'
import { COLOR_MOTIVO, ETIQUETA_MOTIVO, GLIFO_MOTIVO } from './motivosSalida'
import { Icon } from '../icons/Icons'

/** Colores para distinguir varios overlays del mismo tipo sobre el precio (p.ej. las dos medias
 * del cruce de medias, que en `indicadoresConfig` comparten color). */
const PALETA_OVERLAY = ['#3b82f6', '#f59e0b', '#8b5cf6', '#10b981', '#fbbf24']
const COLOR_ESTRATEGIA = '#3b82f6'
const COLOR_BUYHOLD = '#94a3b8'
const COLOR_GRID = '#1c1f2a'
const COLOR_EJE = '#94a3b8'

const ALTOS = {
  normal: { precio: 240, oscilador: 90, equity: 110, volumen: 70 },
  fullscreen: { precio: 400, oscilador: 130, equity: 150, volumen: 100 },
}

/**
 * Gráfico del resultado de un backtest: velas del precio + indicadores de la estrategia (medias,
 * RSI, MACD…) + marcadores de entrada/salida y niveles de riesgo + curva de rendimiento vs. buy &
 * hold, todo sobre la misma escala X para que el crosshair quede alineado entre paneles.
 *
 * Las series (`indicadoresSeries`, `curvaEquity`, `curvaBuyHold`) vienen del backtest ya alineadas
 * 1:1 con `barras` y con `senales[].indice`, así que no hay que realinear por fecha. El zoom y el
 * desplazamiento viven en `useVentanaVisible` y viajan por `useEscalaX`: los paneles reciben
 * siempre las series completas y dibujan sólo el tramo visible.
 */
export default function GraficoBacktest({
  barras: barrasRaw, indicadoresSeries: indicadoresRaw, dslIndicadores, senales: senalesRaw,
  operaciones: operacionesRaw = [], primeraBarraEvaluable,
  curvaEquity: curvaEquityRaw, curvaBuyHold: curvaBuyHoldRaw,
  indiceDesde = 0, moneda, tieneVelas, tieneVolumen, fullscreen = false, onToggleFullscreen,
}: {
  barras: BarraOut[]
  indicadoresSeries: Record<string, Record<string, (number | null)[]>>
  dslIndicadores: IndicadorDsl[]
  senales: SenalOut[]
  operaciones?: OperacionOut[]
  primeraBarraEvaluable?: number | null
  curvaEquity: CurvaPuntoOut[]
  curvaBuyHold: CurvaPuntoOut[]
  indiceDesde?: number
  moneda?: string
  tieneVelas: boolean
  tieneVolumen: boolean
  fullscreen?: boolean
  onToggleFullscreen?: () => void
}) {
  // Recorta el warm-up de indicadores previo a `desde` (puede ser cientos de ruedas para MM200),
  // reindexando señales, operaciones y `primera_barra_evaluable` para que sigan alineadas con
  // `barras`. Esto es un recorte de una vez, distinto de la ventana de zoom (que no recorta nada).
  const off = Math.max(0, Math.min(indiceDesde, Math.max(0, barrasRaw.length - 2)))
  const barras = off ? barrasRaw.slice(off) : barrasRaw
  const curvaEquity = off ? curvaEquityRaw.slice(off) : curvaEquityRaw
  const curvaBuyHold = off ? curvaBuyHoldRaw.slice(off) : curvaBuyHoldRaw
  const senales = off ? senalesRaw.filter(s => s.indice >= off).map(s => ({ ...s, indice: s.indice - off })) : senalesRaw
  const operaciones = off
    ? operacionesRaw
        .filter(o => (o.indice_salida ?? barrasRaw.length - 1) >= off)
        .map(o => ({
          ...o,
          indice_entrada: o.indice_entrada - off,
          indice_salida: o.indice_salida != null ? o.indice_salida - off : null,
        }))
    : operacionesRaw
  const indicadoresSeries: Record<string, Record<string, (number | null)[]>> = off
    ? Object.fromEntries(
        Object.entries(indicadoresRaw).map(([id, series]) => [
          id, Object.fromEntries(Object.entries(series).map(([k, v]) => [k, v.slice(off)])),
        ]),
      )
    : indicadoresRaw
  const pbe = primeraBarraEvaluable != null && primeraBarraEvaluable > off ? primeraBarraEvaluable - off : undefined

  const [containerRef, ancho] = useAnchoContenedor<HTMLDivElement>(280)
  const controles = useVentanaVisible(barras.length, ancho)
  const escalaX = useEscalaX(barras.length, ancho, controles.ventana)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const alto = fullscreen ? ALTOS.fullscreen : ALTOS.normal

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

  // Motivos efectivamente presentes: una leyenda con los cinco siempre sería ruido en una
  // estrategia que sólo sale por regla.
  const motivosPresentes = Array.from(new Set(senales.filter(s => s.tipo === 'venta').map(s => s.motivo)))

  return (
    <div ref={containerRef} className="w-full">
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="text-label text-app-text-dim font-mono tabular-nums h-4 truncate">
          {barraHover
            ? `${barraHover.fecha} · ${moneda ? moneda + ' ' : ''}O ${barraHover.apertura?.toFixed(2) ?? '—'} A ${barraHover.maximo?.toFixed(2) ?? '—'} B ${barraHover.minimo?.toFixed(2) ?? '—'} C ${barraHover.cierre.toFixed(2)}`
            : ' '}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <BotonControl label="Alejar" onClick={() => controles.zoom(1 / 1.5)} disabled={controles.completa}>−</BotonControl>
          <BotonControl label="Acercar" onClick={() => controles.zoom(1.5)}>+</BotonControl>
          <BotonControl label="Ver todo el período" onClick={controles.reset} disabled={controles.completa}>⤢</BotonControl>
          {onToggleFullscreen && (
            <button
              type="button" onClick={onToggleFullscreen}
              aria-label={fullscreen ? 'Salir de pantalla completa' : 'Ver en pantalla completa'}
              className="w-7 h-7 rounded flex items-center justify-center bg-app-surface-2 text-app-text-dim"
            >
              {fullscreen ? <Icon name="close" className="w-3.5 h-3.5" /> : <span className="text-body leading-none">⛶</span>}
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-1.5 text-label text-app-text-dim">
        {overlaysPrecio.map(o => (
          <span key={o.clave} className="inline-flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 rounded" style={{ background: o.color }} />
            {o.clave}
          </span>
        ))}
        {senales.length > 0 && (
          <span className="inline-flex items-center gap-1"><span style={{ color: '#10b981' }}>▲</span> compra</span>
        )}
        {motivosPresentes.map(m => (
          <span key={m} className="inline-flex items-center gap-1">
            <span className="font-mono font-bold" style={{ color: COLOR_MOTIVO[m] ?? '#ef4444' }}>{GLIFO_MOTIVO[m] ?? '▼'}</span>
            {ETIQUETA_MOTIVO[m] ?? m}
          </span>
        ))}
      </div>

      <div
        className={controles.arrastrando ? 'cursor-grabbing' : 'cursor-grab'}
        {...controles.handlers}
      >
        <PanelPrecio
          barras={barras} escalaX={escalaX} alto={alto.precio} tieneVelas={tieneVelas} moneda={moneda}
          overlays={overlaysPrecio} senales={senales} operaciones={operaciones} primeraBarraEvaluable={pbe}
          hoverIndex={hoverIndex} onHover={setHoverIndex}
        />

        {panelesOsciladores.map(p => (
          <div key={p.clave} className="mt-2">
            <PanelIndicador
              tipo={p.tipo} clave={p.clave} series={p.series} escalaX={escalaX}
              alto={alto.oscilador} hoverIndex={hoverIndex} onHover={setHoverIndex}
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
            curvaEquity={curvaEquity} curvaBuyHold={curvaBuyHold} escalaX={escalaX} alto={alto.equity}
            hoverIndex={hoverIndex} onHover={setHoverIndex}
          />
        </div>

        {tieneVolumen && (
          <div className="mt-2">
            <PanelVolumen
              barras={barras} overlays={overlaysVolumen} escalaX={escalaX}
              alto={alto.volumen} hoverIndex={hoverIndex} onHover={setHoverIndex}
            />
          </div>
        )}
      </div>

      <div className="mt-1 text-label text-app-text-faint font-mono tabular-nums">
        {barras.length > 0 && (
          <>
            {escalaX.visibles} de {barras.length} ruedas · {barras[escalaX.inicio]?.fecha} → {barras[escalaX.fin]?.fecha}
            {!controles.completa && ' · doble clic para ver todo'}
          </>
        )}
      </div>
    </div>
  )
}

function BotonControl({
  children, label, onClick, disabled,
}: {
  children: React.ReactNode
  label: string
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button" onClick={onClick} disabled={disabled} aria-label={label} title={label}
      className="w-7 h-7 rounded flex items-center justify-center bg-app-surface-2 text-app-text-dim disabled:opacity-40"
    >
      {children}
    </button>
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
  const todos = [...valoresVisibles(est, escalaX), ...valoresVisibles(bh, escalaX)]
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
      {hoverIndex != null && escalaX.visible(hoverIndex) && (
        <line x1={escalaX.xDeIndice(hoverIndex)} x2={escalaX.xDeIndice(hoverIndex)} y1={0} y2={alto} stroke={COLOR_EJE} strokeOpacity={0.5} />
      )}
    </svg>
  )
}
