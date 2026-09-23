import { HelpContent } from '../types'

// Prefijo "matrizcorr_" a propósito: ya existe "correlacion" en glosario.ts (el término general)
// y no se toca; esta pantalla lo enlaza vía relatedTerms en vez de reexplicarlo.
export type MatrizCorrelacionesHelpKey =
  | 'matrizcorr_correlacion'
  | 'matrizcorr_frecuencia'
  | 'matrizcorr_moneda'
  | 'matrizcorr_solapamiento'
  | 'matrizcorr_diversificacion'
  | 'matrizcorr_causalidad'
  | 'matrizcorr_min_obs'

export const MATRIZCORRELACIONES_HELP: Record<MatrizCorrelacionesHelpKey, HelpContent> = {
  matrizcorr_correlacion: {
    title: 'Correlación entre dos instrumentos',
    shortDescription: 'Qué tan parecido se movieron dos instrumentos en el período elegido, en una escala de -1 a +1.',
    whyItMatters: 'Tener muchas posiciones no diversifica si todas se mueven juntas: la correlación muestra qué tan "juntas" van en los hechos, no en el papel.',
    howItIsCalculated: 'Coeficiente de correlación de Pearson sobre los retornos de cada instrumento, calculados en USD, con la frecuencia y el período que elegiste.',
    howToInterpret: '+1 significa que se movieron de manera muy similar. 0 significa que no se observa una relación lineal clara entre ellos. -1 significa que se movieron en direcciones opuestas.',
    limitations: 'Es un resumen de lo que ya pasó, con la cantidad de datos disponibles: no dice qué va a pasar, y en una crisis las correlaciones suelen subir de golpe (todo cae junto) aunque hayan sido bajas antes.',
    relatedTerms: ['correlacion', 'matrizcorr_causalidad', 'matrizcorr_solapamiento'],
  },
  matrizcorr_frecuencia: {
    title: 'Frecuencia de los datos',
    shortDescription: 'Diaria, semanal o mensual: cada cuánto se toma un precio para calcular los retornos que después se correlacionan.',
    whyItMatters: 'Con menos datos cargados por día, pedir una frecuencia muy fina puede dejar casi todas las celdas vacías en vez de mostrar un número poco confiable.',
    howToInterpret: 'Si con "Diaria" ves muchas celdas sin dato, probá "Semanal" o "Mensual": vas a perder algo de detalle pero vas a tener más observaciones por par.',
    limitations: 'Un precio sólo se usa si está lo bastante cerca de la fecha exacta que corresponde (más estricto cuanto más fina la frecuencia). Si no hay un precio suficientemente reciente, ese punto queda afuera en vez de inventarse con el último precio conocido.',
  },
  matrizcorr_moneda: {
    title: 'Moneda de esta pantalla',
    shortDescription: 'Todo se calcula en USD (dólar MEP): los precios en pesos se convierten a la fecha de cada punto antes de calcular el retorno.',
    whyItMatters: 'Si se comparara en pesos, buena parte de la correlación entre dos activos en pesos reflejaría simplemente el movimiento del dólar, no el de los activos en sí.',
  },
  matrizcorr_solapamiento: {
    title: 'Observaciones y solapamiento',
    shortDescription: 'Cuántos períodos con datos válidos tienen en común los dos instrumentos de un par, y qué porcentaje representan sobre el total de períodos posibles.',
    whyItMatters: 'Una correlación calculada con pocas observaciones es mucho menos confiable que una calculada con muchas, aunque el número final se vea igual de "redondo".',
    howToInterpret: 'Un solapamiento bajo (por ejemplo, porque uno de los dos instrumentos entró a la cartera hace poco) es una señal para tomar ese número con pinzas.',
  },
  matrizcorr_diversificacion: {
    title: 'Diversificación de la cartera',
    shortDescription: 'Lectura rápida del promedio de todas las correlaciones calculadas entre tus instrumentos.',
    howItIsCalculated: 'Promedio simple de los valores de correlación de todos los pares con estado "ok" (excluye la diagonal y los pares sin datos suficientes).',
    howToInterpret: 'Un promedio alto sugiere que tus posiciones tienden a moverse juntas (menos diversificación real de la que parece por la cantidad de tickers); uno bajo o negativo sugiere que se compensan entre sí.',
    limitations: 'Es un promedio simple, no ponderado por cuánto pesa cada instrumento en tu cartera.',
  },
  matrizcorr_causalidad: {
    title: 'Correlación no es causalidad',
    shortDescription: 'Que dos instrumentos se hayan movido parecido no significa que uno haya causado el movimiento del otro.',
    whyItMatters: 'Dos activos pueden moverse juntos por compartir un factor común (el mismo sector, la misma moneda, el ciclo económico general) sin que exista ninguna relación directa entre ellos.',
  },
  matrizcorr_min_obs: {
    title: 'Mínimo de observaciones',
    shortDescription: 'La cantidad mínima de períodos en común que exige la pantalla antes de mostrar un valor de correlación entre dos instrumentos.',
    whyItMatters: 'Con muy pocos datos, cualquier coincidencia o casualidad puede parecer una correlación fuerte. Este mínimo evita mostrar un número que en realidad no dice nada.',
    howToInterpret: 'Es más alto para frecuencias más finas (diaria) que para las más gruesas (mensual), porque hacen falta más puntos para que el resultado sea confiable.',
  },
}
