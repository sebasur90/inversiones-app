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
      'Los filtros de arriba (Con alerta, Stop loss, Objetivo) muestran sólo lo que necesita una decisión tuya.',
    ],
    queHacer: ['Tocá cualquier fila para ver el detalle completo de ese ticker.'],
    terminos: ['posiciones_rendimiento_simple', 'stopLoss', 'objetivo'],
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
    queEs: 'Todo sobre un instrumento puntual: resumen, rendimiento, riesgo e histórico de precios.',
    comoLeerla: [
      'Las pestañas de arriba cambian la vista sin salir de la pantalla.',
      '"Resumen" da la foto rápida; el resto son las mismas métricas que ves en Rendimiento y Riesgo, pero sólo para este ticker.',
    ],
    terminos: ['tickerdetalle_total_pl', 'tickerdetalle_retorno_anualizado'],
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
    queEs: 'Cuánta plata nueva ponés en tus inversiones cada mes, y si ese ritmo mejora o empeora contra tu propio historial.',
    comoLeerla: [
      'La tarjeta de arriba es este mes: lo aportado hasta hoy, cómo terminaría al ritmo actual, y cómo se compara con el mes pasado y con tu promedio.',
      'El estado (acelerando / sostenido / frenando / parado) compara tus últimos 3 meses cerrados con los 3 anteriores.',
      'Las barras son tu aporte neto mes a mes; en rojo los meses en que retiraste más de lo que pusiste. La línea es el promedio móvil de 3 meses.',
      'La proyección a fin de año muestra tres escenarios según qué ritmo mantengas; el calendario y la tabla por año dejan ver los meses buenos y malos.',
    ],
    queHacer: [
      'Si el estado es "frenando", mirá en el calendario qué meses bajaron y decidí si fue algo puntual o una tendencia.',
      'Usá las rachas y los logros como referencia de constancia: sostener un aporte chico todos los meses vale más que uno grande cada tanto.',
    ],
    ojo: 'Acá no hay metas: todo se compara contra vos mismo, y siempre en USD. Para fijar una meta en dólares y ver el aporte necesario, está la pantalla Objetivo.',
    terminos: ['aportes_neto_criterio', 'aportes_estado_ritmo', 'aportes_racha', 'aportes_proyeccion_fin_anio'],
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
    queEs: 'De qué está compuesta tu cartera, bajando de lo general a lo particular: Familia → País → Sector → Ticker.',
    comoLeerla: [
      'Tocá una categoría para entrar a su detalle; el camino de arriba ("Cartera › …") te deja volver a un nivel anterior.',
      'El selector %/ARS/USD cambia cómo se ven los valores, no lo que se calcula.',
      'La familia (Renta fija, Renta variable, Fondos, Liquidez) se deriva del Tipo Instrumento y el Sector que cargaste en el Sheet: no es un dato que se carga a mano.',
    ],
    ojo: 'Un ticker sin ficha en Instrumentos, o con País/Sector vacío, aparece como "Sin clasificar" — la app nunca inventa esa clasificación.',
    terminos: ['descomposicion_familia', 'descomposicion_sin_clasificar'],
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

  '/mas': {
    queEs: 'El resto de las pantallas, agrupadas por tema: todo lo que no entra en la barra de abajo vive acá.',
    comoLeerla: ['Buscá por nombre o usá la lupa del encabezado para encontrar cualquier pantalla más rápido.'],
  },

  '/ajustes': {
    queEs: 'Tus preferencias personales: moneda, sincronización automática, alertas y tamaño de texto.',
    comoLeerla: ['Nada de esto cambia tus datos: sólo cómo se te muestran.'],
    queHacer: ['"Restablecer" vuelve todo a los valores de fábrica sin tocar tu cartera.'],
  },
}

/** Normaliza rutas con segmento dinámico a su clave de guía (`/ticker/AAPL` → `/ticker`). */
export function claveRutaGuia(pathname: string): string {
  return pathname.startsWith('/ticker/') ? '/ticker' : pathname
}

export function resolverGuia(pathname: string): GuiaPantalla | null {
  return GUIAS_PANTALLA[claveRutaGuia(pathname)] ?? null
}
