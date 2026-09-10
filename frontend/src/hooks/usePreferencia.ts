import { useCallback, useState } from 'react'

// localStorage puede fallar (modo privado, cookies bloqueadas): nunca debe tumbar la app.
export function leerPreferencia(clave: string): string | null {
  try {
    return localStorage.getItem(clave)
  } catch {
    return null
  }
}

export function guardarPreferencia(clave: string, valor: string | null): void {
  try {
    if (valor === null) localStorage.removeItem(clave)
    else localStorage.setItem(clave, valor)
  } catch {
    // sin persistencia, la sesión sigue funcionando igual
  }
}

/**
 * Estado persistido en localStorage. `parse` valida lo leído: si el valor guardado quedó
 * viejo o corrupto, devuelve el default en vez de propagar basura a la UI.
 */
export function usePreferencia<T>(
  clave: string,
  valorPorDefecto: T,
  parse: (crudo: string) => T | null,
  serializar: (valor: T) => string,
): [T, (valor: T) => void] {
  const [valor, setValor] = useState<T>(() => {
    const crudo = leerPreferencia(clave)
    if (crudo === null || crudo === '') return valorPorDefecto
    return parse(crudo) ?? valorPorDefecto
  })

  const actualizar = useCallback(
    (nuevo: T) => {
      setValor(nuevo)
      // Cadena vacía = "sin valor": se borra la clave en vez de guardar un string vacío que
      // después habría que distinguir del valor real.
      const serializado = serializar(nuevo)
      guardarPreferencia(clave, serializado === '' ? null : serializado)
    },
    [clave, serializar],
  )

  return [valor, actualizar]
}

/** Preferencia numérica acotada a un rango (horas de auto-sync, escala tipográfica, …). */
export function usePreferenciaNumerica(
  clave: string,
  valorPorDefecto: number,
  min: number,
  max: number,
): [number, (valor: number) => void] {
  return usePreferencia<number>(
    clave,
    valorPorDefecto,
    crudo => {
      const n = Number(crudo)
      return Number.isFinite(n) && n >= min && n <= max ? n : null
    },
    n => String(n),
  )
}

/** Preferencia booleana ('1'/'0' en localStorage). */
export function usePreferenciaBooleana(
  clave: string,
  valorPorDefecto: boolean,
): [boolean, (valor: boolean) => void] {
  return usePreferencia<boolean>(
    clave,
    valorPorDefecto,
    crudo => (crudo === '1' ? true : crudo === '0' ? false : null),
    v => (v ? '1' : '0'),
  )
}

export const CLAVE_CARTERA = 'inversiones-cartera'
export const CLAVE_MONEDA = 'inversiones-moneda'
export const CLAVE_AUTOSYNC_HORAS = 'inversiones-autosync-horas'
export const CLAVE_ESCALA_TEXTO = 'inversiones-escala-texto'
export const CLAVE_UMBRAL_PROXIMIDAD = 'inversiones-alerta-proximidad-pct'
/** Interruptor global de "Ajustes": si está apagado, las guías 💡 arrancan colapsadas en toda la app. */
export const CLAVE_MODO_GUIADO = 'inversiones-modo-guiado'
/** Si ya se vio (o salteó) el tour de bienvenida. */
export const CLAVE_TOUR_VISTO = 'inversiones-tour-visto'
/** Prefijo de la clave de colapso por pantalla: se completa con la ruta (`claveRutaGuia`). */
export const PREFIJO_GUIA_COLAPSADA = 'inversiones-guia-colapsada:'

/** "Volver a mostrar todas las guías" en Ajustes: borra el colapso guardado de cada pantalla. */
export function limpiarGuiasColapsadas(): void {
  try {
    const claves = Object.keys(localStorage).filter(k => k.startsWith(PREFIJO_GUIA_COLAPSADA))
    for (const k of claves) localStorage.removeItem(k)
  } catch {
    // sin acceso a localStorage, no hay nada que limpiar
  }
}

/** 0 = auto-sync desactivado. */
export const AUTOSYNC_HORAS_DEFAULT = 12
export const AUTOSYNC_HORAS_MAX = 72
export const ESCALA_TEXTO_DEFAULT = 1
export const ESCALA_TEXTO_MIN = 1
export const ESCALA_TEXTO_MAX = 1.3

/**
 * A cuántos puntos porcentuales del stop-loss o del precio objetivo una posición empieza a
 * avisar. En porcentaje, no en ratio: es lo que se elige en Ajustes. 0 = sólo avisar cuando
 * el precio ya cruzó el nivel.
 */
export const UMBRAL_PROXIMIDAD_DEFAULT = 5
export const UMBRAL_PROXIMIDAD_MAX = 20
