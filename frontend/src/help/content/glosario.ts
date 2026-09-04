import { HelpContent } from '../types'

export type GlosarioKey =
  | 'xirr'
  | 'xirrPeriodo'
  | 'twr'
  | 'simple'
  | 'invertido'
  | 'realizado'
  | 'noRealizado'
  | 'ingresos'
  | 'benchmark'
  | 'cer'
  | 'mep'
  | 'pp'
  | 'objetivo'
  | 'stopLoss'
  | 'rebalanceo'
  | 'drawdown'
  | 'maximoHistorico'
  | 'volatilidad'
  | 'sharpe'
  | 'sortino'
  | 'calmar'
  | 'hhi'
  | 'correlacion'
  | 'contribucion'
  | 'alpha'
  | 'beta'
  | 'trackingError'
  | 'informationRatio'
  | 'costoOportunidad'
  | 'rendimiento_ars'
  | 'rendimiento_usd'
  | 'efecto_fx'
  | 'retorno_activo'
  | 'efectoAportes'
  | 'twrBruto'
  | 'costoOperar'

export const GLOSARIO_HELP: Record<GlosarioKey, HelpContent> = {
  xirr: {
    title: 'XIRR (TIR) anualizada',
    shortDescription:
      'Tasa Interna de Retorno anualizada. Calcula cuánto rindió tu dinero teniendo en cuenta CUÁNDO pusiste o sacaste cada peso (aportes, retiros, ventas). Es la métrica más fiel a "cuánto gané realmente" con tu forma particular de invertir.',
    whyItMatters:
      'Viene expresada como tasa ANUAL: responde "a este ritmo, cuánto rendiría en 12 meses". Si tu historial es más corto que un año, el número extrapola y va a ser bastante más grande que lo que efectivamente ganaste hasta hoy.',
    howToInterpret:
      'No la compares contra el TWRR ni contra el rendimiento simple, que son acumulados del período. Para eso está "TIR (XIRR) del período".',
    relatedTerms: ['xirrPeriodo', 'twr'],
  },
  xirrPeriodo: {
    title: 'TIR (XIRR) del período',
    shortDescription:
      'La misma TIR, pero expresada como lo que efectivamente rindió tu plata desde el primer movimiento hasta hoy, sin anualizar.',
    whyItMatters:
      'Es la versión de la TIR que se puede comparar de igual a igual contra el TWRR y contra el rendimiento simple: las tres miden el mismo tramo de tiempo.',
    howItIsCalculated: 'XIRR del período = (1 + XIRR anualizada) ^ (días del período ÷ 365) − 1.',
    relatedTerms: ['xirr', 'twr', 'efectoAportes'],
  },
  twr: {
    title: 'TWR / TWRR (Time-Weighted Return)',
    shortDescription:
      'Mide el rendimiento de la estrategia en sí misma, sin que importe cuándo depositaste o retiraste plata. Se usa para comparar tu cartera contra un índice o benchmark de forma justa, ya que tus aportes y retiros no distorsionan el número.',
    howToInterpret:
      'Está expresado como retorno ACUMULADO del período (no anualizado): es lo que rindió la estrategia desde tu primer movimiento hasta hoy.',
    relatedTerms: ['xirrPeriodo', 'efectoAportes'],
  },
  efectoAportes: {
    title: 'Efecto de tus aportes',
    shortDescription:
      'La diferencia entre la TIR del período y el TWRR. Te dice si el momento en que pusiste o sacaste plata jugó a tu favor o en tu contra, más allá de cómo rindió la estrategia en sí.',
    whyItMatters:
      'XIRR y TWR miden cosas distintas: XIRR pondera por cuánta plata había invertida en cada momento, TWR no. Si sumaste aportes justo antes de una suba, tu XIRR va a ser mejor que tu TWR (el timing jugó a favor); si aportaste antes de una baja, va a ser peor.',
    howItIsCalculated:
      'Efecto = TIR del período − TWRR, en la misma moneda. Se usa la TIR del período y no la anualizada porque el TWRR tampoco está anualizado: restar una tasa anual menos un acumulado daría una brecha inventada por la diferencia de unidades.',
    howToInterpret:
      'Positivo: tus aportes/retiros mejoraron el resultado respecto a la estrategia pura. Negativo: el timing de tus movimientos te costó rendimiento, aunque la estrategia haya sido buena.',
    limitations: 'No es "buen" o "mal" timing en un sentido predictivo — es una lectura hacia atrás de cómo coincidieron tus aportes con los movimientos de precio.',
    relatedTerms: ['xirrPeriodo', 'twr'],
  },
  twrBruto: {
    title: 'TWRR sin comisiones',
    shortDescription:
      'El mismo TWR de la estrategia, pero calculado como si operar no tuviera costo: las comisiones de compra y venta no se descuentan de los flujos.',
    howToInterpret:
      'Siempre es igual o mejor que el TWR real. La brecha entre ambos es lo que te costaron las comisiones, medido en puntos de rendimiento.',
    relatedTerms: ['twr', 'costoOperar'],
  },
  costoOperar: {
    title: 'Costo de operar',
    shortDescription:
      'Cuánto rendimiento te comieron las comisiones: TWR real menos TWR sin comisiones, en la misma moneda.',
    whyItMatters:
      'Las comisiones parecen chicas por operación, pero acumuladas y comparadas contra el rendimiento total pueden pesar. Este número las expresa en la misma unidad que mirás el rendimiento.',
    howItIsCalculated: 'Costo de operar = TWR real − TWR sin comisiones (≤ 0).',
    howToInterpret:
      'Es negativo o cero. Cuanto más lejos de cero, más rendimiento perdiste por comisiones. Cero significa que no hubo comisiones registradas.',
    relatedTerms: ['twr', 'twrBruto'],
  },
  simple: {
    title: 'Rendimiento simple',
    shortDescription:
      'La cuenta más básica: (Valor actual − Invertido) ÷ Invertido. No tiene en cuenta el tiempo transcurrido, así que no es comparable entre períodos distintos, pero da una idea rápida de la ganancia total.',
  },
  invertido: {
    title: 'Invertido',
    shortDescription: 'El total de plata que pusiste en la cartera (compras menos ventas), sin contar ganancias ni pérdidas todavía.',
  },
  realizado: {
    title: 'Realizado (ventas)',
    shortDescription: 'La ganancia o pérdida que ya "cerraste" al vender un activo. Es plata concreta: ya no depende de lo que pase con el precio después.',
  },
  noRealizado: {
    title: 'No realizado (en cartera)',
    shortDescription: 'La ganancia o pérdida "en el papel" de lo que todavía tenés sin vender. Sube y baja todos los días con el precio; recién se hace real si vendés.',
  },
  ingresos: {
    title: 'Ingresos (dividendos / cupones)',
    shortDescription: 'Plata que cobraste sin vender nada: dividendos de acciones o cupones de bonos. Se suma a la ganancia total de la cartera.',
  },
  benchmark: {
    title: 'Benchmark',
    shortDescription: 'Un punto de comparación para saber si tu cartera rindió bien o mal. Por ejemplo: "¿me hubiera ido mejor si compraba dólares en vez de estos activos?"',
  },
  cer: {
    title: 'CER',
    shortDescription: 'Coeficiente de Estabilización de Referencia: sigue la inflación en Argentina. "ARS Real (CER)" muestra tu rendimiento en pesos ya descontando la inflación, para saber si ganaste poder de compra de verdad.',
  },
  mep: {
    title: 'MEP',
    shortDescription: 'Dólar MEP (Mercado Electrónico de Pagos): la cotización del dólar que resulta de comprar y vender bonos en el mercado local. Se usa para convertir tu cartera a dólares de forma legal.',
  },
  pp: {
    title: 'Puntos porcentuales (pp)',
    shortDescription: 'La diferencia entre dos porcentajes, medida en unidades de porcentaje absoluto (no relativo). No es lo mismo que "% de aumento": 10pp es diferente de "10% de aumento".',
    example: 'Si tu cartera rindió 15% y el benchmark rindió 10%, la diferencia es 5 pp (no 5%, que sería 10% × 1.05 = 10.5%). Si una métrica cambia de 50% a 55%, subió 5 pp (no 5%).',
    howToInterpret: 'Los pp se usan cuando comparás dos números que ya son porcentajes (rendimientos, tasas, pesos dentro de una cartera). Siempre restá los % directamente: sin hacer cálculos relativos.',
  },
  objetivo: {
    title: 'Precio Objetivo',
    shortDescription: 'El precio al que te gustaría vender para tomar ganancias. Se define en el Sheet como % sobre tu precio promedio de compra o como precio fijo. Cuando el precio actual lo alcanza o supera, se marca como alcanzado.',
  },
  stopLoss: {
    title: 'Stop Loss',
    shortDescription: 'El precio al que cortarías la pérdida y saldrías de la posición. Se define en el Sheet como % sobre tu precio promedio de compra o como precio fijo. Cuando el precio actual cae a ese nivel o por debajo, se marca como disparado.',
  },
  rebalanceo: {
    title: 'Rebalanceo',
    shortDescription: 'Compara tu asignación actual contra los porcentajes objetivo que cargaste en la pestaña "Rebalanceo" del Sheet, en 4 ejes independientes (cada uno suma su propio 100%): Cartera (peso de cada cartera sobre el total), Tipo (CEDEAR, Bono, etc. dentro de una cartera), Sector (dentro de una cartera) y Ticker (objetivo por instrumento puntual). Lo que tiene valor invertido pero no tiene objetivo cargado aparece aparte, en "Sin objetivo". Desde "Simular rebalanceo" podés ver una propuesta de compra/venta sin registrar ningún movimiento real.',
  },
  drawdown: {
    title: 'Drawdown',
    shortDescription: 'Cuánto cayó tu cartera desde su punto más alto (máximo histórico) hasta hoy o hasta el peor momento registrado. El "drawdown máximo" es la peor caída que sufriste alguna vez; el "actual" es cuánto estás por debajo del último máximo ahora mismo.',
  },
  maximoHistorico: {
    title: 'Máximo histórico',
    shortDescription: 'El valor más alto que alcanzó tu cartera en el período mostrado (también llamado "high-water mark"). Es la referencia contra la que se mide el drawdown actual.',
    relatedTerms: ['drawdown'],
  },
  volatilidad: {
    title: 'Volatilidad',
    shortDescription: 'Qué tan bruscos son los altibajos mensuales de tu cartera. Se calcula sobre retornos mensuales y se anualiza (× √12) para comparar contra otras métricas anuales. Más volatilidad no es necesariamente malo, pero implica un camino más incómodo.',
  },
  sharpe: {
    title: 'Sharpe (vs. benchmark)',
    shortDescription: 'Compara el retorno de tu cartera contra un benchmark elegido, ajustado por lo volátil que fue esa diferencia. Un Sharpe más alto significa que ganaste más que el benchmark sin asumir demasiada volatilidad extra para lograrlo.',
  },
  sortino: {
    title: 'Sortino',
    shortDescription: 'Parecido al Sharpe, pero solo penaliza la volatilidad "mala" (los meses negativos), ignorando los meses buenos. Es útil porque a nadie le molesta la volatilidad hacia arriba.',
  },
  calmar: {
    title: 'Calmar',
    shortDescription: 'Compara tu retorno anualizado contra el peor drawdown que sufriste. Un Calmar alto significa que ganaste mucho en relación a lo doloroso que fue el peor momento de la cartera.',
  },
  hhi: {
    title: 'HHI (Índice de concentración)',
    shortDescription: 'Mide qué tan concentrada está tu cartera en pocas posiciones: se suma el cuadrado del peso % de cada componente. Un valor bajo (cerca de 0) indica diversificación; uno alto (cerca de 10.000, el máximo si todo está en una sola posición) indica alta concentración. El "N efectivo" traduce ese número a algo más intuitivo: cuántas posiciones de igual tamaño equivalen a tu nivel de concentración actual.',
  },
  correlacion: {
    title: 'Correlación',
    shortDescription: 'Mide qué tan parecido se mueve un activo respecto a otro, en una escala de -1 a +1. Cerca de +1 significa que suben y bajan casi juntos (poca diversificación real entre ellos); cerca de -1 significa que se mueven en sentido contrario; cerca de 0 significa que no hay relación clara. Se calcula sobre retornos mensuales en USD, así que necesita varios meses de historial de precios para ser confiable.',
  },
  contribucion: {
    title: 'Contribución al retorno',
    shortDescription: 'Qué parte del resultado total de la cartera (en dólares) aportó cada posición, sector, tipo o mercado. Se calcula como el P&L de cada uno dividido por el costo total invertido en toda la cartera, así que la suma de todas las contribuciones coincide con el retorno simple total. No es lo mismo que el TWR/XIRR de la cartera: es una forma de repartir el resultado ya conocido entre sus componentes, no una tasa de retorno ajustada por tiempo.',
  },
  alpha: {
    title: 'Alpha',
    shortDescription: 'Cuánto ganaste (o perdiste) por encima de lo que tu nivel de riesgo (beta) justificaría respecto al benchmark. Un alpha positivo significa que sacaste provecho de tu estrategia más allá de simplemente seguir el mercado. Se calcula como: retorno cartera − (beta × retorno benchmark).',
  },
  beta: {
    title: 'Beta',
    shortDescription: 'Mide cuánto se mueve tu cartera en relación al benchmark: si beta=1 te movés igual que el benchmark; si >1, eres más volátil; si <1, eres más estable. Un beta de 1.5 significa que si el benchmark sube 10%, tu cartera sube ~15% (en promedio). Se calcula sobre retornos mensuales comunes.',
  },
  trackingError: {
    title: 'Tracking error',
    shortDescription: 'Mide qué tan diferente fue tu rendimiento mes a mes respecto al benchmark, anualizado. Es la volatilidad del "exceso de retorno": si es bajo, tu cartera sigue de cerca al benchmark; si es alto, tuviste resultados muy distintos cada mes.',
  },
  informationRatio: {
    title: 'Information Ratio',
    shortDescription: 'Compara tu exceso de retorno respecto al benchmark contra la volatilidad de ese exceso. Un ratio más alto significa que ganaste más que el benchmark sin que esa diferencia fuera muy errática mes a mes. Es útil para evaluar si un gestor activo agrega valor de forma consistente.',
  },
  costoOportunidad: {
    title: 'Costo de oportunidad',
    shortDescription: 'La diferencia entre lo que tu cartera real valió y lo que hubiera valido si hubieras seguido exactamente el benchmark elegido. Puede expresarse en dinero (dólares, pesos) o en rendimiento %.',
    whyItMatters: 'Cuantifica el costo exacto de tus decisiones de selección: si es positivo, dejaste dinero/rentabilidad en la mesa siguiendo tu criterio vs. el benchmark; si es negativo, ganaste plata siendo diferente.',
    howItIsCalculated: 'Se calcula con los mismos aportes/retiros que tu cartera real, pero invirtiendo 100% en el benchmark en vez de en tus activos elegidos. La diferencia entre tu valor actual (o rendimiento) y este valor "shadow" es el costo de oportunidad.',
    howToInterpret: 'Positivo = el benchmark te hubiera ido mejor (oportunidad perdida). Negativo = tu selección fue mejor que seguir ciegamente el benchmark. Recuerda que esta es una visión retrospectiva: lo que pasó ayer no garantiza lo que pasará mañana.',
    limitations: 'Solo relevante si comparas con un período en el que el benchmark tuvo datos. Es una métrica histórica: los benchmarks pasados no garantizan rendimientos futuros. No constituye una recomendación de inversión.',
    example: 'En dinero: si tu cartera real vale USD 100.000 pero el valor shadow es USD 95.000, tu costo es USD -5.000 (ganaste diferente). En rendimiento: si tu cartera rindió 10% pero el benchmark rindió 8%, tu costo de oportunidad es -2 pp (ganaste 2 pp extra).',
  },
  rendimiento_ars: {
    title: 'Rendimiento en ARS',
    shortDescription: 'Tu retorno medido en pesos argentinos, incluido el efecto del tipo de cambio. Si el dólar se depreció, este número será menor que el retorno en USD; si se aprenció, será mayor.',
  },
  rendimiento_usd: {
    title: 'Rendimiento en USD',
    shortDescription: 'Tu retorno medido en dólares estadounidenses, sin efectos cambiarios. Representa el rendimiento puro de tus activos en dólares.',
  },
  efecto_fx: {
    title: 'Efecto FX (tipo de cambio)',
    shortDescription: 'La porción del retorno en ARS que proviene de la variación del MEP (tipo de cambio). Si es positivo, el dólar se aprenció; si es negativo, se depreció. La relación es: Retorno ARS ≈ Retorno USD × (1 + Efecto FX).',
  },
  retorno_activo: {
    title: 'Retorno del activo',
    shortDescription: 'Tu rendimiento puramente por la selección y evolución de los activos en tu cartera, medido en la moneda original de cada instrumento (sin efectos cambiarios).',
  },
}
