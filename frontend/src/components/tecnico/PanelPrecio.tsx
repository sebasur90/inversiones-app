import { useMemo, useRef, useState } from 'react'
import type { MutableRefObject, PointerEvent as ReactPointerEvent } from 'react'
import type { BarraOut, NivelAutoOut, OperacionOut, OperacionesGraficoOut, SenalOut } from '../../api'
import type { EscalaX } from './useEscalaX'
import { manejadoresPuntero } from './crosshair'
import { trazoDeSerie, valoresVisibles } from './trazo'
import { formatoPrecio } from './formatoEjes'
import { COLOR_MOTIVO, GLIFO_MOTIVO } from './motivosSalida'
import ZonasPrecio, { valoresDeZonas, type BordeZona, type ZonasDibujo } from './ZonasPrecio'
import type { TipoZona } from '../../api'
import DibujosGrafico from './DibujosGrafico'
import { dibujoEnPunto } from './dibujosGrafico'
import type { ControlDibujos } from './useDibujos'
import { BandasCiclos, MarcasIngresos, MarcasOperaciones } from './OperacionesPropias'
import { ubicarOperaciones } from './operacionesPropias'

export interface OverlayPrecio {
  clave: string
  tipo: string
  color: string
  series: Record<string, (number | null)[]>
}

/** Nivel al que el screener calculó que una estrategia dispara, para marcarlo sobre el precio de
 * la última barra. `precioActual`/`distanciaPct` vienen de la misma fila del screener (no se
 * re-derivan del backtest, que puede correr sobre una ventana distinta): ver `DetalleDisparo`. */
export interface GatilloPrecio {
  precio: number
  precioActual: number
  distanciaPct: number
  tipo: 'compra' | 'venta'
  motivo: string
}

const COLOR_ALCISTA = '#10b981'
const COLOR_BAJISTA = '#ef4444'
const COLOR_PRECIO = '#3b82f6'
const COLOR_GRID = '#1c1f2a'
const COLOR_EJE = '#94a3b8'
const COLOR_STOP = '#ef4444'
const COLOR_TAKE = '#10b981'
const COLOR_TRAILING = '#fbbf24'
const COLOR_GATILLO_COMPRA = '#10b981'
const COLOR_GATILLO_VENTA = '#ef4444'
const COLOR_CRUZ = '#475569'
const COLOR_RESISTENCIA = '#fb923c'
const COLOR_SOPORTE = '#a3e635'
/** Halo detrás de las etiquetas del eje: se leen aunque pase una vela o una media por debajo. */
const COLOR_HALO = '#121621'
/** Con velas más angostas que esto, el cuerpo y la mecha se confunden en una mancha: se dibuja la
 * línea de cierres hasta que el zoom las vuelva legibles. */
const PASO_MINIMO_VELAS = 2
const FRACCIONES_GRILLA = [0.25, 0.5, 0.75]

/** Salidas de un indicador de precio que NO están en la escala del precio (p.ej. Bollinger trae
 * `ancho_pct`/`pctb`, que son porcentajes u oscilan 0-1, junto con `media`/`superior`/`inferior`
 * que sí son precios): se excluyen acá para que no aplasten la escala de las velas. */
const SALIDAS_EXCLUIDAS_PRECIO: Record<string, string[]> = {
  BOLLINGER: ['ancho_pct', 'pctb'],
  // `dist_max_pct` (~0 a ~-40) y `dist_min_pct` (~0 a ~+80) son porcentajes: en la escala de las
  // velas aplastarían el precio contra el borde. `maximo`/`minimo`/`medio` sí son precios.
  EXTREMOS: ['dist_max_pct', 'dist_min_pct'],
  // `direccion` es +1 / −1: no es un precio. Sólo sirve para pintar la línea de verde o de rojo.
  SUPERTREND: ['direccion'],
}
export function salidasGraficables(o: OverlayPrecio): [string, (number | null)[]][] {
  const excluidas = SALIDAS_EXCLUIDAS_PRECIO[o.tipo] ?? []
  return Object.entries(o.series).filter(([salida]) => !excluidas.includes(salida))
}

/** Precio (velas o línea de cierres) + overlays de indicadores (SMA/EMA/Bollinger) + señales de
 * estrategia + niveles de riesgo de cada operación, sobre la escala X compartida del gráfico.
 *
 * Los niveles (`operaciones[].nivel_stop_loss`, `nivel_take_profit`, `trailing`) los calcula el
 * motor de backtest y viajan en la respuesta: dibujarlos re-derivándolos acá daría una línea que
 * no es la que efectivamente disparó la salida. */
