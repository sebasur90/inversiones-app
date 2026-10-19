import { useRef, useState } from 'react'
import type { BarraOut, CurvaPuntoOut, IndicadorDsl, OperacionOut, OperacionesGraficoOut, SenalOut } from '../../api'
import { useEscalaX } from './useEscalaX'
import { estiloContenedorGestos, useVentanaVisible } from './useVentanaVisible'
import { useAnchoContenedor } from './useAnchoContenedor'
import { useAltosGrafico } from './useAltosGrafico'
import { manejadoresPuntero } from './crosshair'
import { trazoDeSerie, valoresVisibles } from './trazo'
import PanelPrecio, { salidasGraficables, type GatilloPrecio, type OverlayPrecio } from './PanelPrecio'
import PanelIndicador from './PanelIndicador'
import PanelVolumen from './PanelVolumen'
import EjeFechas from './EjeFechas'
import FichaBarra from './FichaBarra'
import { BarraHerramientas, BotonesGrafico, PieGrafico } from './ControlesGrafico'
import { formatoValor } from './formatoEjes'
import GuiaGestos, { AVISO_SIN_RECORRIDO, AvisoGrafico, useAvisoGrafico, useGuiaGestos } from './GuiaGestos'
import { ESPEC_POR_TIPO, claveIndicador } from './indicadoresConfig'
import { COLOR_MOTIVO, ETIQUETA_MOTIVO, GLIFO_MOTIVO } from './motivosSalida'

/** Colores para distinguir varios overlays del mismo tipo sobre el precio (p.ej. las dos medias
 * del cruce de medias, que en `indicadoresConfig` comparten color). */
