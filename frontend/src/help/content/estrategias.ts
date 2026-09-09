/** Fichas del catálogo de estrategias técnicas: una entrada por preset de
 * `services/estrategia_engine.PRESETS`, con clave `estrategia_<slug>`.
 *
 * Convención de campos (la respeta `FichaEstrategia.tsx`, que las renderiza como bloque
 * desplegable en vez de modal):
 * - `shortDescription`: qué mira la estrategia, en una línea.
 * - `howItIsCalculated`: los tres momentos concretos — cuándo compra, cuándo vende y cómo corta
 *   pérdidas —, con los números del preset. Es lo que el usuario necesita para decidir si la
 *   regla es la que tenía en la cabeza.
 * - `howToInterpret`: en qué mercado suele funcionar.
 * - `limitations`: dónde pierde plata, y qué datos necesita (muchas series de esta app no traen
 *   velas OHLC ni volumen; el motor degrada a cierres y la estrategia deja de medir lo que
 *   promete).
 *
 * Los números tienen que seguir a los del preset: si cambia un stop loss en el backend, cambia
 * acá. `test_estrategia_engine.py` verifica los metadatos del preset, no estos textos.
 */
import { HelpContent } from '../types'

export type EstrategiasHelpKey =
  | 'estrategia_cruce_medias'
  | 'estrategia_cruce_ema_corto'
  | 'estrategia_tendencia_media_larga'
  | 'estrategia_macd_cruce'
  | 'estrategia_macd_con_tendencia'
  | 'estrategia_rsi_sobreventa'
  | 'estrategia_bollinger_reversion'
  | 'estrategia_estocastico_sobreventa'
  | 'estrategia_pullback_en_tendencia'
  | 'estrategia_percentil_bajo'
  | 'estrategia_recuperacion_drawdown'
  | 'estrategia_extremos_historicos'
  | 'estrategia_bollinger_ruptura'
  | 'estrategia_ruptura_maximos'
  | 'estrategia_ruptura_con_volumen'
  | 'estrategia_momentum_12m'

