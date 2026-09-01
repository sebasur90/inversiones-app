import {
  leerPreferencia,
  CLAVE_ESCALA_TEXTO,
  ESCALA_TEXTO_DEFAULT,
  ESCALA_TEXTO_MIN,
  ESCALA_TEXTO_MAX,
} from '../hooks/usePreferencia'

/**
 * La escala vive en una variable CSS del `<html>` y las medidas tipográficas cuelgan de ella
 * (ver `index.css`). Se aplica al arrancar, antes del primer render, para que no haya salto.
 */
export function aplicarEscalaTexto(escala: number): void {
  const acotada = Math.min(Math.max(escala, ESCALA_TEXTO_MIN), ESCALA_TEXTO_MAX)
  document.documentElement.style.setProperty('--escala-texto', String(acotada))
}

export function escalaTextoGuardada(): number {
  const crudo = leerPreferencia(CLAVE_ESCALA_TEXTO)
  if (crudo === null) return ESCALA_TEXTO_DEFAULT
  const n = Number(crudo)
  if (!Number.isFinite(n) || n < ESCALA_TEXTO_MIN || n > ESCALA_TEXTO_MAX) return ESCALA_TEXTO_DEFAULT
  return n
}
