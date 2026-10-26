import { Children, type ReactNode } from 'react'
import type { BarraOut } from '../../api'
import type { EscalaX } from './useEscalaX'
import type { ControlesVentana } from './useVentanaVisible'
import { fechaCorta } from './formatoEjes'
import { Icon, type IconName } from '../icons/Icons'
import { TACTIL } from './GuiaGestos'

/** Botones de zoom y pantalla completa, compartidos por el gráfico técnico y el del backtest.
 * 36 px: lo mínimo que un dedo acierta sin tocar el de al lado. */
export function BotonesGrafico({
  controles, fullscreen, onToggleFullscreen,
}: {
  controles: ControlesVentana
  fullscreen?: boolean
  onToggleFullscreen?: () => void
}) {
  return (
    <>
      <Boton label="Alejar" onClick={() => controles.zoom(1 / 1.5)} disabled={controles.completa}>−</Boton>
      <Boton label="Acercar" onClick={() => controles.zoom(1.5)}>+</Boton>
      <Boton label="Ver todo el período" onClick={controles.reset} disabled={controles.completa && controles.escalaY === 1}>⤢</Boton>
      {onToggleFullscreen && (
        <Boton label={fullscreen ? 'Salir de pantalla completa' : 'Pantalla completa'} onClick={onToggleFullscreen}>
          {fullscreen ? <Icon name="close" className="w-4 h-4" /> : '⛶'}
        </Boton>
      )}
    </>
  )
}

/** Un interruptor de la barra de herramientas del gráfico (mis operaciones, escala log, ...). */
export interface Herramienta {
  clave: string
  /** Lo que se ve en el botón. */
  texto: string
  /** Lo que lee un lector de pantalla y el tooltip. */
  label: string
  activo: boolean
  onToggle: () => void
  /** Con ícono, el botón va con el ícono arriba y `texto` abajo, como una barra de pestañas. */
  icono?: IconName
}

/** Fila de interruptores del gráfico. Va aparte de la ficha: con siete botones en la misma línea
 * que la fecha y el precio, en el celular no quedaba lugar para leerlos.
 *
 * Con íconos (el gráfico técnico) es una barra de botones de 48 px de alto, cada uno con su
 * nombre: "log" o "S/R" sueltos no decían qué hacían. Sin íconos (el gráfico del backtest) queda
 * la fila compacta de siempre. */
export function BarraHerramientas({
  herramientas, children,
}: {
  herramientas: Herramienta[]
  /** Controles extra a continuación de los interruptores (p.ej. el selector de índice). */
  children?: ReactNode
}) {
  if (herramientas.length === 0) return null
  if (herramientas.some(h => h.icono)) {
    const extras = Children.toArray(children)
    return (
      <div className="flex flex-col gap-1.5">
        <div role="toolbar" aria-label="Herramientas del gráfico" className="flex gap-1 overflow-x-auto no-scrollbar">
          {herramientas.map(h => (
            <button
              key={h.clave} type="button" onClick={h.onToggle} aria-label={h.label} title={h.label}
              aria-pressed={h.activo}
              className={`flex-1 min-w-[58px] h-12 px-1.5 flex flex-col items-center justify-center gap-1 rounded-xl text-label font-semibold leading-none whitespace-nowrap transition-colors ${
                h.activo ? 'bg-app-accent-soft text-app-accent' : 'bg-app-surface-2 text-app-text-dim'
              }`}
            >
              {h.icono && <Icon name={h.icono} className="w-[18px] h-[18px]" />}
              {h.texto}
            </button>
          ))}
        </div>
        {extras.length > 0 && <div className="flex flex-wrap items-center gap-1">{extras}</div>}
      </div>
    )
  }
  return (
    <div className="flex flex-wrap items-center gap-1 mb-1">
      {herramientas.map(h => (
        <button
          key={h.clave} type="button" onClick={h.onToggle} aria-label={h.label} title={h.label}
          aria-pressed={h.activo}
          className={`h-8 px-2.5 rounded-lg text-label font-bold leading-none ${
            h.activo ? 'bg-app-accent-soft text-app-accent' : 'bg-app-surface-2 text-app-text-dim'
          }`}
        >
          {h.texto}
        </button>
      ))}
      {children}
    </div>
  )
}

function Boton({
  children, label, onClick, disabled, pulsado,
}: {
  children: ReactNode
  label: string
  onClick: () => void
  disabled?: boolean
  /** Botón de estado (interruptor): se marca cuando está activo. */
  pulsado?: boolean
}) {
  return (
    <button
      type="button" onClick={onClick} disabled={disabled} aria-label={label} title={label}
      aria-pressed={pulsado}
      className={`w-9 h-9 rounded-lg flex items-center justify-center text-title leading-none disabled:opacity-40 ${
        pulsado ? 'bg-app-accent-soft text-app-accent' : 'bg-app-surface-2 text-app-text-dim'
      }`}
    >
      {children}
    </button>
  )
}

/** La pista de qué se puede hacer ahora, según el estado: con todo el período a la vista lo único
 * útil es acercar; con zoom, deslizar y volver; con la cruz puesta, cómo sacarla. */
function pistaSegunEstado(completa: boolean, conCruz: boolean): string {
  if (TACTIL) {
    if (conCruz) return 'Tocá la misma vela o ✕ para quitar la cruz · mantené y arrastrá para recorrer'
    if (completa) return 'Pellizcá o tocá + para acercar · pellizcá en vertical para achicar las velas'
    return 'Deslizá de costado para moverte · doble toque: ver todo'
  }
  if (completa) return 'Rueda o + para acercar'
  return 'Arrastrá para moverte · doble clic: ver todo'
}

/** Pie del gráfico: qué tramo se está mirando, qué gesto sirve ahora y la guía completa. */
export function PieGrafico({
  barras, escalaX, completa, conCruz = false, unidad = 'ruedas', onAyuda,
}: {
  barras: BarraOut[]
  escalaX: EscalaX
  completa: boolean
  conCruz?: boolean
  /** Qué es cada barra: 'ruedas', 'semanas' o 'meses'. */
  unidad?: string
  /** Abre la guía de gestos (`GuiaGestos`). */
  onAyuda?: () => void
}) {
  if (barras.length === 0) return null
  return (
    <div className="mt-1 flex flex-col gap-0.5 text-label text-app-text-faint">
      <span className="font-mono tabular-nums">
        {escalaX.visibles} de {barras.length} {unidad} · {fechaCorta(barras[escalaX.inicio]?.fecha)} → {fechaCorta(barras[escalaX.fin]?.fecha)}
      </span>
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0">{pistaSegunEstado(completa, conCruz)}</span>
        {onAyuda && (
          <button type="button" onClick={onAyuda} className="shrink-0 font-semibold text-app-accent">
            Cómo se usa
          </button>
        )}
      </div>
    </div>
  )
}
