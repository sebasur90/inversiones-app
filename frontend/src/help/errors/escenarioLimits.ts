// IMPORTANTE: Debe reflejar backend/app/schemas.py EscenarioParamsIn (líneas 136-149)
// Fuente de verdad única en frontend para los rangos de validación

export const ESCENARIO_PARAM_LIMITS: Record<string, { min?: number; max?: number; unit: string; label: string }> = {
  horizonte_meses: {
    min: 1,
    max: 600,
    unit: 'meses',
    label: 'Horizonte',
  },
  variacion_dolar_pct: {
    min: -90,
    max: 500,
    unit: '%',
    label: 'Variación del dólar',
  },
  variacion_por_defecto_pct: {
    min: -95,
    max: 500,
    unit: '%',
    label: 'Variación por defecto',
  },
  aporte_mensual_usd: {
    min: 0,
    unit: 'USD/mes',
    label: 'Aporte mensual',
  },
  crecimiento_aporte_anual_pct: {
    min: -50,
    max: 100,
    unit: '%',
    label: 'Crecimiento del aporte anual',
  },
  retiro_mensual_usd: {
    min: 0,
    unit: 'USD/mes',
    label: 'Retiro mensual',
  },
  dividend_yield_anual_pct: {
    min: 0,
    max: 50,
    unit: '%',
    label: 'Dividend yield anual',
  },
  pct_dividendo_reinvertido: {
    min: 0,
    max: 100,
    unit: '%',
    label: 'Porcentaje dividendo reinvertido',
  },
  comision_pct: {
    min: 0,
    max: 10,
    unit: '%',
    label: 'Comisión',
  },
  inflacion_anual_pct: {
    min: 0,
    max: 1000,
    unit: '%',
    label: 'Inflación anual',
  },
}
