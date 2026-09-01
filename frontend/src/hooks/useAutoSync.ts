import { useEffect, useRef } from 'react'
import { useInversionesContext } from '../context/InversionesContext'
import { calcularFrescura } from '../utils/frescura'
import { leerPreferencia, CLAVE_AUTOSYNC_HORAS, AUTOSYNC_HORAS_DEFAULT } from './usePreferencia'

function horasConfiguradas(): number {
  const crudo = leerPreferencia(CLAVE_AUTOSYNC_HORAS)
  if (crudo === null) return AUTOSYNC_HORAS_DEFAULT
  const n = Number(crudo)
  return Number.isFinite(n) && n >= 0 ? n : AUTOSYNC_HORAS_DEFAULT
}

/**
 * Sincroniza solo si los datos ya están viejos: al abrir la app y al volver a ella. El sync
 * tarda y pega contra Google Sheets, así que no se dispara en cada foco — sólo cuando pasó
 * el umbral configurado en Ajustes (0 = desactivado).
 */
export function useAutoSync() {
  const { ultimoSync, syncing, triggerSync } = useInversionesContext()
  // Marca de agua del último intento. Si el sync falla, `ultimoSync` no cambia: sin esto el
  // efecto volvería a evaluar al bajar `syncing` y reintentaría en bucle contra un backend
  // caído. Se reintenta recién cuando el sync tuvo éxito (y `ultimoSync` avanzó) o al volver
  // a la app.
  const intentadoParaRef = useRef<string | null>(null)

  useEffect(() => {
    function evaluar(reintentar = false) {
      if (document.visibilityState !== 'visible') return
      if (syncing) return
      if (!reintentar && intentadoParaRef.current === ultimoSync) return

      const umbral = horasConfiguradas()
      if (umbral <= 0) return

      const { horas } = calcularFrescura(ultimoSync)
      // horas === null (nunca sincronizado) lo resuelve el sync manual: sin datos la app
      // muestra el splash, no una pantalla que convenga refrescar sola.
      if (horas === null || horas < umbral) return

      intentadoParaRef.current = ultimoSync
      void triggerSync()
    }

    // Al volver a la app sí se reintenta, aunque el intento anterior con estos mismos datos
    // haya fallado.
    const alVolver = () => evaluar(true)

    evaluar()
    document.addEventListener('visibilitychange', alVolver)
    return () => document.removeEventListener('visibilitychange', alVolver)
  }, [ultimoSync, syncing, triggerSync])
}