export const ESTRATEGIAS_HELP: Record<EstrategiasHelpKey, HelpContent> = {
  // ── Tendencia ───────────────────────────────────────────────────────────────
  estrategia_cruce_medias: {
    title: 'Cruce de medias 50/200 (golden cross)',
    shortDescription: 'La estrategia de seguimiento de tendencia más conocida: compara el precio promedio de las últimas 50 ruedas contra el de las últimas 200.',
    howItIsCalculated: 'Compra cuando la media de 50 cruza hacia arriba la de 200 (el famoso "golden cross"). Vende cuando la de 50 vuelve a cruzar hacia abajo la de 200 ("death cross"). Corta pérdidas con un stop loss del 8 % por debajo del precio de entrada.',
    howToInterpret: 'Funciona en mercados con tendencias largas y sostenidas: entra tarde y sale tarde a propósito, cambiando precisión por aguante. Una sola operación bien agarrada puede pagar varias falsas.',
    limitations: 'En un mercado lateral genera cruces falsos encadenados (whipsaw), cada uno con su comisión de ida y vuelta. Necesita al menos 200 ruedas de historia antes de dar la primera señal, así que sobre un ticker recién agregado no dice nada.',
    relatedTerms: ['analisis_tecnico_backtest', 'analisis_tecnico_indicadores'],
  },
  estrategia_cruce_ema_corto: {
    title: 'Cruce de EMAs 9/21 (swing corto)',
    shortDescription: 'La misma idea del cruce de medias pero mucho más rápida, con medias exponenciales de 9 y 21 ruedas que pesan más los días recientes.',
    howItIsCalculated: 'Compra cuando la EMA de 9 cruza hacia arriba la de 21. Vende cuando la cruza hacia abajo. Corta pérdidas con stop loss del 6 % y, además, con un trailing stop del 8 % que acompaña al precio: si sube y después retrocede 8 % desde el máximo alcanzado, sale.',
    howToInterpret: 'Pensada para movimientos de semanas, no de años. Reacciona rápido a los giros y el trailing stop protege la ganancia que ya se acumuló, en vez de devolverla esperando el cruce de salida.',
    limitations: 'Opera mucho: con una comisión del 0,6 % por lado, un puñado de señales falsas se come el resultado. Mirá siempre "Comisiones acumuladas" y "Operaciones" en las métricas antes de creerle al retorno.',
    relatedTerms: ['estrategia_cruce_medias', 'analisis_tecnico_backtest'],
  },
  estrategia_tendencia_media_larga: {
    title: 'Precio vs. media de 200',
    shortDescription: 'El filtro de tendencia más simple que existe: estar comprado sólo mientras el precio esté por encima de su media de 200 ruedas.',
    howItIsCalculated: 'Compra cuando el cierre cruza hacia arriba la media de 200. Vende cuando el cierre cruza hacia abajo esa misma media. Corta pérdidas con un stop loss del 10 %.',
    howToInterpret: 'Es la regla de referencia contra la que conviene medir cualquier estrategia más elaborada: si una idea complicada no le gana a ésta, la complicación no está pagando. Suele evitar los tramos peores de los mercados bajistas.',
    limitations: 'El precio oscila alrededor de la media justo cuando el mercado está indeciso, y ahí encadena entradas y salidas seguidas. Como toda estrategia de tendencia, siempre entra después de que el movimiento empezó y sale después de que terminó.',
    relatedTerms: ['estrategia_cruce_medias', 'estrategia_momentum_12m'],
  },
  estrategia_macd_cruce: {
    title: 'Cruce de MACD',
    shortDescription: 'Usa el MACD (la diferencia entre dos medias exponenciales) y su línea de señal para detectar cuándo se acelera el movimiento.',
    howItIsCalculated: 'Compra cuando la línea MACD cruza hacia arriba su línea de señal. Vende cuando la cruza hacia abajo. Corta pérdidas con un stop loss del 8 %.',
    howToInterpret: 'Es más temprana que el cruce de medias: avisa cuando el impulso cambia, no cuando el precio promedio ya cambió. Suele dar la señal varias ruedas antes.',
    limitations: 'Sin filtro de tendencia dispara igual en los rebotes de un mercado bajista, donde la mayoría de las señales se dan vuelta enseguida. Si te pasa eso, probá la variante "MACD con filtro de tendencia".',
    relatedTerms: ['estrategia_macd_con_tendencia', 'analisis_tecnico_indicadores'],
  },
  estrategia_macd_con_tendencia: {
    title: 'MACD con filtro de tendencia',
    shortDescription: 'El cruce de MACD, pero operando sólo del lado en que el mercado ya viene subiendo.',
    howItIsCalculated: 'Compra cuando el MACD cruza hacia arriba su señal Y además el cierre está por encima de la media de 200. Vende cuando el MACD cruza hacia abajo su señal O cuando el precio pierde la media de 200 (lo que ocurra primero). Corta pérdidas con stop loss del 8 % y trailing stop del 12 %.',
    howToInterpret: 'El filtro de la media de 200 es lo único que la separa del cruce de MACD suelto, y suele ser la diferencia entre una estrategia rentable y una que devuelve todo: descarta las señales de compra que aparecen en plena caída.',
    limitations: 'Al pedir dos condiciones a la vez opera bastante menos: en un período corto puede no cerrar ninguna operación, y ahí las métricas por operación no se calculan. Ampliá el período antes de descartarla.',
    relatedTerms: ['estrategia_macd_cruce', 'estrategia_tendencia_media_larga'],
  },

  // ── Reversión ───────────────────────────────────────────────────────────────
  estrategia_rsi_sobreventa: {
    title: 'RSI en sobreventa',
    shortDescription: 'Compra el pesimismo: entra cuando el RSI de 14 ruedas marca que la caída fue exagerada respecto de las subas recientes.',
    howItIsCalculated: 'Compra cuando el RSI de 14 baja de 30 (zona de sobreventa). Vende cuando el RSI supera 60, es decir cuando el rebote ya se dio. Corta pérdidas con un stop loss del 10 %.',
    howToInterpret: 'Es una estrategia de reversión a la media: apuesta a que el precio vuelve a su promedio después de un exceso. Rinde mejor en activos que oscilan dentro de un rango que en los que tienen tendencia marcada.',
    limitations: 'El riesgo clásico es "atajar un cuchillo cayendo": en un derrumbe real el RSI se queda por debajo de 30 durante semanas y la estrategia compra al principio de la caída. El stop loss del 10 % es lo único que limita ese escenario.',
    relatedTerms: ['estrategia_pullback_en_tendencia', 'analisis_tecnico_indicadores'],
  },
  estrategia_bollinger_reversion: {
    title: 'Reversión a la banda de Bollinger',
    shortDescription: 'Toma la banda inferior de Bollinger como "precio anormalmente bajo" y la media como el valor al que debería volver.',
    howItIsCalculated: 'Compra cuando el cierre queda por debajo de la banda inferior (dos desvíos por debajo de la media de 20 ruedas). Vende cuando el cierre vuelve a la media de las bandas. Corta pérdidas con un stop loss del 10 %.',
    howToInterpret: 'La ganancia objetivo es el camino de vuelta desde la banda hasta la media: operaciones cortas y frecuentes, con ganancias chicas. El win rate suele ser alto y las ganancias por operación, modestas.',
    limitations: 'Cuando la volatilidad se dispara, las bandas se ensanchan y el precio puede "caminar" por debajo de la inferior durante días. Ahí una sola operación perdedora borra varias ganadoras: mirá "Peor operación" además del win rate.',
    relatedTerms: ['estrategia_bollinger_ruptura', 'analisis_tecnico_indicadores'],
  },
  estrategia_estocastico_sobreventa: {
    title: 'Estocástico saliendo de sobreventa',
    shortDescription: 'Ubica el cierre dentro del rango máximo-mínimo de las últimas 14 ruedas y espera a que empiece a recuperarse desde abajo.',
    howItIsCalculated: 'Compra cuando %K cruza hacia arriba a %D estando %K por debajo de 30: no alcanza con estar en zona baja, se espera la señal de que la caída dejó de acelerar. Vende cuando %K supera 80. Corta pérdidas con stop loss del 8 %, y toma ganancia automáticamente en +15 %.',
    howToInterpret: 'El cruce de %K sobre %D es lo que la hace menos impaciente que el RSI en sobreventa: espera confirmación antes de entrar, a costa de comprar un poco más arriba.',
    limitations: 'Es la estrategia del catálogo que más depende de tener velas OHLC: sin máximo y mínimo diarios, el estocástico se calcula sobre cierres y mide algo bastante distinto. En una serie sin velas la app te avisa, y conviene tomar el resultado con pinzas.',
    relatedTerms: ['estrategia_rsi_sobreventa', 'analisis_tecnico_indicadores'],
  },
  estrategia_pullback_en_tendencia: {
    title: 'Pullback en tendencia alcista (RSI-2)',
    shortDescription: 'Compra la corrección corta dentro de una tendencia que sigue siendo alcista: la idea de Larry Connors, con un RSI de sólo 2 ruedas.',
    howItIsCalculated: 'Compra cuando el cierre está por encima de la media de 200 (la tendencia sigue arriba) Y el RSI de 2 baja de 10 (la corrección de corto plazo es fuerte). Vende cuando el RSI de 2 supera 70 O cuando el precio pierde la media de 200. Corta pérdidas con stop loss del 8 % y, además, cierra a las 10 ruedas si nada de eso pasó.',
    howToInterpret: 'Es la combinación más conocida de tendencia + reversión: sólo compra la baja cuando el contexto es alcista, que es donde comprar la baja históricamente funciona. Las operaciones duran pocos días.',
    limitations: 'El RSI de 2 ruedas es muy nervioso: da muchas señales y necesita comisiones bajas para sobrevivir. El límite de 10 ruedas evita quedarse atrapado en una posición que no rebota, pero corta operaciones que estaban por dar vuelta.',
    relatedTerms: ['estrategia_rsi_sobreventa', 'estrategia_tendencia_media_larga'],
  },
  estrategia_percentil_bajo: {
    title: 'Zona baja del rango con rebote (percentil)',
    shortDescription: 'Compara el precio de hoy contra todo su último año: entra cuando está entre los más bajos del período, pero sólo si ya empezó a recuperarse.',
    howItIsCalculated: 'Compra cuando el percentil de 252 ruedas es menor a 10 (el precio está en el 10 % más bajo del año) Y el retorno de las últimas 20 ruedas es positivo. Vende cuando el percentil supera 60, o sea cuando el precio volvió a la mitad alta de su rango. Corta pérdidas con un stop loss del 12 %.',
    howToInterpret: 'El filtro del retorno de 20 ruedas es la clave: sin él, la estrategia compraría en plena caída libre. Con él, espera a que el precio deje de bajar antes de entrar.',
    limitations: 'Un percentil bajo no significa "barato": un activo en decadencia estructural pasa años en la zona baja de su rango, haciendo mínimos cada vez más bajos. Sirve para activos que oscilan, no para los que se deterioran.',
    relatedTerms: ['analisis_tecnico_percentil', 'estrategia_recuperacion_drawdown'],
  },
  estrategia_recuperacion_drawdown: {
    title: 'Recuperación tras caída fuerte',
    shortDescription: 'Espera una caída grande desde el máximo histórico y compra recién cuando el precio empieza a recuperarse.',
    howItIsCalculated: 'Compra cuando el precio está 30 % o más por debajo de su máximo histórico Y el retorno de las últimas 10 ruedas es positivo. Vende cuando la caída se reduce al 10 % del máximo, es decir cuando ya recuperó buena parte del terreno. Corta pérdidas con stop loss del 15 % y trailing stop del 15 %.',
    howToInterpret: 'Es la versión disciplinada de "comprar cuando todos venden": el filtro de retorno positivo evita entrar mientras el precio sigue cayendo, y el trailing stop protege la recuperación si se corta a mitad de camino.',
    limitations: 'El "máximo histórico" es el de la serie cargada en la app, no el de toda la vida del instrumento. Si el activo nunca vuelve a acercarse a su máximo, la regla de salida no se cumple nunca y la posición queda abierta hasta que salta un stop.',
    relatedTerms: ['analisis_tecnico_extremos', 'estrategia_extremos_historicos'],
  },
  estrategia_extremos_historicos: {
    title: 'Mínimo histórico',
    shortDescription: 'La regla más extrema del catálogo: comprar prácticamente en el piso de la serie y vender prácticamente en el techo.',
    howItIsCalculated: 'Compra cuando el cierre está a menos del 1 % del mínimo de toda la historia cargada. Vende cuando llega a menos del 1 % del máximo histórico. Corta pérdidas con un stop loss del 20 %, más ancho que el resto porque las operaciones son largas.',
    howToInterpret: 'Da poquísimas señales, y ése es el punto: es una estrategia de paciencia extrema, para tenerla corriendo en el screener y que avise cuando algo llega a un extremo.',
    limitations: 'Un mínimo histórico casi siempre se hace en el medio de una caída, y "casi siempre hay uno más abajo". Además, la primera barra de cualquier serie es su propio máximo y mínimo, así que en un ticker con poca historia la señal es un artefacto: usá un período de análisis largo.',
    relatedTerms: ['analisis_tecnico_extremos', 'estrategia_recuperacion_drawdown'],
  },

  // ── Ruptura ─────────────────────────────────────────────────────────────────
  estrategia_bollinger_ruptura: {
    title: 'Ruptura de la banda de Bollinger',
    shortDescription: 'La lectura opuesta a la reversión sobre el mismo indicador: tocar la banda superior se interpreta como fuerza, no como exceso.',
    howItIsCalculated: 'Compra cuando el cierre cruza hacia arriba la banda superior (dos desvíos por encima de la media de 20). Vende cuando el cierre vuelve por debajo de la media de las bandas. Corta pérdidas con stop loss del 8 % y trailing stop del 10 %.',
    howToInterpret: 'Sirve para activos que arrancan movimientos fuertes después de períodos de calma. Que la misma banda se pueda leer como "caro" o como "fuerte" es justamente por qué conviene backtestear las dos versiones sobre el mismo ticker antes de elegir.',
    limitations: 'En un activo que oscila dentro de un rango, la ruptura de la banda superior es casi siempre una falsa alarma y esta estrategia compra los techos. Es el espejo exacto del riesgo de la versión de reversión.',
    relatedTerms: ['estrategia_bollinger_reversion', 'estrategia_ruptura_maximos'],
  },
  estrategia_ruptura_maximos: {
    title: 'Ruptura de máximos de 20 ruedas (Donchian)',
    shortDescription: 'El sistema "de las tortugas": comprar cuando el precio hace un máximo de 20 ruedas y salir cuando hace un mínimo de 10.',
    howItIsCalculated: 'Compra cuando el máximo de la rueda iguala o supera el techo del canal de 20 ruedas, o sea cuando el día hace un máximo de 20 ruedas. Vende cuando el mínimo de la rueda perfora el piso del canal de 10. No usa stop loss fijo: la protección es un trailing stop del 12 %, que acompaña al precio mientras sube.',
    howToInterpret: 'Es seguimiento de tendencia puro: acepta muchas operaciones perdedoras chicas a cambio de unas pocas ganadoras grandes. No mires el win rate en ésta, mirá el profit factor y la mejor operación.',
    limitations: 'Necesita velas OHLC: compara el máximo y el mínimo del día contra el canal, y en una serie que sólo tiene cierres esas condiciones no se pueden evaluar, así que la estrategia no opera nunca (no da error, simplemente no entra). La app te avisa cuando la serie del ticker no tiene velas.',
    relatedTerms: ['analisis_tecnico_extremos', 'estrategia_bollinger_ruptura'],
  },
  estrategia_ruptura_con_volumen: {
    title: 'Ruptura con volumen',
    shortDescription: 'Pide que la suba venga acompañada de volumen: que haya más gente operando, no sólo un precio que se mueve solo.',
    howItIsCalculated: 'Compra cuando el cierre cruza hacia arriba la media de 20 ruedas Y el volumen del día supera su propio promedio de 20 ruedas. Vende cuando el cierre vuelve por debajo de la media de 20. Corta pérdidas con stop loss del 8 % y trailing stop del 10 %.',
    howToInterpret: 'El volumen es la confirmación clásica de una ruptura: una suba con poco volumen suele deshacerse. Descarta buena parte de las rupturas falsas de la media de 20 sola.',
    limitations: 'Necesita volumen, y muchas series de esta app no lo traen: sin volumen la condición nunca se cumple y la estrategia no opera nunca (no da error, simplemente no entra). La app te avisa cuando la serie del ticker no tiene volumen. Además, el DSL no multiplica: el filtro es "por encima del promedio", no el clásico "1,5 veces el promedio".',
    relatedTerms: ['estrategia_ruptura_maximos', 'analisis_tecnico_indicadores'],
  },

  // ── Momentum ────────────────────────────────────────────────────────────────
  estrategia_momentum_12m: {
    title: 'Momentum de 12 meses',
    shortDescription: 'Se queda con lo que viene subiendo hace un año, que es una de las regularidades más estudiadas de los mercados.',
    howItIsCalculated: 'Compra cuando el retorno de las últimas 252 ruedas (un año bursátil) es positivo Y el cierre está por encima de la media de 200. Vende cuando el precio pierde la media de 200. Corta pérdidas con un stop loss del 15 %, ancho a propósito porque las posiciones se mantienen meses.',
    howToInterpret: 'Es una estrategia de baja frecuencia: pocas operaciones, muy largas. Está pensada para acompañar movimientos de meses, no para acertar el timing fino.',
    limitations: 'Necesita más de un año de historia antes de dar la primera señal, así que sobre series cortas no dice nada. Su punto débil son los giros bruscos de mercado: el momentum sigue marcando "positivo" mientras el precio ya se dio vuelta, y el stop del 15 % llega tarde.',
    relatedTerms: ['estrategia_tendencia_media_larga', 'analisis_tecnico_backtest'],
  },
}
