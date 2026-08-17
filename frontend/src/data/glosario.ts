export type GlosarioKey =
  | 'xirr'
  | 'twr'
  | 'simple'
  | 'invertido'
  | 'realizado'
  | 'noRealizado'
  | 'ingresos'
  | 'benchmark'
  | 'cer'
  | 'mep'
  | 'objetivo'
  | 'stopLoss'
  | 'rebalanceo'
  | 'drawdown'
  | 'volatilidad'
  | 'sharpe'
  | 'sortino'
  | 'calmar'
  | 'hhi'
  | 'correlacion'
  | 'contribucion'

export const GLOSARIO: Record<GlosarioKey, { titulo: string; texto: string }> = {
  xirr: {
    titulo: 'XIRR (TIR)',
    texto:
      'Tasa Interna de Retorno anualizada. Calcula cuánto rindió tu dinero teniendo en cuenta CUÁNDO pusiste o sacaste cada peso (aportes, retiros, ventas). Es la métrica más fiel a "cuánto gané realmente" con tu forma particular de invertir.',
  },
  twr: {
    titulo: 'TWR / TWRR (Time-Weighted Return)',
    texto:
      'Mide el rendimiento de la estrategia en sí misma, sin que importe cuándo depositaste o retiraste plata. Se usa para comparar tu cartera contra un índice o benchmark de forma justa, ya que tus aportes y retiros no distorsionan el número.',
  },
  simple: {
    titulo: 'Rendimiento simple',
    texto:
      'La cuenta más básica: (Valor actual − Invertido) ÷ Invertido. No tiene en cuenta el tiempo transcurrido, así que no es comparable entre períodos distintos, pero da una idea rápida de la ganancia total.',
  },
  invertido: {
    titulo: 'Invertido',
    texto: 'El total de plata que pusiste en la cartera (compras menos ventas), sin contar ganancias ni pérdidas todavía.',
  },
  realizado: {
    titulo: 'Realizado (ventas)',
    texto: 'La ganancia o pérdida que ya "cerraste" al vender un activo. Es plata concreta: ya no depende de lo que pase con el precio después.',
  },
  noRealizado: {
    titulo: 'No realizado (en cartera)',
    texto: 'La ganancia o pérdida "en el papel" de lo que todavía tenés sin vender. Sube y baja todos los días con el precio; recién se hace real si vendés.',
  },
  ingresos: {
    titulo: 'Ingresos (dividendos / cupones)',
    texto: 'Plata que cobraste sin vender nada: dividendos de acciones o cupones de bonos. Se suma a la ganancia total de la cartera.',
  },
  benchmark: {
    titulo: 'Benchmark',
    texto: 'Un punto de comparación para saber si tu cartera rindió bien o mal. Por ejemplo: "¿me hubiera ido mejor si compraba dólares en vez de estos activos?"',
  },
  cer: {
    titulo: 'CER',
    texto: 'Coeficiente de Estabilización de Referencia: sigue la inflación en Argentina. "ARS Real (CER)" muestra tu rendimiento en pesos ya descontando la inflación, para saber si ganaste poder de compra de verdad.',
  },
  mep: {
    titulo: 'MEP',
    texto: 'Dólar MEP (Mercado Electrónico de Pagos): la cotización del dólar que resulta de comprar y vender bonos en el mercado local. Se usa para convertir tu cartera a dólares de forma legal.',
  },
  objetivo: {
    titulo: 'Precio Objetivo',
    texto: 'El precio al que te gustaría vender para tomar ganancias. Se define en el Sheet como % sobre tu precio promedio de compra o como precio fijo. Cuando el precio actual lo alcanza o supera, se marca como alcanzado.',
  },
  stopLoss: {
    titulo: 'Stop Loss',
    texto: 'El precio al que cortarías la pérdida y saldrías de la posición. Se define en el Sheet como % sobre tu precio promedio de compra o como precio fijo. Cuando el precio actual cae a ese nivel o por debajo, se marca como disparado.',
  },
  rebalanceo: {
    titulo: 'Rebalanceo',
    texto: 'Compara tu asignación actual contra los porcentajes objetivo que cargaste en la pestaña "Rebalanceo" del Sheet, en 4 ejes independientes (cada uno suma su propio 100%): Cartera (peso de cada cartera sobre el total), Tipo (CEDEAR, Bono, etc. dentro de una cartera), Sector (dentro de una cartera) y Ticker (objetivo por instrumento puntual). Lo que tiene valor invertido pero no tiene objetivo cargado aparece aparte, en "Sin objetivo". Desde "Simular rebalanceo" podés ver una propuesta de compra/venta sin registrar ningún movimiento real.',
  },
  drawdown: {
    titulo: 'Drawdown',
    texto: 'Cuánto cayó tu cartera desde su punto más alto (máximo histórico) hasta hoy o hasta el peor momento registrado. El "drawdown máximo" es la peor caída que sufriste alguna vez; el "actual" es cuánto estás por debajo del último máximo ahora mismo.',
  },
  volatilidad: {
    titulo: 'Volatilidad',
    texto: 'Qué tan bruscos son los altibajos mensuales de tu cartera. Se calcula sobre retornos mensuales y se anualiza (× √12) para comparar contra otras métricas anuales. Más volatilidad no es necesariamente malo, pero implica un camino más incómodo.',
  },
  sharpe: {
    titulo: 'Sharpe (vs. benchmark)',
    texto: 'Compara el retorno de tu cartera contra un benchmark elegido, ajustado por lo volátil que fue esa diferencia. Un Sharpe más alto significa que ganaste más que el benchmark sin asumir demasiada volatilidad extra para lograrlo.',
  },
  sortino: {
    titulo: 'Sortino',
    texto: 'Parecido al Sharpe, pero solo penaliza la volatilidad "mala" (los meses negativos), ignorando los meses buenos. Es útil porque a nadie le molesta la volatilidad hacia arriba.',
  },
  calmar: {
    titulo: 'Calmar',
    texto: 'Compara tu retorno anualizado contra el peor drawdown que sufriste. Un Calmar alto significa que ganaste mucho en relación a lo doloroso que fue el peor momento de la cartera.',
  },
  hhi: {
    titulo: 'HHI (Índice de concentración)',
    texto: 'Mide qué tan concentrada está tu cartera en pocas posiciones: se suma el cuadrado del peso % de cada componente. Un valor bajo (cerca de 0) indica diversificación; uno alto (cerca de 10.000, el máximo si todo está en una sola posición) indica alta concentración. El "N efectivo" traduce ese número a algo más intuitivo: cuántas posiciones de igual tamaño equivalen a tu nivel de concentración actual.',
  },
  correlacion: {
    titulo: 'Correlación',
    texto: 'Mide qué tan parecido se mueve un activo respecto a otro, en una escala de -1 a +1. Cerca de +1 significa que suben y bajan casi juntos (poca diversificación real entre ellos); cerca de -1 significa que se mueven en sentido contrario; cerca de 0 significa que no hay relación clara. Se calcula sobre retornos mensuales en USD, así que necesita varios meses de historial de precios para ser confiable.',
  },
  contribucion: {
    titulo: 'Contribución al retorno',
    texto: 'Qué parte del resultado total de la cartera (en dólares) aportó cada posición, sector, tipo o mercado. Se calcula como el P&L de cada uno dividido por el costo total invertido en toda la cartera, así que la suma de todas las contribuciones coincide con el retorno simple total. No es lo mismo que el TWR/XIRR de la cartera: es una forma de repartir el resultado ya conocido entre sus componentes, no una tasa de retorno ajustada por tiempo.',
  },
}
