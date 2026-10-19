import type { GuiaPantalla } from '../types'

/**
 * Guías "Cómo leer esta pantalla", una por ruta. Las consume `GuiaPantalla.tsx` (el componente,
 * homónimo del tipo) resolviendo por `useLocation().pathname` desde `ScreenHeader`, así que no
 * hace falta tocar cada página para agregar o editar una guía.
 *
 * Las claves son las rutas tal como están declaradas en `App.tsx`, con dos excepciones:
 * `/ticker` es una clave "virtual" que cubre cualquier `/ticker/:ticker` (ver `resolverGuia`).
 *
 * Los `terminos` son claves de `HELP` (`help/content/index.ts`): se muestran como chips que abren
 * el modal de ese término, así la guía no tiene que reexplicar lo que el glosario ya explica.
 */
export const GUIAS_PANTALLA: Record<string, GuiaPantalla> = {
  '/resumen': {
    queEs: 'La portada: cuánto vale tu cartera hoy y qué necesita tu atención primero.',
    comoLeerla: [
      'El número grande es el valor total de tu cartera, en la moneda que elegiste (USD o ARS).',
      'Los indicadores debajo resumen cuánto ganaste o perdiste en total.',
      '"Requiere atención" junta lo urgente —alertas de precio, datos viejos— para no tener que recorrer pantalla por pantalla.',
      'Los dos círculos de "Salud de cartera" y "Calidad de datos" son scores de 0 a 100: más alto es mejor.',
    ],
    queHacer: [
      'Si aparece algo en "Requiere atención", tocalo para ir directo al detalle.',
      'Si la línea de "Datos hace…" se ve en naranja o coral, tocá el ícono de sincronizar.',
    ],
    ojo: 'El valor total cambia también cuando cambiás entre USD y ARS: no es que tu cartera se movió, es el tipo de cambio.',
    terminos: ['benchmark', 'xirr'],
  },

  '/posiciones': {
    queEs: 'El detalle de cada instrumento que tenés hoy: cuánto, a qué precio y cómo viene rindiendo.',
    comoLeerla: [
      'Cada fila es un ticker: cantidad, precio promedio de compra y precio actual.',
      'El % de rendimiento compara el precio actual contra tu precio promedio de compra, no contra lo que pagaste en cada operación.',
      'Si una posición dice "al costo", todavía no entró una cotización: se valúa a lo que pagaste, así que su rendimiento figura en cero hasta que haya precio.',
      'Los filtros de arriba (Con alerta, Stop loss, Objetivo) muestran sólo lo que necesita una decisión tuya.',
    ],
    queHacer: [
      'Tocá cualquier fila para ver el detalle completo de ese ticker.',
      'Para poner o mover el stop loss y el objetivo, entrá al ticker y tocá esas dos tiles.',
    ],
    terminos: ['posiciones_rendimiento_simple', 'stopLoss', 'objetivo', 'nivel_origen'],
  },

  '/rendimiento': {
    queEs: 'Cuánto ganaste o perdiste en total, medido de varias formas distintas.',
    comoLeerla: [
      '"Realizado" es lo que ya cobraste al vender; "no realizado" es la ganancia en papel de lo que todavía tenés.',
      'La tabla compara el mismo período en pesos nominales, pesos ajustados por inflación (CER) y dólares (MEP): son tres fotos distintas de la misma plata.',
      'La TIR (XIRR) tiene en cuenta cuándo pusiste o sacaste plata; el TWRR mide sólo cómo rindió la estrategia, sin que tus aportes lo distorsionen.',
      'El mapa de calor mensual marca cada mes como positivo (verde) o negativo (coral), de un vistazo.',
    ],
    queHacer: ['Si sólo querés "cuánto gané", mirá "Simple (período)" o el Total.'],
    ojo: 'La TIR anualizada extrapola tu historial a 12 meses: con pocos meses de actividad puede verse exageradamente alta o baja.',
    terminos: ['xirr', 'twr', 'simple', 'realizado', 'noRealizado'],
  },

  '/riesgo': {
    queEs: 'Qué tan agitado fue el camino de tu cartera, no sólo a dónde llegó.',
    comoLeerla: [
      'El drawdown es la peor caída desde un máximo: cuánto habrías perdido vendiendo en el peor momento.',
      'La volatilidad mide cuánto se mueve tu cartera mes a mes; alta no es "malo" en sí, es más montaña rusa.',
      'Sharpe, Sortino y Calmar comparan cuánto ganaste contra cuánto riesgo tomaste: más alto es mejor.',
      '"Mejores meses" y "peores meses" son los extremos reales, no un promedio.',
    ],
    ojo: 'Estas métricas piden varios meses de historial: con una cartera nueva, casi todas van a decir "Datos insuficientes", y es esperable.',
    terminos: ['drawdown', 'volatilidad', 'sharpe', 'sortino', 'calmar'],
  },

  '/rebalanceo': {
    queEs: 'Compara cómo está repartida tu cartera hoy contra cómo definiste que debería estar.',
    comoLeerla: [
      'Cada eje (por ejemplo, tipo de activo) tiene un peso objetivo %; la barra muestra qué tan lejos estás de él.',
      '"Sin objetivo" son categorías que tenés pero todavía no les definiste un peso.',
      'El simulador de abajo traduce la diferencia a plata: cuánto comprar o vender de cada cosa.',
    ],
    queHacer: ['Usá "Solo nuevos aportes" si preferís acercarte al objetivo sin vender nada.'],
    ojo: 'Simular no ejecuta nada real: es una cuenta hipotética para decidir antes de operar.',
    terminos: ['rebalanceo', 'objetivo'],
  },

  '/simulador': {
    queEs: 'Un "qué pasaría si…?" para tu cartera: probás escenarios sin tocar nada real.',
    comoLeerla: [
      'Modo "Sencillo": preguntas cotidianas en lenguaje simple ("¿y si aporto más?", "¿y si dejo de aportar?"), con sólo 6 supuestos.',
      'Modo "Avanzado": el simulador de siempre, con escenarios de mercado (dólar, dividendos, comisiones) para quien ya sabe esos números.',
      'En ambos modos, el gráfico proyecta la evolución de tu patrimonio mes a mes y la tabla compara los escenarios entre sí.',
    ],
    queHacer: ['Si no sabés qué poner en "variación del dólar" o "dividend yield", empezá por el modo Sencillo.'],
    ojo: 'Es una proyección con los supuestos que vos cargaste, no una predicción: cambiá los números y el resultado va a cambiar mucho.',
    terminos: ['vida_crecimiento_anual', 'vida_aporte_mensual', 'escenario_horizonte'],
  },

  '/analisis-tecnico': {
    queEs: 'Gráfico de velas con indicadores técnicos, para estudiar un ticker y probar reglas de entrada/salida.',
    comoLeerla: [
      'Elegís un ticker y un período; si activás indicadores, sus líneas se superponen al precio.',
      'El botón ▲▼ marca tus compras y ventas reales: ▼ verde si esa venta ganó, roja si perdió. En una posición abierta, una línea punteada marca tu costo promedio. En un CEDEAR, la marca ubica tu precio en pesos sobre la vela del subyacente de ese día: sirve para ver el momento, no es el precio exacto en dólares. Las "D" de la base son dividendos o cupones cobrados, y la línea fina punteada es el VWAP anclado a tu primera compra (el precio medio del mercado desde que entraste). Al tocar una vela, la ficha suma el contexto de cada compra (RSI, distancia a la SMA200, posición en el rango anual) y qué pasó 30, 90 y 180 días después de cada venta.',
      'El selector D / S / M cambia las velas a diarias, semanales o mensuales (los indicadores se calculan sobre esas barras; las estrategias, el backtest y las alertas siguen en diario). Los botones de arriba del gráfico prenden: ▲▼ tus compras y ventas, "log" la escala logarítmica, "S/R" los soportes y resistencias automáticos (niveles donde el precio rebotó al menos dos veces en el período que estás mirando; el número es la cantidad de toques) y "Fuerza rel." un panel con el ratio del activo contra un índice (S&P 500, Nasdaq o Merval): si sube, le gana al índice; si baja, le pierde. El botón "log" pasa el precio a escala logarítmica: la misma distancia vertical es el mismo porcentaje de variación, útil para períodos largos.',
      'El botón ✎ te deja dibujar sobre el gráfico: una línea horizontal (un toque), una línea de tendencia (dos toques, se extiende hacia la derecha) o un retroceso de Fibonacci (dos toques: del inicio al final del movimiento). Tocá un dibujo para seleccionarlo y borrarlo. Quedan guardados y anclados a fecha y precio, así que se mantienen al cambiar el período o el intervalo; sólo se ven en la serie (local o subyacente) en la que los dibujaste.',
      'La pestaña "Estrategias" te deja definir reglas (por ejemplo, cruce de medias) y correr un backtest sobre el historial.',
      'El backtest simula cómo le habría ido a esa estrategia en el pasado.',
    ],
    queHacer: ['Si es tu primera vez, arrancá desde un preset ya armado en vez de crear una estrategia desde cero.'],
    ojo: 'Que una estrategia haya funcionado en el pasado no garantiza que siga funcionando: los mercados cambian.',
    terminos: ['analisis_tecnico_indicadores', 'analisis_tecnico_estrategias', 'analisis_tecnico_backtest'],
  },

  '/screener': {
    queEs: 'Recorre varios tickers a la vez y avisa cuáles están cerca de disparar una estrategia guardada.',
    comoLeerla: [
      'Elegís una o más estrategias y un umbral de distancia %: el screener busca tickers a esa distancia de la señal.',
      '"Dispara ahora" significa que la condición ya se cumple hoy, no que esté por cumplirse.',
    ],
    queHacer: ['Necesitás al menos una estrategia guardada en Análisis técnico antes de poder escanear.'],
    terminos: ['screener_umbral', 'screener_dispara_ahora', 'screener_grafico_gatillo'],
  },

  '/mapa-mercado': {
    queEs: 'Todas las acciones, CEDEARs y ETFs del mercado dibujados como un mapa: las empresas parecidas quedan juntas y el color dice cuánto subieron o bajaron.',
    comoLeerla: [
      'Cada rectángulo es una empresa. Verde subió, rojo bajó, y cuanto más fuerte el color, más se movió. Gris es que todavía no hay dato.',
      'Las empresas están agrupadas por sector, región, tamaño o tipo (lo elegís arriba). Cada bloque trae su nombre y cuánto se movió en conjunto.',
      'El tamaño del rectángulo puede ser la capitalización de la empresa, lo que pesa en tu cartera, o igual para todas.',
      'Un borde blanco marca lo que tenés en cartera y uno azul lo que seguís en la watchlist.',
    ],
    queHacer: [
      'Tocá el nombre de un bloque para entrar a sus subgrupos (de un sector a sus industrias, de una región a sus países).',
      'Tocá un rectángulo para ver la ficha: sus variaciones a 1 día, semana, mes y año, su tamaño y su peso en tu cartera, con un atajo a la ficha completa.',
      'Probá "Parejo" para contar cuántas subieron y cuántas bajaron sin que las gigantes tapen al resto.',
    ],
    ojo: 'La variación es en dólares y se actualiza una vez por día, después del cierre de EE.UU.: no es en vivo. Y que algo esté en rojo no quiere decir que esté barato: para eso está Valuación vs. pares.',
    terminos: ['mapa_que_es', 'mapa_agrupar', 'mapa_tamano', 'mapa_variacion', 'mapa_promedio_grupo', 'mapa_sin_dato'],
  },

  '/valuacion': {
    queEs: 'Qué acciones, CEDEARs y ETFs están más baratos o más caros que sus competidores, para decidir dónde mirar antes de entrar o salir.',
    comoLeerla: [
      'Cada tarjeta es un instrumento con su lectura en palabras (Barata, Cara, En línea, Mixta…), cuatro estados por separado (valuación, calidad, crecimiento y solidez), la confianza en los datos y las dos razones principales.',
      'Arriba elegís el universo: lo que tenés, lo que seguís en la watchlist, o todo el catálogo de IOL. Los chips filtran por lectura, región y tipo, y "Ordenar por" ordena por un criterio a la vez (más baratas, mejor calidad, más crecimiento, más confianza).',
      '"Barata con alertas" es barata pero con calidad, crecimiento o precio flojos: puede estar barata por una buena razón.',
      'La barra de arriba dice cuántos emisores ya tienen datos: la app los baja de Yahoo de a poco, dos veces por día.',
    ],
    queHacer: [
      'Tocá una tarjeta para ver el detalle: métrica por métrica contra sus pares, quiénes son esos pares y su precio comparado. Ahí mismo, "¿Qué compraría en su lugar?" lo compara con alternativas que elijas.',
      'Si falta un competidor o la clasificación está mal, corregilo desde la ficha: vale para todas las pantallas.',
    ],
    ojo: 'No es una recomendación de compra o venta. Los datos de Yahoo pueden estar atrasados o tener errores; la ficha muestra la fecha y las advertencias.',
    terminos: ['valuacion_que_es', 'diagnostico_que_es', 'valuacion_percentil', 'valuacion_trampa_valor', 'valuacion_pares_criterio', 'per'],
  },

  '/movimientos': {
    queEs: 'El historial completo: cada compra, venta, dividendo, cupón y amortización que cargaste en el Sheet.',
    comoLeerla: [
      'Están agrupados por fecha, más reciente primero.',
      'Buscá por ticker o cartera con la lupa; "Ver comisiones pagadas" lleva al desglose de costos.',
    ],
    terminos: ['movimientos_dividendo', 'movimientos_cupon', 'movimientos_amortizacion'],
  },

  '/watchlist': {
    queEs: 'Instrumentos que seguís sin tenerlos todavía: cuánto falta para que entren en tu zona de compra.',
    comoLeerla: [
      '"Zona de compra" es el rango de precio que vos definiste como atractivo para entrar.',
      'El filtro "Con alerta" muestra sólo los que ya están cerca o dentro de esa zona.',
    ],
    queHacer: [
      'Tocá "Agregar" y buscá el instrumento en el catálogo (podés filtrar por acción, CEDEAR, bono, ON, letra o FCI): la app le baja el último precio al elegirlo.',
      'Tocá cualquier fila para fijar o cambiar su precio objetivo, anotarte por qué lo seguís, refrescar el precio o dejar de seguirlo.',
    ],
    terminos: ['watchlist_zona_compra', 'watchlist_distancia'],
  },

  '/ticker': {
    queEs: 'Todo sobre un instrumento puntual: resumen, rendimiento, riesgo, histórico de precios y cómo está valuado contra sus pares.',
    comoLeerla: [
      'Las pestañas de arriba cambian la vista sin salir de la pantalla.',
      '"Resumen" da la foto rápida; el resto son las mismas métricas que ves en Rendimiento y Riesgo, pero sólo para este ticker.',
      '"Pares" lo compara contra competidores parecidos (misma industria y tamaño) y muestra de dónde sale su sector, país y región.',
      'Dentro de "Pares", la tarjeta "¿Qué compraría en su lugar?" lo pone lado a lado con alternativas comparables que elegís vos (o sugeridas), con una conclusión que explica por qué podría merecer un múltiplo mayor o menor.',
      'Dentro de "Pares", la tarjeta "Valor razonable" estima a qué precio cotizaría con los múltiplos de sus pares (pesimista, base y optimista), separa el margen de seguridad del potencial y deja editar los supuestos.',
      'Dentro de "Pares", "¿Cómo cambiaría mi cartera?" simula sumar un monto en dólares de ese emisor y muestra cómo quedarían tus pesos por emisor, sector, país, región y tipo, con los umbrales de Salud de cartera. Sólo simula: no guarda nada.',
      'Dentro de "Pares", "Cómo fue cambiando" muestra las fotos del diagnóstico que fue guardando la app, con la versión de las reglas de cada una; si lo tenés en cartera o watchlist, también te puede avisar por Telegram cuando un estado cambia.',
    ],
    terminos: ['tickerdetalle_total_pl', 'tickerdetalle_retorno_anualizado', 'valuacion_que_es', 'diagnostico_que_es', 'comparador_que_es', 'valor_razonable_que_es', 'impacto_cartera_que_es', 'historial_que_es', 'valuacion_fuentes'],
  },

  '/objetivo': {
    queEs: 'Tu meta de patrimonio: cuánto falta y qué aporte mensual necesitás para llegar a tiempo.',
    comoLeerla: [
      'El plan compara tu ritmo actual de aportes contra el necesario para llegar a la fecha límite.',
      'Los tres escenarios (conservador/base/optimista) usan distintas tasas de rendimiento esperado.',
      'La grilla de sensibilidad muestra cómo cambia la fecha estimada si aportás más o menos por mes.',
    ],
    queHacer: ['Si todavía no cargaste un objetivo, hacelo en la pestaña Objetivo del Sheet y sincronizá.'],
    ojo: 'Son estimaciones con la tasa de rendimiento que elijas, no una promesa de resultado.',
    terminos: ['objetivo_monto', 'objetivo_fecha_limite', 'objetivo_aporte_mensual'],
  },

  '/aportes': {
    queEs: 'Cuánta plata nueva ponés en tus inversiones cada mes, qué tan constante venís siendo y a dónde llegarías si mantenés el ritmo.',
    comoLeerla: [
      'Tiene dos pestañas: "Progreso" mira tu hábito (racha, nivel, objetivo del mes, logros, récords) y "Análisis" mira el detalle estadístico de siempre (comparaciones, proyección a fin de año, tabla por año).',
      'El nivel de constancia depende sólo de cuántos meses aportaste y de tu mejor racha: nunca del monto ni de cuánto rindieron tus inversiones.',
      'Si definís un objetivo mensual, la tarjeta de arriba muestra cuánto llevás, cuánto falta y a qué ritmo semanal llegarías antes de que termine el mes.',
      'El calendario marca con un anillo los meses en que alcanzaste el objetivo; el gráfico muestra tu aporte mes a mes con el promedio móvil de 3 meses.',
      '"Si mantenés este ritmo" es una suma de aportes, sin rendimiento: sirve para dimensionar el hábito, no para predecir tu patrimonio.',
    ],
    queHacer: [
      'Definí un objetivo mensual realista: la pantalla te sugiere el promedio que ya venís sosteniendo.',
      'Usá las rachas y los logros como referencia de constancia: sostener un aporte chico todos los meses vale más que uno grande cada tanto.',
      'Si querés ver qué pasaría con rendimiento incluido, desde "Si mantenés este ritmo" pasás al simulador con tu aporte ya cargado.',
    ],
    ojo: 'Todo está en USD, siempre. El objetivo mensual es una meta de hábito y es independiente por cartera; para fijar una meta de patrimonio con fecha, está la pantalla Objetivo.',
    terminos: ['aportes_neto_criterio', 'aportes_meta_mensual', 'aportes_nivel', 'aportes_racha', 'aportes_proyeccion_ritmo'],
  },

  '/precios': {
    queEs: 'La evolución histórica del precio de un ticker, en las tres monedas/vistas disponibles.',
    comoLeerla: [
      'Elegí el ticker y la vista: nominal (pesos), USD (al MEP del día) o ARS real (ajustado por inflación con CER).',
      '"Último registro" indica cuándo se cargó el dato más reciente para ese ticker.',
    ],
    terminos: ['precios_ars_nominal', 'precios_usd_mep', 'precios_ars_real_cer'],
  },

  '/indicadores': {
    queEs: 'Los indicadores macro de referencia que usa toda la app: CER, MEP, riesgo país e inflación.',
    comoLeerla: [
      'CER y MEP son los que la app usa para convertir tus valores entre pesos nominales, pesos reales y dólares.',
      'Riesgo país e inflación son sólo de referencia: no afectan ningún cálculo de tu cartera.',
    ],
    terminos: ['cer', 'mep'],
  },

  '/vencimientos': {
    queEs: 'El calendario de vencimientos de tus bonos: cuándo cobrás y cuánto.',
    comoLeerla: [
      'Cada fila es un vencimiento con fecha y días restantes; los que ya pasaron quedan marcados como vencidos.',
      'Paridad y TIR muestran si el bono cotiza caro o barato respecto de lo que va a pagar.',
      'El resumen por año indica qué porcentaje de tu cartera vence en cada año calendario.',
    ],
    terminos: ['vencimientos_dias_restantes', 'vencimientos_paridad', 'vencimientos_tir'],
  },

  '/flujo-caja': {
    queEs: 'Proyecta cuánto vas a cobrar mes a mes por cupones y amortizaciones de tus bonos.',
    comoLeerla: [
      'Las barras separan cupones (intereses) de amortizaciones (devolución de capital).',
      'El nivel de confianza (alta/media/baja) indica qué tan segura es la proyección de capital de cada bono.',
    ],
    ojo: 'Es una proyección con las condiciones conocidas hoy: un bono puede cambiar sus términos.',
    terminos: ['flujocaja_confianza', 'flujocaja_inferido'],
  },

  '/comparar': {
    queEs: 'Compará la evolución de precio de hasta 5 tickers en un mismo gráfico.',
    comoLeerla: [
      '"Base 100" normaliza todos los tickers para que arranquen del mismo punto: así comparás variación %, no precio absoluto.',
      '"Nominal" muestra el precio real de cada uno, útil cuando el precio en sí importa.',
    ],
    terminos: ['comparador_base100', 'comparador_nominal'],
  },

  '/comisiones': {
    queEs: 'Cuánto pagaste en comisiones, desglosado como prefieras verlo.',
    comoLeerla: [
      'Elegí el desglose: por cartera, ticker, mes o año.',
      'El total pagado es la suma de todas las comisiones de tus movimientos en el período.',
    ],
    terminos: ['comisiones_total_pagado'],
  },

  '/vista-fiscal': {
    queEs: 'Un resumen por año calendario, pensado para tu declaración de impuestos.',
    comoLeerla: [
      'Por cada año: ganancia realizada (ventas), ingresos (dividendos/cupones) y comisiones pagadas.',
      'Expandí un año para ver el detalle por ticker.',
    ],
    queHacer: ['Exportá a CSV si necesitás llevarle estos números a tu contador.'],
  },

  '/patrimonio': {
    queEs: 'Cómo evolucionó el valor total de tu cartera, separando qué fue aporte tuyo y qué fue rendimiento.',
    comoLeerla: [
      'El gráfico distingue el valor de mercado de tu capital aportado: la diferencia entre ambas líneas es tu ganancia o pérdida.',
      'Los puntos marcados son eventos: aportes, retiros o ingresos (dividendos/cupones).',
      'La descomposición separa cuánto del cambio vino de aportar/retirar plata y cuánto de que los activos subieron o bajaron.',
    ],
    terminos: ['patrimonio_valor_mercado', 'patrimonio_capital_aportado', 'patrimonio_descomposicion_rendimiento'],
  },

  '/performance-relativa': {
    queEs: 'Compara el rendimiento de tu cartera contra un benchmark (un índice de referencia) en el mismo período.',
    comoLeerla: [
      'El gráfico normaliza ambas series para que arranquen igual: la que termina más arriba, ganó ese período.',
      'Alpha, beta y tracking error miden aspectos distintos de esa comparación: cuánto rendimiento generaste "de más", cuánto te movés con el mercado, y qué tan parecido sos al benchmark.',
    ],
    terminos: ['benchmark', 'alpha', 'beta', 'trackingError'],
  },

  '/contribucion': {
    queEs: 'Qué posiciones aportaron más (o restaron más) a tu rendimiento total, y qué tan concentrada está tu cartera.',
    comoLeerla: [
      'Cada barra es cuánto contribuyó ese ticker al resultado total, no lo que rindió individualmente: uno chico puede rendir mucho y aportar poco.',
      'El HHI mide concentración: cuanto más alto, más depende tu cartera de pocos tickers.',
      'La matriz de correlación muestra qué tan parecido se mueven tus activos entre sí.',
    ],
    terminos: ['contribucion', 'hhi', 'correlacion'],
  },

  '/descomposicion': {
    queEs: 'De qué está compuesta tu cartera, bajando de lo general a lo particular: Familia → Región → Sector → Ticker.',
    comoLeerla: [
      'Tocá una categoría para entrar a su detalle; el camino de arriba ("Cartera › …") te deja volver a un nivel anterior.',
      'El selector %/ARS/USD cambia cómo se ven los valores, no lo que se calcula.',
      'La familia (Renta fija, Renta variable, Fondos, Liquidez) se deriva del tipo de instrumento y del sector: no es un dato que se carga a mano.',
      'La región (EEUU, Argentina, Desarrollados ex-EEUU, Emergentes, Global) sale del país de la empresa, no de dónde cotiza: un CEDEAR de Coca-Cola es EEUU.',
    ],
    ojo: 'Sector, país y región salen de la clasificación automática (Yahoo) con el Sheet de respaldo. Lo que ninguna fuente informa aparece como "Sin clasificar": la app nunca lo inventa, y se puede corregir a mano desde la ficha del ticker.',
    terminos: ['descomposicion_familia', 'descomposicion_sin_clasificar', 'valuacion_fuentes'],
  },

  '/explicacion-resultado': {
    queEs: 'Qué factores explican el resultado de tu cartera en el período elegido: no sólo el porcentaje final, sino de dónde vino.',
    comoLeerla: [
      'Reutiliza los mismos cálculos que Rendimiento y Contribución: no es una fórmula nueva.',
      '"De dónde viene el resultado" separa movimiento de precio, dividendos/cupones y comisiones — y, en ARS, cuánto fue el activo y cuánto el dólar.',
      'Los aportes y retiros de capital nunca se mezclan con la ganancia: comprar no es ganar, vender a precio de mercado no es perder.',
    ],
    ojo: 'Si un instrumento no tiene precio o tipo de cambio para el período, aparece como "No disponible" en vez de una estimación.',
    terminos: ['explicacion_que_es', 'explicacion_no_disponible'],
  },

  '/diagnostico': {
    queEs: 'Un chequeo general de salud de tu cartera, con un score y una lista de hallazgos a revisar.',
    comoLeerla: [
      'El score de 0 a 100 combina cuatro dimensiones: rendimiento, diversificación, riesgo y costos.',
      'Cada hallazgo indica qué está bien o qué conviene mirar, ordenado por importancia.',
    ],
    terminos: ['diagnostico_salud_cartera', 'diagnostico_hallazgos'],
  },

  '/salud': {
    queEs: 'Un chequeo de 8 aspectos de tu cartera (riesgo, concentración, liquidez, costos, vencimientos, entre otros), cada uno con su propio estado y su regla.',
    comoLeerla: [
      'Cada dimensión dice "Normal", "Atención" o "Revisar" — nunca un número único: tocá "¿Cómo se decide?" para ver la regla exacta.',
      '"Cosas para revisar" lista observaciones concretas (ej. "AL30 representa 31% de la cartera") con un botón para ir directo a esa pantalla.',
    ],
    queHacer: ['Si algo aparece en "Revisar", andá a la pantalla que te sugiere el botón de esa observación para ver el detalle y decidir si hace falta actuar.'],
    ojo: 'No es un puntaje: cada estado sale de una regla que podés leer, no de una fórmula que combina todo en un número.',
    terminos: ['salud_que_es', 'salud_estados'],
  },

  '/calidad-datos': {
    queEs: 'El estado del último sync con tu Google Sheet: qué se cargó bien y qué tuvo problemas.',
    comoLeerla: [
      'El health score resume qué tan limpia llegó la última sincronización.',
      'Los problemas están separados por severidad: críticos (rompen algo) y advertencias (conviene revisar).',
    ],
    queHacer: ['Si ves errores críticos que se repiten, revisá esa fila en el Sheet: seguramente falta un dato o el formato no es el esperado.'],
    terminos: ['calidaddatos_health_score', 'calidaddatos_issues'],
  },

  '/benchmarks-comparacion': {
    queEs: 'Compará varios benchmarks (o tickers) entre sí, sin que tu cartera sea parte de la comparación.',
    comoLeerla: ['Elegí el período y los benchmarks/tickers a comparar; la tabla y el gráfico muestran el rendimiento de cada uno en ese lapso.'],
  },

  '/costo-oportunidad': {
    queEs: 'Cómo se comportó tu cartera durante un período, comparada con una referencia que elegís: en porcentaje y en dinero.',
    comoLeerla: [
      'Las dos líneas arrancan en el mismo punto y reciben los mismos aportes y retiros: lo único distinto es dónde estuvo invertido el dinero.',
      'La diferencia en puntos porcentuales y la diferencia en dinero describen el mismo hecho: positivo significa que la cartera terminó por encima de la referencia.',
      'El período que se compara se redondea a meses completos, y se muestra arriba: puede no coincidir exactamente con el botón que apretaste.',
    ],
    ojo: 'Es una descripción de lo que ya pasó, nunca una recomendación. La referencia se sigue de forma teórica, sin comisiones, impuestos ni mínimos de operación.',
    terminos: ['costooportunidad_comparacion', 'costooportunidad_diferencia_monetaria', 'costooportunidad_homogeneidad'],
  },

  '/correlaciones': {
    queEs: 'Qué tan parecido se movieron tus instrumentos entre sí, en una matriz que podés filtrar por período, frecuencia y activos.',
    comoLeerla: [
      'Cada celda es la correlación entre dos instrumentos: +1 se movieron de manera muy similar, 0 no se observa relación lineal clara, -1 se movieron en direcciones opuestas.',
      'Tocá una celda para ver el detalle del par: el valor exacto, cuántas observaciones lo respaldan y qué porcentaje del período cubren.',
      'Si la frecuencia elegida deja muchas celdas vacías, es porque no hay suficientes precios cargados con esa frecuencia: probá una más gruesa (semanal o mensual).',
    ],
    queHacer: ['Usá la tabla de pares para ordenar por correlación y encontrar rápido qué instrumentos se mueven más parecido (o más al revés) entre sí.'],
    ojo: 'Correlación no es causalidad: dos instrumentos pueden moverse juntos por un factor común, sin que uno influya sobre el otro. Además, la correlación pasada no se sostiene siempre: en las crisis, activos que antes iban por separado suelen caer todos juntos.',
    terminos: ['matrizcorr_correlacion', 'matrizcorr_frecuencia', 'matrizcorr_moneda'],
  },

  '/comparador-estrategias': {
    queEs: 'Corre varias estrategias guardadas sobre el mismo ticker y el mismo período, para ver cómo les fue una al lado de la otra.',
    comoLeerla: [
      'Elegí un ticker, un período y hasta 8 estrategias guardadas: todas corren sobre exactamente la misma serie de precios.',
      'La tabla y el gráfico de capital comparan el resultado; "La diferencia" lo traduce a puntos porcentuales y a dinero contra la referencia que elijas.',
      '"Comprar y mantener" siempre aparece como piso de comparación, además de poder elegir cualquiera de las estrategias como referencia.',
      'Los tramos de divergencia muestran en qué meses se originó la diferencia final, no sólo cuánto fue.',
    ],
    queHacer: ['Si el resultado es "Sin señales" o "Datos insuficientes", probá un período más largo o un ticker con más historia.'],
    ojo: 'Es un backtest, no una recomendación: describe qué habría pasado con los datos históricos disponibles, nunca cuál es "la mejor" estrategia para este instrumento de acá en adelante.',
    terminos: ['comparador_simulado', 'comparador_referencia', 'comparador_costos', 'comparador_limitaciones'],
  },

  '/mas': {
    queEs: 'El resto de las pantallas, agrupadas por tema: todo lo que no entra en la barra de abajo vive acá.',
    comoLeerla: ['Buscá por nombre o usá la lupa del encabezado para encontrar cualquier pantalla más rápido.'],
  },

  '/ajustes': {
    queEs: 'Tus preferencias personales: moneda, privacidad, sincronización automática, alertas y tamaño de texto.',
    comoLeerla: [
      'Nada de esto cambia tus datos: sólo cómo se te muestran.',
      'El ojo del encabezado activa y desactiva el modo privacidad desde cualquier pantalla, sin entrar acá.',
    ],
    queHacer: [
      '"Restablecer" vuelve todo a los valores de fábrica sin tocar tu cartera.',
      'Si prestás el teléfono o lo perdés, "Borrar datos guardados para uso offline" saca del dispositivo las últimas respuestas del servidor, que incluyen tus importes reales.',
    ],
    terminos: ['modoPrivacidad'],
  },
}

/** Normaliza rutas con segmento dinámico a su clave de guía (`/ticker/AAPL` → `/ticker`). */
export function claveRutaGuia(pathname: string): string {
  return pathname.startsWith('/ticker/') ? '/ticker' : pathname
}

export function resolverGuia(pathname: string): GuiaPantalla | null {
  return GUIAS_PANTALLA[claveRutaGuia(pathname)] ?? null
}
