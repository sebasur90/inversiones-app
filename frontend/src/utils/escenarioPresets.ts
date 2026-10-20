import type { EscenarioParamsIn } from '../api'

/** Parámetros neutros: lo que vale un campo que ni el preset ni el usuario definieron. */
export const PARAMS_VACIOS: EscenarioParamsIn = {
  horizonte_meses: 60,
  variacion_dolar_pct: 0,
  variacion_por_instrumento: {},
  variacion_por_defecto_pct: 0,
  aporte_mensual_usd: 0,
  crecimiento_aporte_anual_pct: 0,
  retiro_mensual_usd: 0,
  modo_dividendos: 'reinvertir_total',
  dividend_yield_anual_pct: 0,
  pct_dividendo_reinvertido: null,
  comision_pct: 0,
  inflacion_anual_pct: null,
}

/**
 * Espejo de `PRESETS` en `backend/app/services/escenario_engine.py`: es lo que el backend aplica
 * a un escenario no personalizado para los campos que el cliente no envía. Sirve para mostrar en
 * el panel los mismos valores que se van a simular.
 */
export const PRESET_DEFAULTS: Record<string, Partial<EscenarioParamsIn>> = {
  alcista: { horizonte_meses: 120, variacion_por_defecto_pct: 20, variacion_dolar_pct: 5, dividend_yield_anual_pct: 2 },
  bajista: { horizonte_meses: 120, variacion_por_defecto_pct: -10, variacion_dolar_pct: 10, dividend_yield_anual_pct: 1.5 },
  crisis: { horizonte_meses: 120, variacion_por_defecto_pct: -35, variacion_dolar_pct: 60, dividend_yield_anual_pct: 0.5 },
  personalizado: {},
}

/** Parámetros efectivos de un escenario: neutros < preset < lo que el usuario editó. */
export function parametrosEfectivos(
  tipoPreset: string,
  parametros?: Partial<EscenarioParamsIn> | null,
): EscenarioParamsIn {
  return { ...PARAMS_VACIOS, ...(PRESET_DEFAULTS[tipoPreset] ?? {}), ...(parametros ?? {}) }
}
