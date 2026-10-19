import { useRef } from 'react'
import type {
  BarraOut, BenchmarkFR, FuerzaRelativaOut, IntervaloSerie, NivelAutoOut, OperacionesGraficoOut, SenalOut,
} from '../../api'
import Segmented from '../ui/Segmented'
import { useEscalaX } from './useEscalaX'
import { estiloContenedorGestos, useVentanaVisible } from './useVentanaVisible'
import { useAnchoContenedor } from './useAnchoContenedor'
import { useAltosGrafico } from './useAltosGrafico'
import PanelPrecio, { salidasGraficables, type OverlayPrecio } from './PanelPrecio'
import type { BordeZona, ZonasDibujo } from './ZonasPrecio'
import type { TipoZona } from '../../api'
import PanelIndicador from './PanelIndicador'
import PanelVolumen from './PanelVolumen'
import EjeFechas from './EjeFechas'
import FichaBarra from './FichaBarra'
import { BarraHerramientas, BotonesGrafico, PieGrafico, type Herramienta } from './ControlesGrafico'
import { formatoValor } from './formatoEjes'
import GuiaGestos, { AVISO_SIN_RECORRIDO, AvisoGrafico, useAvisoGrafico, useGuiaGestos } from './GuiaGestos'
import { ESPEC_POR_TIPO, claveIndicador, colorIndicador, type IndicadorActivo } from './indicadoresConfig'

/** Estado del panel de fuerza relativa, que vive en la pantalla (la consulta se hace allá). */
export interface ControlFuerzaRelativa {
  activa: boolean
  onToggle: () => void
  benchmark: BenchmarkFR | null
  onBenchmark: (b: BenchmarkFR) => void
  datos?: FuerzaRelativaOut
  cargando: boolean
  error: boolean
}

const OPCIONES_BENCHMARK: { value: BenchmarkFR; label: string }[] = [
  { value: 'SPY', label: 'S&P 500' }, { value: 'QQQ', label: 'Nasdaq' }, { value: '^MERV', label: 'Merval' },
]

const TEXTO_ADVERTENCIA_FR: Record<string, string> = {
  sin_benchmark: 'No se pudo obtener el índice (sin conexión a Yahoo, o todavía sin datos). Probá de nuevo en un rato.',
  benchmark_incompleto: 'Al índice le faltan datos en parte del período: la línea tiene huecos.',
}

/** Orquesta precio + paneles de osciladores + volumen sobre una escala X compartida
 * (`useEscalaX`), con el ancho medido del contenedor (`useAnchoContenedor`). El hover/crosshair
 * vive en el padre (`AnalisisTecnico`/`GraficoFullscreen`) para que sobreviva el toggle de
 * pantalla completa sin reiniciar estado. */
