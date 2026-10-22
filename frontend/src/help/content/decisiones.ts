import { HelpContent } from '../types'

export type DecisionesHelpKey =
  | 'decisiones_que_es'
  | 'decisiones_orden'
  | 'decisiones_pesos'
  | 'decisiones_fundamentales'
  | 'decisiones_valoracion'
  | 'decisiones_riesgo'
  | 'decisiones_tecnico'
  | 'decisiones_encaje'
  | 'decisiones_banderas'
  | 'decisiones_alternativas'
  | 'decisiones_escenarios'
  | 'decisiones_invalidacion'
  | 'decisiones_conclusion'
  | 'decisiones_posicion'
  | 'decisiones_simulador'
  | 'decisiones_diario'
  | 'decisiones_revision'
  | 'decisiones_aprendizaje'
  | 'decisiones_volatilidad'
  | 'decisiones_caida_maxima'
  | 'decisiones_beta'
  | 'decisiones_atr'

export const DECISIONES_HELP: Record<DecisionesHelpKey, HelpContent> = {
  decisiones_que_es: {
    title: 'Centro de Decisiones',
    shortDescription: 'Junta en un solo lugar lo que la app ya calcula de un activo para ayudarte a decidir con fundamento y a revisar después cómo te fue.',
    whyItMatters: 'Una decisión mezcla muchas cosas: si el negocio es bueno, si el precio es razonable, cuánto riesgo tiene, cómo queda tu cartera. Verlas juntas y por separado evita decidir por un solo dato.',
    howToInterpret: 'Todo lo que ves sale de reglas fijas sobre datos con fecha. Nada es una orden de operar: es material para pensar.',
    limitations: 'No hay inteligencia artificial generando textos ni cifras: los textos son plantillas que sólo usan números calculados. Bonos, ONs y FCI no se analizan acá.',
  },
  decisiones_orden: {
    title: 'Puntaje de orden',
    shortDescription: 'Un número de 0 a 100 que sirve para ordenar qué mirar primero. No reemplaza leer las dimensiones.',
    howItIsCalculated: 'Promedio ponderado de los puntajes de las cinco dimensiones que tienen dato. Si las que tienen dato suman menos del 60 % del peso, o los datos son poco confiables, no se calcula: dice "incompleto".',
    howToInterpret: 'Más alto = mejor ubicado con tus preferencias. Dos activos a menos de 10 puntos son, en la práctica, parecidos.',
    limitations: 'Un faltante nunca cuenta como cero. Un puntaje alto puede convivir con una bandera crítica: mirá siempre las banderas.',
    relatedTerms: ['decisiones_pesos', 'decisiones_banderas'],
  },
  decisiones_pesos: {
    title: 'Pesos de las dimensiones',
    shortDescription: 'Cuánto cuenta cada dimensión en el puntaje de orden, según tu enfoque y horizonte.',
    howItIsCalculated: 'Salen de una tabla por enfoque (fundamental, técnico, combinado) y horizonte (corto, mediano, largo). A más largo el horizonte, menos pesa el técnico. Con tolerancia baja al riesgo, Riesgo pesa 1,5 veces; con alta, la mitad.',
    howToInterpret: 'Son una decisión de diseño, no una verdad financiera. Podés cambiarlos en Preferencias.',
    limitations: 'Si el primero cambia cuando probás otro enfoque, la conclusión dice que "depende de supuestos".',
  },
  decisiones_fundamentales: {
    title: 'Fundamentales',
    shortDescription: 'La calidad del negocio: márgenes y retornos, crecimiento y solidez financiera.',
    howItIsCalculated: 'Promedio de las dimensiones calidad, crecimiento y solidez del diagnóstico de empresa, cada una con su percentil contra sus pares (100 = la mejor del grupo).',
    howToInterpret: 'Alto: negocio mejor que el de sus pares en lo que Yahoo informa. Bajo: más débil o más frágil.',
    limitations: 'Sólo hay el último trimestre contra el mismo del año anterior: la consistencia de varios años no se evalúa. No aplica a ETFs.',
    relatedTerms: ['diagnostico_calidad', 'diagnostico_solidez'],
  },
  decisiones_valoracion: {
    title: 'Valoración',
    shortDescription: 'Qué tan caro o barato está el precio frente a sus pares. No dice nada de la calidad del negocio.',
    howItIsCalculated: 'Percentil favorable de la valuación contra el grupo de pares (100 = la más barata). El valor razonable por múltiplos ajusta ±5 puntos porque sale de los mismos múltiplos (si contara aparte, se contaría dos veces).',
    howToInterpret: 'Una empresa puede ser excelente y estar cara, o barata por un buen motivo (problemas que el mercado ya ve).',
    limitations: 'Es relativa a los pares, no un valor intrínseco.',
    relatedTerms: ['valuacion_percentil', 'valor_razonable_que_es', 'valuacion_trampa_valor'],
  },
  decisiones_riesgo: {
    title: 'Riesgo',
    shortDescription: 'Cuánto se movió y cuánto llegó a caer el precio en el pasado, y su sensibilidad al mercado.',
    howItIsCalculated: 'Promedio de tres medidas con bandas fijas: volatilidad anual, caída máxima de la serie semanal (~5 años, en USD) y beta. Más alto = menos riesgo.',
    howToInterpret: 'Un puntaje bajo indica que históricamente tuvo caídas grandes o movimientos bruscos.',
    limitations: 'Es riesgo histórico: no predice el futuro. El riesgo de divisa se informa aparte y no cambia el puntaje.',
    relatedTerms: ['decisiones_volatilidad', 'decisiones_caida_maxima', 'decisiones_beta'],
  },
  decisiones_tecnico: {
    title: 'Técnico',
    shortDescription: 'El momento del precio: tendencia, RSI y fuerza relativa contra su índice.',
    howItIsCalculated: 'Tendencia contra la media de 50 ruedas, RSI de 14 ruedas y fuerza relativa de 63 ruedas, con puntajes fijos por estado.',
    howToInterpret: 'Es una lectura de semanas, no de años: no cambia las conclusiones de fundamentales.',
    limitations: 'Sólo se calcula para activos de tu cartera o tu watchlist (necesita la serie diaria).',
  },
  decisiones_encaje: {
    title: 'Encaje con tu cartera',
    shortDescription: 'Cómo quedaría tu cartera si sumaras un monto de referencia de este activo.',
    howItIsCalculated: 'Parte de 60 y resta por cada observación de concentración del simulador (umbrales de Salud de cartera). Con objetivo ingresos suma o resta por el dividendo; con diversificación, por sector o país nuevos.',
    howToInterpret: 'Bajo: con ese monto la cartera se concentraría demasiado.',
    limitations: 'El monto de referencia por defecto es el 5 % de la cartera.',
  },
  decisiones_banderas: {
    title: 'Banderas críticas',
    shortDescription: 'Riesgos que se muestran siempre, aunque el puntaje sea alto.',
    howItIsCalculated: 'Solidez en riesgo, pérdidas, ingresos cayendo, payout mayor al 100 %, datos o cotización viejos, concentración en "revisar", confianza baja de los datos, riesgo alto para tu tolerancia.',
    howToInterpret: 'Las de severidad alta cambian la conclusión a "riesgo elevado".',
  },
  decisiones_alternativas: {
    title: 'Alternativas comparables',
    shortDescription: 'Otras empresas parecidas, evaluadas con la misma metodología.',
    howItIsCalculated: 'Salen del comparador de alternativas (misma industria, tamaño y región; se descartan ETFs frente a empresas y modelos de negocio distintos). Cada una se diagnostica contra las demás del grupo.',
    howToInterpret: 'Que una alternativa supere en un ratio no la hace mejor: la conclusión pide al menos 10 puntos de diferencia, sin banderas críticas y el mismo resultado con otros pesos.',
    limitations: 'Si comparan balances de trimestres distintos, se avisa.',
    relatedTerms: ['comparador_comparabilidad'],
  },
  decisiones_escenarios: {
    title: 'Escenarios de entrada',
    shortDescription: 'Entrar ahora, esperar una condición técnica o de precio, escalonar o descartar, con sus números.',
    howItIsCalculated: 'Potencial = (valor razonable − precio de entrada) ÷ precio de entrada, contra los valores pesimista, base y optimista de los pares. Riesgo = distancia a la invalidación.',
    howToInterpret: 'Son escenarios hipotéticos, no predicciones ni rendimientos esperados.',
    limitations: 'Sin serie diaria no hay ATR ni soporte, y el escenario lo dice en vez de inventar un nivel.',
    relatedTerms: ['decisiones_atr', 'decisiones_invalidacion'],
  },
  decisiones_invalidacion: {
    title: 'Condición de invalidación',
    shortDescription: 'El precio o el cambio de datos que haría dejar de sostener la idea.',
    howItIsCalculated: 'Precio: soporte − 1 ATR (o entrada − 2 ATR sin soporte). Datos: Fundamentales o Valoración por debajo de 35.',
    howToInterpret: 'Definirla antes de decidir evita justificar después cualquier caída.',
  },
  decisiones_conclusion: {
    title: 'Conclusión',
    shortDescription: 'Una lectura por reglas: alternativa relativamente más atractiva, oportunidad pendiente de condiciones, valoración exigente, riesgo elevado, datos insuficientes o ninguna claramente superior.',
    howToInterpret: 'Siempre trae la evidencia en contra y qué la invalidaría. "Ninguna claramente superior" es una respuesta válida.',
  },
  decisiones_posicion: {
    title: 'Evaluar una posición',
    shortDescription: 'Mantener, aumentar, reducir o salir: la evidencia a favor y en contra de cada opción.',
    howToInterpret: 'Son opciones para evaluar, no órdenes. La ganancia o pérdida de la posición no se usa como argumento: describe el pasado, no lo que conviene desde hoy.',
  },
  decisiones_simulador: {
    title: 'Simulador de decisiones',
    shortDescription: 'Cómo quedaría tu cartera con una o varias operaciones hipotéticas, sin tocar nada real.',
    howItIsCalculated: 'Montos en USD: positivos suman, negativos reducen una tenencia. Lo liberado y no reasignado queda como liquidez.',
    limitations: 'Los impuestos no se calculan. La comisión se estima con tu tasa histórica.',
  },
  decisiones_diario: {
    title: 'Diario de decisiones',
    shortDescription: 'Cada decisión guardada con lo que la app concluía ese día, para revisarla después.',
    howToInterpret: 'Lo calculado queda congelado; sólo editás tu nota, si la llevaste a cabo, la fecha de revisión y si está cerrada.',
  },
  decisiones_revision: {
    title: 'Revisión de una decisión',
    shortDescription: 'Compara la foto del día de la decisión con el análisis de hoy: precio, índice, alternativas, dimensiones y supuestos.',
    limitations: 'El resultado sólo se muestra si marcaste la decisión como ejecutada, y es una aproximación por precio.',
  },
  decisiones_aprendizaje: {
    title: 'Aprendizaje',
    shortDescription: 'Patrones de tu proceso de decisión: si revisás, si definís cómo invalidar, si seguís el análisis.',
    howToInterpret: 'Con menos de 3 casos no se dice nada; de 3 a 9 es un patrón descriptivo; desde 10, un patrón repetido.',
    limitations: 'No son conclusiones estadísticas ni diagnósticos de sesgos.',
  },
  decisiones_volatilidad: {
    title: 'Volatilidad anual',
    shortDescription: 'Cuánto suele moverse el precio en un año.',
    howItIsCalculated: 'Desvío estándar de los retornos semanales × √52.',
    howToInterpret: 'Bajo 25 %: moderada. Sobre 40 %: alta.',
    limitations: 'Una volatilidad baja en el pasado no garantiza calma futura.',
  },
  decisiones_caida_maxima: {
    title: 'Caída máxima',
    shortDescription: 'La peor caída desde un máximo previo en la serie disponible.',
    howToInterpret: 'Te da una idea de cuánto podrías tener que aguantar.',
  },
  decisiones_beta: {
    title: 'Beta',
    shortDescription: 'Cuánto se mueve el activo cuando se mueve el mercado (informado por Yahoo).',
    howToInterpret: '1 = como el mercado; más de 1,5 = mucho más sensible.',
  },
  decisiones_atr: {
    title: 'ATR (rango verdadero promedio)',
    shortDescription: 'El movimiento diario típico del precio, en su misma moneda.',
    howItIsCalculated: 'Promedio de Wilder de 14 ruedas del rango verdadero de cada vela.',
    howToInterpret: 'Se usa para ubicar la invalidación lejos del ruido diario.',
  },
}
