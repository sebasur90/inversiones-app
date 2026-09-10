/**
 * Traduce métricas a "bien / atención / riesgo" + una etiqueta en palabras, para no depender
 * sólo del color (verde/dorado/coral no dice nada por sí solo a alguien con daltonismo, o que
 * simplemente no conoce la convención). Se usa con `components/ui/Semaforo.tsx`.
 *
 * Los umbrales de drawdown, volatilidad y concentración son los mismos que ya dispara
 * `backend/app/services/diagnostico_engine.py` para generar un hallazgo — no son un criterio
 * nuevo, es el mismo que la app ya usa para decir "esto amerita un hallazgo".
 */
export type Nivel = 'bien' | 'atencion' | 'riesgo'

export interface NivelInfo {
  nivel: Nivel
  etiqueta: string
}

// Ídem `UMBRAL_DRAWDOWN_ADVERTENCIA` / `_CRITICO` en diagnostico_engine.py.
const UMBRAL_DRAWDOWN_ADVERTENCIA = -0.15
const UMBRAL_DRAWDOWN_CRITICO = -0.3

// Ídem `UMBRAL_VOLATILIDAD_ADVERTENCIA` / `_CRITICO`.
const UMBRAL_VOLATILIDAD_ADVERTENCIA = 0.3
const UMBRAL_VOLATILIDAD_CRITICO = 0.45

// Escala clásica de HHI (suma de participaciones % al cuadrado, 0-10000), la misma que ya usaba
// `etiquetaHhi` en `pages/Contribucion.tsx` antes de este archivo — no la de `hhi_normalizado`
// (0-1) que usa el backend para el hallazgo, que es otra escala para el mismo concepto.
const UMBRAL_HHI_MODERADO = 1500
const UMBRAL_HHI_ALTO = 2500

/** Score de salud (0-100): diagnóstico o calidad de datos. El corte de "riesgo" en 60 replica
 *  `TOPE_SCORE_CON_CRITICOS = 59` del health score: por debajo, siempre hay al menos un
 *  problema crítico. El corte de "atención" en 85 es un redondeo razonable, no algo que el
 *  backend imponga. */
export function nivelScore(score: number | null | undefined): NivelInfo | null {
  if (score == null) return null
  if (score < 60) return { nivel: 'riesgo', etiqueta: 'Necesita atención' }
  if (score < 85) return { nivel: 'atencion', etiqueta: 'Para revisar' }
  return { nivel: 'bien', etiqueta: 'Saludable' }
}

/** Drawdown como ratio negativo (-0.12 = -12%), igual que `riesgo.drawdown.actual/maximo`. */
export function nivelDrawdown(ratio: number | null | undefined): NivelInfo | null {
  if (ratio == null) return null
  if (ratio <= UMBRAL_DRAWDOWN_CRITICO) return { nivel: 'riesgo', etiqueta: 'Caída importante' }
  if (ratio <= UMBRAL_DRAWDOWN_ADVERTENCIA) return { nivel: 'atencion', etiqueta: 'Caída moderada' }
  return { nivel: 'bien', etiqueta: 'Dentro de lo normal' }
}

/** Volatilidad anualizada como ratio positivo (0.35 = 35%). */
export function nivelVolatilidad(ratio: number | null | undefined): NivelInfo | null {
  if (ratio == null) return null
  if (ratio >= UMBRAL_VOLATILIDAD_CRITICO) return { nivel: 'riesgo', etiqueta: 'Volatilidad alta' }
  if (ratio >= UMBRAL_VOLATILIDAD_ADVERTENCIA) return { nivel: 'atencion', etiqueta: 'Volatilidad moderada' }
  return { nivel: 'bien', etiqueta: 'Volatilidad baja' }
}

/** HHI en escala clásica 0-10000 (no normalizado 0-1). */
export function nivelConcentracion(hhi: number | null | undefined): NivelInfo | null {
  if (hhi == null) return null
  if (hhi > UMBRAL_HHI_ALTO) return { nivel: 'riesgo', etiqueta: 'Muy concentrado' }
  if (hhi >= UMBRAL_HHI_MODERADO) return { nivel: 'atencion', etiqueta: 'Moderadamente concentrado' }
  return { nivel: 'bien', etiqueta: 'Poco concentrado' }
}
