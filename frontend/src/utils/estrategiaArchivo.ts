/** Sobre versionado para exportar/importar estrategias como archivo `.json`. Puro, sin React.
 *
 * Dos versiones a propósito: `formato_version` (el sobre) y `definicion.version` (el DSL, que ya
 * existe). `ticker: null` es lo que hace la estrategia reusable en cualquier activo. El importador
 * **también acepta un DSL crudo** (tiene `version` y `entrada` en la raíz, no tiene `definicion`),
 * así pegar el `definicion` de un preset o de una respuesta de la API funciona sin fricción.
 *
 * **No** reimplementa `validar_estrategia`: la autoridad es el backend (el backtest tras importar
 * dispara el 422 si el DSL es inválido). Acá sólo se chequea que el archivo tenga forma de
 * estrategia y que sus indicadores sean conocidos por esta versión de la app. */
import type { EstrategiaDsl, VarianteSerie } from '../api'
import { ESPEC_POR_TIPO } from '../components/tecnico/indicadoresConfig'
import { sufijoFechaHoy } from './csv'

export const FORMATO_ARCHIVO = 'inversiones-app/estrategia'
export const FORMATO_VERSION = 1
const TAMANO_MAXIMO_BYTES = 200 * 1024

export interface EstrategiaArchivo {
  definicion: EstrategiaDsl
  nombre: string | null
  descripcion: string | null
  ticker: string | null
  variante: VarianteSerie
}

interface MetaEstrategia {
  nombre?: string | null
  descripcion?: string | null
  ticker?: string | null
  variante?: VarianteSerie
}

export function serializarEstrategia(definicion: EstrategiaDsl, meta: MetaEstrategia = {}): string {
  const sobre = {
    formato: FORMATO_ARCHIVO,
    formato_version: FORMATO_VERSION,
    exportado_en: new Date().toISOString(),
    nombre: meta.nombre ?? null,
    descripcion: meta.descripcion ?? null,
    ticker: meta.ticker ?? null,
    variante: meta.variante ?? 'local',
    definicion,
  }
  return JSON.stringify(sobre, null, 2) + '\n'
}

const DIACRITICOS = new RegExp('[\\u0300-\\u036f]', 'g')

function slugArchivo(nombre: string): string {
  return (nombre || 'estrategia')
    .toLowerCase()
    .normalize('NFD').replace(DIACRITICOS, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'estrategia'
}

/** `estrategia-minimo-historico-2026-09-07.json` */
export function nombreArchivoEstrategia(nombre: string): string {
  return `estrategia-${slugArchivo(nombre)}-${sufijoFechaHoy()}.json`
}

export class ArchivoEstrategiaInvalido extends Error {}

function esDslCrudo(obj: Record<string, unknown>): boolean {
  return 'version' in obj && 'entrada' in obj && !('definicion' in obj)
}

export function parsearArchivoEstrategia(texto: string): EstrategiaArchivo {
  if (texto.length > TAMANO_MAXIMO_BYTES) {
    throw new ArchivoEstrategiaInvalido('el archivo es demasiado grande para ser una estrategia')
  }
  let raiz: unknown
  try {
    raiz = JSON.parse(texto)
  } catch {
    throw new ArchivoEstrategiaInvalido('el archivo no es JSON válido')
  }
  if (typeof raiz !== 'object' || raiz === null || Array.isArray(raiz)) {
    throw new ArchivoEstrategiaInvalido('el archivo no tiene la forma de una estrategia')
  }
  const obj = raiz as Record<string, unknown>

  const crudo = esDslCrudo(obj)
  const definicionRaw = crudo ? obj : obj.definicion
  if (typeof definicionRaw !== 'object' || definicionRaw === null || Array.isArray(definicionRaw)) {
    throw new ArchivoEstrategiaInvalido('el archivo no tiene una "definicion" de estrategia')
  }
  const def = definicionRaw as Record<string, unknown>

  if (def.version !== 1) {
    throw new ArchivoEstrategiaInvalido(`versión de definición no soportada: ${JSON.stringify(def.version)} (esperado 1)`)
  }
  if (typeof def.entrada !== 'object' || def.entrada === null) {
    throw new ArchivoEstrategiaInvalido('la definición no tiene "entrada"')
  }
  if (!Array.isArray(def.indicadores)) {
    throw new ArchivoEstrategiaInvalido('la definición no tiene la lista "indicadores"')
  }
  for (const ind of def.indicadores as Array<Record<string, unknown>>) {
    const tipo = ind?.tipo
    if (typeof tipo !== 'string' || !(tipo in ESPEC_POR_TIPO)) {
      throw new ArchivoEstrategiaInvalido(
        `el archivo usa el indicador ${JSON.stringify(tipo)}, que esta versión de la app no conoce`,
      )
    }
  }

  const meta = crudo ? {} : obj
  const varianteRaw = meta.variante
  return {
    definicion: def as unknown as EstrategiaDsl,
    nombre: typeof meta.nombre === 'string' ? meta.nombre : null,
    descripcion: typeof meta.descripcion === 'string' ? meta.descripcion : null,
    ticker: typeof meta.ticker === 'string' ? meta.ticker : null,
    variante: varianteRaw === 'subyacente' ? 'subyacente' : 'local',
  }
}
