import type { FuenteClasificacion, LecturaValuacion } from '../../api'

/** Lectura en palabras + un color de apoyo. El color nunca va solo: el texto dice lo mismo. */
const ESTILO_LECTURA: Record<LecturaValuacion, string> = {
  barata: 'bg-app-pos-soft text-app-pos',
  cara: 'bg-app-neg-soft text-app-neg',
  barata_con_alertas: 'bg-[rgba(245,158,11,0.14)] text-app-warn',
  cara_justificada: 'bg-app-accent-soft text-app-accent',
  mixta: 'bg-app-surface-2 text-app-text',
  en_linea: 'bg-app-surface-2 text-app-text-dim',
  datos_insuficientes: 'bg-app-surface-2 text-app-text-faint',
}

export const LECTURAS_ORDEN: LecturaValuacion[] = [
  'barata', 'barata_con_alertas', 'en_linea', 'mixta', 'cara_justificada', 'cara', 'datos_insuficientes',
]

export const TEXTO_LECTURA_CORTO: Record<LecturaValuacion, string> = {
  barata: 'Barata',
  barata_con_alertas: 'Barata con alertas',
  en_linea: 'En línea',
  mixta: 'Mixta',
  cara_justificada: 'Cara justificada',
  cara: 'Cara',
  datos_insuficientes: 'Sin datos',
}

export function LecturaBadge({ lectura, texto }: { lectura: LecturaValuacion; texto?: string }) {
  return (
    <span className={`inline-block font-bold text-label px-2 py-1 rounded-[7px] shrink-0 ${ESTILO_LECTURA[lectura]}`}>
      {texto ?? TEXTO_LECTURA_CORTO[lectura]}
    </span>
  )
}

const TEXTO_FUENTE: Record<NonNullable<FuenteClasificacion>, string> = {
  manual: 'corregido a mano',
  seed: 'corrección de la app',
  yahoo: 'Yahoo',
  sheet: 'Sheet',
}

export function FuenteBadge({ fuente }: { fuente: FuenteClasificacion | undefined }) {
  if (!fuente) return null
  return (
    <span className={`text-label px-1.5 py-0.5 rounded-[6px] ${fuente === 'manual' ? 'bg-app-accent-soft text-app-accent' : 'bg-app-surface-2 text-app-text-faint'}`}>
      {TEXTO_FUENTE[fuente]}
    </span>
  )
}

/** Valor de una métrica: "x" en veces (25,3x), "pct" como fracción → porcentaje. Son datos de
 *  mercado públicos (no importes de la cartera), así que no pasan por el modo privacidad. */
export function formatMetrica(valor: number | null | undefined, formato: 'x' | 'pct'): string {
  if (valor == null) return '—'
  if (formato === 'x') return `${valor.toLocaleString('es-AR', { maximumFractionDigits: 1, minimumFractionDigits: 1 })}x`
  const pct = valor * 100
  const decimales = Math.abs(pct) < 1 ? 2 : 1
  return `${pct.toLocaleString('es-AR', { maximumFractionDigits: decimales, minimumFractionDigits: decimales })}%`
}

/** Market cap / AUM: dato público del emisor, en USD compacto. */
export function formatTamano(usd: number | null | undefined): string {
  if (usd == null) return '—'
  if (usd >= 1e12) return `US$ ${(usd / 1e12).toFixed(1)} B`
  if (usd >= 1e9) return `US$ ${(usd / 1e9).toFixed(1)} mil M`
  if (usd >= 1e6) return `US$ ${(usd / 1e6).toFixed(0)} M`
  return `US$ ${usd.toFixed(0)}`
}

export const NOMBRE_GRUPO: Record<string, string> = {
  valuacion: 'Valuación',
  calidad: 'Calidad',
  crecimiento: 'Crecimiento',
  momentum: 'Precio (momentum)',
}

export const TONO_FRASE: Record<string, string> = {
  positivo: 'border-l-app-pos',
  negativo: 'border-l-app-neg',
  alerta: 'border-l-app-warn',
  neutro: 'border-l-app-border',
}
