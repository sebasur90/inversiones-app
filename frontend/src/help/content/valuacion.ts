import { HelpContent } from '../types'

export type ValuacionHelpKey =
  | 'valuacion_que_es'
  | 'valuacion_percentil'
  | 'valuacion_trampa_valor'
  | 'valuacion_pares_criterio'
  | 'valuacion_fuentes'

export const VALUACION_HELP: Record<ValuacionHelpKey, HelpContent> = {
  valuacion_que_es: {
    title: 'Valuación contra pares',
    shortDescription:
      'Compara cada acción, CEDEAR o ETF contra empresas o fondos parecidos (sus "pares": misma industria y tamaño similar) y dice si cotiza más barato, más caro o en línea con ellos.',
    whyItMatters:
      'Un P/E de 25 no dice nada solo: en bebidas puede ser caro y en software barato. Lo que sirve es compararlo contra competidores directos. Por eso la pantalla no da un puntaje: muestra dónde cae cada métrica dentro del grupo y la regla que produce la lectura.',
    howToInterpret:
      '"Más barata que sus pares" significa que en al menos dos métricas de valuación está entre el 25% más barato del grupo y en ninguna entre el 25% más caro. "Barata, con señales de alerta" es lo mismo pero con calidad, crecimiento o precio en el piso del grupo: puede estar barata por una buena razón.',
    limitations:
      'Es un punto de partida para investigar, no una recomendación de compra o venta. Los datos salen de Yahoo y pueden tener errores o estar atrasados (se indica la fecha). Bonos, ONs, letras y FCI todavía no se comparan.',
    relatedTerms: ['valuacion_percentil', 'valuacion_trampa_valor', 'valuacion_pares_criterio', 'per', 'evEbitda'],
  },
  valuacion_percentil: {
    title: 'Percentil dentro del grupo',
    shortDescription:
      'Dónde cae el ticker entre sus pares en una métrica, de 0 a 100. Acá está orientado para que 100 sea siempre lo mejor: en valuación, lo más barato; en márgenes o crecimiento, lo más alto.',
    howItIsCalculated:
      'Se ordena el grupo (el ticker más sus pares) y se mira la posición del ticker, contando la mitad de los empates. Con 5 o más valores, los extremos raros se recortan (más allá de 3 veces el rango intercuartil) para que un dato absurdo no aplaste al resto. Con menos de 3 valores no se calcula.',
    howToInterpret:
      'La barra va de peor (izquierda) a mejor (derecha). La franja del medio es el 50% central: ahí está "en línea". 75 o más es "mejor" (en valuación, "más barata"); 25 o menos es "peor" ("más cara").',
    limitations:
      'Con un solo par con datos no hay grupo para ordenar: se compara directo contra ese par, y cuenta como "mejor" o "peor" una diferencia de al menos 15% (o 2 puntos en las métricas en %). La ficha lo avisa.',
  },
  valuacion_trampa_valor: {
    title: 'Trampa de valor',
    shortDescription:
      'Una acción que parece barata porque el mercado espera que le vaya mal. Los múltiplos bajos no son una oportunidad si las ganancias van a caer.',
    howItIsCalculated:
      'Se marca cuando la lectura sería "barata" pero además: dos o más métricas de calidad (márgenes, ROE, ROA, deuda) están en el 25% peor del grupo, los ingresos caen contra el año anterior, el precio en 12 meses quedó en el 25% peor de sus pares, o la empresa no tiene ganancias.',
    howToInterpret:
      'No significa que sea mala inversión: significa que lo barato tiene una explicación probable que conviene entender antes de comprar.',
  },
  valuacion_pares_criterio: {
    title: 'Cómo se eligen los pares',
    shortDescription:
      'Acciones: misma industria según Yahoo y tamaño parecido (valor de mercado entre 0,2 y 5 veces). Si no alcanzan 4, se amplía el rango de tamaño, después se saca, y por último se completa con el mismo sector. ETFs: misma categoría, ordenados por patrimonio.',
    whyItMatters:
      'El universo es todo el catálogo de CEDEARs y acciones de IOL, así que el competidor aparece aunque no lo tengas ni lo sigas. Entre empresas de distinta región, se prefieren las de la misma (un banco argentino se compara primero con bancos argentinos).',
    howToInterpret:
      'Si falta un competidor obvio o sobra uno que no tiene nada que ver, corregilo desde "Editar": tus cambios quedan guardados y valen en adelante.',
  },
  valuacion_fuentes: {
    title: 'De dónde sale la clasificación',
    shortDescription:
      'Cada dato (tipo, sector, industria, país, región) puede venir de cuatro lugares, y gana el primero que tenga valor: tu corrección manual, una corrección incluida en la app, Yahoo, o la ficha del Sheet.',
    whyItMatters:
      'Antes sector y país salían sólo del Sheet, escritos a mano (y un CEDEAR de Coca-Cola figuraba como "AR"). Ahora Exposición, Descomposición, Balance y Salud usan esta clasificación, así que corregir algo acá lo corrige en todas.',
    limitations:
      'Para bonos, ONs, letras y FCI sigue mandando el Sheet. Un sector "Liquidez" del Sheet se respeta siempre: marca un FCI que usás como caja.',
  },
}
