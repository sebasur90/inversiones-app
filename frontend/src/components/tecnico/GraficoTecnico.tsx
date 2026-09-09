import type { BarraOut, SenalOut } from '../../api'
import { useEscalaX } from './useEscalaX'
import { useVentanaVisible } from './useVentanaVisible'
import { useAnchoContenedor } from './useAnchoContenedor'
import PanelPrecio, { type OverlayPrecio } from './PanelPrecio'
import PanelIndicador from './PanelIndicador'
import PanelVolumen from './PanelVolumen'
import { ESPEC_POR_TIPO, claveIndicador } from './indicadoresConfig'
import { Icon } from '../icons/Icons'

/** Orquesta precio + paneles de osciladores + volumen sobre una escala X compartida
 * (`useEscalaX`), con el ancho medido del contenedor (`useAnchoContenedor`). El hover/crosshair
 * vive en el padre (`AnalisisTecnico`/`GraficoFullscreen`) para que sobreviva el toggle de
 * pantalla completa sin reiniciar estado. */
export default function GraficoTecnico({
  barras, indicadores, activos, tieneVelas, tieneVolumen, senales, primeraBarraEvaluable,
  moneda, fullscreen, onToggleFullscreen, hoverIndex, onHover,
}: {
  barras: BarraOut[]
  indicadores: Record<string, Record<string, (number | null)[]>>
  activos: Record<string, Record<string, number>>
  tieneVelas: boolean
  tieneVolumen: boolean
  senales?: SenalOut[]
  primeraBarraEvaluable?: number | null
  moneda?: string
  fullscreen?: boolean
  onToggleFullscreen?: () => void
  hoverIndex: number | null
  onHover: (i: number | null) => void
}) {
  const [containerRef, ancho] = useAnchoContenedor<HTMLDivElement>(280)
  // Zoom con la rueda, desplazamiento arrastrando y doble clic para volver a todo el período:
  // el selector de período recarga la serie del backend, esto navega la que ya está en pantalla.
  const controles = useVentanaVisible(barras.length, ancho)
  const escalaX = useEscalaX(barras.length, ancho, controles.ventana)

  const overlaysPrecio: OverlayPrecio[] = []
  const overlaysVolumen: { clave: string; color: string; series: Record<string, (number | null)[]> }[] = []
  const panelesOsciladores: { tipo: string; clave: string; series: Record<string, (number | null)[]> }[] = []

  for (const tipo of Object.keys(activos)) {
    const espec = ESPEC_POR_TIPO[tipo]
    if (!espec) continue
    const clave = claveIndicador(tipo, activos[tipo])
    const series = indicadores[clave]
    if (!series) continue
    if (espec.destino === 'precio') overlaysPrecio.push({ clave, tipo, color: espec.color, series })
    else if (espec.destino === 'volumen') overlaysVolumen.push({ clave, color: espec.color, series })
    else panelesOsciladores.push({ tipo, clave, series })
  }

  const altoPrecio = fullscreen ? 380 : 240
  const altoOscilador = fullscreen ? 130 : 90
  const altoVolumen = fullscreen ? 110 : 70

  const barraHover = hoverIndex != null ? barras[hoverIndex] : undefined

  return (
    <div ref={containerRef} className="w-full">
      <div className="flex items-center justify-between mb-1.5 gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
        {moneda && (
          <span className="shrink-0 text-label font-semibold px-1.5 py-0.5 rounded border border-app-border text-app-text-dim">
            {moneda}
          </span>
        )}
        <div className="text-label text-app-text-dim font-mono tabular-nums h-4 truncate">
          {barraHover
            ? `${barraHover.fecha} · ${moneda ? moneda + ' ' : ''}O ${barraHover.apertura?.toFixed(2) ?? '—'} A ${barraHover.maximo?.toFixed(2) ?? '—'} B ${barraHover.minimo?.toFixed(2) ?? '—'} C ${barraHover.cierre.toFixed(2)}${barraHover.volumen != null ? ` · Vol ${Math.round(barraHover.volumen).toLocaleString('es-AR')}` : ''}`
            : ' '}
        </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button" onClick={() => controles.zoom(1 / 1.5)} disabled={controles.completa}
            aria-label="Alejar" title="Alejar"
            className="w-7 h-7 rounded flex items-center justify-center bg-app-surface-2 text-app-text-dim disabled:opacity-40"
          >−</button>
          <button
            type="button" onClick={() => controles.zoom(1.5)} aria-label="Acercar" title="Acercar"
            className="w-7 h-7 rounded flex items-center justify-center bg-app-surface-2 text-app-text-dim"
          >+</button>
          <button
            type="button" onClick={controles.reset} disabled={controles.completa}
            aria-label="Ver todo el período" title="Ver todo el período"
            className="w-7 h-7 rounded flex items-center justify-center bg-app-surface-2 text-app-text-dim disabled:opacity-40"
          >⤢</button>
          {onToggleFullscreen && (
            <button
              onClick={onToggleFullscreen} className="text-app-text-dim shrink-0 w-7 h-7 flex items-center justify-center"
              aria-label={fullscreen ? 'Salir de pantalla completa' : 'Pantalla completa'}
            >
              {fullscreen ? <Icon name="close" className="w-4 h-4" /> : <span className="text-body leading-none">⛶</span>}
            </button>
          )}
        </div>
      </div>

      <div className={controles.arrastrando ? 'cursor-grabbing' : 'cursor-grab'} {...controles.handlers}>

      <PanelPrecio
        barras={barras} escalaX={escalaX} alto={altoPrecio} tieneVelas={tieneVelas} moneda={moneda}
        overlays={overlaysPrecio} senales={senales} primeraBarraEvaluable={primeraBarraEvaluable}
        hoverIndex={hoverIndex} onHover={onHover}
      />

      {panelesOsciladores.map(p => (
        <div key={p.clave} className="mt-2">
          <PanelIndicador
            tipo={p.tipo} clave={p.clave} series={p.series} escalaX={escalaX}
            alto={altoOscilador} hoverIndex={hoverIndex} onHover={onHover}
          />
        </div>
      ))}

      {tieneVolumen && (
        <div className="mt-2">
          <PanelVolumen
            barras={barras} overlays={overlaysVolumen} escalaX={escalaX}
            alto={altoVolumen} hoverIndex={hoverIndex} onHover={onHover}
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
