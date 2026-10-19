import type { ReactNode } from 'react'
import type { BarraOut } from '../../api'
import type { EscalaX } from './useEscalaX'
import type { ControlesVentana } from './useVentanaVisible'
import { fechaCorta } from './formatoEjes'
import { Icon } from '../icons/Icons'
import { TACTIL } from './GuiaGestos'

/** Botones de zoom y pantalla completa, compartidos por el gráfico técnico y el del backtest.
 * 36 px: lo mínimo que un dedo acierta sin tocar el de al lado. */
export function BotonesGrafico({
  controles, fullscreen, onToggleFullscreen, operaciones,
}: {
  controles: ControlesVentana
  fullscreen?: boolean
  onToggleFullscreen?: () => void
  /** Interruptor de "mis operaciones" sobre el gráfico. Sin esta prop el botón no existe. */
  operaciones?: { activo: boolean; onToggle: () => void }
}) {
  return (
    <>
      {operaciones && (
        <Boton
          label={operaciones.activo ? 'Ocultar mis compras y ventas' : 'Mostrar mis compras y ventas'}
          onClick={operaciones.onToggle} pulsado={operaciones.activo}
        >
          <span className="text-caption font-bold">▲▼</span>
        </Boton>
      )}
      <Boton label="Alejar" onClick={() => controles.zoom(1 / 1.5)} disabled={controles.completa}>−</Boton>
      <Boton label="Acercar" onClick={() => controles.zoom(1.5)}>+</Boton>
      <Boton label="Ver todo el período" onClick={controles.reset} disabled={controles.completa}>⤢</Boton>
      {onToggleFullscreen && (
        <Boton label={fullscreen ? 'Salir de pantalla completa' : 'Pantalla completa'} onClick={onToggleFullscreen}>
          {fullscreen ? <Icon name="close" className="w-4 h-4" /> : '⛶'}
        </Boton>
      )}
    </>
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
    if (completa) return 'Pellizcá o tocá + para acercar · tocá una vela para ver sus datos'
    return 'Deslizá de costado para moverte · doble toque: ver todo'
  }
  if (completa) return 'Rueda o + para acercar'
  return 'Arrastrá para moverte · doble clic: ver todo'
}

/** Pie del gráfico: qué tramo se está mirando, qué gesto sirve ahora y la guía completa. */
export function PieGrafico({
  barras, escalaX, completa, conCruz = false, onAyuda,
}: {
  barras: BarraOut[]
  escalaX: EscalaX
  completa: boolean
  conCruz?: boolean
  /** Abre la guía de gestos (`GuiaGestos`). */
  onAyuda?: () => void
}) {
  if (barras.length === 0) return null
  return (
    <div className="mt-1 flex flex-col gap-0.5 text-label text-app-text-faint">
      <span className="font-mono tabular-nums">
        {escalaX.visibles} de {barras.length} ruedas · {fechaCorta(barras[escalaX.inicio]?.fecha)} → {fechaCorta(barras[escalaX.fin]?.fecha)}
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
