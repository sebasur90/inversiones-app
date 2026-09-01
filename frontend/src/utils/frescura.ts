export type NivelFrescura = 'fresco' | 'tibio' | 'viejo' | 'desconocido'

const MS_HORA = 60 * 60 * 1000

export interface Frescura {
  nivel: NivelFrescura
  /** Horas transcurridas desde el último sync; null si nunca se sincronizó. */
  horas: number | null
  /** Texto listo para mostrar: "Recién sincronizado", "hace 3 h", "hace 2 d". */
  etiqueta: string
}

/**
 * Antigüedad del último sync. Los umbrales son deliberadamente laxos: los precios del Sheet
 * se actualizan una vez por día, así que "hace 6 horas" no es un problema, pero "hace 3 días"
 * sí merece que el usuario lo vea antes de decidir algo con esos números.
 */
export function calcularFrescura(ultimoSync: string | null | undefined, ahora: number = Date.now()): Frescura {
  if (!ultimoSync) return { nivel: 'desconocido', horas: null, etiqueta: 'Sin sincronizar' }

  const ts = new Date(ultimoSync).getTime()
  if (!Number.isFinite(ts)) return { nivel: 'desconocido', horas: null, etiqueta: 'Sin sincronizar' }

  const horas = Math.max(0, (ahora - ts) / MS_HORA)

  if (horas < 1) return { nivel: 'fresco', horas, etiqueta: 'Recién sincronizado' }
  if (horas < 24) {
    return { nivel: horas < 12 ? 'fresco' : 'tibio', horas, etiqueta: `hace ${Math.floor(horas)} h` }
  }

  const dias = Math.floor(horas / 24)
  return { nivel: dias >= 3 ? 'viejo' : 'tibio', horas, etiqueta: `hace ${dias} d` }
}
