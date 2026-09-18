import { HelpContent } from '../types'

export type AportesHelpKey =
  | 'aportes_neto_criterio'
  | 'aportes_mes_en_curso'
  | 'aportes_proyeccion_mes'
  | 'aportes_estado_ritmo'
  | 'aportes_racha'
  | 'aportes_promedio'
  | 'aportes_promedio_movil'
  | 'aportes_constancia'
  | 'aportes_proyeccion_fin_anio'
  | 'aportes_hitos'
  | 'aportes_mismo_periodo'
  | 'aportes_moneda'

export const APORTES_HELP: Record<AportesHelpKey, HelpContent> = {
  aportes_neto_criterio: {
    title: 'Aporte neto del mes',
    shortDescription: 'La plata nueva que pusiste en tus inversiones ese mes: compras menos ventas y amortizaciones.',
    howItIsCalculated:
      'Se suman las compras y se restan las ventas y amortizaciones del mes, con la comisión incluida, convertidas a USD al dólar MEP del día de cada movimiento. Los dividendos y cupones no cuentan: son rendimiento, no capital tuyo (si los reinvertís, la compra ya los registra). Es el mismo criterio de "capital aportado" de Patrimonio y Objetivo.',
    howToInterpret:
      'Un mes en cero es un mes en que no aportaste. Un mes negativo es un retiro neto: sacaste más de lo que pusiste. Una rotación (vender A para comprar B) se cancela sola y no cuenta como aporte.',
    limitations:
      'Si un movimiento en pesos no tiene tipo de cambio para su fecha, no se puede convertir y queda afuera; la pantalla avisa cuántos son.',
    relatedTerms: ['mep', 'patrimonio_capital_aportado', 'objetivo_aporte_mensual'],
  },
  aportes_mes_en_curso: {
    title: 'Mes en curso',
    shortDescription: 'El mes actual está incompleto, así que se muestra aparte y no entra en promedios ni récords.',
    whyItMatters:
      'Si el día 3 compararas lo que llevás aportado contra un mes entero, siempre saldrías perdiendo. Por eso el mes en curso se compara por su proyección al ritmo actual y no por lo acumulado hasta hoy.',
    howToInterpret:
      'En las rachas, el mes en curso suma si ya tiene aporte y no la corta si todavía está en cero: recién se corta cuando termina un mes sin aportar.',
  },
  aportes_proyeccion_mes: {
    title: 'Al ritmo actual',
    shortDescription: 'Cómo terminaría el mes si seguís aportando al mismo ritmo diario que hasta hoy.',
    howItIsCalculated: 'Lo aportado hasta hoy × días del mes ÷ días transcurridos.',
    example: 'Si al día 15 de un mes de 30 llevás USD 250, al ritmo actual cerrás en USD 500.',
    limitations:
      'Antes del día 7 la proyección es una "estimación temprana": un solo aporte grande al principio del mes la dispara. Si aportás una vez por mes (por ejemplo al cobrar), el ritmo diario tiene poco sentido hasta que hagas ese aporte.',
  },
  aportes_estado_ritmo: {
    title: 'Estado del ritmo',
    shortDescription: 'En una palabra: ¿estás aportando más, igual o menos que hace unos meses?',
    howItIsCalculated:
      'Compara el promedio de tus últimos 3 meses cerrados contra el de los 3 anteriores. Acelerando: más de 15% arriba. Frenando: más de 15% abajo. Sostenido: entre medio. Parado: sin aporte neto en los últimos 3 meses ni en lo que va de este. Arrancando: menos de 4 meses cerrados, todavía no hay con qué comparar.',
    howToInterpret:
      'No es una meta: es tu propio ritmo comparado con tu propio ritmo anterior. "Frenando" con aportes altos puede ser sólo un trimestre excepcional que no se repitió; mirá el calendario para ver qué meses bajaron.',
    limitations: 'Con un solo mes muy grande (un aguinaldo, una venta reinvertida) la comparación de trimestres se distorsiona por unos meses.',
  },
  aportes_racha: {
    title: 'Racha de aportes',
    shortDescription: 'Cuántos meses seguidos llevás con aporte neto positivo.',
    howItIsCalculated:
      'Se cuentan hacia atrás los meses cerrados con aporte mayor a cero, sin saltear meses. El mes en curso suma si ya aportaste y no corta la racha si todavía no. El récord es la racha más larga de tu historial.',
    howToInterpret: 'La constancia importa más que el monto: doce meses de USD 200 suman más que un mes de USD 1.000 seguido de once en cero.',
  },
  aportes_promedio: {
    title: 'Promedio de 3, 6 y 12 meses',
    shortDescription: 'Cuánto venís aportando por mes en el último tiempo.',
    howItIsCalculated:
      'Promedio simple de los últimos N meses cerrados, contando los meses en cero como cero. Si no tenés N meses de historial, aparece "Datos insuficientes" en vez de un número engañoso.',
    howToInterpret: 'Si el promedio de 3 está arriba del de 12, venís acelerando; si está abajo, frenando.',
  },
  aportes_promedio_movil: {
    title: 'Promedio móvil de 3 meses',
    shortDescription: 'La línea que suaviza las barras: cada punto es el promedio de ese mes y los dos anteriores.',
    whyItMatters: 'Un mes aislado puede ser raro; la línea muestra la tendencia sin el ruido mes a mes.',
    howItIsCalculated: 'Para el mes en curso usa la proyección al ritmo actual en vez de lo acumulado, así la línea no se desploma al principio de cada mes.',
  },
  aportes_constancia: {
    title: 'Constancia',
    shortDescription: 'Qué tan parejos son tus aportes mes a mes.',
    howItIsCalculated:
      'Desvío estándar de los aportes mensuales cerrados, dividido por el promedio (coeficiente de variación). Menos de 0,5: constante. Entre 0,5 y 1: irregular. Más de 1: muy irregular. Necesita al menos 6 meses cerrados.',
    howToInterpret:
      'El número que se muestra es el desvío en USD: "± USD 150" quiere decir que un mes típico se aleja unos USD 150 de tu promedio. Ser irregular no es malo si aportás cuando podés; es información, no una nota.',
  },
  aportes_proyeccion_fin_anio: {
    title: 'Proyección a fin de año',
    shortDescription: 'Cuánto habrías aportado al 31 de diciembre si mantenés cierto ritmo.',
    howItIsCalculated:
      'Tres escenarios: (1) al ritmo de este mes: lo aportado en los meses ya cerrados del año + la proyección del mes actual × los meses que quedan (incluido éste); (2) al promedio de los últimos 3 meses; (3) al promedio del año. En (2) y (3), el mes en curso aporta lo que ya pusiste o el ritmo, lo que sea mayor: lo ya aportado nunca se descuenta.',
    example: 'Con USD 800 en 8 meses cerrados, USD 60 en lo que va de septiembre y un ritmo de USD 100/mes, cerrás el año con USD 1.200.',
    limitations: 'Son proyecciones lineales de tu propio ritmo, no una meta ni una recomendación.',
  },
  aportes_hitos: {
    title: 'Logros',
    shortDescription: 'Hitos que ya alcanzaste con tus aportes, y cuánto falta para el siguiente.',
    howItIsCalculated:
      'Capital aportado neto acumulado (USD 5.000, 10.000, 25.000, 50.000, 100.000…), rachas de meses seguidos aportando (3, 6, 12, 24, 36), tu récord mensual, y "tu mejor año" cuando el año en curso ya superó al mejor anterior. Un hito alcanzado se conserva aunque después retires plata.',
    howToInterpret: 'Los hitos de los últimos dos meses se destacan como "Nuevo".',
  },
  aportes_mismo_periodo: {
    title: 'Mismo período del año pasado',
    shortDescription: 'Compara este mes (o lo que va del año) contra el mismo momento del año anterior.',
    howItIsCalculated:
      'Para el mes: el aporte del mismo mes del año pasado contra tu proyección de este mes. Para el año: lo aportado hasta hoy contra lo que llevabas el año pasado a esta misma altura, con el mes equivalente prorrateado al día.',
    howToInterpret: 'Sirve para ver si estás por delante o por detrás de vos mismo hace un año, sin importar la meta.',
  },
  aportes_moneda: {
    title: 'Sólo en USD',
    shortDescription: 'Esta pantalla no cambia con el selector de moneda: todo está en dólares MEP.',
    whyItMatters:
      'Comparar meses en pesos nominales entre años mide inflación, no ritmo de ahorro: USD 500 de hace dos años y USD 500 de hoy son el mismo esfuerzo, pero en pesos el segundo parecería mucho mayor. Cada movimiento se convierte al dólar MEP del día en que lo hiciste.',
    relatedTerms: ['mep'],
  },
}
