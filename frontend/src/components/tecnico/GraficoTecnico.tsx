import { useRef } from 'react'
import type { BarraOut, OperacionesGraficoOut, SenalOut } from '../../api'
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
import { BotonesGrafico, PieGrafico } from './ControlesGrafico'
import { formatoValor } from './formatoEjes'
import GuiaGestos, { AVISO_SIN_RECORRIDO, AvisoGrafico, useAvisoGrafico, useGuiaGestos } from './GuiaGestos'
import { ESPEC_POR_TIPO, claveIndicador, colorIndicador, type IndicadorActivo } from './indicadoresConfig'

/** Orquesta precio + paneles de osciladores + volumen sobre una escala X compartida
 * (`useEscalaX`), con el ancho medido del contenedor (`useAnchoContenedor`). El hover/crosshair
 * vive en el padre (`AnalisisTecnico`/`GraficoFullscreen`) para que sobreviva el toggle de
 * pantalla completa sin reiniciar estado. */
export default function GraficoTecnico({
  barras, indicadores, activos, tieneVelas, tieneVolumen, senales, primeraBarraEvaluable,
  moneda, fullscreen, onToggleFullscreen, zonas, editandoZonas, onArrastrarZona, edicionZonas,
  misOperaciones, operacionesActivas, onToggleOperaciones, hoverIndex, onHover,
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

  const alto = useAltosGrafico(!!fullscreen, {
    osciladores: panelesOsciladores.length, equity: false, volumen: tieneVolumen,
  })

  return (
    <div ref={containerRef} className="w-full">
      <FichaBarra
        barras={barras} indice={hoverIndex} moneda={moneda} onQuitar={() => onHover(null)}
        misOperaciones={misOperaciones}
        acciones={
          <BotonesGrafico
            controles={controles} fullscreen={fullscreen} onToggleFullscreen={onToggleFullscreen}
            operaciones={onToggleOperaciones ? { activo: !!operacionesActivas, onToggle: onToggleOperaciones } : undefined}
          />
        }
      />

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
          misOperaciones={misOperaciones}
          hoverIndex={hoverIndex} onHover={onHover}
        />
        <EjeFechas barras={barras} escalaX={escalaX} />

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

      <PieGrafico
        barras={barras} escalaX={escalaX} completa={controles.completa}
        conCruz={hoverIndex != null} onAyuda={guia.mostrar}
      />
    </div>
  )
}
