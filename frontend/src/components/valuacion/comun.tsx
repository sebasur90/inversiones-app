import type { EstadoCelda, FuenteClasificacion, LecturaValuacion, NivelComparabilidad, NivelDimension, OrigenDato } from '../../api'

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

/** Estado de una dimensión del diagnóstico: punto + palabra (nunca sólo color). La valuación es
 *  "neutro" a propósito: estar barata o cara no es bueno ni malo por sí solo. */
const PUNTO_NIVEL: Record<NivelDimension, string> = {
  bien: 'bg-app-pos',
  atencion: 'bg-app-warn',
  riesgo: 'bg-app-neg',
  neutro: 'bg-app-text-dim',
  sin_datos: 'bg-app-text-faint',
  no_aplica: 'bg-app-text-faint',
}
const TEXTO_NIVEL: Record<NivelDimension, string> = {
  bien: 'text-app-pos',
  atencion: 'text-app-warn',
  riesgo: 'text-app-neg',
  neutro: 'text-app-text',
  sin_datos: 'text-app-text-faint',
  no_aplica: 'text-app-text-faint',
}

export function EstadoDimension({ nivel, estado, className = '' }: { nivel: NivelDimension; estado: string; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 min-w-0 ${className}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${PUNTO_NIVEL[nivel]}`} aria-hidden="true" />
      <span className={`text-label font-semibold truncate ${TEXTO_NIVEL[nivel]}`}>{estado}</span>
    </span>
  )
}

const TEXTO_ORIGEN: Record<OrigenDato, string> = {
  observado: 'dato',
  estimado: 'estimación',
  calculado: 'calculado',
}

/** Qué es cada cosa que se muestra: un dato informado, una estimación de analistas o algo que
 *  calculó la app. Lo "observado" va sin etiqueta en las tablas para no cargarlas. */
export function OrigenTag({ origen }: { origen: OrigenDato }) {
  return (
    <span className={`text-label px-1.5 py-0.5 rounded-[6px] shrink-0 ${origen === 'estimado' ? 'bg-app-accent-soft text-app-accent' : 'bg-app-surface-2 text-app-text-faint'}`}>
      {TEXTO_ORIGEN[origen]}
    </span>
  )
}

export const ORDEN_NIVEL_CONFIANZA: Record<string, number> = { alta: 3, media: 2, baja: 1, sin_datos: 0 }

const ESTILO_COMPARABILIDAD: Record<NivelComparabilidad, { punto: string; texto: string; palabra: string }> = {
  alta: { punto: 'bg-app-pos', texto: 'text-app-pos', palabra: 'Comparabilidad alta' },
  media: { punto: 'bg-app-warn', texto: 'text-app-warn', palabra: 'Comparabilidad media' },
  baja: { punto: 'bg-app-text-faint', texto: 'text-app-text-dim', palabra: 'Comparabilidad baja' },
  no_comparable: { punto: 'bg-app-neg', texto: 'text-app-neg', palabra: 'No comparable' },
}

/** Qué tan comparable es una alternativa: punto + palabra (nunca sólo color). */
export function ComparabilidadBadge({ nivel, corto = false }: { nivel: NivelComparabilidad; corto?: boolean }) {
  const e = ESTILO_COMPARABILIDAD[nivel]
  return (
    <span className="inline-flex items-center gap-1.5 min-w-0">
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${e.punto}`} aria-hidden="true" />
      <span className={`text-label font-semibold whitespace-nowrap ${e.texto}`}>{corto ? e.palabra.replace('Comparabilidad ', '') : e.palabra}</span>
    </span>
  )
}

const TEXTO_CELDA: Record<Exclude<EstadoCelda, 'dato'>, string> = {
  sin_dato: '—',
  no_aplica: 'no aplica',
  sin_ganancias: 'sin ganancias',
  moneda: 'otra moneda',
}

/** El contenido de una celda de la tabla comparativa: el valor, o por qué no hay (sin dato ≠ no aplica). */
export function textoCelda(celda: { valor: number | null; estado: EstadoCelda }, formato: 'x' | 'pct'): string {
  return celda.estado === 'dato' ? formatMetrica(celda.valor, formato) : TEXTO_CELDA[celda.estado]
}

export const fechaCorta = (iso: string | null | undefined): string =>
  iso ? iso.split('-').reverse().join('/') : '—'
