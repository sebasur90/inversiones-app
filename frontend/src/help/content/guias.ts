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
      'Cada escenario (Base, Alcista, Bajista, o uno que armes) es una combinación de supuestos: cuánto sube el dólar, cuánto aportás por mes, etc.',
      'El gráfico proyecta la evolución de tu patrimonio mes a mes bajo cada escenario.',
      'Podés comparar hasta 6 escenarios en la misma tabla.',
    ],
    queHacer: ['Empezá por los presets antes de armar uno personalizado desde cero.'],
    ojo: 'Es una proyección con los supuestos que vos cargaste, no una predicción: cambiá los números y el resultado va a cambiar mucho.',
    terminos: ['escenario_horizonte', 'escenario_variacion_dolar', 'escenario_aporte_mensual'],
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
    terminos: ['screener_umbral', 'screener_dispara_ahora'],
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
    queHacer: ['Se carga desde la pestaña Watchlist del Sheet: agregá filas ahí y sincronizá para verlas acá.'],
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

  '/diagnostico': {
    queEs: 'Un chequeo general de salud de tu cartera, con un score y una lista de hallazgos a revisar.',
    comoLeerla: [
      'El score de 0 a 100 combina cuatro dimensiones: rendimiento, diversificación, riesgo y costos.',
      'Cada hallazgo indica qué está bien o qué conviene mirar, ordenado por importancia.',
    ],
    terminos: ['diagnostico_salud_cartera', 'diagnostico_hallazgos'],
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
