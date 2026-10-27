import dayjs from 'dayjs'
import type { CategoriaEvento, Evento, FiltrosEventos } from '../api'

/** Color de cada categoría (puntos del calendario, marcas del gráfico, etiquetas). */
export const COLOR_CATEGORIA: Record<CategoriaEvento, string> = {
  elecciones: '#a78bfa',
  politica: '#818cf8',
  geopolitica: '#ef4444',
  sanciones_aranceles: '#fb923c',
  regulacion: '#facc15',
  banco_central: '#3b82f6',
  dato_macro: '#22d3ee',
  resultados: '#10b981',
  corporativo: '#2dd4bf',
  crisis_financiera: '#f472b6',
  tecnologia_sector: '#a3e635',
  materias_primas: '#f59e0b',
  otro: '#94a3b8',
}

export const ETIQUETA_CATEGORIA: Record<CategoriaEvento, string> = {
  elecciones: 'Elecciones',
  politica: 'Política',
  geopolitica: 'Geopolítica',
  sanciones_aranceles: 'Sanciones y aranceles',
  regulacion: 'Regulación',
  banco_central: 'Bancos centrales',
  dato_macro: 'Datos macro',
  resultados: 'Resultados',
  corporativo: 'Corporativo',
  crisis_financiera: 'Crisis financieras',
  tecnologia_sector: 'Tecnología y sectores',
  materias_primas: 'Materias primas',
  otro: 'Otros',
}

export const CATEGORIAS = Object.keys(ETIQUETA_CATEGORIA) as CategoriaEvento[]

export const ETIQUETA_IMPORTANCIA: Record<number, string> = { 1: 'Baja', 2: 'Media', 3: 'Alta' }

export const ETIQUETA_ESTADO: Record<string, string> = {
  previsto: 'Previsto',
  confirmado: 'Confirmado',
  en_desarrollo: 'En desarrollo',
  concluido: 'Concluido',
  cancelado: 'Cancelado',
  reprogramado: 'Reprogramado',
}

export const ETIQUETA_VERIFICACION: Record<string, string> = {
  sin_verificar: 'Sin verificar',
  fuente_oficial: 'Fuente oficial',
  multiples_fuentes: 'Varias fuentes',
  verificado_usuario: 'Verificado por vos',
  catalogo_revisar: 'Catálogo · revisar',
  rumor: 'Rumor',
}

export const ETIQUETA_PRECISION: Record<string, string> = {
  exacta: 'Fecha exacta',
  aproximada: 'Fecha estimada',
  mes: 'Sólo el mes',
  anio: 'Sólo el año',
  desconocida: 'Fecha desconocida',
}

export const ETIQUETA_ORIGEN: Record<string, string> = {
  manual: 'Cargado por vos',
  catalogo: 'Catálogo histórico',
  calendario_oficial: 'Calendario oficial',
  proveedor: 'Importado de noticias',
  importacion: 'Archivo importado',
}

export const ETIQUETA_RELACION: Record<string, string> = {
  directa: 'Directa',
  matriz: 'Empresa matriz',
  sector: 'Sector',
  pais: 'País',
  macro: 'Macro',
  materia_prima: 'Materia prima',
  indice: 'Índice',
  otra: 'Otra',
  general: 'General',
}

export const ETIQUETA_CONFIANZA: Record<string, string> = { alta: 'Confianza alta', media: 'Confianza media', baja: 'Confianza baja' }

export const AVISO_ANALISIS: Record<string, string> = {
  hora_desconocida: 'No se sabe la hora: si fue después del cierre, la reacción aparece recién en la rueda siguiente.',
  sin_datos_posteriores: 'La serie no tiene ruedas posteriores al evento: no hay nada que medir todavía.',
  sin_datos_previos: 'La serie empieza en la rueda del evento: no hay datos previos.',
  sin_serie: 'No hay serie de precios para este instrumento.',
  otro_evento_misma_rueda: 'Hubo otro evento relevante en la misma rueda: el movimiento no se le puede atribuir a uno solo.',
  posible_split: 'La serie tiene un salto que parece un split o un cambio de escala: los retornos que lo crucen no son reales.',
  serie_con_huecos: 'La serie tiene huecos de más de una semana.',
  sin_benchmark: 'No hay serie del índice para comparar.',
  fuera_del_universo: 'No está en tu cartera ni en la watchlist: no hay serie para analizarlo.',
  moneda_mixta: 'La serie mezcla monedas.',
}

export const MOTIVO_VENTANA: Record<string, string> = {
  ventana_incompleta_antes: 'faltan ruedas antes',
  ventana_incompleta_despues: 'faltan ruedas después',
  sin_datos_posteriores: 'todavía no hay ruedas después',
  huecos: 'la serie tiene huecos',
}

export const esEstimada = (e: Pick<Evento, 'precision_fecha'>) => e.precision_fecha !== 'exacta'

/** `2026-03-18` → `Date` local (sin corrimiento por zona horaria). */
export const fechaLocal = (iso: string) => dayjs(iso.slice(0, 10)).toDate()

export const isoDia = (d: dayjs.Dayjs | Date) => dayjs(d).format('YYYY-MM-DD')