export default function PanelPrecio({
  barras, escalaX, alto, tieneVelas, overlays, senales, operaciones, primeraBarraEvaluable, moneda, gatillo, zonas, editandoZonas, onArrastrarZona, misOperaciones, escalaLog, nivelesAuto, dibujos, toqueRef, hoverIndex, onHover,
}: {
  barras: BarraOut[]
  escalaX: EscalaX
  alto: number
  tieneVelas: boolean
  overlays: OverlayPrecio[]
  senales?: SenalOut[]
  operaciones?: OperacionOut[]
  primeraBarraEvaluable?: number | null
  moneda?: string
  /** Nivel de disparo del screener a marcar sobre la última barra (ver `GatilloPrecio`). */
  gatillo?: GatilloPrecio
  /** Zonas de compra/venta y niveles de la posición (ver `ZonasPrecio`). */
  zonas?: ZonasDibujo
  editandoZonas?: boolean
  onArrastrarZona?: (tipo: TipoZona, borde: BordeZona, valor: number) => void
  /** Compras y ventas que el usuario ya hizo (ver `OperacionesPropias`). `undefined` = apagado. */
  misOperaciones?: OperacionesGraficoOut | null
  /** Escala logarítmica en el eje de precio (los osciladores quedan lineales). */
  escalaLog?: boolean
  /** Soportes y resistencias automáticos. No entran en la escala Y: como una zona lejana, un nivel
   * fuera del tramo que se mira simplemente no se ve. */
  nivelesAuto?: NivelAutoOut[] | null
  /** Dibujos manuales y la herramienta en uso (ver `useDibujos`). */
  dibujos?: ControlDibujos
  /** Acá se deja el manejador de toques del panel: el gráfico lo llama (con el índice de barra y la
   * `y` del toque) y devuelve si el toque fue de un dibujo, para que no mueva también la cruz. */
  toqueRef?: MutableRefObject<((indice: number, y: number) => boolean) | null>
  hoverIndex: number | null
  onHover: (i: number | null) => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const handlers = manejadoresPuntero(svgRef, escalaX, onHover)
  /** Escala Y congelada mientras se arrastra el borde de una zona. Si se recalculara, mover el
   * borde que define el máximo cambiaría la escala bajo el dedo y la línea se escaparía. */
  const [vistaPrevia, setVistaPrevia] = useState<{ x: number; y: number } | null>(null)
  const [dominioCongelado, setDominioCongelado] = useState<[number, number] | null>(null)
  const dibujarVelas = tieneVelas && escalaX.pasoX >= PASO_MINIMO_VELAS
  const ubicadas = useMemo(
    () => (misOperaciones ? ubicarOperaciones(barras, misOperaciones) : null),
    [barras, misOperaciones],
  )

  const cierres = barras.map(b => b.cierre)
  const valoresBase = dibujarVelas
    ? [
        ...valoresVisibles(barras.map(b => b.maximo ?? b.cierre), escalaX),
        ...valoresVisibles(barras.map(b => b.minimo ?? b.cierre), escalaX),
      ]
    : valoresVisibles(cierres, escalaX)
  const valoresOverlay = overlays.flatMap(o => salidasGraficables(o).flatMap(([, s]) => valoresVisibles(s, escalaX)))
  const valoresSenales = (senales ?? []).filter(s => escalaX.visible(s.indice)).map(s => s.precio)
  const ultimaBarraVisible = escalaX.visible(barras.length - 1)
  const valoresGatillo = gatillo && ultimaBarraVisible ? [gatillo.precio, gatillo.precioActual] : []
  // Las zonas se dibujan siempre, pero no siempre entran en la escala Y. Con la última barra a la
  // vista (o editando: no se puede arrastrar lo que no se ve) entran todas. Con zoom sobre un tramo
  // viejo, sólo las que caen cerca del precio de ese tramo: una zona a 40 % de distancia aplastaría
  // las velas contra el borde. Las que quedan afuera se señalan con una flecha en el borde del
  // panel (`ZonasPrecio`), así no desaparecen al hacer zoom.
  // Las marcas propias quedan dentro de su vela (el backend las recorta al rango), así que entran en
  // la escala sin aplastarla. La línea de costo de una posición que empezó antes del tramo visible
  // no entra: podría estar lejos del precio de este tramo.
  const valoresOperaciones = ubicadas
    ? [
        ...ubicadas.marcas.filter(m => escalaX.visible(m.indice)).map(m => m.op.precio_grafico as number),
        ...ubicadas.ciclos
          .filter(c => c.ciclo.abierto && c.ciclo.costo_promedio_grafico != null && !c.empiezaAntes && escalaX.visible(c.desde))
          .map(c => c.ciclo.costo_promedio_grafico as number),
      ]
    : []
  const sinZonas = [...valoresBase, ...valoresOverlay, ...valoresSenales, ...valoresGatillo, ...valoresOperaciones]
  const minSin = sinZonas.length ? Math.min(...sinZonas) : 0
  const maxSin = sinZonas.length ? Math.max(...sinZonas) : 1
  const margenZonas = (maxSin - minSin) * 0.5
  const valoresZonas = valoresDeZonas(zonas).filter(v =>
    editandoZonas || ultimaBarraVisible || (v >= minSin - margenZonas && v <= maxSin + margenZonas))
  const todos = [...sinZonas, ...valoresZonas]
  // En escala log el dominio y el margen se calculan sobre log(valor), descartando los valores ≤ 0
  // (no tienen logaritmo). Sin ningún valor positivo se cae a la escala lineal.
  const usarLog = !!escalaLog && todos.some(v => v > 0)
  const aEscala = (v: number) => (usarLog ? Math.log(v) : v)
  const deEscala = (t: number) => (usarLog ? Math.exp(t) : t)
  const enEscala = usarLog ? todos.filter(v => v > 0).map(aEscala) : todos
  const minV = enEscala.length ? Math.min(...enEscala) : 0
  const maxV = enEscala.length ? Math.max(...enEscala) : 1
  const pad = (maxV - minV) * 0.08 || Math.abs(maxV) * 0.05 || 1
  const [y0, y1] = dominioCongelado ?? [minV - pad, maxV + pad]
  const yDeValor = (v: number) => (usarLog && !(v > 0) ? alto : alto - ((aEscala(v) - y0) / (y1 - y0 || 1)) * alto)
  /** Inversa de `yDeValor`: la usa el arrastre de los bordes de zona. */
  const valorDeY = (y: number) => deEscala(y0 + ((alto - y) / (alto || 1)) * (y1 - y0))

  // Toques sobre el panel (celular) y clics (mouse): con una herramienta elegida ponen el punto del
  // dibujo; sin herramienta, seleccionan el dibujo bajo el dedo, si lo hay.
  if (toqueRef) {
    toqueRef.current = (indice, y) => {
      if (!dibujos || y < 0 || y > alto) return false
      if (dibujos.herramienta) {
        const barra = barras[indice]
        if (barra) dibujos.tocarPunto({ fecha: barra.fecha.slice(0, 10), precio: Number(valorDeY(y).toPrecision(8)) })
        return true
      }
      const tocado = dibujoEnPunto(dibujos.lista, escalaX.xDeIndice(indice), y, barras, escalaX, yDeValor)
      dibujos.seleccionar(tocado ? tocado.id : null)
      return tocado != null
    }
  }
  // Dónde está el mouse mientras falta el segundo punto de un dibujo: para la línea de vista previa.
  const alMoverMouse = (e: ReactPointerEvent<SVGSVGElement>) => {
    handlers.onPointerMove(e)
    if (!dibujos?.primerPunto || e.pointerType !== 'mouse') return
    const rect = svgRef.current?.getBoundingClientRect()
    if (rect) setVistaPrevia({ x: e.clientX - rect.left, y: e.clientY - rect.top })
  }
  const alSalirMouse = (e: ReactPointerEvent<SVGSVGElement>) => {
    handlers.onPointerLeave(e)
    setVistaPrevia(null)
  }

  const anchoVela = Math.max(1, escalaX.pasoX * 0.62)
  const ultimoIndice = barras.length - 1
  const visibles: number[] = []
  for (let i = Math.max(0, escalaX.inicio); i <= Math.min(ultimoIndice, escalaX.fin); i++) visibles.push(i)

  /** Los niveles de riesgo se recortan al tramo de su operación, no a toda la serie: una línea de
   * stop loss extendida más allá de la salida sugeriría una protección que ya no existía. */
  const tramo = (o: OperacionOut) => {
    const desde = o.indice_entrada
    const hasta = o.indice_salida ?? ultimoIndice
    return { desde, hasta, x1: escalaX.xDeIndice(desde), x2: escalaX.xDeIndice(hasta) }
  }
  const opsVisibles = (operaciones ?? []).filter(o => {
    const { desde, hasta } = tramo(o)
    return hasta >= escalaX.inicio && desde <= escalaX.fin
  })

  // Eje de precio: el último cierre (con su color según la rueda) y, con la cruz puesta, el cierre
  // de esa vela. Las etiquetas de la grilla que quedarían debajo de alguna de las dos se omiten.
  const ultima = barras[ultimoIndice]
  const yUltimo = ultima ? yDeValor(ultima.cierre) : null
  const ultimoEnRango = yUltimo != null && yUltimo >= 6 && yUltimo <= alto - 6
  const colorUltimo = ultima && ultima.cierre >= (barras[ultimoIndice - 1]?.cierre ?? ultima.cierre) ? COLOR_ALCISTA : COLOR_BAJISTA
  const barraCruz = hoverIndex != null && escalaX.visible(hoverIndex) ? barras[hoverIndex] : undefined
  const yCruz = barraCruz ? yDeValor(barraCruz.cierre) : null
  const ocupadas = [ultimoEnRango ? yUltimo : null, yCruz].filter((y): y is number => y != null)
  const etiquetasGrilla = FRACCIONES_GRILLA
    .map(f => ({ y: alto * f, valor: valorDeY(alto * f) }))
    .filter(e => ocupadas.every(y => Math.abs(y - e.y) > 13))

  return (
    <svg ref={svgRef} width={escalaX.ancho} height={alto} className="block select-none" onPointerMove={alMoverMouse} onPointerLeave={alSalirMouse}>
      {primeraBarraEvaluable != null && primeraBarraEvaluable > 0 && escalaX.inicio < primeraBarraEvaluable && (
        <rect
          x={0} y={0}
          width={Math.max(0, escalaX.xDeIndice(primeraBarraEvaluable) - escalaX.pasoX / 2)}
          height={alto} fill="#000" fillOpacity={0.22}
        />
      )}

      {FRACCIONES_GRILLA.map(f => (
        <line key={f} x1={0} x2={escalaX.ancho} y1={alto * f} y2={alto * f} stroke={COLOR_GRID} strokeDasharray="3 3" />
      ))}

      {/* Banda tenue mientras la estrategia estuvo comprada. */}
      {opsVisibles.map((o, i) => {
        const { x1, x2 } = tramo(o)
        return (
          <rect
            key={`pos-${i}`} x={x1} y={0} width={Math.max(1, x2 - x1)} height={alto}
            fill={COLOR_ALCISTA} fillOpacity={0.06}
          />
        )
      })}

      {ubicadas && <BandasCiclos ubicadas={ubicadas} escalaX={escalaX} alto={alto} />}

      {moneda && (
        <text x={4} y={12} fontSize={10} fill={COLOR_EJE} fillOpacity={0.85} className="font-mono">
          {moneda}
        </text>
      )}

      {dibujarVelas ? (
        visibles.map(i => {
          const b = barras[i]
          const alcista = b.cierre >= (b.apertura ?? b.cierre)
          const color = alcista ? COLOR_ALCISTA : COLOR_BAJISTA
          const x = escalaX.xDeIndice(i)
          const yAlto = yDeValor(b.maximo ?? b.cierre)
          const yBajo = yDeValor(b.minimo ?? b.cierre)
          const yApertura = yDeValor(b.apertura ?? b.cierre)
          const yCierre = yDeValor(b.cierre)
          const yTop = Math.min(yApertura, yCierre)
          const yBottom = Math.max(yApertura, yCierre)
          return (
            <g key={i}>
              <line x1={x} x2={x} y1={yAlto} y2={yBajo} stroke={color} strokeWidth={1} />
              <rect x={x - anchoVela / 2} y={yTop} width={anchoVela} height={Math.max(1, yBottom - yTop)} fill={color} />
            </g>
          )
        })
      ) : (
        <path d={trazoDeSerie(cierres, escalaX, yDeValor)} fill="none" stroke={COLOR_PRECIO} strokeWidth={1.75} />
      )}

      {overlays.filter(o => o.tipo === 'ICHIMOKU').map(o => {
        const nube = trazoNube(o.series.senkou_a, o.series.senkou_b, escalaX, yDeValor)
        return (
          <g key={`nube-${o.clave}`} pointerEvents="none">
            {nube.alcista && <path d={nube.alcista} fill={COLOR_ALCISTA} fillOpacity={0.14} />}
            {nube.bajista && <path d={nube.bajista} fill={COLOR_BAJISTA} fillOpacity={0.14} />}
          </g>
        )
      })}

      {overlays.filter(o => o.tipo === 'SUPERTREND').map(o => {
        const valor = o.series.valor ?? []
        const direccion = o.series.direccion ?? []
        const subiendo = valor.map((v, i) => (direccion[i] === 1 ? v : null))
        const bajando = valor.map((v, i) => (direccion[i] === -1 ? v : null))
        return (
          <g key={o.clave} pointerEvents="none">
            <path d={trazoDeSerie(subiendo, escalaX, yDeValor)} fill="none" stroke={COLOR_ALCISTA} strokeWidth={1.75} />
            <path d={trazoDeSerie(bajando, escalaX, yDeValor)} fill="none" stroke={COLOR_BAJISTA} strokeWidth={1.75} />
          </g>
        )
      })}

      {overlays.filter(o => o.tipo !== 'SUPERTREND').map(o => salidasGraficables(o).map(([salida, vals]) => (
        <path
          key={`${o.clave}-${salida}`}
          d={trazoDeSerie(vals, escalaX, yDeValor)}
          fill="none"
          stroke={o.color}
          strokeWidth={salida === 'superior' || salida === 'inferior' || salida.startsWith('senkou') ? 1 : 1.5}
          strokeDasharray={salida === 'superior' || salida === 'inferior' || salida === 'kijun' ? '4 3' : undefined}
          opacity={salida === 'superior' || salida === 'inferior' ? 0.7 : salida.startsWith('senkou') ? 0.6 : 1}
        />
      )))}

      {zonas && (
        <ZonasPrecio
          zonas={zonas} ancho={escalaX.ancho} alto={alto}
          yDeValor={yDeValor} valorDeY={valorDeY} svgRef={svgRef}
          editando={editandoZonas} onArrastrar={onArrastrarZona}
          onArrastreActivo={activo => setDominioCongelado(activo ? [y0, y1] : null)}
        />
      )}

      {nivelesAuto && nivelesAuto.length > 0 && (
        <g pointerEvents="none">
          {nivelesAuto.map(n => {
            const y = yDeValor(n.precio)
            if (y < 0 || y > alto) return null
            const color = n.tipo === 'resistencia' ? COLOR_RESISTENCIA : COLOR_SOPORTE
            return (
              <g key={`${n.tipo}-${n.precio}`}>
                <line x1={0} x2={escalaX.ancho} y1={y} y2={y} stroke={color} strokeWidth={1} strokeDasharray="1 3" opacity={0.75}>
                  <title>{`${n.tipo === 'resistencia' ? 'Resistencia' : 'Soporte'} ${formatoPrecio(n.precio)}: ${n.toques} toques`}</title>
                </line>
                <text
                  x={4} y={y - 3} fontSize={9} fill={color} stroke={COLOR_HALO} strokeWidth={3} paintOrder="stroke"
                  className="font-mono font-bold"
                >
                  {`${n.tipo === 'resistencia' ? 'R' : 'S'} · ${n.toques} toques`}
                </text>
              </g>
            )
          })}
        </g>
      )}

      {dibujos && (
        <DibujosGrafico
          dibujos={dibujos.lista} barras={barras} escalaX={escalaX} yDeValor={yDeValor}
          seleccionado={dibujos.seleccionado} primerPunto={dibujos.primerPunto} vistaPrevia={vistaPrevia}
        />
      )}

      {ubicadas && <MarcasOperaciones ubicadas={ubicadas} escalaX={escalaX} alto={alto} yDeValor={yDeValor} />}
      {ubicadas && <MarcasIngresos ubicadas={ubicadas} escalaX={escalaX} alto={alto} />}

      {/* Niveles de riesgo por operación: stop loss y take profit son constantes; el trailing es
          una escalera que sólo sube. */}
      {opsVisibles.map((o, i) => {
        const { desde, hasta, x1, x2 } = tramo(o)
        const escalera = trazoEscalera(o.trailing ?? null, desde, hasta, escalaX, yDeValor)
        return (
          <g key={`riesgo-${i}`}>
            {o.nivel_stop_loss != null && (
              <line
                x1={x1} x2={x2} y1={yDeValor(o.nivel_stop_loss)} y2={yDeValor(o.nivel_stop_loss)}
                stroke={COLOR_STOP} strokeWidth={1} strokeDasharray="5 3" opacity={0.75}
              >
                <title>Stop loss: {o.nivel_stop_loss.toFixed(2)}</title>
              </line>
            )}
            {o.nivel_take_profit != null && (
              <line
                x1={x1} x2={x2} y1={yDeValor(o.nivel_take_profit)} y2={yDeValor(o.nivel_take_profit)}
                stroke={COLOR_TAKE} strokeWidth={1} strokeDasharray="5 3" opacity={0.75}
              >
                <title>Take profit: {o.nivel_take_profit.toFixed(2)}</title>
              </line>
            )}
            {escalera && (
              <path d={escalera} fill="none" stroke={COLOR_TRAILING} strokeWidth={1.25} strokeDasharray="2 2" opacity={0.9}>
                <title>Trailing stop</title>
              </path>
            )}
          </g>
        )
      })}

      {/* Nivel de gatillo del screener: línea horizontal en el precio que hace disparar la
          estrategia, conector desde el cierre de hoy y marcador del "hoy". Sólo si la última
          barra está en la ventana visible: con zoom sobre un tramo viejo, meterlo en el dominio Y
          aplastaría las velas contra el borde por un nivel que ni siquiera se ve. */}
      {gatillo && ultimaBarraVisible && (() => {
        const xHoy = escalaX.xDeIndice(ultimoIndice)
        const yGatillo = yDeValor(gatillo.precio)
        const yHoy = yDeValor(gatillo.precioActual)
        const colorGatillo = COLOR_MOTIVO[gatillo.motivo] ?? (gatillo.tipo === 'compra' ? COLOR_GATILLO_COMPRA : COLOR_GATILLO_VENTA)
        const etiqueta = `Gatillo ${gatillo.precio.toFixed(2)} (${gatillo.distanciaPct > 0 ? '+' : ''}${gatillo.distanciaPct.toFixed(1)}%)`
        return (
          <g>
            <line
              x1={0} x2={escalaX.ancho} y1={yGatillo} y2={yGatillo}
              stroke={colorGatillo} strokeWidth={1.5} strokeDasharray="6 3" opacity={0.9}
            >
              <title>{etiqueta}</title>
            </line>
            <text
              x={escalaX.ancho - 4} y={yGatillo - 4} fontSize={10} textAnchor="end"
              fill={colorGatillo} className="font-mono font-bold"
            >
              {etiqueta}
            </text>
            <line
              x1={xHoy} x2={xHoy} y1={yHoy} y2={yGatillo}
              stroke={colorGatillo} strokeWidth={1.25} opacity={0.7}
            />
            <circle cx={xHoy} cy={yHoy} r={3.5} fill={colorGatillo}>
              <title>{`Hoy: ${gatillo.precioActual.toFixed(2)}`}</title>
            </circle>
          </g>
        )
      })()}

      {(senales ?? []).filter(s => escalaX.visible(s.indice)).map((s, i) => {
        const x = escalaX.xDeIndice(s.indice)
        const compra = s.tipo === 'compra'
        const y = yDeValor(s.precio) + (compra ? 14 : -8)
        const glifo = compra ? '▲' : GLIFO_MOTIVO[s.motivo] ?? '▼'
        return (
          <text
            key={i} x={x} y={y} fontSize={glifo.length > 1 ? 9 : 12} textAnchor="middle"
            fill={compra ? COLOR_ALCISTA : COLOR_MOTIVO[s.motivo] ?? COLOR_BAJISTA}
            className={glifo.length > 1 ? 'font-mono font-bold' : undefined}
          >
            {glifo}
            <title>{`${s.fecha} · ${compra ? 'compra' : 'venta'} a ${s.precio.toFixed(2)}`}</title>
          </text>
        )
      })}

      {etiquetasGrilla.map(e => (
        <text
          key={e.y} x={escalaX.ancho - 3} y={e.y + 3} fontSize={9} textAnchor="end"
          fill={COLOR_EJE} fillOpacity={0.85} stroke={COLOR_HALO} strokeWidth={3} paintOrder="stroke"
          className="font-mono" pointerEvents="none"
        >
          {formatoPrecio(e.valor)}
        </text>
      ))}

      {ultima && ultimoEnRango && yUltimo != null && (
        <g pointerEvents="none">
          <line x1={0} x2={escalaX.ancho} y1={yUltimo} y2={yUltimo} stroke={colorUltimo} strokeOpacity={0.45} strokeDasharray="1 3" />
          <EtiquetaEje x={escalaX.ancho} y={yUltimo} texto={formatoPrecio(ultima.cierre)} fondo={colorUltimo} />
        </g>
      )}

      {hoverIndex != null && barras[hoverIndex] && escalaX.visible(hoverIndex) && (
        <line x1={escalaX.xDeIndice(hoverIndex)} x2={escalaX.xDeIndice(hoverIndex)} y1={0} y2={alto} stroke={COLOR_EJE} strokeOpacity={0.5} />
      )}
      {barraCruz && yCruz != null && (
        <g pointerEvents="none">
          <line x1={0} x2={escalaX.ancho} y1={yCruz} y2={yCruz} stroke={COLOR_EJE} strokeOpacity={0.35} strokeDasharray="3 3" />
          <EtiquetaEje x={escalaX.ancho} y={yCruz} texto={formatoPrecio(barraCruz.cierre)} fondo={COLOR_CRUZ} />
        </g>
      )}
    </svg>
  )
}

/** Valor sobre el borde derecho, en una cajita del color de la línea que rotula. */
function EtiquetaEje({ x, y, texto, fondo }: { x: number; y: number; texto: string; fondo: string }) {
  const ancho = texto.length * 5.6 + 8
  return (
    <g>
      <rect x={x - ancho} y={y - 7} width={ancho} height={14} rx={2} fill={fondo} />
      <text x={x - 4} y={y + 3} fontSize={9.5} textAnchor="end" fill="#fff" className="font-mono font-bold">
        {texto}
      </text>
    </g>
  )
}

/** Path en escalones del trailing stop: horizontal mientras el nivel no cambia, vertical cuando
 * sube. Dibujarlo como línea recta entre puntos daría la impresión de que el stop subía de a poco
 * durante la rueda, cuando en realidad salta de una barra a la otra. */
function trazoEscalera(
  niveles: number[] | null, desde: number, hasta: number, escalaX: EscalaX, yDeValor: (v: number) => number,
): string {
  if (!niveles || niveles.length === 0) return ''
  let d = ''
  for (let k = 0; k < niveles.length; k++) {
    const i = desde + k
    if (i > hasta || !escalaX.visible(i)) continue
    const x = escalaX.xDeIndice(i)
    const y = yDeValor(niveles[k])
    const medio = escalaX.pasoX / 2
    if (!d) {
      d = `M ${x - medio} ${y}`
    } else {
      d += ` L ${x - medio} ${y}`
    }
    d += ` L ${x + medio} ${y}`
  }
  return d
}

/** Relleno de la nube de Ichimoku: un cuadrilátero entre Senkou A y B por cada par de barras
 * consecutivas donde las dos existen. Verde cuando A queda sobre B (nube alcista), rojo cuando no.
 * Son dos paths en total, no un nodo por barra. */
function trazoNube(
  a: (number | null)[] | undefined, b: (number | null)[] | undefined, escalaX: EscalaX,
  yDeValor: (v: number) => number,
): { alcista: string; bajista: string } {
  let alcista = ''
  let bajista = ''
  if (!a || !b) return { alcista, bajista }
  const desde = Math.max(1, escalaX.inicio)
  const hasta = Math.min(a.length - 1, b.length - 1, escalaX.fin + 1)
  for (let i = desde; i <= hasta; i++) {
    const [a0, a1, b0, b1] = [a[i - 1], a[i], b[i - 1], b[i]]
    if (a0 == null || a1 == null || b0 == null || b1 == null) continue
    const x0 = escalaX.xDeIndice(i - 1)
    const x1 = escalaX.xDeIndice(i)
    const poligono = `M ${x0} ${yDeValor(a0)} L ${x1} ${yDeValor(a1)} L ${x1} ${yDeValor(b1)} L ${x0} ${yDeValor(b0)} Z `
    if (a0 + a1 >= b0 + b1) alcista += poligono
    else bajista += poligono
  }
  return { alcista, bajista }
}
