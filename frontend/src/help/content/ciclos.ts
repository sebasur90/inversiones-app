import { HelpContent } from '../types'

// Claves prefijadas "ciclos_" para no chocar con "correlacion", "benchmark" y otros términos que ya
// existen en el glosario y hablan de cálculos parecidos pero de otras pantallas.
export type CiclosHelpKey =
  | 'ciclos_rotacion'
  | 'ciclos_rs_ratio'
  | 'ciclos_rs_momentum'
  | 'ciclos_leading'
  | 'ciclos_weakening'
  | 'ciclos_lagging'
  | 'ciclos_improving'
  | 'ciclos_trayectoria'
  | 'ciclos_cambio_confirmado'
  | 'ciclos_efectividad'
  | 'ciclos_episodio'
  | 'ciclos_base_semanas'
  | 'ciclos_proxy'
  | 'ciclos_benchmark'
  | 'ciclos_retorno_total'
  | 'ciclos_rendimiento_relativo'
  | 'ciclos_volatilidad'
  | 'ciclos_drawdown'
  | 'ciclos_tendencia'
  | 'ciclos_correlacion'
  | 'ciclos_desfase'
  | 'ciclos_vehiculo_pais'
  | 'ciclos_efecto_cambiario'
  | 'ciclos_no_suman'
  | 'ciclos_lista_curada'
  | 'ciclos_regimen'
  | 'ciclos_simulador'
  | 'ciclos_sin_clasificar'
  | 'ciclos_moneda'

