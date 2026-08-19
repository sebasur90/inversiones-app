import { HelpContent } from '../types'

export type SimuladorHelpKey =
  | 'escenario_horizonte'
  | 'escenario_variacion_dolar'
  | 'escenario_variacion_default'
  | 'escenario_aporte_mensual'
  | 'escenario_crecimiento_aporte'
  | 'escenario_retiro_mensual'
  | 'escenario_modo_dividendos'
  | 'escenario_dividend_yield'
  | 'escenario_pct_dividendo_reinvertido'
  | 'escenario_comision'
  | 'escenario_inflacion'
  | 'escenario_preset'

export const SIMULADOR_HELP: Record<SimuladorHelpKey, HelpContent> = {
  escenario_horizonte: {
    title: 'Horizonte',
    shortDescription: 'Cantidad de meses en los que deseas proyectar tu cartera.',
    whyItMatters: 'Define el período sobre el cual se calcula la simulación.',
    example: 'Para proyectar 5 años, ingresa 60 meses.',
    limitations: 'Debe estar entre 1 y 600 meses.',
  },
  escenario_variacion_dolar: {
    title: 'Variación del dólar',
    shortDescription: 'El cambio porcentual esperado en la cotización del dólar (MEP) durante el período de simulación.',
    whyItMatters: 'Afecta el valor en ARS de tus posiciones en USD y tus inversiones en activos dolarizados.',
    example: '10 significa que esperas que el dólar se aprecie un 10%. -5 significa una depreciación del 5%.',
    limitations: 'Debe estar entre -90% y 500%. Una caída del -100% implicaría la eliminación del dólar.',
  },
  escenario_variacion_default: {
    title: 'Variación por defecto',
    shortDescription: 'La tasa de retorno anual esperada para los activos que no tengan una variación específica ingresada.',
    whyItMatters: 'Es el retorno base aplicado a la mayoría de tus posiciones en la simulación.',
    example: '8 significa que esperas un retorno anual del 8%.',
    limitations: 'Debe estar entre -95% y 500%.',
  },
  escenario_aporte_mensual: {
    title: 'Aporte mensual',
    shortDescription: 'Cantidad de dólares que planeas aportar cada mes a la cartera.',
    whyItMatters: 'Los aportes regulares aceloran el crecimiento del patrimonio y afectan el retorno calculado.',
    example: '500 significa 500 USD por mes.',
  },
  escenario_crecimiento_aporte: {
    title: 'Crecimiento del aporte anual',
    shortDescription: 'Porcentaje en el que aumenta tu aporte mensual cada año (ej: por inflación o incremento salarial).',
    whyItMatters: 'Permite simular aumentos realistas en tus aportes a lo largo del tiempo.',
    example: '3 significa que el aporte crece un 3% cada año.',
    limitations: 'Debe estar entre -50% y 100%.',
  },
  escenario_retiro_mensual: {
    title: 'Retiro mensual',
    shortDescription: 'Cantidad de dólares que planeas retirar cada mes de la cartera.',
    whyItMatters: 'Los retiros frecuentes reducen el patrimonio y afectan tu rendimiento.',
    example: '100 significa 100 USD retirados por mes.',
  },
  escenario_modo_dividendos: {
    title: 'Modo dividendos',
    shortDescription: 'Determina qué sucede con los dividendos cobrados: reinvertirlos totalmente, reinvertir parte, o retirarlos.',
    whyItMatters: 'Reinvertir dividendos acelera el crecimiento por capitalización; retirarlos da liquidez pero reduce el crecimiento.',
    example: '"Reinvertir total" acumula dividendos en la cartera. "Retirar" te da el flujo de dividendos como ingreso.',
  },
  escenario_dividend_yield: {
    title: 'Dividend yield anual',
    shortDescription: 'Porcentaje de retorno anual que se espera recibir en forma de dividendos y cupones.',
    whyItMatters: 'Agrega un componente de ingresos pasivos a la simulación, importante para carteras con bonos y acciones con dividendos.',
    example: '4 significa 4% anual en dividendos.',
    limitations: 'Debe estar entre 0% y 50%.',
  },
  escenario_pct_dividendo_reinvertido: {
    title: 'Porcentaje dividendo reinvertido',
    shortDescription: 'Cuando el modo es "Reinvertir parcial", qué porcentaje de los dividendos se reinvierte (el resto se retira).',
    whyItMatters: 'Te permite balancear el crecimiento por capitalización con la liquidez que necesitas.',
    example: '50 reinvierte el 50% de dividendos y retira el otro 50%.',
    limitations: 'Debe estar entre 0% y 100%. Solo se aplica en modo "Reinvertir parcial".',
  },
  escenario_comision: {
    title: 'Comisión',
    shortDescription: 'Porcentaje anual de comisión de gestión aplicado al patrimonio.',
    whyItMatters: 'Las comisiones reducen significativamente tu retorno neto a largo plazo.',
    example: '0.5 significa una comisión del 0.5% anual sobre tu patrimonio.',
    limitations: 'Debe estar entre 0% y 10%.',
  },
  escenario_inflacion: {
    title: 'Inflación anual',
    shortDescription: 'Porcentaje de inflación anual esperada. Se usa para calcular el rendimiento real (descontando inflación).',
    whyItMatters: 'La inflación reduce tu poder de compra. Conocer tu retorno real es crucial para evaluar si ganaste dinero de verdad.',
    example: '3 significa 3% de inflación anual.',
    limitations: 'Debe estar entre 0% y 1.000%. Opcional.',
  },
  escenario_preset: {
    title: 'Preset de escenario',
    shortDescription: 'Escenarios predefinidos que representan situaciones típicas: Base (neutral), Alcista (positivo), Bajista (negativo) y Crisis (muy negativo).',
    whyItMatters: 'Los presets son atajos para no tener que ingresar manualmente cada parámetro en escenarios comunes.',
    howItIsCalculated: 'Los valores de cada preset se calculan en el servidor based on histórico y benchmarks.',
    limitations: 'Cuando seleccionas un preset que no sea "Personalizado", los campos se deshabilitan. Para editar, debes cambiar a "Personalizado".',
  },
}
