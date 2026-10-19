import { hierarchy, treemap, treemapSquarify, type HierarchyRectangularNode } from 'd3-hierarchy'
import type { MapaMercadoItem } from '../api'

export type Eje = 'sector' | 'region' | 'tamano' | 'tipo'
export type Periodo = '1d' | '1s' | '1m' | '1a'
export type TamanoRect = 'cap' | 'cartera' | 'parejo'

export const SIN_CLASIFICAR = 'Sin clasificar'

/** Orden fijo de las bandas de tamaño de empresa (de la más grande a la más chica). */
const ORDEN_TAMANO = ['Mega', 'Grande', 'Mediana', 'Chica', 'Sin dato']

export interface NodoMapa {
  clave: string
  etiqueta: string
  hijos?: NodoMapa[]
  /** Sólo en hojas. */
  item?: MapaMercadoItem
  /** Sólo en hojas: lo que pesa el rectángulo según el "tamaño" elegido. */
  peso: number
  /** Variación promedio ponderada (grupos) o propia (hojas). null si nada del grupo tiene dato. */
  variacion: number | null
}

export function variacionDe(item: MapaMercadoItem, periodo: Periodo): number | null {
  return { '1d': item.var_1d, '1s': item.var_1s, '1m': item.var_1m, '1a': item.var_1a }[periodo]
}

/** |variación| que satura el color: un día se mueve poco, un año mucho. */
export const TOPE_COLOR: Record<Periodo, number> = { '1d': 0.03, '1s': 0.06, '1m': 0.1, '1a': 0.3 }

// ── Color ────────────────────────────────────────────────────────────────────────────────────

const NEUTRO: [number, number, number] = [58, 63, 76]
const POS: [number, number, number] = [16, 185, 129] // app-pos
const NEG: [number, number, number] = [239, 68, 68] // app-neg
export const COLOR_SIN_DATO = '#252a36'

