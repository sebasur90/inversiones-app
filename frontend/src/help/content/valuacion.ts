import { HelpContent } from '../types'

export type ValuacionHelpKey =
  | 'valuacion_que_es'
  | 'valuacion_percentil'
  | 'valuacion_trampa_valor'
  | 'valuacion_pares_criterio'
  | 'valuacion_fuentes'
  | 'diagnostico_que_es'
  | 'diagnostico_familias'
  | 'diagnostico_calidad'
  | 'diagnostico_crecimiento'
  | 'diagnostico_solidez'
  | 'diagnostico_confianza'
  | 'diagnostico_origen'
  | 'comparador_que_es'
  | 'comparador_comparabilidad'
  | 'comparador_ranking'
  | 'comparador_conclusion'
  | 'comparador_minimo'
  | 'valor_razonable_que_es'
  | 'valor_razonable_margen'
  | 'valor_razonable_escenarios'
  | 'valor_razonable_supuestos'
  | 'valor_razonable_analistas'
  | 'impacto_cartera_que_es'
  | 'impacto_cartera_emisor'
  | 'historial_que_es'
  | 'historial_backtest'
  | 'aviso_diagnostico'

export const VALUACION_HELP: Record<ValuacionHelpKey, HelpContent> = {
  valuacion_que_es: {
    title: 'Valuación contra pares',
    shortDescription:
      'Compara cada acción, CEDEAR o ETF contra empresas o fondos parecidos (sus "pares": misma industria y tamaño similar) y dice si cotiza más barato, más caro o en línea con ellos.',
    whyItMatters:
      'Un P/E de 25 no dice nada solo: en bebidas puede ser caro y en software barato. Lo que sirve es compararlo contra competidores directos. Por eso la pantalla no da un puntaje: muestra dónde cae cada métrica dentro del grupo y la regla que produce la lectura.',
    howToInterpret:
      '"Más barata que sus pares" significa que al menos dos familias de métricas de valuación (ganancias, ventas y EBITDA, flujo de caja, valor libro) están entre el 25% más barato del grupo y ninguna entre el 25% más caro. Las métricas de una misma familia (P/E, P/E estimado y PEG) cuentan como un solo voto: miden lo mismo. "Barata, con señales de alerta" es lo mismo pero con calidad, crecimiento o precio en el piso del grupo: puede estar barata por una buena razón.',
    limitations:
      'Es un punto de partida para investigar, no una recomendación de compra o venta. Los datos salen de Yahoo y pueden tener errores o estar atrasados (se indica la fecha). Bonos, ONs, letras y FCI todavía no se comparan.',
    relatedTerms: ['diagnostico_que_es', 'valuacion_percentil', 'valuacion_trampa_valor', 'valuacion_pares_criterio', 'per', 'evEbitda'],
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
  diagnostico_que_es: {
    title: 'Diagnóstico de la empresa',
    shortDescription:
      'Responde cinco preguntas por separado: ¿está barata o cara?, ¿qué tan buen negocio es?, ¿cuánto crece?, ¿qué tan sólida es financieramente? y ¿cuánto se puede confiar en los datos?',
    whyItMatters:
      'Una acción puede estar barata y ser frágil, o cara y ser excelente. Un puntaje único mezclaría todo y escondería justo lo que importa, así que cada pregunta tiene su propio estado en palabras, las razones y la regla que lo produce.',
    howToInterpret:
      'Tocá cada fila para ver por qué, cómo se decide y qué información falta. "Barata" o "cara" no son buenas ni malas por sí solas. Si la confianza es baja, las demás conclusiones son poco firmes.',
    limitations:
      'Es una herramienta para investigar, no una recomendación de compra o venta. Se apoya en los datos de Yahoo (una foto de los últimos 12 meses, sin historia de varios años) y en la comparación con los pares elegidos.',
    relatedTerms: ['diagnostico_familias', 'diagnostico_origen', 'diagnostico_confianza', 'valuacion_que_es'],
  },
  diagnostico_familias: {
    title: 'Familias de métricas',
    shortDescription:
      'Agrupa las métricas que miden lo mismo para que cuenten una sola vez: P/E, P/E estimado y PEG (precio contra ganancias); EV/EBITDA y P/Ventas; flujo de caja libre; valor libro; dividendo.',
    whyItMatters:
      'Si tres métricas parecidas cuentan como tres votos, un P/E bajo alcanza solo para decir "barata". Con familias hace falta que coincidan visiones distintas de la empresa.',
    howItIsCalculated:
      'Cada familia vota lo que vota la mayoría de sus métricas. El dividendo suma pero no decide solo: uno alto puede ser un precio hundido y uno bajo es normal en empresas que reinvierten. El valor libro tampoco decide en tecnología, comunicaciones y salud, donde el patrimonio contable dice poco. En bancos y empresas inmobiliarias no se usan EV/EBITDA ni P/Ventas.',
  },
  diagnostico_calidad: {
    title: 'Calidad del negocio',
    shortDescription: 'Qué tan rentable es la empresa: márgenes (bruto, operativo, neto) y retornos (ROE, ROA), comparados con sus pares.',
    howItIsCalculated:
      '"Alta": márgenes y retornos entre el 25% mejor del grupo. "Débil": entre el 25% peor, o pérdidas (margen operativo o neto negativo, ROE negativo) aunque los pares estén igual o peor. "Media": el resto.',
    limitations:
      'Mide el último año contra los pares; no evalúa si los márgenes son estables en el tiempo porque no hay historia de varios años. Para bancos o petroleras faltan indicadores propios del sector (se listan en "qué falta").',
  },
  diagnostico_crecimiento: {
    title: 'Crecimiento',
    shortDescription:
      'Cuánto crecieron los ingresos y las ganancias del último trimestre frente al mismo trimestre del año anterior (dato), y cuánto crecimiento de ganancias descuenta el mercado para el año que viene (estimación).',
    howItIsCalculated:
      'El crecimiento esperado sale de comparar el P/E de los últimos 12 meses con el P/E estimado: ganancia estimada ÷ ganancia actual − 1. "En caída": ingresos cayendo más de 2% interanual. "Alto"/"Bajo": ingresos y ganancias entre el 25% mejor o peor del grupo; la estimación suma pero no decide sola.',
    limitations:
      'Un trimestre no dice si el crecimiento es sostenido, y la estimación depende de lo que proyectan los analistas: pueden equivocarse. Con ganancias negativas el crecimiento de ganancias no se calcula.',
  },
  diagnostico_solidez: {
    title: 'Solidez financiera',
    shortDescription: 'Si la empresa puede sostenerse: deuda, flujo de caja, liquidez, si el dividendo se cubre con ganancias y qué tan volátil es.',
    howItIsCalculated:
      '"Frágil": dos o más señales fuertes (deuda mayor a 2 veces el patrimonio, flujo de caja libre negativo, sin ganancias, dividendo mayor a las ganancias). "Con señales de atención": una señal fuerte, liquidez corriente menor a 1, beta mayor a 1,5 o deuda entre las más altas del grupo. "Sólida": al menos dos indicadores evaluados y ninguna señal.',
    limitations:
      'Algunos negocios (retail, restaurantes) operan con liquidez menor a 1 sin problema. Faltan deuda y caja absolutas: se usa el cociente deuda/patrimonio de Yahoo.',
  },
  diagnostico_confianza: {
    title: 'Confianza de los datos',
    shortDescription: 'Cuánto de las conclusiones se apoya en datos completos, recientes y comparables.',
    howItIsCalculated:
      'Se toma el peor de estos chequeos: cuántas métricas aplicables tienen dato, cuántos pares tienen datos, qué tan reciente es la descarga y el último balance, y si hubo conversión de moneda o balances de períodos distintos.',
    howToInterpret:
      'Confianza baja no significa que la empresa sea mala: significa que faltan datos, son viejos o hay pocos competidores comparables. Un dato que falta nunca se toma como malo.',
  },
  diagnostico_origen: {
    title: 'Dato, estimación o calculado',
    shortDescription:
      'Dato: lo informó Yahoo tal cual. Estimación: depende de proyecciones de analistas (P/E estimado, PEG, crecimiento esperado). Calculado: lo derivó la app (rendimiento del precio, flujo de caja libre sobre capitalización, ratios recalculados en USD). Las conclusiones ("Barata", "Débil"…) las calcula siempre la app.',
    whyItMatters: 'Una estimación puede no cumplirse. Por eso se marca y no mueve por sí sola la lectura clásica.',
  },
  comparador_que_es: {
    title: '¿Qué compraría en su lugar?',
    shortDescription:
      'Pone el instrumento lado a lado con alternativas comparables —incluso de afuera de su grupo de pares— y muestra en qué es mejor o peor, dónde queda en el grupo y por qué podría merecer un múltiplo mayor o menor.',
    whyItMatters:
      'Saber que algo está barato no alcanza: hay que saber barato contra qué. Esta comparación te deja elegir contra quién medirlo y te dice, con reglas que se ven, si la diferencia de precio tiene una explicación en la calidad, el crecimiento o la solidez.',
    howToInterpret:
      'Sin elegir, usa tu grupo de pares. Podés sumar las sugeridas, buscar otra alternativa o quitar las que no te convencen. Cada alternativa dice por qué es (o no) comparable; la tabla sólo muestra las métricas que importan al sector y aclara lo que no aplica.',
    limitations:
      'Es un análisis relativo: no dice si el precio es el correcto (para eso está la tarjeta «Valor razonable»), no mide el efecto en tu cartera (para eso está «¿Cómo cambiaría mi cartera?») y no es una recomendación de compra o venta. La elección de alternativas no se guarda; para cambiar tu grupo permanente usá "Editar" en Pares.',
    relatedTerms: ['comparador_comparabilidad', 'comparador_ranking', 'comparador_conclusion', 'comparador_minimo', 'diagnostico_que_es'],
  },
  comparador_comparabilidad: {
    title: 'Comparabilidad de una alternativa',
    shortDescription:
      'Qué tan parecida es una alternativa: alta, media o baja. Compartir la industria de Yahoo no alcanza: también cuentan el tamaño, la región, el modelo de negocio y si hay datos suficientes y de la misma moneda y período.',
    howItIsCalculated:
      'Alta: misma industria, tamaño parecido (entre 0,2 y 5 veces) y misma región. Media: misma industria con una de las otras dos, o mismo sector con tamaño parecido y misma región. Baja: el resto; se ve en la tabla pero no entra al ranking ni a la conclusión. Si los balances son de otro período, están en otra moneda o son viejos, una "alta" baja a "media". Una alternativa que agregaste a mano como par sube a "media" como mínimo.',
    howToInterpret:
      '"No comparable" es un descarte con motivo: el mismo emisor en otro mercado (tu CEDEAR y su acción de origen no son dos exposiciones distintas), un ETF contra una empresa individual, un banco contra una industrial, o pocos datos.',
    limitations: 'La industria y el sector son los de Yahoo (o tu corrección); si están mal clasificados, la comparabilidad también.',
  },
  comparador_ranking: {
    title: 'Ranking dentro del grupo',
    shortDescription:
      'Dónde queda el instrumento entre las alternativas que cuentan, dimensión por dimensión (valuación, calidad, crecimiento, solidez). Puesto 1 es el mejor; en valuación, el más barato.',
    howItIsCalculated:
      'Se vuelve a calcular el diagnóstico de cada miembro contra los demás miembros del grupo (no contra sus pares automáticos), así los percentiles son comparables entre sí. Se ordena por la mediana de los percentiles favorables; en solidez, primero por el estado. "Arriba" es el primer tercio de los puestos y "abajo" el último; con 4 miembros sólo el 1.º es arriba y sólo el 4.º es abajo.',
    limitations: 'Con pocos miembros el percentil es grueso: con 3, cada puesto vale un salto grande. Por eso la conclusión dice qué tan firme es.',
  },
  comparador_conclusion: {
    title: 'La conclusión comparativa',
    shortDescription:
      'Una lectura armada con reglas fijas, no un texto libre: ubica el precio del instrumento en el grupo y lo cruza con su calidad, crecimiento y solidez. Cada frase muestra la regla que la produjo.',
    howItIsCalculated:
      'Si cotiza entre los más caros y sus fundamentos lo respaldan, la prima tiene una explicación. Si cotiza caro y los fundamentos no lo acompañan, la prima es difícil de justificar. Si cotiza entre los más baratos y hay debilidades, el descuento puede explicarse por ellas; si no las hay, no se ve con estos datos por qué está barato. En el medio, está en línea. Además se avisa cuando una alternativa es más barata y no es peor en ninguna dimensión (o al revés).',
    howToInterpret:
      '"Podría merecer un múltiplo mayor/menor" explica la diferencia de precio relativo, no si es una buena inversión. "Lectura firme/orientativa/poco firme" depende de cuántas alternativas hay, de la confianza en los datos y de si hay balances de otro período o moneda.',
    limitations:
      'No dice "comprá" ni "vendé". No hay historia contable de varios años; el valor razonable por múltiplos y el efecto en tu cartera son otros cálculos, aparte.',
  },
  comparador_minimo: {
    title: 'Mínimo de alternativas',
    shortDescription: 'Hacen falta al menos 2 alternativas comparables con datos para ordenar y concluir.',
    whyItMatters:
      'Con el instrumento y 2 alternativas hay 3 valores por métrica: lo mínimo para hablar de posición en un grupo. Con una sola, podés ver la tabla lado a lado pero no hay ranking ni conclusión.',
    howToInterpret: 'Si faltan, sumá alguna de las sugeridas o buscá otra con parecido de industria, tamaño y región. Las de comparabilidad baja se ven pero no cuentan para el mínimo.',
  },
  valor_razonable_que_es: {
    title: 'Valor razonable y escenarios',
    shortDescription:
      'A qué precio cotizaría la empresa si se le aplicaran los múltiplos que hoy pagan sus pares (P/E, P/Ventas, EV/EBITDA, flujo de caja, valor libro). Da un rango con tres escenarios —pesimista, base y optimista— y lo compara con el precio de hoy.',
    whyItMatters:
      'Saber que algo cotiza más barato que sus pares no dice cuánto más. Esto lo traduce a un precio y muestra cuánto colchón hay (margen de seguridad) y cuánto subiría hasta ese valor (potencial), con los supuestos a la vista y editables.',
    howItIsCalculated:
      'Por cada múltiplo: precio × múltiplo de los pares ÷ múltiplo propio. En EV/EBITDA se descuenta además la deuda neta (EV − capitalización). Las métricas de una misma familia (P/E y P/E estimado; EV/EBITDA y P/Ventas) cuentan una vez: se toma la mediana de cada familia y después la mediana entre familias. Hacen falta al menos 2 familias, cada método con 4 o más pares con dato.',
    howToInterpret:
      'Si el precio está por debajo del escenario pesimista, cotiza más barato que todo el rango según sus pares; por encima del optimista, más caro; en el medio, dentro del rango. "Los métodos no convergen" significa que los múltiplos dan valores muy distintos entre sí (más de 2 veces): el rango es poco confiable.',
    limitations:
      'Es un valor relativo a los pares elegidos, no un valor intrínseco ni un pronóstico: si todo el grupo está caro o barato, el valor lo hereda. Usa los datos de los últimos 12 meses de Yahoo: no compara con los múltiplos históricos de la propia empresa. No es una recomendación de compra o venta.',
    relatedTerms: ['valor_razonable_margen', 'valor_razonable_escenarios', 'valor_razonable_supuestos', 'valuacion_pares_criterio', 'comparador_que_es'],
  },
  valor_razonable_margen: {
    title: 'Margen de seguridad y potencial',
    shortDescription:
      'Dos números distintos para la misma brecha entre el valor y el precio. Margen de seguridad = (valor − precio) ÷ valor: cuánto del valor es colchón. Potencial = (valor − precio) ÷ precio: cuánto subiría el precio hasta llegar al valor.',
    example:
      'Valor 125 y precio 100: el margen de seguridad es 20 % (el precio está 20 % por debajo del valor) y el potencial es +25 % (el precio tendría que subir 25 % para llegar a 125).',
    howToInterpret:
      'Los dos son negativos cuando el precio está por encima del valor. El potencial siempre es mayor que el margen cuando el valor supera al precio; no los confundas ni los restes.',
    limitations: 'Ninguno de los dos es una predicción: dependen de que los pares estén bien valuados.',
  },
  valor_razonable_escenarios: {
    title: 'Escenarios pesimista, base y optimista',
    shortDescription:
      'Los tres valores salen de los múltiplos de los pares: el pesimista usa el cuartil inferior (el 25 % más barato del grupo), el base la mediana y el optimista el cuartil superior (el 25 % más caro).',
    whyItMatters: 'Un solo número da una falsa precisión. El rango muestra cuánto cambia el valor según cuánto paga el mercado por empresas parecidas.',
    limitations: 'No son pronósticos de precio ni probabilidades: sólo describen la dispersión de los múltiplos de los pares.',
  },
  valor_razonable_supuestos: {
    title: 'Supuestos editables',
    shortDescription:
      'Podés mover tres cosas: un ajuste general sobre los múltiplos de referencia (por ejemplo −10 % si creés que merece un descuento), excluir métodos que no te convencen y fijar a mano el múltiplo de un método.',
    howToInterpret:
      'El ajuste general no se aplica a un múltiplo que fijaste a mano. Los supuestos se guardan para este emisor y se repiten en la respuesta; "Restablecer" vuelve a la mediana de los pares.',
    limitations: 'Cambiar los supuestos cambia el resultado: es tu criterio, no un dato. Quedan a la vista para que sepas qué estás mirando.',
  },
  valor_razonable_analistas: {
    title: 'Referencia: precio objetivo de analistas',
    shortDescription:
      'Promedio, mínimo y máximo de los precios objetivo que informan los analistas que sigue Yahoo, y cuántos son. Es una estimación de terceros.',
    howToInterpret: 'Se muestra aparte y no entra en el valor razonable, el rango ni la lectura: sirve para contrastar, no para sumar.',
    limitations: 'Puede estar desactualizado o venir de pocos analistas; sólo se muestra cuando el balance está en la misma moneda que la cotización.',
  },
  impacto_cartera_que_es: {
    title: '¿Cómo cambiaría mi cartera?',
    shortDescription:
      'Simula sumar un monto en dólares de este emisor y muestra cómo quedarían los pesos de tu cartera antes y después: por emisor, sector, país, región y tipo de instrumento.',
    whyItMatters:
      'Una idea que parece buena sola puede dejarte demasiado concentrado en un emisor, un sector o un país. Acá lo ves antes de decidir nada.',
    howItIsCalculated:
      'Se toma tu cartera valuada hoy (con el mismo criterio que el Resumen: lo que no tiene cotización se valúa al costo y se avisa) y se le suma el monto en una fila simulada. Los pesos "antes" son exactamente los de Exposición. Las observaciones usan los umbrales de Salud de cartera: por emisor, desde 20 % de atención y 30 % de revisar (o tu peso máximo configurado, y 1,5 veces ese valor para revisar); por país, desde 70 % y 90 %.',
    howToInterpret:
      'Mirá la fila marcada con ◂ en cada eje: es donde cae el monto. "Cambio (pp)" son puntos porcentuales de la cartera. Si el ticker no tiene sector, país o región cargados, el monto cuenta en «Sin sector», «Sin país» o «Sin región» hasta que lo corrijas en la ficha.',
    limitations:
      'No guarda nada, no escribe movimientos, no estima el precio ni la cantidad de títulos y no es una recomendación de compra o venta. El resultado es con la cartera de hoy: no proyecta precios.',
    relatedTerms: ['impacto_cartera_emisor', 'valuacion_que_es'],
  },
  impacto_cartera_emisor: {
    title: 'Emisor (un CEDEAR y su acción de origen cuentan una sola vez)',
    shortDescription:
      'Un mismo emisor puede cotizar con varios tickers: el CEDEAR en pesos, el CEDEAR en dólares y la acción de origen. A efectos de concentración son una sola exposición.',
    whyItMatters:
      'Tener KO y KOD no es diversificar: si Coca-Cola cae, caen los dos. Por eso este eje suma las variantes y lo aclara debajo del nombre.',
    howToInterpret: 'Los "emisores equivalentes" dicen cuántas posiciones iguales darían la misma concentración: más alto, más repartida la cartera.',
  },
  historial_que_es: {
    title: 'Historial del diagnóstico',
    shortDescription:
      'Cada vez que cambia algo en el diagnóstico de una empresa de tu cartera o tu watchlist (el dato de Yahoo, los estados o los pares), la app guarda una foto con lo que decía ese día y la versión de las reglas que lo dijo.',
    whyItMatters:
      'Sin esas fotos no hay forma honesta de saber si "barata" o "calidad débil" anticiparon algo: recalcular el pasado con las reglas y los datos de hoy sería mirar el futuro.',
    howToInterpret:
      'Una foto nunca se modifica. Si cambian las reglas del diagnóstico, la foto lo marca y sus estados no se comparan con los de la anterior: no es un cambio de la empresa. "Sin cambios de estado" significa que cambió el dato o los pares pero las conclusiones siguieron igual.',
    limitations:
      'Empieza a acumularse desde que existe esta función: no reconstruye el pasado, porque no hay datos contables históricos. Se guarda después de cada corrida de la ingesta de fundamentales.',
    relatedTerms: ['historial_backtest', 'aviso_diagnostico'],
  },
  historial_backtest: {
    title: '¿Anticiparon algo estos estados?',
    shortDescription:
      'Compara, para cada estado del diagnóstico, qué hizo el precio (en USD) a 30, 90 y 180 días de la entrada a ese estado, al lado del resultado de todos los eventos.',
    howItIsCalculated:
      'Sólo cuentan entradas a un estado (la primera foto o un cambio), no cada foto repetida, y estados de versiones de reglas distintas no se mezclan. Hasta tener al menos 30 eventos por estado y horizonte no se muestra ningún promedio.',
    howToInterpret: 'Un retorno solo no dice nada: se mira contra la fila "Todos los eventos". Si en general subió, que un estado haya subido no lo distingue.',
    limitations:
      'Es el precio sin dividendos ni costos y no promete nada sobre el futuro. Con una muestra chica, o un período donde todo subió o bajó, no se puede concluir.',
  },
  aviso_diagnostico: {
    title: 'Aviso de cambio de diagnóstico',
    shortDescription:
      'Un mensaje por Telegram cuando la valuación, la calidad o la solidez de una empresa de tu cartera o tu watchlist pasa a otro estado, con el estado anterior, el nuevo, la razón principal y la fecha del dato.',
    howItIsCalculated:
      'Para no avisar por ruido, el cambio tiene que verse en dos actualizaciones de datos distintas seguidas. No avisa si el dato tiene más de 21 días, si la confianza de los datos es baja, ni cuando cambian las reglas del diagnóstico (se toma el estado nuevo como punto de partida). La primera vez sólo registra el estado actual.',
    limitations: 'Es información de seguimiento: no indica qué hacer. Se puede apagar en Ajustes → Avisos.',
  },
}