/** Rango del mes que contiene a `mes` (`YYYY-MM`), extendido a semanas completas de lunes a domingo. */
export function grillaMes(mes: string): { dias: dayjs.Dayjs[]; desde: string; hasta: string } {
  const inicio = dayjs(`${mes}-01`)
  const offset = (inicio.day() + 6) % 7 // lunes = 0
  const primero = inicio.subtract(offset, 'day')
  const fin = inicio.endOf('month')
  const offsetFin = (7 - ((fin.day() + 6) % 7) - 1) % 7
  const ultimo = fin.add(offsetFin, 'day')
  const dias: dayjs.Dayjs[] = []
  for (let d = primero; !d.isAfter(ultimo, 'day'); d = d.add(1, 'day')) dias.push(d)
  return { dias, desde: isoDia(primero), hasta: isoDia(ultimo) }
}

export function agruparPorDia(eventos: Evento[]): Map<string, Evento[]> {
  const out = new Map<string, Evento[]>()
  for (const e of eventos) {
    const k = e.fecha_evento
    const lista = out.get(k)
    if (lista) lista.push(e)
    else out.set(k, [e])
  }
  for (const lista of out.values()) lista.sort((a, b) => b.importancia - a.importancia || a.titulo.localeCompare(b.titulo))
  return out
}

/** Días hábiles (lunes a viernes) posteriores a `desde`, hasta `hasta` inclusive. El eje futuro del
 * gráfico: no hay feriados porque no hay precios que ubicar ahí, sólo fechas. */
export function diasHabilesEntre(desde: string, hasta: string, tope = 160): string[] {
  const out: string[] = []
  let d = dayjs(desde).add(1, 'day')
  const fin = dayjs(hasta)
  while (!d.isAfter(fin, 'day') && out.length < tope) {
    if (d.day() !== 0 && d.day() !== 6) out.push(isoDia(d))
    d = d.add(1, 'day')
  }
  return out
}

export function pct(v: number | null | undefined, decimales = 1): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(decimales).replace('.', ',')} %`
}

export const tonoPct = (v: number | null | undefined) =>
  v == null ? 'text-app-text-faint' : v > 0 ? 'text-app-pos' : v < 0 ? 'text-app-neg' : 'text-app-text-dim'

// ── Filtros persistidos ─────────────────────────────────────────────────────────────────────

export interface FiltrosPantalla {
  categorias: CategoriaEvento[]
  paises: string[]
  tickers: string[]
  sectores: string[]
  enCartera: boolean
  importanciaMin: number | null
  verificaciones: string[]
  origenes: string[]
  proveedores: string[]
  temporalidad: 'todos' | 'pasados' | 'futuros'
  desde: string | null
  hasta: string | null
  incluirDescartados: boolean
}

export const FILTROS_VACIOS: FiltrosPantalla = {
  categorias: [], paises: [], tickers: [], sectores: [], enCartera: false, importanciaMin: null,
  verificaciones: [], origenes: [], proveedores: [], temporalidad: 'todos', desde: null, hasta: null,
  incluirDescartados: false,
}

const lista = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [])

/** Parse defensivo de lo guardado en localStorage: lo que no cuadra vuelve al valor vacío. */
export function parseFiltros(crudo: string): FiltrosPantalla | null {
  try {
    const o = JSON.parse(crudo) as Record<string, unknown>
    const temporalidad = o.temporalidad === 'pasados' || o.temporalidad === 'futuros' ? o.temporalidad : 'todos'
    const imp = typeof o.importanciaMin === 'number' && [1, 2, 3].includes(o.importanciaMin) ? o.importanciaMin : null
    const fecha = (v: unknown) => (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : null)
    return {
      categorias: lista(o.categorias).filter((c): c is CategoriaEvento => c in ETIQUETA_CATEGORIA),
      paises: lista(o.paises), tickers: lista(o.tickers), sectores: lista(o.sectores), enCartera: o.enCartera === true,
      importanciaMin: imp, verificaciones: lista(o.verificaciones), origenes: lista(o.origenes),
      proveedores: lista(o.proveedores), temporalidad, desde: fecha(o.desde), hasta: fecha(o.hasta),
      incluirDescartados: o.incluirDescartados === true,
    }
  } catch {
    return null
  }
}

export const serializarFiltros = (f: FiltrosPantalla) => JSON.stringify(f)

/** Filtros de la pantalla + búsqueda → parámetros del endpoint. */
export function aParametros(f: FiltrosPantalla, q: string): FiltrosEventos {
  return {
    categoria: f.categorias.length ? f.categorias : undefined,
    pais: f.paises.length ? f.paises : undefined,
    ticker: f.tickers.length ? f.tickers : undefined,
    sector: f.sectores.length ? f.sectores : undefined,
    en_cartera: f.enCartera || undefined,
    importancia_min: f.importanciaMin ?? undefined,
    verificacion: f.verificaciones.length ? f.verificaciones : undefined,
    origen: f.origenes.length ? f.origenes : undefined,
    proveedor: f.proveedores.length ? f.proveedores : undefined,
    temporalidad: f.temporalidad,
    desde: f.desde ?? undefined,
    hasta: f.hasta ?? undefined,
    incluir_descartados: f.incluirDescartados || undefined,
    q: q.trim() || undefined,
  }
}

/** Cuántos filtros (fuera de las categorías y la búsqueda) están activos, para el botón "Más filtros". */
export function filtrosActivos(f: FiltrosPantalla): number {
  return [
    f.paises.length, f.tickers.length, f.sectores.length, f.enCartera, f.importanciaMin != null,
    f.verificaciones.length, f.origenes.length, f.proveedores.length, f.temporalidad !== 'todos',
    f.desde, f.hasta, f.incluirDescartados,
  ].filter(Boolean).length
}
