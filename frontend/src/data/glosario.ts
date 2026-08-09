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
}
