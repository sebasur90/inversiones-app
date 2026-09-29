import { HelpContent } from '../types'

// Prefijo "comparador_" compartido con `comparador.ts` (el comparador de precios de /comparar):
// no hay colisión porque las claves puntuales son distintas, pero es a propósito que ambos hablen
// de "comparar" — son la misma familia de pantalla, sobre datos distintos.
export type ComparadorEstrategiasHelpKey =
  | 'comparador_simulado'
  | 'comparador_puntos_porcentuales'
  | 'comparador_referencia'
  | 'comparador_capital_final'
  | 'comparador_diferencia_monetaria'
  | 'comparador_tiempo_invertido'
  | 'comparador_divergencias'
  | 'comparador_costos'
  | 'comparador_limitaciones'

export const COMPARADORESTRATEGIAS_HELP: Record<ComparadorEstrategiasHelpKey, HelpContent> = {
  comparador_simulado: {
    title: 'Simulado / Backtest',
    shortDescription: 'Todo en esta pantalla es un backtest: cómo les habría ido a estas estrategias sobre el historial de precios disponible. No es una posición real ni una sugerencia de qué comprar.',
    whyItMatters: 'Corre exactamente el mismo motor que el backtest de Análisis técnico, sólo que varias estrategias a la vez, sobre el mismo ticker y período, para que la comparación sea pareja.',
    limitations: 'Es explicativa, no prescriptiva: dice "según los datos históricos disponibles, estas fueron las diferencias", nunca "esta es la mejor estrategia para comprar este instrumento". Rendimiento pasado no garantiza nada sobre el futuro.',
    relatedTerms: ['analisis_tecnico_backtest', 'comparador_limitaciones'],
  },
  comparador_puntos_porcentuales: {
    title: 'Puntos porcentuales (pp)',
    shortDescription: 'La resta directa entre dos retornos expresados en %, no una razón entre ellos: 15% − 5% = 10 pp de diferencia.',
    whyItMatters: 'Es intuitivo pero engañoso si se lee como "el doble": 10 pp de diferencia sobre una base de 5% es un resultado muy distinto a 10 pp sobre una base de 50%. Por eso la pantalla también muestra la diferencia en dinero y la diferencia relativa (%) por separado, sin mezclarlas.',
    howItIsCalculated: 'retorno de la estrategia (%) − retorno de la referencia (%).',
  },
  comparador_referencia: {
    title: 'Referencia',
    shortDescription: 'Contra qué se mide la diferencia de cada estrategia: por defecto "Comprar y mantener" (Buy & Hold), o cualquiera de las estrategias que elegiste comparar.',
    whyItMatters: 'Cambiar la referencia no cambia los resultados de cada estrategia, sólo la vara con la que se las compara: todas las columnas de "diferencia" y los tramos de divergencia se recalculan contra la nueva referencia.',
    howToInterpret: 'Con "Comprar y mantener" como referencia, un valor positivo dice "superó a quedarse quieto sin operar"; con otra estrategia como referencia, dice "superó a esa otra regla".',
  },
  comparador_capital_final: {
    title: 'Capital final',
    shortDescription: 'El capital inicial que definiste, aplicado al retorno % de cada estrategia sobre el período elegido.',
    howItIsCalculated: 'capital_inicial × (1 + retorno_total_% / 100). Es una cuenta lineal a partir del retorno porcentual: no simula sizing, apalancamiento ni reinversión parcial (el motor es long-only, todo o nada).',
    limitations: 'El capital es una vara para leer los números en dinero, no una posición que el motor haya operado de verdad: el backtest corre sobre el retorno %, el capital se aplica después, en el frontend.',
  },
  comparador_diferencia_monetaria: {
    title: 'Diferencia en dinero',
    shortDescription: 'La diferencia en puntos porcentuales contra la referencia, llevada a dinero con el capital inicial elegido.',
    howItIsCalculated: 'capital_inicial × diferencia_pp / 100.',
    limitations: 'No es una ganancia o pérdida real: es una comparación entre dos escenarios hipotéticos con el mismo capital de partida, no dinero que efectivamente se ganó o se dejó de ganar.',
    relatedTerms: ['comparador_puntos_porcentuales'],
  },
  comparador_tiempo_invertido: {
    title: 'Tiempo invertido / fuera del mercado',
    shortDescription: 'Qué porcentaje de las ruedas del período la estrategia tuvo una posición abierta (invertido) contra cuánto estuvo afuera, en liquidez, sin exposición al precio.',
    whyItMatters: 'Dos estrategias con retornos parecidos pueden haber corrido riesgos muy distintos si una estuvo invertida todo el tiempo y la otra sólo una fracción: "Comprar y mantener" siempre está 100% invertida, por definición.',
    howItIsCalculated: 'Invertido = exposición % (barras con posición abierta / barras del período). Fuera del mercado = 100 − esa exposición.',
  },
  comparador_divergencias: {
    title: 'Tramos de divergencia',
    shortDescription: 'Los meses donde la curva de una estrategia y la de la referencia se separaron más: dónde se originó la diferencia final, no sólo cuánto fue.',
    whyItMatters: 'El resultado total puede venir de un solo mes bisagra (una estrategia que salió justo antes de una caída, o que se perdió una suba fuerte) en vez de una diferencia pareja mes a mes.',
    howItIsCalculated: 'Se agrupa por mes calendario y se compara cuánto cambió la razón (curva de la estrategia / curva de la referencia) entre el primer y el último punto del mes. Se muestran los tramos de mayor separación, no necesariamente los más recientes.',
    howToInterpret: '"Invertida" dice qué porcentaje de ese tramo cada una tuvo una posición abierta: si la estrategia estaba afuera del mercado y la referencia adentro (o viceversa), suele ser la explicación de la divergencia.',
  },
  comparador_costos: {
    title: 'Con costos / Sin costos',
    shortDescription: 'Corre el mismo backtest con la comisión configurada en cada estrategia, o con comisión 0%, para separar cuánto de la diferencia contra la referencia viene de las señales en sí y cuánto se lo lleva el costo de operar.',
    whyItMatters: 'Una estrategia con muchas operaciones puede perder buena parte de su ventaja (o toda) en comisiones; "Sin costos" aísla esa parte. "Comprar y mantener" no cambia entre los dos modos: es una sola operación.',
    limitations: 'Sólo se simula la comisión por lado que cada estrategia tiene configurada. Spread y slippage (el precio real de ejecución suele ser un poco peor que el de la señal) no están en el motor: se muestran como "No disponible", nunca se inventan.',
  },
  comparador_limitaciones: {
    title: 'Limitaciones de esta comparación',
    shortDescription: 'Lo que este backtest no puede representar, para no leer más de lo que hay.',
    limitations: 'DCA (aportes periódicos) no es representable: el motor es long-only y todo-o-nada, sin sizing ni compras parciales, así que no aparece como una estrategia más para comparar. Spread y slippage no se simulan. La serie del subyacente (USD) viene ajustada por dividendos/splits; la serie local, no. No hay calendario de feriados: un hueco largo en la serie se avisa, nunca se rellena. En series muy largas el período puede recortarse por un tope de ruedas cargadas.',
    relatedTerms: ['comparador_costos', 'analisis_tecnico_riesgo'],
  },
}