export const CICLOS_HELP: Record<CiclosHelpKey, HelpContent> = {
  ciclos_rotacion: {
    title: 'Rotación relativa',
    shortDescription: 'Un mapa que muestra, para cada grupo (un sector, un país, el oro...), si le está yendo mejor o peor que su referencia y si esa diferencia se está fortaleciendo o debilitando.',
    whyItMatters: 'Ayuda a ver cambios de liderazgo entre mercados antes de que se noten en el rendimiento acumulado de un año.',
    howItIsCalculated: 'Con cierres semanales: se divide el precio del grupo por el de su referencia, y se mide ese cociente contra su propio promedio reciente (13 semanas) y contra la velocidad con que cambia. Es una metodología propia inspirada en los gráficos de rotación relativa (RRG); no es la de los indicadores JdK.',
    howToInterpret: 'Mirá hacia dónde se mueve cada punto en las últimas semanas, no sólo dónde está. El cuadrante describe lo que pasó, no lo que va a pasar.',
    limitations: 'Describe el pasado reciente. Un grupo puede estar en Leading y aun así caer. No es una recomendación ni una señal de compra o venta.',
    relatedTerms: ['ciclos_rs_ratio', 'ciclos_rs_momentum', 'ciclos_cambio_confirmado'],
  },
  ciclos_rs_ratio: {
    title: 'Fortaleza relativa (RS-Ratio)',
    shortDescription: 'Qué tan por encima o por debajo de su promedio reciente está el cociente entre el grupo y su referencia. 100 es el punto neutro.',
    howItIsCalculated: 'RS = precio del grupo ÷ precio de la referencia. RS-Ratio = 100 × RS ÷ promedio exponencial de RS (13 semanas).',
    howToInterpret: 'Por encima de 100: el grupo viene rindiendo mejor que su referencia en relación a su propio promedio. Por debajo de 100: peor.',
    limitations: 'Depende de la referencia elegida: el mismo grupo puede verse fuerte contra un benchmark y débil contra otro.',
  },
  ciclos_rs_momentum: {
    title: 'Momentum relativo (RS-Momentum)',
    shortDescription: 'Si la fortaleza relativa del grupo está aumentando o disminuyendo. 100 es el punto neutro.',
    howItIsCalculated: 'RS-Momentum = 100 × RS-Ratio ÷ promedio exponencial de RS-Ratio (13 semanas).',
    howToInterpret: 'Por encima de 100: la fortaleza relativa viene mejorando. Por debajo de 100: viene empeorando, aunque todavía pueda ser alta.',
    limitations: 'Es sensible a cambios recientes: una semana atípica mueve el punto. Por eso se distinguen los cambios confirmados de los transitorios.',
  },
  ciclos_leading: {
    title: 'Leading',
    shortDescription: 'Fortaleza relativa por encima de 100 y momentum por encima de 100: al grupo le viene yendo mejor que a su referencia y esa ventaja viene creciendo.',
    limitations: 'Es una descripción del pasado reciente. No indica que convenga comprar ni que vaya a seguir así.',
  },
  ciclos_weakening: {
    title: 'Weakening',
    shortDescription: 'Fortaleza relativa por encima de 100 pero momentum por debajo de 100: el grupo todavía le gana a su referencia, pero esa ventaja viene achicándose.',
    limitations: 'Es una descripción del pasado reciente. No indica que convenga vender.',
  },
  ciclos_lagging: {
    title: 'Lagging',
    shortDescription: 'Fortaleza relativa y momentum por debajo de 100: al grupo le viene yendo peor que a su referencia y esa diferencia viene creciendo.',
    limitations: 'Que un grupo rinda peor que su referencia no significa que esté barato ni que vaya a recuperarse: la valuación es otra dimensión que este mapa no mide.',
  },
  ciclos_improving: {
    title: 'Improving',
    shortDescription: 'Fortaleza relativa por debajo de 100 pero momentum por encima de 100: el grupo todavía rinde peor que su referencia, pero esa diferencia viene achicándose.',
    limitations: 'Un cambio a Improving puede ser transitorio: mirá si se sostiene varias semanas (cambio confirmado).',
  },
  ciclos_trayectoria: {
    title: 'Trayectoria',
    shortDescription: 'El recorrido de un punto en las últimas semanas: de dónde viene y hacia dónde se desplaza dentro del mapa.',
    howToInterpret: 'Una cola larga y recta indica un cambio sostenido; una cola corta o que da vueltas indica poco cambio relativo. El período elegido arriba define cuántas semanas se muestran.',
  },
  ciclos_cambio_confirmado: {
    title: 'Cambio confirmado',
    shortDescription: 'Un cambio de cuadrante que se sostuvo al menos 3 semanas seguidas. Si dura menos, se considera transitorio.',
    whyItMatters: 'Evita leer como un nuevo ciclo lo que fue el movimiento de una sola semana.',
    howToInterpret: 'Los cambios sin confirmar figuran como pendientes: todavía no se sabe si se sostienen.',
    limitations: 'Confirmar no es predecir: el cambio sólo quedó sostenido en los datos que ya pasaron.',
  },
  ciclos_efectividad: {
    title: 'Qué pasó después de cada estado',
    shortDescription: 'Para cada vez que el grupo estuvo en un estado confirmado, cuánto rindió contra su referencia en las 4, 13 o 26 semanas siguientes.',
    whyItMatters: 'Muestra si, en el pasado, un estado vino acompañado de una ventaja o una desventaja posterior, y qué tan dispersos fueron los resultados.',
    howItIsCalculated: 'Rendimiento relativo = (1 + rendimiento del grupo) ÷ (1 + rendimiento de la referencia) − 1, entre la semana en que el grupo estaba en ese estado y el horizonte elegido, en dólares. El estado de cada semana usa sólo los datos hasta esa semana.',
    howToInterpret: 'Mirá la mediana y el rango típico (de un cuarto a tres cuartos de los casos), no sólo el promedio, y compará con "cualquier semana": una ventaja que también existe en la base no es del estado. Si hay pocos episodios la app no calcula nada.',
    limitations: 'Describe el pasado de los grupos que existen hoy, sin costos ni impuestos. Con 4 estados, 3 horizontes y 2 vistas es esperable que alguna diferencia aparezca por azar. No es una predicción ni una recomendación.',
    relatedTerms: ['ciclos_episodio', 'ciclos_base_semanas', 'ciclos_cambio_confirmado'],
  },
  ciclos_episodio: {
    title: 'Episodio',
    shortDescription: 'Una racha continua del grupo en un mismo estado confirmado, desde que se confirmó hasta que cambió a otro.',
    whyItMatters: 'Las semanas seguidas dentro de una racha se parecen mucho entre sí (comparten casi todo su futuro). Lo que da información independiente es la cantidad de episodios, no la de semanas.',
    howToInterpret: 'Con menos de 5 episodios la app muestra sólo el conteo y no calcula medianas ni porcentajes.',
  },
  ciclos_base_semanas: {
    title: 'Cualquier semana (base)',
    shortDescription: 'El rendimiento relativo posterior de todas las semanas, sin mirar en qué estado estaba el grupo.',
    whyItMatters: 'Es el punto de comparación: si un grupo le ganaba a su referencia el 60 % de las semanas, un estado que "acierta" el 60 % no aporta nada.',
    howToInterpret: 'La diferencia de cada estado contra esta base es lo que importa, y sólo si hay suficientes episodios.',
  },
  ciclos_proxy: {
    title: 'Proxy',
    shortDescription: 'El instrumento que se usa para medir a un grupo: por ejemplo, el ETF XLK para medir el sector tecnología o GLD para el oro.',
    whyItMatters: 'La app no tiene "el precio del sector": lo mide a través de un fondo o índice que lo representa.',
    limitations: 'Un proxy nunca es el grupo completo: tiene su propia composición, gastos y distribuciones. Los ETFs de futuros (petróleo, gas, agrícolas) incluyen además el efecto del roll de contratos.',
  },
  ciclos_benchmark: {
    title: 'Referencia (benchmark)',
    shortDescription: 'El índice contra el que se mide a cada grupo: por defecto el S&P 500 para sectores, industrias y temas, y el mercado global (ACWI) para commodities, regiones y países.',
    howToInterpret: 'Se puede cambiar arriba. Todo el mapa se recalcula contra la referencia elegida.',
  },
  ciclos_retorno_total: {
    title: 'Retorno total vs. de precio',
    shortDescription: 'El retorno total incluye los dividendos y distribuciones reinvertidos; el de precio sólo mira cuánto cambió la cotización.',
    whyItMatters: 'Comparar uno con otro favorece al primero, sobre todo en grupos que pagan mucho dividendo.',
    limitations: 'Los ETFs se miden con precios ajustados por dividendos y splits (retorno total). Bitcoin y Ethereum son precio spot, y los índices locales de cada país son de precio. Cuando se mezclan en una misma comparación, la pantalla lo avisa.',
  },
  ciclos_rendimiento_relativo: {
    title: 'Rendimiento relativo',
    shortDescription: 'Cuánto más (o menos) rindió el grupo que su referencia en el mismo período.',
    howItIsCalculated: '(1 + rendimiento del grupo) ÷ (1 + rendimiento de la referencia) − 1, sobre las mismas dos fechas.',
    howToInterpret: 'Positivo: el grupo le ganó a la referencia. Negativo: le perdió. No es lo mismo que la diferencia de porcentajes.',
  },
  ciclos_volatilidad: {
    title: 'Volatilidad',
    shortDescription: 'Cuánto suben y bajan los precios del grupo semana a semana, expresado en términos anuales.',
    howItIsCalculated: 'Desvío estándar de los retornos semanales × raíz de 52. Sobre los últimos 3 años (o los que haya).',
    limitations: 'Mide qué tan irregular fue el recorrido, no la probabilidad de perder dinero. Con pocos datos no se calcula.',
  },
  ciclos_drawdown: {
    title: 'Máxima caída (drawdown)',
    shortDescription: 'La mayor caída desde un máximo hasta el mínimo siguiente, en el período mostrado, y cuánto tardó en recuperarse.',
    howToInterpret: 'Si no se recuperó, figura "sin recuperar". La caída actual indica a qué distancia está hoy de su último máximo.',
    limitations: 'Depende del período mirado: una caída más antigua puede quedar afuera.',
  },
  ciclos_tendencia: {
    title: 'Tendencia de largo plazo',
    shortDescription: 'A qué distancia está el precio de su promedio de 40 semanas y hacia dónde apunta ese promedio.',
    howToInterpret: 'Precio por encima de su promedio y promedio subiendo suele describir una tendencia alcista sostenida; lo contrario, una bajista.',
    limitations: 'Que un grupo haya subido durante algunas semanas no es un nuevo ciclo alcista. Es sólo la posición actual contra su promedio.',
  },
  ciclos_correlacion: {
    title: 'Correlación entre grupos',
    shortDescription: 'Qué tan parecido se movieron dos grupos en el mismo período, de −1 a +1.',
    howToInterpret: '+1: se movieron muy parecido. 0: no hay relación lineal clara. −1: tendieron a moverse en sentidos opuestos. Se mide con retornos en dólares sobre fechas en común.',
    limitations: 'Correlación no es causalidad. Cambia con el período y con pocas observaciones es poco confiable: la pantalla muestra la cantidad de datos usados.',
  },
  ciclos_desfase: {
    title: 'Adelantos y rezagos',
    shortDescription: 'Si lo que le pasó a un grupo una semana se parece a lo que le pasó a otro algunas semanas después.',
    howToInterpret: 'Un desfase positivo significa que el primer grupo "va primero". La banda gris marca lo que puede salir sólo por azar.',
    limitations: 'Es una hipótesis estadística, no una predicción. Con 17 desfases probados es normal que alguno supere la banda por azar sin que exista relación real.',
  },
  ciclos_vehiculo_pais: {
    title: 'Diferencia del vehículo',
    shortDescription: 'La diferencia entre lo que rindió el ETF del país en dólares y lo que rindió el índice local llevado a dólares.',
    whyItMatters: 'Un ETF no es el índice: tiene gastos, distribuye dividendos, y su composición puede diferir.',
    limitations: 'El índice local es de precio (sin dividendos) y puede no coincidir en composición con el ETF. No son medidas equivalentes.',
  },
  ciclos_efecto_cambiario: {
    title: 'Efecto cambiario',
    shortDescription: 'Cuánto le suma o le resta el tipo de cambio al rendimiento, medido en dólares, de un activo que cotiza en otra moneda.',
    howItIsCalculated: 'Índice local en dólares = (1 + rendimiento local) × (1 + efecto cambiario) − 1, sobre las mismas dos fechas.',
    howToInterpret: 'Si la moneda local se deprecia, el efecto resta; si se aprecia, suma.',
    limitations: 'Sólo se calcula si hay datos del tipo de cambio cerca de las dos fechas. Si faltan, queda "sin dato" en vez de estimarse.',
  },
  ciclos_no_suman: {
    title: 'Pertenencias que se superponen',
    shortDescription: 'Una misma empresa puede estar en varios grupos a la vez: NVIDIA es tecnología, semiconductores e inteligencia artificial.',
    whyItMatters: 'Por eso los porcentajes de industrias, commodities y temas no se suman entre sí ni con los de sector, región o país: se contaría dos veces el mismo dinero.',
    howToInterpret: 'Sector, región y país son excluyentes y suman 100 %. Industrias, commodities y temas se muestran aparte, con su propia unión.',
  },
  ciclos_lista_curada: {
    title: 'Lista curada',
    shortDescription: 'Los temas (inteligencia artificial, transición energética) no tienen una clasificación oficial. Acá se arman con una regla sobre la industria más una lista de tickers elegida a mano.',
    limitations: 'Es un criterio amplio y revisable, no una clasificación de fuente externa. Podés ver la regla exacta en cada tema.',
  },
  ciclos_regimen: {
    title: 'Régimen macroeconómico',
    shortDescription: 'Un escenario según si el crecimiento y la inflación se aceleran o se desaceleran: reflación, expansión equilibrada, estanflación o desinflación.',
    whyItMatters: 'Distintos activos suelen comportarse distinto en cada escenario, y por eso interesa saber en cuál estamos.',
    limitations: 'Hoy la app no tiene series macro globales confiables (actividad, inflación, tasas, liquidez), así que no asigna ningún escenario. CER, MEP y riesgo país describen a la Argentina y no alcanzan.',
  },
  ciclos_simulador: {
    title: 'Simulador de rotación',
    shortDescription: 'Muestra cómo quedaría la mezcla de tu cartera si trasladaras un porcentaje de un grupo a otro.',
    howToInterpret: 'Compará la distribución de antes y de después por emisor, sector, país y región, y la distancia a tus objetivos.',
    limitations: 'Es una simulación en memoria: no guarda nada, no modifica tu cartera ni estima rendimientos futuros. El destino se simula con la clasificación del grupo; no se calculan impuestos ni comisiones.',
  },
  ciclos_sin_clasificar: {
    title: 'Sin clasificar o sin estado',
    shortDescription: 'Posiciones que no tienen sector, país o región cargados, o categorías que no tienen un grupo con datos en el catálogo de ciclos.',
    howToInterpret: 'Se muestran como una categoría más para que el total de la cartera siga siendo el real. Podés corregir la clasificación en la ficha del ticker.',
  },
  ciclos_moneda: {
    title: 'Moneda en Ciclos',
    shortDescription: 'Los rendimientos, riesgos y gráficos pueden verse en dólares o en pesos (al MEP de cada fecha). El mapa de rotación se calcula siempre en dólares.',
    limitations: 'Al medir un grupo contra su referencia, el tipo de cambio se cancela: el cuadrante no cambia con la moneda. En pesos, las fechas sin MEP se descartan, no se completan.',
  },
}
