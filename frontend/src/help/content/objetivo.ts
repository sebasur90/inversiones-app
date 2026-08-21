import { HelpContent } from '../types'

export type ObjetivoHelpKey =
  | 'objetivo_monto'
  | 'objetivo_fecha_limite'
  | 'objetivo_patrimonio_inicial'
  | 'objetivo_aporte_mensual'
  | 'objetivo_rentabilidad_anual'
  | 'objetivo_modo_solver'
  | 'objetivo_escenario_mostrado'
  | 'objetivo_tasa_override'
  | 'objetivo_desviacion_plan'
  | 'objetivo_fechas_estimadas'
  | 'objetivo_aporte_actual'
  | 'objetivo_aporte_objetivo'

export const OBJETIVO_HELP: Record<ObjetivoHelpKey, HelpContent> = {
  objetivo_monto: {
    title: 'Monto objetivo',
    shortDescription: 'El valor en dólares que deseas alcanzar.',
    whyItMatters: 'Es el destino de tu plan: cuánto dinero buscas tener acumulado.',
    example: '100000 significa que quieres llegar a USD 100.000.',
  },
  objetivo_fecha_limite: {
    title: 'Fecha límite',
    shortDescription: 'La fecha para la cual esperas alcanzar tu objetivo.',
    whyItMatters: 'Define el horizonte temporal. Cuanto más corto, mayor debe ser tu rentabilidad o aportes.',
    example: '31/12/2030 es tu fecha destino.',
  },
  objetivo_patrimonio_inicial: {
    title: 'Patrimonio inicial',
    shortDescription: 'El valor actual de tu cartera, el punto de partida del plan.',
    whyItMatters: 'Se usa como base para calcular cuánto necesitas ahorrar y qué retorno se requiere.',
  },
  objetivo_aporte_mensual: {
    title: 'Aporte mensual',
    shortDescription: 'Cantidad en dólares que planeas aportar cada mes.',
    whyItMatters: 'Los aportes regulares son la palanca más poderosa para alcanzar objetivos.',
  },
  objetivo_rentabilidad_anual: {
    title: 'Rentabilidad anual',
    shortDescription: 'Porcentaje de retorno anual esperado en tu cartera.',
    whyItMatters: 'Junto con los aportes, determina la velocidad a la que crece tu patrimonio.',
    example: '8 significa esperas un 8% de retorno anual.',
  },
  objetivo_modo_solver: {
    title: '¿Qué querés resolver?',
    shortDescription: 'Elige qué parámetro deseas calcular automáticamente: el aporte requerido (mensual), la fecha alcanzable (cuándo), o la rentabilidad necesaria (a qué tasa).',
    whyItMatters: 'Te permite explorar diferentes "qué pasaría si" sin cambiar manualmente los valores cada vez.',
    example: 'Si eliges "Aporte requerido", el simulador calcula cuánto necesitas ahorrar por mes. Si eliges "Fecha alcanzable", calcula en cuánto tiempo lo logras con tus aportes y retorno esperado.',
  },
  objetivo_escenario_mostrado: {
    title: 'Escenario mostrado',
    shortDescription: 'Selecciona cuál de los tres escenarios pre-calculados deseas visualizar: Conservador (tasa baja), Base (tasa media), u Optimista (tasa alta).',
    whyItMatters: 'Te permite ver un rango de posibilidades: desde un escenario pesimista a uno optimista.',
    limitations: 'Solo cambia qué serie se grafica. No dispara un nuevo cálculo; los escenarios son pre-computados con tasas fijas. Para editar libremente, usa el "Simulador inverso".',
  },
  objetivo_tasa_override: {
    title: 'Tasa personalizada',
    shortDescription: 'Ingresa una tasa de rentabilidad personalizada para reemplazar la tasa por defecto del escenario.',
    whyItMatters: 'Te permite simular un retorno distinto del que calcula automáticamente la app.',
    example: '7.5 para un retorno del 7.5% anual.',
    limitations: 'Se guarda solo en este navegador (localStorage). Si cambias de dispositivo o borras los datos, desaparece.',
  },
  objetivo_desviacion_plan: {
    title: 'Desviación vs. plan',
    shortDescription: 'Diferencia entre lo que aportaste realmente hasta hoy y lo que el plan simple (objetivo ÷ meses totales) esperaba que hubieras aportado a esta altura.',
    whyItMatters: 'Indica si tu ritmo de aportes va adelantado, a tiempo o atrasado, sin mezclar el efecto del rendimiento de mercado.',
    example: 'Con un plan de USD 250/mes y 2 meses transcurridos, se esperaban USD 500 aportados. Si aportaste USD 3.000, la desviación es +2.500 USD (adelantado).',
  },
  objetivo_fechas_estimadas: {
    title: 'Fechas estimadas',
    shortDescription: 'Proyecciones de cuándo alcanzarás tu objetivo bajo diferentes escenarios de aporte mensual, sin considerar rendimientos.',
    whyItMatters: 'Te ayuda a entender el impacto del aporte mensual en el tiempo necesario para alcanzar tu meta. Mayor aporte = menos tiempo. El cálculo es lineal (sin rendimientos) para ver el efecto puro del ahorro.',
    howItIsCalculated: 'Se calcula considerando únicamente: patrimonio actual + aporte mensual × meses restantes = monto objetivo. Los rendimientos se visualizan separadamente en Escenarios, Proyección patrimonial y Sensibilidad.',
  },
  objetivo_aporte_actual: {
    title: 'Manteniendo aporte actual',
    shortDescription: 'Fecha estimada para alcanzar tu objetivo si continúas aportando el promedio actual cada mes.',
    whyItMatters: 'Te muestra tu trayectoria actual: cuánto tiempo más necesitas si no cambias tu ritmo de aportes.',
    example: 'Si aportas USD 1.993/mes en promedio y tu objetivo es USD 100.000, esta sección muestra en cuántos meses lo alcanzarás.',
  },
  objetivo_aporte_objetivo: {
    title: 'Con aporte objetivo',
    shortDescription: 'Fecha estimada para alcanzar tu objetivo bajo diferentes aumentos de aporte: desde el monto "Necesario" hasta 2x ese monto.',
    whyItMatters: 'Te permite explorar cómo cambios en tu aporte mensual afectan la velocidad de tu plan. Cada botón (+25%, +50%, +100%) acelera el proceso.',
    example: 'El botón "Necesario" muestra la fecha si aportas el mínimo calculado. "+50%" te muestra qué sucede si incrementas ese aporte en 50%.',
  },
}
