import type { CicloGrupoCatalogo, CicloTipo, Cuadrante } from '../../api'
import type { HelpKey } from '../../help/content/index'

export const CUADRANTES: Cuadrante[] = ['leading', 'weakening', 'lagging', 'improving']

export const INFO_CUADRANTE: Record<Cuadrante, { nombre: string; frase: string; color: string; termino: HelpKey }> = {
  leading: {
    nombre: 'Leading',
    frase: 'Fortaleza relativa y momentum positivos',
    color: '#10b981',
    termino: 'ciclos_leading',
  },
  weakening: {
    nombre: 'Weakening',
    frase: 'Mantiene fortaleza, pero pierde momentum',
    color: '#f59e0b',
    termino: 'ciclos_weakening',
  },
  lagging: {
    nombre: 'Lagging',
    frase: 'Debilidad relativa y momentum negativo',
    color: '#ef4444',
    termino: 'ciclos_lagging',
  },
  improving: {
    nombre: 'Improving',
    frase: 'Sigue débil, pero recupera momentum',
    color: '#3b82f6',
    termino: 'ciclos_improving',
  },
}

export const TIPOS_ANALISIS: { value: CicloTipo; label: string }[] = [
  { value: 'sector', label: 'Sectores' },
  { value: 'industria', label: 'Industrias' },
  { value: 'commodity', label: 'Commodities' },
  { value: 'region', label: 'Regiones' },
  { value: 'pais', label: 'Países' },
  { value: 'activo', label: 'Activos' },
  { value: 'tema', label: 'Temas' },
]

export const ETIQUETA_TIPO: Record<CicloTipo, string> = {
  sector: 'Sector',
  industria: 'Industria',
  commodity: 'Commodity',
  region: 'Región',
  pais: 'País',
  activo: 'Activo',
  tema: 'Tema',
}

// Paleta categórica de la app (azul, esmeralda, ámbar, violeta, cian, ...) sin el rojo y el verde puros de los
// estados: el color de un grupo identifica al punto, el del cuadrante identifica el estado.
export const COLORES_GRUPOS = [
  '#60a5fa', '#a78bfa', '#22d3ee', '#fbbf24', '#f472b6', '#34d399',
  '#fb923c', '#818cf8', '#2dd4bf', '#e879f9', '#a3e635', '#38bdf8',
  '#c084fc', '#facc15', '#4ade80', '#f87171',
]

// |rendimiento| (en %) a partir del cual el color del mapa de calor satura: más largo el horizonte, más ancho.
export const CAP_HEATMAP: Record<string, number> = { '1M': 10, '3M': 15, '6M': 25, '1A': 40, '3A': 80, '5A': 120, '10A': 200 }

export function fmtPct(v: number | null | undefined, decimales = 1, signo = true): string {
  if (v == null || !Number.isFinite(v)) return '—'
  const t = (v * 100).toLocaleString('es-AR', { minimumFractionDigits: decimales, maximumFractionDigits: decimales })
  return `${signo && v > 0 ? '+' : ''}${t}%`
}

export function fmtNum(v: number | null | undefined, decimales = 1): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toLocaleString('es-AR', { minimumFractionDigits: decimales, maximumFractionDigits: decimales })
}

/** Etiqueta compacta para puntos y celdas angostas: el símbolo del proxy, o el nombre si no tiene. */
export function etiquetaCorta(g: Pick<CicloGrupoCatalogo, 'nombre' | 'proxy'> | { nombre: string; proxy: string | null }): string {
  return g.proxy ?? g.nombre
}

export function colorGrupo(indice: number): string {
  return COLORES_GRUPOS[indice % COLORES_GRUPOS.length]
}

export function tonoDe(v: number | null | undefined): 'pos' | 'neg' | undefined {
  if (v == null || v === 0) return undefined
  return v > 0 ? 'pos' : 'neg'
}

export const MOTIVO_SIN_ESTADO: Record<string, string> = {
  sin_clasificar: 'Sin clasificar',
  sin_grupo: 'Sin grupo en el catálogo',
  sin_datos: 'Sin datos del grupo',
  desactualizado: 'Datos desactualizados',
  insuficiente: 'Historia insuficiente',
  sin_estado: 'Sin estado',
}
