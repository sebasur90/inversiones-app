import { useSyncExternalStore } from 'react'
import { CLAVE_MONTOS_OCULTOS, guardarPreferencia, leerPreferencia } from '../hooks/usePreferencia'

/**
 * Modo privacidad: interruptor global que reemplaza los importes de la cartera por una máscara
 * (ver `formatoMonto.ts`) para poder mirar la app con alguien al lado.
 *
 * Es un store externo y no parte de `InversionesContext` a propósito: el `value` del contexto
 * está memoizado con dependencias acotadas porque invalidarlo re-renderiza ~21 pantallas con
 * Recharts. Acá la reactividad llega sólo a quien muestra montos, vía `useFormatoMoneda()`.
 *
 * El flag se inicializa al importar el módulo, así que ya está bien antes del primer render:
 * a diferencia de la escala de texto, no hace falta aplicarlo desde `main.tsx` ni hay un frame
 * con los importes a la vista al abrir la app con el modo activo.
 */
let ocultos = leerPreferencia(CLAVE_MONTOS_OCULTOS) === '1'

// StrictMode monta y desmonta dos veces en desarrollo: el Set tolera el add/delete duplicado.
const suscriptores = new Set<() => void>()

function subscribe(alCambiar: () => void): () => void {
  suscriptores.add(alCambiar)
  return () => {
    suscriptores.delete(alCambiar)
  }
}

// Devuelve un booleano primitivo: identidad estable entre renders, sin loop de re-render.
function getSnapshot(): boolean {
  return ocultos
}

/** Para código que no es un componente (formateadores puros, handlers sueltos). */
export function montosOcultosAhora(): boolean {
  return ocultos
}

export function setMontosOcultos(valor: boolean): void {
  if (valor === ocultos) return
  ocultos = valor
  guardarPreferencia(CLAVE_MONTOS_OCULTOS, valor ? '1' : '0')
  for (const alCambiar of suscriptores) alCambiar()
}

export function toggleMontosOcultos(): void {
  setMontosOcultos(!ocultos)
}

/** Se suscribe al interruptor. Normalmente se usa a través de `useFormatoMoneda()`. */
export function useMontosOcultos(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
}
