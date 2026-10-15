import type { ReactNode } from 'react'
import type { BarraOut } from '../../api'
import type { EscalaX } from './useEscalaX'
import type { ControlesVentana } from './useVentanaVisible'
import { fechaCorta } from './formatoEjes'
import { Icon } from '../icons/Icons'
import InfoTooltip from '../../help/components/InfoTooltip'

/** ¿Pantalla táctil? Decide la pista del pie ("doble toque" o "doble clic"). */
const TACTIL = typeof window !== 'undefined' && !!window.matchMedia?.('(pointer: coarse)').matches

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
  children, label, onClick, disabled,
}: {
  children: ReactNode
  label: string
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button" onClick={onClick} disabled={disabled} aria-label={label} title={label}
      className="w-9 h-9 rounded-lg flex items-center justify-center bg-app-surface-2 text-title leading-none text-app-text-dim disabled:opacity-40"
    >
      {children}
    </button>
  )
}

/** Pie del gráfico: qué tramo se está mirando y cómo volver a todo el período. */
export function PieGrafico({
  barras, escalaX, completa,
}: {
  barras: BarraOut[]
  escalaX: EscalaX
  completa: boolean
}) {
  if (barras.length === 0) return null
  const pista = !completa ? (TACTIL ? 'doble toque: ver todo' : 'doble clic: ver todo') : null
  return (
    <div className="mt-1 flex items-center gap-1 text-label text-app-text-faint font-mono tabular-nums">
      <span className="min-w-0">
        {escalaX.visibles} de {barras.length} ruedas · {fechaCorta(barras[escalaX.inicio]?.fecha)} → {fechaCorta(barras[escalaX.fin]?.fecha)}
        {pista && ` · ${pista}`}
      </span>
      <InfoTooltip term="grafico_gestos" />
    </div>
  )
}