export default function GraficoTecnico({
  barras, indicadores, activos, tieneVelas, tieneVolumen, senales, primeraBarraEvaluable,
  moneda, fullscreen, onToggleFullscreen, zonas, editandoZonas, onArrastrarZona, edicionZonas,
  misOperaciones, operacionesActivas, onToggleOperaciones, intervalo = 'D', escalaLog, onToggleEscalaLog, nivelesAuto, nivelesActivos, onToggleNiveles, fuerzaRelativa,
  hoverIndex, onHover,
}: {
  barras: BarraOut[]
  indicadores: Record<string, Record<string, (number | null)[]>>
  activos: IndicadorActivo[]
  tieneVelas: boolean
  tieneVolumen: boolean
  senales?: SenalOut[]
  primeraBarraEvaluable?: number | null
  moneda?: string
  fullscreen?: boolean
  onToggleFullscreen?: () => void
  /** Zonas de compra/venta y niveles de la posición, a dibujar sobre el precio. */
  zonas?: ZonasDibujo
  editandoZonas?: boolean
  onArrastrarZona?: (tipo: TipoZona, borde: BordeZona, valor: number) => void
  /** Guardar/cancelar la edición desde el propio gráfico: en el celular el editor queda abajo,
   * fuera de la pantalla, y en pantalla completa no está. */
  edicionZonas?: { onGuardar: () => void; onCancelar: () => void; guardando?: boolean; problema?: string | null }
  /** Compras y ventas propias a dibujar; `null`/`undefined` = apagado. */
  misOperaciones?: OperacionesGraficoOut | null
  /** El interruptor está prendido (aunque los datos todavía estén cargando). */
  operacionesActivas?: boolean
  /** Si viene, el gráfico ofrece el botón que prende y apaga `misOperaciones`. */
  onToggleOperaciones?: () => void
  /** Qué es cada barra: diaria, semanal o mensual. */
  intervalo?: IntervaloSerie
  /** Escala logarítmica en el panel de precio; si viene `onToggleEscalaLog`, el gráfico ofrece el botón. */
  escalaLog?: boolean
  onToggleEscalaLog?: () => void
  /** Soportes y resistencias automáticos a dibujar; con `onToggleNiveles` el gráfico ofrece el botón. */
  nivelesAuto?: NivelAutoOut[] | null
  nivelesActivos?: boolean
  onToggleNiveles?: () => void
  /** Panel de fuerza relativa contra un índice; sin esta prop el botón no existe. */
  fuerzaRelativa?: ControlFuerzaRelativa
  hoverIndex: number | null
  onHover: (i: number | null) => void
}) {
  const [containerRef, ancho] = useAnchoContenedor<HTMLDivElement>(280)
  const gestosRef = useRef<HTMLDivElement>(null)
  const guia = useGuiaGestos()
  const aviso = useAvisoGrafico()
  // Gestos (desplazar, pellizcar, rueda, doble toque/clic) sobre la serie que ya está en pantalla:
  // el selector de período recarga la serie del backend, esto navega la que ya está.
  // Editando zonas el gráfico sigue navegable: las manijas se marcan como gesto propio y el hook no
  // las toma (ver `ZonasPrecio`).
  const controles = useVentanaVisible(barras.length, ancho, gestosRef, {
    activo: true,
    // Tocar la vela que ya tiene la cruz la quita: en el celular no hay "sacar el mouse".
    onToque: i => onHover(hoverIndex === i ? null : i),
    onCruz: onHover,
    serie: barras,
    onCambioSerie: () => onHover(null),
    onSinRecorrido: () => aviso.avisar(AVISO_SIN_RECORRIDO),
  })
  const escalaX = useEscalaX(barras.length, ancho, controles.ventana)

  const overlaysPrecio: OverlayPrecio[] = []
  const overlaysVolumen: { clave: string; color: string; series: Record<string, (number | null)[]> }[] = []
  const panelesOsciladores: { tipo: string; clave: string; series: Record<string, (number | null)[]> }[] = []

  // Dos instancias con los mismos parámetros (SMA(50) dos veces) piden la misma serie: se dibuja
  // una sola, si no habría paths con la misma key encimados.
  const clavesDibujadas = new Set<string>()
  for (const a of activos) {
    const espec = ESPEC_POR_TIPO[a.tipo]
    if (!espec) continue
    const clave = claveIndicador(a.tipo, a.params)
    const series = indicadores[clave]
    if (!series || clavesDibujadas.has(clave)) continue
    clavesDibujadas.add(clave)
    const color = colorIndicador(activos, a)
    if (espec.destino === 'precio') overlaysPrecio.push({ clave, tipo: a.tipo, color, series })
    else if (espec.destino === 'volumen') overlaysVolumen.push({ clave, color, series })
    else panelesOsciladores.push({ tipo: a.tipo, clave, series })
  }
  // La leyenda lleva el valor de cada overlay en la vela de la cruz (o la última): con dos medias
  // del mismo tipo el color es lo único que las distingue, y el número es lo que no se ve a ojo.
  const indiceLeyenda = hoverIndex ?? barras.length - 1
  const leyenda = [
    ...overlaysPrecio.map(o => ({ clave: o.clave, color: o.color, valores: salidasGraficables(o).map(([, s]) => s[indiceLeyenda]) })),
    ...overlaysVolumen.map(o => ({ clave: o.clave, color: o.color, valores: Object.values(o.series).map(s => s[indiceLeyenda]) })),
  ]

  // La fuerza relativa llega con su propia lista de fechas (sólo las barras visibles): se alinea al
  // gráfico por fecha. Las barras de calentamiento anteriores quedan sin valor.
  const fr = fuerzaRelativa?.activa ? fuerzaRelativa.datos : undefined
  const seriesFR = fr
    ? (() => {
        const indice = new Map(fr.fechas.map((f, i) => [f.slice(0, 10), i]))
        const alinear = (v: (number | null)[]) => barras.map(b => {
          const i = indice.get(b.fecha.slice(0, 10))
          return i == null ? null : v[i]
        })
        return { ratio: alinear(fr.ratio), sma: alinear(fr.sma) }
      })()
    : undefined
  const advertenciasFR = [
    ...(fr?.advertencias ?? []).filter(a => a in TEXTO_ADVERTENCIA_FR).map(a => TEXTO_ADVERTENCIA_FR[a]),
    ...(fr?.advertencias.includes('moneda_distinta')
      ? [`La serie está en ${fr.moneda} y el índice en ${fr.benchmark_moneda}: la comparación incluye el efecto del tipo de cambio.`]
      : []),
  ]

  const herramientas: Herramienta[] = []
  if (onToggleOperaciones) {
    herramientas.push({
      clave: 'operaciones', texto: '▲▼', activo: !!operacionesActivas, onToggle: onToggleOperaciones,
      label: operacionesActivas ? 'Ocultar mis compras y ventas' : 'Mostrar mis compras y ventas',
    })
  }
  if (onToggleEscalaLog) {
    herramientas.push({
      clave: 'log', texto: 'log', activo: !!escalaLog, onToggle: onToggleEscalaLog,
      label: escalaLog ? 'Volver a la escala lineal' : 'Escala logarítmica',
    })
  }
  if (onToggleNiveles) {
    herramientas.push({
      clave: 'niveles', texto: 'S/R', activo: !!nivelesActivos, onToggle: onToggleNiveles,
      label: nivelesActivos ? 'Ocultar soportes y resistencias' : 'Mostrar soportes y resistencias automáticos',
    })
  }
  if (fuerzaRelativa) {
    herramientas.push({
      clave: 'fuerza-relativa', texto: 'Fuerza rel.', activo: fuerzaRelativa.activa, onToggle: fuerzaRelativa.onToggle,
      label: fuerzaRelativa.activa ? 'Ocultar la fuerza relativa' : 'Mostrar la fuerza relativa contra un índice',
    })
  }

  const alto = useAltosGrafico(!!fullscreen, {
    osciladores: panelesOsciladores.length, equity: false, volumen: tieneVolumen,
  })

  return (
    <div ref={containerRef} className="w-full">
      <FichaBarra
        barras={barras} indice={hoverIndex} moneda={moneda} onQuitar={() => onHover(null)}
        misOperaciones={misOperaciones} intervalo={intervalo}
        acciones={<BotonesGrafico controles={controles} fullscreen={fullscreen} onToggleFullscreen={onToggleFullscreen} />}
      />

      <BarraHerramientas herramientas={herramientas}>
        {fuerzaRelativa?.activa && (
          <Segmented
            options={OPCIONES_BENCHMARK}
            value={fuerzaRelativa.benchmark ?? fuerzaRelativa.datos?.benchmark ?? 'SPY'}
            onChange={fuerzaRelativa.onBenchmark}
          />
        )}
      </BarraHerramientas>

      {leyenda.length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 mb-1 text-label text-app-text-dim font-mono tabular-nums">
          {leyenda.map(o => (
            <span key={o.clave} className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full shrink-0" style={{ background: o.color }} />
              {o.clave}
              <span style={{ color: o.color }}>{o.valores.map(v => formatoValor(v)).join(' / ')}</span>
            </span>
          ))}
        </div>
      )}

      {editandoZonas && edicionZonas && (
        <div className="mb-1.5 flex items-center gap-2 rounded-xl bg-app-accent-soft px-2.5 py-1.5">
          <span className={`min-w-0 flex-1 text-label ${edicionZonas.problema ? 'text-app-neg' : 'text-app-text-dim'}`}>
            {edicionZonas.problema ?? 'Arrastrá las manijas ↕ para mover los bordes.'}
          </span>
          <button
            type="button" onClick={edicionZonas.onCancelar}
            className="shrink-0 h-9 px-3 rounded-lg text-caption font-semibold text-app-text-dim"
          >
            Cancelar
          </button>
          <button
            type="button" onClick={edicionZonas.onGuardar}
            disabled={!!edicionZonas.problema || edicionZonas.guardando}
            className="shrink-0 h-9 px-3 rounded-lg bg-app-accent text-caption font-semibold text-white disabled:opacity-40"
          >
            {edicionZonas.guardando ? 'Guardando…' : 'Guardar'}
          </button>
        </div>
      )}

      <div className="relative">
      {guia.visible && <GuiaGestos onCerrar={guia.cerrar} conZonas={editandoZonas} />}
      <AvisoGrafico texto={aviso.texto} />
      <div
        ref={gestosRef}
        className={controles.arrastrando ? 'cursor-grabbing' : 'cursor-grab'}
        style={estiloContenedorGestos()}
      >
        <PanelPrecio
          barras={barras} escalaX={escalaX} alto={alto.precio} tieneVelas={tieneVelas} moneda={moneda}
          overlays={overlaysPrecio} senales={senales} primeraBarraEvaluable={primeraBarraEvaluable}
          zonas={zonas} editandoZonas={editandoZonas} onArrastrarZona={onArrastrarZona}
          misOperaciones={misOperaciones} escalaLog={escalaLog} nivelesAuto={nivelesActivos ? nivelesAuto : null}
          hoverIndex={hoverIndex} onHover={onHover}
        />
        <EjeFechas barras={barras} escalaX={escalaX} />

        {fuerzaRelativa?.activa && (
          <div className="mt-1.5">
            {seriesFR && fr ? (
              <PanelIndicador
                tipo="FUERZA_RELATIVA" clave={`Fuerza relativa vs ${fr.benchmark_nombre}`} series={seriesFR}
                escalaX={escalaX} alto={alto.oscilador} hoverIndex={hoverIndex} onHover={onHover}
              />
            ) : (
              <p className="text-label text-app-text-dim py-2">
                {fuerzaRelativa.error
                  ? 'No se pudo calcular la fuerza relativa.'
                  : fuerzaRelativa.cargando ? 'Calculando la fuerza relativa (la primera vez baja el índice)…' : ''}
              </p>
            )}
          </div>
        )}

        {panelesOsciladores.map(p => (
          <div key={p.clave} className="mt-1.5">
            <PanelIndicador
              tipo={p.tipo} clave={p.clave} series={p.series} escalaX={escalaX}
              alto={alto.oscilador} hoverIndex={hoverIndex} onHover={onHover}
            />
          </div>
        ))}

        {tieneVolumen && (
          <div className="mt-1.5">
            <PanelVolumen
              barras={barras} overlays={overlaysVolumen} escalaX={escalaX}
              alto={alto.volumen} hoverIndex={hoverIndex} onHover={onHover}
            />
          </div>
        )}
      </div>
      </div>

      {advertenciasFR.map(t => <p key={t} className="mt-1 text-label text-app-text-dim">{t}</p>)}

      <PieGrafico
        barras={barras} escalaX={escalaX} completa={controles.completa}
        conCruz={hoverIndex != null} unidad={intervalo === 'S' ? 'semanas' : intervalo === 'M' ? 'meses' : 'ruedas'}
        onAyuda={guia.mostrar}
      />
    </div>
  )
}
