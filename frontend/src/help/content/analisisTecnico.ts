import { HelpContent } from '../types'

export type AnalisisTecnicoHelpKey =
  | 'analisis_tecnico_titulo'
  | 'analisis_tecnico_indicadores'
  | 'analisis_tecnico_estrategias'
  | 'analisis_tecnico_riesgo'
  | 'analisis_tecnico_backtest'
  | 'analisis_tecnico_precio_ejecucion'
  | 'analisis_tecnico_extremos'
  | 'analisis_tecnico_percentil'
  | 'analisis_tecnico_adx'
  | 'analisis_tecnico_supertrend'
  | 'analisis_tecnico_keltner'
  | 'analisis_tecnico_ichimoku'
  | 'calculadora_posicion'
  | 'zonas_precio'
  | 'serie_referencia'
  | 'grafico_gestos'
  | 'screener_titulo'
  | 'screener_universo'
  | 'screener_distancia'
  | 'screener_precio_gatillo'
  | 'screener_umbral'
  | 'screener_dispara_ahora'
  | 'screener_motivo'
  | 'screener_condiciones'
  | 'screener_grafico_gatillo'

export const ANALISISTECNICO_HELP: Record<AnalisisTecnicoHelpKey, HelpContent> = {
  grafico_gestos: {
    title: 'Cómo moverse por el gráfico',
    shortDescription: 'En el celular: deslizá de costado para recorrer la historia, pellizcá para acercar o alejar y tocá una vela para ver sus números. Deslizar hacia arriba o abajo mueve la pantalla, no el gráfico.',
    howToInterpret: 'Tocar una vela fija la cruz y arriba aparecen su fecha, el cierre, la variación contra la rueda anterior, apertura, máximo, mínimo y volumen; la leyenda y cada panel muestran el valor de sus indicadores en esa vela. Tocar la misma vela (o la ✕) la quita. Mantené apretado un instante y arrastrá para recorrer vela por vela sin mover el gráfico. Doble toque vuelve a todo el período. En la computadora: la rueda del mouse acerca y aleja, arrastrar desplaza y doble clic vuelve a todo. En el gráfico de una estrategia, la ficha dice además si esa rueda hubo compra o venta (y por qué motivo), o si la estrategia estaba comprada, con el resultado hasta ahí y sus niveles de stop loss, take profit y trailing.',
    limitations: 'Con todo el período a la vista no hay hacia dónde deslizar: primero acercá (pellizco o +) y después deslizá. Los botones + y − mantienen la última rueda contra el borde derecho. La guía "Cómo se usa", al pie del gráfico, repasa todos los gestos. Las zonas que quedan fuera del tramo que estás mirando se señalan con una flecha ▲/▼ en el borde del gráfico. El zoom navega la serie que ya está cargada: para ver más historia, cambiá el período arriba del gráfico. Con muchas ruedas en poco ancho las velas se dibujan como una línea de cierres hasta que acercás. En pantalla completa, "Girar" pone el teléfono en horizontal donde el navegador lo permite (Android); en iPhone basta con girarlo.',
    relatedTerms: ['analisis_tecnico_indicadores', 'analisis_tecnico_riesgo'],
  },
  serie_referencia: {
    title: 'Serie de referencia',
    shortDescription: 'Para un CEDEAR, el precio que sirve para decidir es el de la acción en EE.UU. en dólares, no el del CEDEAR en pesos. La app lo toma como referencia automáticamente.',
    whyItMatters: 'El CEDEAR de MSFT se mueve por dos cosas: lo que hace Microsoft y lo que hace el dólar (más el ratio de conversión). Los indicadores, las bandas y los máximos y mínimos calculados sobre el CEDEAR mezclan las dos; sobre el precio de la acción en dólares describen sólo a la empresa. El CEDEAR importa a la hora de ejecutar la orden, no a la de decidir.',
    howToInterpret: 'Un instrumento usa el precio en dólares como referencia cuando es un CEDEAR (los ETFs del exterior, como SPY o XLP, también lo son) y la app ya bajó su serie en dólares. Al agregar un CEDEAR a la watchlist esa serie se baja en el momento; si Yahoo no respondió, el botón de precio de la watchlist o el próximo sync la vuelven a pedir. El resto (acciones argentinas, bonos, ONs, o un CEDEAR cuya serie todavía no está) usa el precio local. Las acciones argentinas con ADR (GGAL, YPF) se miran en pesos: su mercado de referencia es el local. El gráfico, la watchlist, las estrategias, el backtest y el screener arrancan en la serie de referencia; el selector de serie te deja mirar la otra cuando quieras.',
    limitations: 'No hay conversión entre una serie y otra (no existe un historial confiable del dólar financiero ni del ratio de cada CEDEAR): son dos series distintas, nunca el mismo precio en dos monedas. Por eso una zona de compra o de venta en pesos, medida sobre el CEDEAR, no se puede pasar sola a dólares: hay que volver a dibujarla sobre el gráfico en dólares. El stop loss y el objetivo de una posición siguen en pesos, porque son un porcentaje sobre el precio al que compraste el CEDEAR.',
    relatedTerms: ['zonas_precio', 'watchlist_zona_compra'],
  },
  zonas_precio: {
    title: 'Zonas de compra y de venta',
    shortDescription: 'El rango de precios en el que querés entrar o salir de un instrumento, dibujado sobre el gráfico. Cuando el precio entra en la zona, llega el aviso al celular.',
    whyItMatters: 'Decidir el rango con el gráfico a la vista —y no en el momento en que el precio se mueve— es la diferencia entre una compra planeada y una reacción. El rango además dice algo que un precio solo no dice: entre cuánto y cuánto te parece buena la entrada.',
    howToInterpret: 'De los dos bordes, uno dispara el aviso y el otro es referencia. En una zona de compra dispara el techo (el precio baja y cruza hacia adentro); en una de venta dispara el piso (sube y cruza). El borde que dispara se dibuja con línea llena y el otro punteado. Cualquiera de los dos puede quedar vacío: una zona de compra sin piso es simplemente "comprar por debajo de X". Para dibujarla, tocá "Dibujar zona" o "Editar zonas": la zona nueva arranca cerca del precio actual y cada borde tiene una manija ↕ con su precio a la izquierda del gráfico. Arrastrala para moverlo (va de a pasos redondos según la escala) o escribí el número exacto en el editor. Mientras editás podés acercar y desplazar el gráfico. Nada se guarda hasta tocar Guardar. Debajo del gráfico, el resumen te dice a qué distancia está el precio de cada zona.',
    limitations: 'Hay una sola zona de compra y una sola de venta por instrumento, y cada una se mide sobre la serie en la que la dibujaste: la local en pesos o la del subyacente en dólares (para un CEDEAR, la de referencia es la de dólares). No hay conversión de moneda entre una y otra — son dos instrumentos distintos, no el mismo precio en dos monedas. Las zonas son independientes del stop-loss y el objetivo de una posición, que se editan en el detalle del ticker y acá se dibujan sólo como referencia.',
    relatedTerms: ['serie_referencia', 'watchlist_zona_compra', 'stopLoss', 'objetivo'],
  },
  analisis_tecnico_titulo: {
    title: 'Análisis técnico',
    shortDescription: 'Velas (donde la fuente las provee) o línea de cierres, con indicadores clásicos activables y estrategias propias backtesteables, sobre los tickers de tu cartera y tu watchlist.',
    whyItMatters: 'Te ayuda a decidir cuándo entrar o salir de un instrumento con reglas explícitas y verificables contra la historia, en vez de a ojo.',
  },
  analisis_tecnico_indicadores: {
    title: 'Indicadores',
    shortDescription: 'Medias móviles, RSI, MACD, Bandas de Bollinger, ATR, Estocástico, OBV y volumen promedio, calculados sobre la serie de precios de este ticker.',
    whyItMatters: 'Cada indicador resume un aspecto distinto del precio (tendencia, momentum, volatilidad, volumen); combinarlos da más contexto que mirar el precio solo. Con "+ otra" podés sumar el mismo indicador con otros parámetros (una SMA de 50 y otra de 200, por ejemplo): cada instancia lleva su color, y la leyenda del gráfico dice cuál es cuál.',
    limitations: 'Necesitan un warm-up (p. ej. una media de 200 ruedas recién está definida desde la rueda 200): la zona sombreada del gráfico marca dónde todavía no hay dato.',
  },
  analisis_tecnico_estrategias: {
    title: 'Estrategias',
    shortDescription: 'Reglas de compra y venta combinables (cruces de medias, niveles de RSI, bandas de Bollinger, rupturas, momentum…) que se pueden guardar, duplicar y reusar en cualquier ticker. El catálogo trae las más usadas ya armadas, agrupadas por familia; cada una tiene su ficha con cuándo compra, cuándo vende y cómo corta pérdidas.',
    whyItMatters: 'Formalizar la regla te obliga a ser explícito sobre cuándo entrarías y saldrías, y permite contrastarla contra la historia antes de arriesgar capital real.',
    howToInterpret: 'Las cuatro familias responden a ideas distintas: tendencia (entrar cuando el precio ya se mueve a favor), reversión (comprar la baja apostando a que vuelve), ruptura (entrar cuando sale del rango) y momentum (quedarse con lo que viene subiendo hace tiempo). Sobre un mismo ticker suelen dar resultados muy distintos, y esa diferencia dice más del activo que de la estrategia.',
    limitations: 'El nombre identifica a la estrategia: guardar o importar con un nombre ya usado sobrescribe la existente en vez de dejar dos iguales (la app te lo avisa). Las estrategias del catálogo se cargan solas la primera vez, y "Restaurar catálogo" las devuelve a su definición original, pisando los ajustes que les hayas hecho.',
    relatedTerms: ['analisis_tecnico_backtest', 'analisis_tecnico_riesgo'],
  },
  analisis_tecnico_riesgo: {
    title: 'Límites de riesgo (stop loss, take profit, trailing)',
    shortDescription: 'Las cuatro formas en que una estrategia puede cerrar una posición sin que se cumpla su regla de venta: stop loss, take profit, trailing stop y máximo de barras.',
    howItIsCalculated: 'El stop loss es un nivel fijo bajo el precio de entrada (8 % = sale si cae a 92 de 100). El take profit, uno fijo por encima. El trailing stop se recalcula barra a barra desde el máximo alcanzado desde que entró: sube con el precio y nunca baja, así que va asegurando la ganancia acumulada. El máximo de barras cierra por tiempo, sin mirar el precio.',
    howToInterpret: 'En el gráfico del backtest los tres niveles se dibujan sobre el tramo de cada operación: el stop loss y el take profit como líneas punteadas rectas, y el trailing como una escalera que sólo sube. El marcador de salida dice cuál de los cuatro cerró la operación (SL, TP, TS, T) o si fue la regla de venta (▼).',
    limitations: 'Los stops se chequean contra el máximo y el mínimo de la rueda, no contra el cierre: si el precio pasó por el nivel durante el día, el backtest considera que la operación se cerró ahí. Si la rueda abrió ya pasada del nivel (un gap), se toma el precio de apertura, que es peor — el criterio conservador.',
    relatedTerms: ['analisis_tecnico_backtest'],
  },
  analisis_tecnico_backtest: {
    title: 'Backtest',
    shortDescription: 'Corre la estrategia sobre la historia disponible del ticker: señal por señal, con stop loss/take profit/trailing si los configuraste, comisión por operación, y la compara contra comprar y mantener (buy & hold).',
    whyItMatters: 'Una estrategia que "se ve bien" en el gráfico puede perder contra simplemente comprar y mantener una vez que se cuenta la comisión y el drawdown real.',
    limitations: 'Es sobre historia pasada: no garantiza que la estrategia siga funcionando igual en el futuro. Con menos de 2 operaciones cerradas, las métricas de ratio (win rate, profit factor) no se calculan.',
  },
  analisis_tecnico_precio_ejecucion: {
    title: 'Precio de ejecución',
    shortDescription: '"Cierre": opera al cierre de la misma rueda que generó la señal (coincide con la flecha que ves en el gráfico). "Apertura siguiente": opera a la apertura de la rueda siguiente, sin el sesgo de saber el cierre antes de operar.',
    whyItMatters: 'Con "cierre" el backtest asume que pudiste operar exactamente al precio que generó la señal, algo que en la vida real no siempre es posible antes de que cierre la rueda.',
  },
  analisis_tecnico_extremos: {
    title: 'Extremos (canal)',
    shortDescription: 'Máximo, mínimo y medio de la ventana (canal de Donchian, incluye la barra actual), más la distancia porcentual del cierre a cada extremo: dist_max_pct (≤ 0, es 0 en un máximo nuevo) y dist_min_pct (≥ 0, es 0 en un mínimo nuevo).',
    howItIsCalculated: 'dist_max_pct = (cierre / máximo − 1) × 100; dist_min_pct = (cierre / mínimo − 1) × 100. Con ventana = 0 la ventana es "toda la serie" (histórico acumulado); con ventana = N son las últimas N ruedas.',
    howToInterpret: '"Comprar cerca del mínimo histórico" se escribe dist_min_pct ≤ 1 (a ≤ 1 % del mínimo). dist_max_pct con ventana = 0 es exactamente el drawdown desde el máximo histórico; con ventana = 252, el drawdown de 52 semanas (no hace falta un indicador aparte).',
    limitations: 'Con ventana = 0, "histórico" es desde el inicio de la serie cargada, no desde el debut del instrumento. La primera barra de la serie es su propio máximo y mínimo, así que dist_min_pct y dist_max_pct valen 0 ahí: usá un período de análisis razonable. Muchas series de esta app no tienen velas OHLC — en ese caso el canal usa el cierre.',
  },
  analisis_tecnico_percentil: {
    title: 'Percentil',
    shortDescription: 'Ranking del cierre actual dentro de la ventana: 0 cuando es el mínimo de la ventana, 100 cuando es el máximo. Con ventana = 0 el ranking es contra toda la historia cargada.',
    howItIsCalculated: '100 × (cantidad de cierres de la ventana estrictamente menores al actual) / (tamaño de la ventana − 1). Es un rank real, no un min-max: resiste outliers y da 0 y 100 exactos en los extremos.',
    howToInterpret: 'Valores bajos (< 10) marcan que el precio está en la zona más baja de su rango histórico; valores altos (> 90), en la más alta. Las líneas de referencia del panel están en 10 y 90.',
    limitations: 'Igual que Extremos: con ventana = 0, "histórico" es desde el inicio de la serie cargada. Necesita la ventana completa antes de dar el primer valor.',
  },
  analisis_tecnico_adx: {
    title: 'ADX (fuerza de la tendencia)',
    shortDescription: 'Mide qué tan fuerte es la tendencia, no hacia dónde va: sube cuando el precio se mueve en una dirección sostenida y baja cuando anda de lado. Viene con dos líneas: +DI (fuerza compradora) y −DI (fuerza vendedora).',
    howItIsCalculated: 'Compara el avance del máximo y del mínimo de cada rueda contra el de la anterior, lo suaviza con el método de Wilder (período 14) y lo relaciona con el rango verdadero. El ADX es el promedio suavizado de la diferencia entre +DI y −DI. Necesita unas 28 ruedas antes del primer valor.',
    howToInterpret: 'Por encima de 25 (la línea de referencia del panel) hay tendencia; por debajo, mercado lateral. Si +DI está sobre −DI, la tendencia es alcista; si no, bajista. Sirve de filtro: las estrategias de cruce de medias funcionan con ADX alto y fallan con ADX bajo.',
    limitations: 'Llega tarde: confirma una tendencia que ya está en marcha. Un ADX alto no distingue una suba de una caída; para eso están las líneas +DI y −DI.',
  },
  analisis_tecnico_supertrend: {
    title: 'SuperTrend',
    shortDescription: 'Una línea que acompaña al precio por debajo mientras sube (verde) y por encima mientras baja (roja), y que da vuelta cuando el precio la cruza.',
    howItIsCalculated: 'Toma el punto medio de la vela y le suma y resta un múltiplo del ATR (por defecto 3 × ATR de 10 ruedas). La banda inferior sólo sube y la superior sólo baja mientras la tendencia dura. La salida "dirección" vale +1 en tendencia alcista y −1 en bajista, y se puede usar en una estrategia (cruce de 0).',
    howToInterpret: 'Verde = tendencia alcista, la línea funciona como un stop que se va corriendo hacia arriba. Cuando el cierre la perfora cambia a rojo. Con un múltiplo más grande da menos señales y más lentas.',
    limitations: 'En un mercado lateral cambia de color seguido y cada cambio es una señal falsa con su comisión. Sin velas OHLC el ATR se calcula sobre cierres y pierde precisión.',
  },
  analisis_tecnico_keltner: {
    title: 'Canal de Keltner',
    shortDescription: 'Una media móvil exponencial con una banda arriba y otra abajo cuya distancia depende de la volatilidad reciente (ATR), no del desvío de los precios.',
    howItIsCalculated: 'Media = EMA del cierre (20 ruedas). Banda superior e inferior = media ± 2 × ATR de 20 ruedas.',
    howToInterpret: 'Un cierre fuera de la banda superior indica fuerza (o sobreextensión); dentro del canal, el precio está en su rango normal. Comparado con Bollinger, las bandas de Keltner son más suaves porque el ATR cambia más despacio que el desvío estándar.',
    limitations: 'No dice por sí solo si conviene comprar o vender: rupturas del canal tanto marcan arranques de tendencia como excesos que se revierten.',
  },
  analisis_tecnico_ichimoku: {
    title: 'Ichimoku (sin Chikou)',
    shortDescription: 'Un sistema que dibuja de una vez la tendencia, el soporte y la resistencia: dos líneas (Tenkan y Kijun) y una "nube" entre dos bandas (Senkou A y B).',
    howItIsCalculated: 'Tenkan = punto medio del máximo y mínimo de 9 ruedas; Kijun, de 26. Senkou A = promedio de Tenkan y Kijun; Senkou B = punto medio de 52 ruedas. La nube se dibuja corrida 26 ruedas: acá se muestra en la barra en la que aplica (el valor calculado hace 26 ruedas), así nunca usa datos del futuro. No incluye la línea Chikou, que mira hacia adelante.',
    howToInterpret: 'Precio por encima de la nube = tendencia alcista; por debajo, bajista; dentro, indefinida. La nube verde (A sobre B) es alcista y la roja, bajista. Un cruce de Tenkan sobre Kijun es la señal de corto plazo.',
    limitations: 'Necesita más de 78 ruedas antes de mostrar la nube completa. Tiene muchas líneas y, con períodos cortos o series con huecos, se vuelve difícil de leer en la pantalla del celular.',
  },
  calculadora_posicion: {
    title: 'Calculadora de tamaño de posición',
    shortDescription: 'Responde cuánto comprar para que, si el precio toca tu stop, pierdas sólo lo que decidiste arriesgar.',
    howItIsCalculated: 'Monto a invertir = riesgo ÷ distancia al stop (en %). Ejemplo: arriesgar US$ 100 con un stop a 8 % por debajo del precio significa invertir US$ 1.250. El riesgo puede ser un % del valor actual de tu cartera o un monto en dólares. El stop puede ser un precio, un % o un múltiplo del ATR. En un CEDEAR, la cantidad se calcula con el dólar MEP y el último precio del CEDEAR en pesos.',
    howToInterpret: 'Un stop más cerca permite una posición más grande con el mismo riesgo, pero salta más seguido. Si el monto resultante supera tu cartera, el stop es demasiado ajustado para ese riesgo.',
    limitations: 'La app no conoce tu efectivo disponible: el riesgo en % se mide sobre el valor de lo que ya tenés invertido. No incluye comisiones ni el deslizamiento: si el precio salta por debajo del stop, perdés más de lo calculado.',
  },
  screener_titulo: {
    title: 'Screener de proximidad',
    shortDescription: 'Recorre cada par (estrategia guardada, ticker de tu cartera ∪ watchlist) y te dice cuáles están a menos del umbral de distancia de disparar una compra o una venta.',
    whyItMatters: 'Reemplaza abrir el gráfico de cada ticker uno por uno: en una sola corrida ves dónde vale la pena mirar de cerca.',
    howToInterpret: 'Cada fila es una estrategia a punto de activarse en un ticker, ordenadas por distancia (arriba, lo más inminente). Verde = compra, rojo = venta; el borde dorado marca las que ya disparan hoy.',
    limitations: 'Sólo evalúa estrategias guardadas. Una estrategia atada a un ticker se evalúa nada más que sobre ese ticker; para que corra sobre todo el universo, guardala como "reutilizable" (sin ticker fijo) desde Análisis técnico. Los cruces de dos medias casi nunca aparecen salvo que las medias ya estén casi tocándose.',
    relatedTerms: ['screener_distancia', 'screener_precio_gatillo', 'screener_umbral'],
  },
  screener_universo: {
    title: 'Universo',
    shortDescription: 'Qué tickers entran al escaneo: "Todos" (cartera ∪ watchlist), sólo los que tenés en cartera, o sólo los de la watchlist.',
    whyItMatters: 'Acotar a "Cartera" sirve para vigilar salidas y stops de lo que ya tenés; "Watchlist", para cazar entradas de lo que venís siguiendo.',
  },
  screener_distancia: {
    title: 'Distancia al disparo',
    shortDescription: 'Cuánto tiene que moverse el precio (en %, con signo: negativo = tiene que bajar) para que la estrategia dispare compra o venta. Se busca el movimiento mínimo que hace cumplir la regla, no una proyección de hacia dónde va el precio.',
    whyItMatters: 'Ordena el universo por qué tan cerca está cada estrategia de activarse, sin tener que abrir el gráfico de cada ticker uno por uno.',
    limitations: 'Es una medida de distancia, no una predicción: que el precio esté a 1% de disparar no dice nada sobre si va a moverse en esa dirección.',
    relatedTerms: ['analisis_tecnico_estrategias', 'screener_precio_gatillo'],
  },
  screener_precio_gatillo: {
    title: 'Precio gatillo',
    shortDescription: 'El precio al que, de llegar el ticker, la estrategia dispararía hoy: `precio actual × (1 + distancia / 100)`.',
    whyItMatters: 'Es el número concreto para poner una alerta de precio o comparar contra el book, en vez de tener que calcular el porcentaje a mano.',
    relatedTerms: ['screener_distancia'],
  },
  screener_umbral: {
    title: 'Umbral de proximidad',
    shortDescription: 'El screener sólo muestra los pares (ticker, estrategia) cuya distancia al disparo es menor o igual a este porcentaje.',
    whyItMatters: 'Un umbral más angosto (1-2%) muestra sólo lo más inminente; uno más amplio (10%) da una vista más temprana, con más ruido.',
  },
  screener_dispara_ahora: {
    title: 'Dispara ahora',
    shortDescription: 'La estrategia cumple su regla con el precio actual, sin que el ticker tenga que moverse (distancia = 0%). Se marca con el borde dorado.',
    whyItMatters: 'Es la señal más urgente: no es "está cerca", es "está dada". Conviene revisar el gráfico y el desglose de condiciones antes de operar.',
    limitations: 'Que la regla esté dada hoy no implica que siga dada mañana ni que la señal sea buena: es lo que la estrategia pediría, nada más.',
  },
  screener_motivo: {
    title: 'Motivo',
    shortDescription: 'Qué parte de la estrategia está por dispararse: Entrada (abrir posición), Regla de salida (cierre por condición) o Stop loss / Take profit / Trailing stop (los límites de riesgo).',
    howToInterpret: 'Los motivos de salida y de stop sólo aparecen cuando la estrategia tiene una posición abierta en ese ticker; si no hay posición, únicamente puede aparecer Entrada.',
  },
  screener_condiciones: {
    title: 'Desglose de condiciones',
    shortDescription: 'Cada línea es una condición de la regla que está por dispararse, con su valor actual: el tilde marca las que ya se cumplen y la cruz las que faltan.',
    howToInterpret: 'La distancia al disparo es el movimiento de precio que hace que se cumplan todas a la vez. Si ya están casi todas tildadas, suele bastar un movimiento chico.',
  },
  screener_grafico_gatillo: {
    title: 'Gráfico del disparo',
    shortDescription: 'La línea punteada horizontal es el precio gatillo: el nivel al que la estrategia dispararía. El conector vertical va del cierre de hoy a ese nivel.',
    whyItMatters: 'Ver el gatillo apoyado en una media, un canal o un soporte da mucho más contexto que el número solo: no es lo mismo que el nivel esté a un tick de un cruce de medias que en el aire.',
    limitations: 'El gráfico corre un backtest sobre una ventana de tiempo distinta a la que usó el screener para calcular la distancia: los indicadores recursivos (EMA, RSI, MACD, ATR) pueden diferir en decimales. La distancia, el precio gatillo y las condiciones que se muestran son siempre los del escaneo, no los recalculados acá.',
    relatedTerms: ['screener_precio_gatillo', 'screener_distancia'],
  },
}
