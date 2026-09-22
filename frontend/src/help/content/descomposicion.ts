import { HelpContent } from '../types'

export type DescomposicionHelpKey =
  | 'descomposicion_familia'
  | 'descomposicion_nivel'
  | 'descomposicion_porcentaje'
  | 'descomposicion_sin_clasificar'
  | 'descomposicion_unidad'

export const DESCOMPOSICION_HELP: Record<DescomposicionHelpKey, HelpContent> = {
  descomposicion_familia: {
    title: 'Familia',
    shortDescription: 'Renta fija, Renta variable, Fondos o Liquidez: una agrupación derivada del "Tipo Instrumento" y el "Sector" que cargaste en el Sheet, no un dato que se carga a mano.',
    whyItMatters: 'Es el primer corte para entender de qué está hecha tu cartera, antes de bajar a país, sector o ticker puntual.',
    howItIsCalculated: 'Se deriva así, en orden: si el Sector contiene "Liquidez" → Liquidez (gana sobre el tipo); si el Tipo es un FCI → Fondos; si es un bono/ON/letra → Renta fija; si es una acción/CEDEAR → Renta variable; el resto → Otros. Un ticker sin ficha en Instrumentos cae en "Sin clasificar".',
    example: 'Un FCI Money Market con Sector="Liquidez" en el Sheet aparece en "Liquidez", no en "Fondos": el dato explícito que vos cargaste manda sobre la heurística.',
    limitations: 'No existe una columna "Familia" en el Sheet: es texto libre reinterpretado. Si tenés un instrumento raro que no matchea ningún patrón conocido, cae en "Otros".',
    relatedTerms: ['descomposicion_sin_clasificar'],
  },
  descomposicion_nivel: {
    title: 'Niveles de la descomposición',
    shortDescription: 'El árbol tiene siempre el mismo orden: Familia → País → Sector → Ticker.',
    whyItMatters: 'Ir de lo general a lo particular ayuda a entender la composición sin perderse entre docenas de tickers sueltos.',
    howToInterpret: 'Tocá una categoría para entrar a su detalle; usá el camino de arriba ("Cartera › … ") para volver a un nivel anterior.',
  },
  descomposicion_porcentaje: {
    title: '% sobre el total vs. % del grupo',
    shortDescription: 'En modo "%" se muestra el peso de cada categoría dentro de su grupo (los hermanos de ese nivel suman 100%).',
    whyItMatters: 'Es distinto de "cuánto pesa esto en toda mi cartera": una categoría puede ser el 100% de su grupo y sólo el 5% del total, si el grupo en sí es chico.',
    example: 'Si "Tecnología" es 40% dentro de "Renta variable" y "Renta variable" es 60% del total, Tecnología pesa 24% de la cartera completa, aunque acá se vea 40%.',
  },
  descomposicion_sin_clasificar: {
    title: 'Sin clasificar',
    shortDescription: 'Agrupa lo que falta completar en el Sheet: un ticker sin ficha en Instrumentos, o con País/Sector vacío.',
    whyItMatters: 'La app nunca inventa un país o un sector: si no está en tu Sheet, se muestra así, explícitamente, en vez de adivinarlo.',
    howToInterpret: 'Completá la columna correspondiente (Tipo Instrumento, País o Sector) en la hoja Instrumentos y sincronizá para que deje de aparecer acá.',
  },
  descomposicion_unidad: {
    title: 'Ver en % / ARS / USD',
    shortDescription: 'Cambia cómo se muestran los valores de esta pantalla: porcentaje del grupo, pesos o dólares.',
    whyItMatters: 'Es independiente del selector ARS/USD de arriba de la pantalla, que fija la moneda de referencia de toda la app.',
  },
}