const PALETA_OVERLAY = ['#3b82f6', '#f59e0b', '#8b5cf6', '#10b981', '#fbbf24']
const COLOR_ESTRATEGIA = '#3b82f6'
const COLOR_BUYHOLD = '#94a3b8'
const COLOR_GRID = '#1c1f2a'
const COLOR_EJE = '#94a3b8'

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
  indiceDesde = 0, moneda, tieneVelas, tieneVolumen, gatillo, mostrarEquity = true,
  fullscreen = false, onToggleFullscreen, misOperaciones, operacionesActivas, onToggleOperaciones,
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
  /** Nivel de disparo del screener a marcar sobre la última barra: ver `GatilloPrecio`. No se
   * reindexa por `off` (no son índices de barra, son precios y la última barra). */
  gatillo?: GatilloPrecio
  /** Oculta la curva de rendimiento vs. buy & hold: el panel de "por qué puede disparar" del
   * screener no corre un backtest para evaluar la estrategia, sólo para dibujar el gráfico. */
  mostrarEquity?: boolean
  fullscreen?: boolean
  onToggleFullscreen?: () => void
  /** Tus compras y ventas de este ticker para marcarlas sobre las velas; `null`/`undefined` = apagado. */
  misOperaciones?: OperacionesGraficoOut | null
  /** El interruptor está prendido (aunque los datos todavía estén cargando). */
  operacionesActivas?: boolean
  /** Si viene, el gráfico ofrece el botón ▲▼ que prende y apaga `misOperaciones`. */
  onToggleOperaciones?: () => void
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
  const gestosRef = useRef<HTMLDivElement>(null)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const guia = useGuiaGestos()
  const aviso = useAvisoGrafico()
  const controles = useVentanaVisible(barras.length, ancho, gestosRef, {
    activo: true,
    onToque: i => setHoverIndex(hoverIndex === i ? null : i),
    onCruz: setHoverIndex,
    // `barrasRaw` y no `barras`: ésta es un `.slice()` nuevo en cada render.
    serie: barrasRaw,
    onCambioSerie: () => setHoverIndex(null),
    onSinRecorrido: () => aviso.avisar(AVISO_SIN_RECORRIDO),
  })
  const escalaX = useEscalaX(barras.length, ancho, controles.ventana)

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

  const alto = useAltosGrafico(fullscreen, {
    osciladores: panelesOsciladores.length, equity: mostrarEquity, volumen: tieneVolumen,
  })

  // Valores de la vela de la cruz o, sin cruz, de la última: en el celular no hay hover.
  const indiceValores = hoverIndex ?? barras.length - 1
  const equityHover = curvaEquity[indiceValores]?.valor
  const buyHoldHover = curvaBuyHold[indiceValores]?.valor

  // Motivos efectivamente presentes: una leyenda con los cinco siempre sería ruido en una
  // estrategia que sólo sale por regla.
  const motivosPresentes = Array.from(new Set(senales.filter(s => s.tipo === 'venta').map(s => s.motivo)))

  return (
    <div ref={containerRef} className="w-full">
      <FichaBarra
        barras={barras} indice={hoverIndex} moneda={moneda} senales={senales} operaciones={operaciones}
        conSenales misOperaciones={misOperaciones} onQuitar={() => setHoverIndex(null)}
        acciones={<BotonesGrafico controles={controles} fullscreen={fullscreen} onToggleFullscreen={onToggleFullscreen} />}
      />

      {onToggleOperaciones && (
        <BarraHerramientas
          herramientas={[{
            clave: 'operaciones', texto: '▲▼', activo: !!operacionesActivas, onToggle: onToggleOperaciones,
            label: operacionesActivas ? 'Ocultar mis compras y ventas' : 'Mostrar mis compras y ventas',
          }]}
        />
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-1.5 text-label text-app-text-dim">
        {overlaysPrecio.map(o => (
          <span key={o.clave} className="inline-flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 rounded" style={{ background: o.color }} />
            {o.clave}
            <span className="font-mono tabular-nums" style={{ color: o.color }}>
              {salidasGraficables(o).map(([, s]) => formatoValor(s[indiceValores])).join(' / ')}
            </span>
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
        {gatillo && (
          <span className="inline-flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 rounded border-t border-dashed" style={{ borderColor: COLOR_MOTIVO[gatillo.motivo] ?? (gatillo.tipo === 'compra' ? '#10b981' : '#ef4444') }} />
            gatillo
          </span>
        )}
      </div>

      <div className="relative">
      {guia.visible && <GuiaGestos onCerrar={guia.cerrar} />}
      <AvisoGrafico texto={aviso.texto} />
      <div
        ref={gestosRef}
        className={controles.arrastrando ? 'cursor-grabbing' : 'cursor-grab'}
        style={estiloContenedorGestos()}
      >
        <PanelPrecio
          barras={barras} escalaX={escalaX} alto={alto.precio} tieneVelas={tieneVelas} moneda={moneda}
          overlays={overlaysPrecio} senales={senales} operaciones={operaciones} primeraBarraEvaluable={pbe}
          gatillo={gatillo} misOperaciones={misOperaciones}
          hoverIndex={hoverIndex} onHover={setHoverIndex}
        />
        <EjeFechas barras={barras} escalaX={escalaX} />

        {panelesOsciladores.map(p => (
          <div key={p.clave} className="mt-1.5">
            <PanelIndicador
              tipo={p.tipo} clave={p.clave} series={p.series} escalaX={escalaX}
              alto={alto.oscilador} hoverIndex={hoverIndex} onHover={setHoverIndex}
            />
          </div>
        ))}

        {mostrarEquity && (
          <div className="mt-1.5">
            <div className="flex items-center justify-between gap-2 text-label text-app-text-faint px-1 mb-0.5">
              <span className="min-w-0 truncate">Rendimiento vs. buy &amp; hold (base 100)</span>
              <span className="shrink-0 font-mono tabular-nums">
                {equityHover != null && (
                  <>
                    <span style={{ color: COLOR_ESTRATEGIA }}>{equityHover.toFixed(1)}</span>
                    {' · '}
                    <span>B&amp;H {buyHoldHover?.toFixed(1) ?? '—'}</span>
                  </>
                )}
              </span>
            </div>
            <PanelEquity
              curvaEquity={curvaEquity} curvaBuyHold={curvaBuyHold} escalaX={escalaX} alto={alto.equity}
              hoverIndex={hoverIndex} onHover={setHoverIndex}
            />
          </div>
        )}

        {tieneVolumen && (
          <div className="mt-1.5">
            <PanelVolumen
              barras={barras} overlays={overlaysVolumen} escalaX={escalaX}
              alto={alto.volumen} hoverIndex={hoverIndex} onHover={setHoverIndex}
            />
          </div>
        )}
      </div>
      </div>

      <PieGrafico
        barras={barras} escalaX={escalaX} completa={controles.completa}
        conCruz={hoverIndex != null} onAyuda={guia.mostrar}
      />
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
  const todos = [...valoresVisibles(est, escalaX), ...valoresVisibles(bh, escalaX)]
  const minV = todos.length ? Math.min(...todos, 100) : 0
  const maxV = todos.length ? Math.max(...todos, 100) : 1
  const pad = (maxV - minV) * 0.08 || 1
  const y0 = minV - pad
  const y1 = maxV + pad
  const yDeValor = (v: number) => alto - ((v - y0) / (y1 - y0 || 1)) * alto

  return (
    <svg ref={svgRef} width={escalaX.ancho} height={alto} className="block select-none" {...handlers}>
      <line x1={0} x2={escalaX.ancho} y1={yDeValor(100)} y2={yDeValor(100)} stroke={COLOR_GRID} strokeDasharray="3 3" />
      <path d={trazoDeSerie(bh, escalaX, yDeValor)} fill="none" stroke={COLOR_BUYHOLD} strokeWidth={1.5} strokeDasharray="4 3" />
      <path d={trazoDeSerie(est, escalaX, yDeValor)} fill="none" stroke={COLOR_ESTRATEGIA} strokeWidth={2} />
      {hoverIndex != null && escalaX.visible(hoverIndex) && (
        <line x1={escalaX.xDeIndice(hoverIndex)} x2={escalaX.xDeIndice(hoverIndex)} y1={0} y2={alto} stroke={COLOR_EJE} strokeOpacity={0.5} />
      )}
    </svg>
  )
}