function mezclar(a: [number, number, number], b: [number, number, number], t: number): string {
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t))
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`
}

/** Color sólido, del gris neutro al verde (sube) o al rojo (baja), saturado en `tope`. Sin dato → gris oscuro. */
export function colorVariacion(variacion: number | null, tope: number): string {
  if (variacion == null) return COLOR_SIN_DATO
  const t = Math.min(Math.abs(variacion) / tope, 1)
  return mezclar(NEUTRO, variacion >= 0 ? POS : NEG, t)
}

export const GRADIENTE_LEYENDA = `linear-gradient(to right, ${mezclar(NEUTRO, NEG, 1)}, ${mezclar(NEUTRO, NEUTRO, 0)}, ${mezclar(NEUTRO, POS, 1)})`

// ── Árbol ────────────────────────────────────────────────────────────────────────────────────

function claves(item: MapaMercadoItem, eje: Eje): string[] {
  switch (eje) {
    case 'sector':
      return [item.sector ?? SIN_CLASIFICAR, item.industria ?? SIN_CLASIFICAR]
    case 'region':
      return [item.region ?? SIN_CLASIFICAR, item.pais ?? SIN_CLASIFICAR]
    case 'tamano':
      return [item.tamano_empresa]
    case 'tipo':
      return [item.tipo ?? SIN_CLASIFICAR]
  }
}

/**
 * Lo que pesa cada rectángulo. La capitalización se achata con raíz cuadrada: con la escala
 * real, 3 o 4 gigantes se comen el mapa y los otros 450 quedan como puntos. Un emisor sin
 * capitalización pesa lo que el más chico que sí la tiene (no desaparece, pero tampoco infla).
 */
export function calcularPesos(items: MapaMercadoItem[], tamano: TamanoRect): Map<string, number> {
  const pesos = new Map<string, number>()
  if (tamano === 'parejo') {
    items.forEach(i => pesos.set(i.ticker_base, 1))
  } else if (tamano === 'cartera') {
    items.forEach(i => pesos.set(i.ticker_base, i.peso_cartera ?? 0))
  } else {
    const conCap = items.filter(i => i.market_cap_usd != null && i.market_cap_usd > 0)
    const piso = conCap.length ? Math.min(...conCap.map(i => Math.sqrt(i.market_cap_usd as number))) : 1
    items.forEach(i =>
      pesos.set(i.ticker_base, i.market_cap_usd != null && i.market_cap_usd > 0 ? Math.sqrt(i.market_cap_usd) : piso),
    )
  }
  return pesos
}

function promedioPonderado(hojas: NodoMapa[]): number | null {
  let suma = 0
  let peso = 0
  for (const h of hojas) {
    if (h.variacion == null || h.peso <= 0) continue
    suma += h.variacion * h.peso
    peso += h.peso
  }
  return peso > 0 ? suma / peso : null
}

export function hojasDe(nodo: NodoMapa): NodoMapa[] {
  if (!nodo.hijos) return [nodo]
  return nodo.hijos.flatMap(hojasDe)
}

function ordenGrupos(eje: Eje, a: NodoMapa, b: NodoMapa, valor: (n: NodoMapa) => number): number {
  if (eje === 'tamano') {
    const ia = ORDEN_TAMANO.findIndex(t => a.etiqueta.startsWith(t))
    const ib = ORDEN_TAMANO.findIndex(t => b.etiqueta.startsWith(t))
    return ia - ib
  }
  // "Sin clasificar" siempre al final: no es un grupo, es lo que falta.
  if (a.etiqueta === SIN_CLASIFICAR) return 1
  if (b.etiqueta === SIN_CLASIFICAR) return -1
  return valor(b) - valor(a)
}

/** Arma el árbol completo del eje (grupo → subgrupo → hojas) con la variación de cada nodo. */
export function construirArbol(
  items: MapaMercadoItem[],
  eje: Eje,
  periodo: Periodo,
  tamano: TamanoRect,
): NodoMapa {
  const pesos = calcularPesos(items, tamano)
  const raiz: NodoMapa = { clave: '', etiqueta: 'Mercado', hijos: [], peso: 0, variacion: null }

  for (const item of items) {
    const peso = pesos.get(item.ticker_base) ?? 0
    if (peso <= 0) continue
    let padre = raiz
    for (const etiqueta of claves(item, eje)) {
      const clave = `${padre.clave}/${etiqueta}`
      let nodo = padre.hijos!.find(n => n.clave === clave)
      if (!nodo) {
        nodo = { clave, etiqueta, hijos: [], peso: 0, variacion: null }
        padre.hijos!.push(nodo)
      }
      padre = nodo
    }
    padre.hijos!.push({
      clave: `${padre.clave}/${item.ticker_base}`,
      etiqueta: item.ticker,
      item,
      peso,
      variacion: variacionDe(item, periodo),
    })
  }

  const valor = (n: NodoMapa) => hojasDe(n).reduce((s, h) => s + h.peso, 0)
  const completar = (nodo: NodoMapa) => {
    if (!nodo.hijos) return
    nodo.hijos.forEach(completar)
    nodo.hijos.sort((a, b) => (a.item || b.item ? valor(b) - valor(a) : ordenGrupos(eje, a, b, valor)))
    nodo.variacion = promedioPonderado(hojasDe(nodo))
  }
  completar(raiz)
  return raiz
}

/** El nodo al que lleva `ruta` (lista de claves de grupo), o la raíz si ya no existe. */
export function ubicar(raiz: NodoMapa, ruta: string[]): { nodo: NodoMapa; migas: NodoMapa[]; valida: boolean } {
  let nodo = raiz
  const migas: NodoMapa[] = []
  for (const clave of ruta) {
    const hijo = nodo.hijos?.find(n => n.clave === clave && n.hijos)
    if (!hijo) return { nodo: raiz, migas: [], valida: false }
    migas.push(hijo)
    nodo = hijo
  }
  return { nodo, migas, valida: true }
}

// ── Layout ───────────────────────────────────────────────────────────────────────────────────

export interface Rect {
  x: number
  y: number
  w: number
  h: number
}
export interface RectGrupo extends Rect {
  nodo: NodoMapa
}
export interface RectHoja extends Rect {
  nodo: NodoMapa
}

/**
 * Posiciona los rectángulos del nodo visible. Si sus hijos son grupos, cada grupo muestra **todas
 * sus hojas juntas** (aunque haya un subgrupo en el medio): la vista general es "un bloque por
 * sector con sus empresas adentro", y el subgrupo (industria, país) se ve al entrar al grupo.
 */
export function calcularLayout(
  visible: NodoMapa,
  ancho: number,
  alto: number,
  altoTitulo: number,
): { grupos: RectGrupo[]; hojas: RectHoja[] } {
  if (ancho <= 0 || alto <= 0 || !visible.hijos?.length) return { grupos: [], hojas: [] }

  const hijosSonGrupos = visible.hijos.some(h => h.hijos)
  const aplanado: NodoMapa = hijosSonGrupos
    ? { ...visible, hijos: visible.hijos.map(g => ({ ...g, hijos: hojasDe(g) })) }
    : visible

  const raiz = hierarchy<NodoMapa>(aplanado, n => n.hijos)
    .sum(n => (n.hijos ? 0 : n.peso))
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0))

  treemap<NodoMapa>()
    .tile(treemapSquarify)
    .size([ancho, alto])
    .paddingInner(1)
    .paddingTop(n => (n.depth === 1 && n.children ? altoTitulo : 0))(raiz)

  const grupos: RectGrupo[] = []
  const hojas: RectHoja[] = []
  const rect = (n: HierarchyRectangularNode<NodoMapa>): Rect => ({ x: n.x0, y: n.y0, w: n.x1 - n.x0, h: n.y1 - n.y0 })
  for (const n of raiz.descendants() as HierarchyRectangularNode<NodoMapa>[]) {
    if (n.depth === 0) continue
    if (n.children) grupos.push({ ...rect(n), nodo: n.data })
    else if ((n.value ?? 0) > 0) hojas.push({ ...rect(n), nodo: n.data })
  }
  return { grupos, hojas }
}

// ── Formato ──────────────────────────────────────────────────────────────────────────────────

/** Capitalización en castellano: 3,2 billones / 300 mil millones / 800 millones. */
export function formatCapitalizacion(usd: number | null | undefined): string {
  if (usd == null) return '—'
  const num = (v: number, dec: number) => v.toLocaleString('es-AR', { maximumFractionDigits: dec })
  if (usd >= 1e12) return `US$ ${num(usd / 1e12, 1)} billones`
  if (usd >= 1e9) return `US$ ${num(usd / 1e9, usd >= 1e11 ? 0 : 1)} mil millones`
  return `US$ ${num(usd / 1e6, 0)} millones`
}
