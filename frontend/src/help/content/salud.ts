import { HelpContent } from '../types'

export type SaludHelpKey =
  | 'salud_que_es'
  | 'salud_estados'
  | 'salud_dim_riesgo'
  | 'salud_dim_concentracion'
  | 'salud_dim_diversificacion'
  | 'salud_dim_liquidez'
  | 'salud_dim_costos'
  | 'salud_dim_vencimientos'
  | 'salud_dim_balance'
  | 'salud_dim_calidad_datos'
  | 'salud_exposicion_moneda'
  | 'salud_exposicion_tipo'
  | 'salud_precio_desactualizado'
  | 'salud_umbrales_configurables'
  | 'salud_indicador_patrimonio'
  | 'salud_indicador_rendimiento'
  | 'salud_indicador_drawdown'
  | 'salud_indicador_volatilidad'
  | 'salud_indicador_concentracion'
  | 'salud_indicador_diversificacion'
  | 'salud_indicador_liquidez'
  | 'salud_indicador_costos'
  | 'salud_indicador_calidad_datos'

export const SALUD_HELP: Record<SaludHelpKey, HelpContent> = {
  salud_que_es: {
    title: 'Salud de cartera',
    shortDescription: 'Un chequeo de 8 aspectos de tu cartera, cada uno con un estado (Normal / Atención / Revisar) y la regla exacta que lo produjo.',
    whyItMatters: 'A diferencia de un puntaje único, acá cada estado se explica solo: podés ver qué se midió, qué umbral se usó y de dónde sale el dato, sin tener que confiar en un número que combina todo.',
    limitations: 'No reemplaza a Diagnóstico (que sí da un score 0–100): son dos formas distintas de mirar lo mismo. Elegí la que te resulte más clara.',
    relatedTerms: ['diagnostico_salud_cartera'],
  },
  salud_estados: {
    title: 'Estados: Normal, Atención, Revisar',
    shortDescription: 'Cada dimensión se clasifica con una palabra, nunca sólo con un color, según reglas numéricas fijas y visibles.',
    whyItMatters: '"Normal" significa que no se detectó nada fuera de lo esperado; "Atención" que conviene mirarlo con calma; "Revisar" que hay algo que amerita una decisión pronto. "Sin datos" aparece cuando todavía no hay información suficiente para evaluar esa dimensión.',
  },
  salud_dim_riesgo: {
    title: 'Riesgo',
    shortDescription: 'Combina la caída máxima histórica (drawdown) y cuánto varía tu cartera mes a mes (volatilidad), ambas en USD.',
    whyItMatters: 'Te dice si tu cartera tuvo caídas fuertes o se mueve mucho, algo importante si no tolerás bien la incertidumbre.',
    howItIsCalculated: 'Usa los mismos cálculos que la pantalla Riesgo. Se toma el peor estado entre drawdown y volatilidad.',
    relatedTerms: ['drawdown', 'volatilidad'],
  },
  salud_dim_concentracion: {
    title: 'Concentración',
    shortDescription: 'Muestra cuánto depende tu cartera de pocos instrumentos: el peso de tu posición más grande y el índice HHI.',
    whyItMatters: 'Si una sola posición pesa mucho, un problema puntual con ese instrumento golpea fuerte a toda tu cartera.',
    howItIsCalculated: 'Usa el peso actual (Exposición › Ticker) y el HHI normalizado (Contribución). Si cargaste un "Peso Máximo" en la pestaña Configuración del Sheet, ese valor reemplaza el umbral por defecto.',
    relatedTerms: ['hhi'],
  },
  salud_dim_diversificacion: {
    title: 'Diversificación',
    shortDescription: 'Cuántas posiciones "equivalentes" tiene realmente tu cartera (N efectivo), más allá de la cantidad de tickers que tengas.',
    whyItMatters: 'Tener 20 tickers no sirve de mucho si 2 de ellos explican el 90% del valor: el N efectivo lo detecta.',
    howItIsCalculated: 'N efectivo = 1 / HHI normalizado (eje Ticker de Contribución). También suma si tenés un único tipo de instrumento.',
  },
  salud_dim_liquidez: {
    title: 'Liquidez',
    shortDescription: 'Qué parte de tu cartera podrías convertir en efectivo rápido y sin pérdida de valor.',
    whyItMatters: 'Sin liquidez, un imprevisto te puede obligar a vender en mal momento un instrumento que no querías tocar.',
    howItIsCalculated: 'Se considera líquida una posición cuyo tipo de instrumento sea "FCI", cuyo sector sea "Liquidez", o que venza en menos de 1 año. Es una aproximación: la app no tiene un campo de liquidez propio, así que se deriva de cómo etiquetaste tus instrumentos en el Sheet.',
    limitations: 'Si tenés efectivo fuera de la app (cuenta corriente, plazo fijo no cargado), esta dimensión no lo ve.',
  },
  salud_dim_costos: {
    title: 'Costos',
    shortDescription: 'Cuánto te cuesta operar, expresado como porcentaje anual de tu cartera.',
    whyItMatters: 'Comisiones altas erosionan el rendimiento de forma silenciosa, mes a mes.',
    howItIsCalculated: 'Comisiones de los últimos 12 meses, anualizadas, sobre el valor actual de la cartera. Mismo cálculo que usa Diagnóstico.',
    relatedTerms: ['comisiones_total_pagado'],
  },
  salud_dim_vencimientos: {
    title: 'Vencimientos',
    shortDescription: 'Cuándo vencen tus bonos, ONs o letras, y si hay que planificar qué hacer con ese dinero.',
    whyItMatters: 'Un vencimiento cercano sin plan puede dejarte con dinero ocioso o forzarte a decidir apurado dónde reinvertir.',
    limitations: 'Si no tenés instrumentos con fecha de vencimiento, esta dimensión no aplica.',
  },
  salud_dim_balance: {
    title: 'Balance vs. objetivo',
    shortDescription: 'Qué tan lejos está tu cartera de los porcentajes objetivo que vos mismo definiste (por tipo, sector, ticker, etc.).',
    whyItMatters: 'Si definiste un objetivo (por ejemplo 60% acciones / 40% bonos) y la cartera se desvía mucho, puede ser momento de rebalancear.',
    howItIsCalculated: 'Compara el % actual contra el % objetivo cargado en la pestaña Rebalanceo del Sheet, con la tolerancia configurada.',
    limitations: 'Si no cargaste objetivos en esa pestaña, esta dimensión queda "sin datos".',
    relatedTerms: ['rebalanceo'],
  },
  salud_dim_calidad_datos: {
    title: 'Calidad de datos',
    shortDescription: 'Qué tan limpios y completos llegaron tus datos en la última sincronización con el Sheet/Excel.',
    whyItMatters: 'Si faltan precios, sectores o países, el resto de las dimensiones puede estar calculando con información incompleta.',
    howItIsCalculated: 'Combina el resultado del último sync con si hay posiciones sin precio, con precio de más de 45 días, o sin sector/país.',
    limitations: 'Es la única dimensión que no cambia según la cartera elegida: el sync es uno solo para todo el Sheet.',
  },
  salud_exposicion_moneda: {
    title: 'Exposición ARS / USD',
    shortDescription: 'Qué parte de tu cartera está denominada en pesos y qué parte en dólares.',
    whyItMatters: 'Te ayuda a saber cuánto de tu patrimonio sigue al dólar y cuánto queda expuesto a la inflación en pesos.',
  },
  salud_exposicion_tipo: {
    title: 'Exposición por tipo de instrumento',
    shortDescription: 'Qué parte de tu cartera está en acciones, CEDEARs, bonos, FCI, etc.',
    whyItMatters: 'Cada tipo de instrumento tiene un perfil de riesgo distinto; ver la mezcla te ayuda a saber a qué estás expuesto.',
  },
  salud_precio_desactualizado: {
    title: 'Precio desactualizado',
    shortDescription: 'El último precio cargado para ese instrumento tiene más de 45 días.',
    whyItMatters: 'Un precio viejo puede hacer que el valor mostrado de esa posición esté lejos del valor real de mercado.',
    limitations: 'Actualizalo cargando un precio más reciente en la pestaña Precios del Sheet, o esperando a que la app lo traiga automáticamente si el ticker tiene fuente de mercado.',
  },
  salud_umbrales_configurables: {
    title: 'Umbrales configurables',
    shortDescription: 'El umbral de concentración por ticker usa el "Peso Máximo" que hayas cargado en Configuración; si no cargaste nada, se usa un valor por defecto.',
    whyItMatters: 'Así podés ajustar qué es "demasiado concentrado" según tu propio criterio, sin que la app lo defina por vos.',
  },
  salud_indicador_patrimonio: {
    title: 'Patrimonio',
    shortDescription: 'Valor actual de la cartera, a precios de hoy.',
    relatedTerms: ['patrimonio_valor_mercado'],
  },
  salud_indicador_rendimiento: {
    title: 'Rendimiento (TWR)',
    shortDescription: 'Rendimiento ponderado en el tiempo, en dólares, que aísla el efecto de tus aportes y retiros.',
    relatedTerms: ['twr'],
  },
  salud_indicador_drawdown: {
    title: 'Drawdown máximo',
    shortDescription: 'La mayor caída que tuvo tu cartera desde su punto más alto histórico, en dólares.',
    relatedTerms: ['drawdown'],
  },
  salud_indicador_volatilidad: {
    title: 'Volatilidad anualizada',
    shortDescription: 'Cuánto varían mes a mes los rendimientos de tu cartera, expresado en términos anuales.',
    relatedTerms: ['volatilidad'],
  },
  salud_indicador_concentracion: {
    title: 'Concentración',
    shortDescription: 'Tu posición más grande y qué porcentaje de la cartera representa.',
  },
  salud_indicador_diversificacion: {
    title: 'Diversificación',
    shortDescription: 'Cantidad de posiciones "equivalentes" (N efectivo) que tiene tu cartera.',
  },
  salud_indicador_liquidez: {
    title: 'Liquidez',
    shortDescription: 'Porcentaje de la cartera en instrumentos fácilmente convertibles en efectivo.',
  },
  salud_indicador_costos: {
    title: 'Costos anuales',
    shortDescription: 'Comisiones de los últimos 12 meses, anualizadas, como porcentaje de la cartera.',
  },
  salud_indicador_calidad_datos: {
    title: 'Calidad de datos',
    shortDescription: 'Health score y resultado de la última sincronización con tu Sheet/Excel.',
  },
}
