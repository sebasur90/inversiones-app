import { formatARSCrudo, formatUSDCrudo } from '../utils'

export type Moneda = 'ARS' | 'USD'

/**
 * Máscara del modo privacidad. Cuatro glifos: el importe más corto posible (`$ 1.234`) ocupa
 * siete, así que la máscara nunca ensancha una celda ni mueve una grilla; y con cuatro se lee
 * como "tapado" y no se confunde con `—`, que en toda la app significa "sin dato".
 *
 * La fuente de los números es monoespaciada (JetBrains Mono), así que `•` tiene el mismo avance
 * que un dígito y no hace falta tocar ninguna clase de Tailwind.
 */
export const MASCARA = '••••'
/** Para ejes de gráficos y celdas angostas, donde el valor real ya venía abreviado. */
export const MASCARA_COMPACTA = '•••'

// Cacheado por moneda: `formatToParts` no es gratis y esto se llama en cada celda de una tabla.
const prefijos = new Map<Moneda, string>()

/**
 * El símbolo de moneda tal como lo emite el formateador real, espaciado incluido (`$` en USD,
 * `$ ` en ARS). Se deriva de `Intl` en vez de escribirse a mano para que la máscara no se
 * desalinee del importe si mañana cambia la configuración.
 */
export function prefijoMoneda(moneda: Moneda): string {
  const cacheado = prefijos.get(moneda)
  if (cacheado !== undefined) return cacheado
  const partes = new Intl.NumberFormat(moneda === 'ARS' ? 'es-AR' : 'en-US', {
    style: 'currency',
    currency: moneda,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).formatToParts(0)
  // Todo lo que va antes del primer dígito: el símbolo y el espacio que lo separe.
  const corte = partes.findIndex(p => p.type === 'integer')
  const prefijo = partes.slice(0, corte === -1 ? partes.length : corte).map(p => p.value).join('')
  prefijos.set(moneda, prefijo)
  return prefijo
}

/**
 * El importe tapado, conservando el símbolo de la moneda que se está mirando y, si el valor era
 * negativo, su signo: "esto restó" es parte de lo que la pantalla explica y no dice cuánta plata
 * hay. Sin el signo, una ganancia y una pérdida se verían idénticas.
 */
export function montoOculto(moneda: Moneda, negativo = false): string {
  return `${negativo ? '-' : ''}${prefijoMoneda(moneda)}${MASCARA}`
}

/**
 * Prefijos de las versiones compactas. No pasan por `Intl` a propósito: son los mismos que ya
 * usaban los `formatCompact` locales que esta función reemplaza, así que los ejes de Patrimonio
 * y Precios se ven exactamente igual que antes.
 */
const PREFIJO_COMPACTO: Record<Granularidad, Record<Moneda, string>> = {
  normal: { USD: 'U$S ', ARS: '$' },
  fina: { USD: '$', ARS: '$' },
}

/**
 * `normal` es la de los ejes de patrimonio y precios (`U$S 34K`, `$1.2M`); `fina` la del
 * calendario de aportes, con un escalón más entre 1k y 10k para que trece columnas entren en el
 * ancho de un teléfono (`$1.2k`, `$34k`).
 */
export type Granularidad = 'normal' | 'fina'

export function formatCompacto(v: number, moneda: Moneda, granularidad: Granularidad = 'normal'): string {
  const prefijo = PREFIJO_COMPACTO[granularidad][moneda]
  const abs = Math.abs(v)
  const signo = v < 0 ? '-' : ''
  if (abs >= 1_000_000) return `${signo}${prefijo}${(abs / 1_000_000).toFixed(1)}M`
  if (granularidad === 'fina') {
    if (abs >= 10_000) return `${signo}${prefijo}${(abs / 1000).toFixed(0)}k`
    if (abs >= 1000) return `${signo}${prefijo}${(abs / 1000).toFixed(1)}k`
    return `${signo}${prefijo}${abs.toFixed(0)}`
  }
  if (abs >= 1000) return `${signo}${prefijo}${(abs / 1000).toFixed(0)}K`
  // En USD los valores chicos son precios unitarios: dos decimales o se leen todos igual.
  return `${signo}${prefijo}${moneda === 'USD' ? abs.toFixed(2) : abs.toFixed(0)}`
}

export function montoCompactoOculto(moneda: Moneda, granularidad: Granularidad = 'normal', negativo = false): string {
  return `${negativo ? '-' : ''}${PREFIJO_COMPACTO[granularidad][moneda]}${MASCARA_COMPACTA}`
}

/** El formateador crudo de cada moneda, sin modo privacidad. */
export function formatMonedaCruda(v: number | null | undefined, moneda: Moneda): string {
  return moneda === 'ARS' ? formatARSCrudo(v) : formatUSDCrudo(v)
}

/**
 * Un importe sujeto al modo privacidad, con el interruptor pasado a mano. Es para las filas donde
 * la moneda es un dato de cada ítem y no la del encabezado (un movimiento puede ser en pesos y el
 * siguiente en dólares): ahí no sirve un formateador fijo por componente. En el caso normal usar
 * `useFormatoMoneda()` / `useFormatoFijo()`, que ya resuelven el interruptor.
 */
export function formatMonto(v: number | null | undefined, moneda: Moneda, ocultos: boolean): string {
  if (v == null) return '—'
  return ocultos ? montoOculto(moneda, v < 0) : formatMonedaCruda(v, moneda)
}
