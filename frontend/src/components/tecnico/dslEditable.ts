/** Traducción DSL ⇄ formulario del editor visual, y `esEditableVisual` derivada de la misma
 * función que lee el editor — una sola fuente de verdad, imposible de desincronizar.
 *
 * El editor visual sólo entiende: una condición hoja comparadora, o un `y`/`o` cuyos hijos son
 * *todos* condiciones hoja comparadoras. Cualquier otra cosa (`no`, `entre`, `subiendo`,
 * `bajando`, anidamiento de `y`/`o`) no es representable: `bloqueDeDsl` la descarta y lo cuenta
 * en `descartadas`, y `esEditableVisual` lo usa para decidir si mostrar el editor visual o el
 * panel avanzado de solo lectura. */
import type { CondicionDsl, EstrategiaDsl, OperandoDsl } from '../../api'

export type CampoPrecio = 'cierre' | 'apertura' | 'maximo' | 'minimo' | 'volumen'
export type OpComparador = 'mayor' | 'menor' | 'mayor_igual' | 'menor_igual' | 'cruce_arriba' | 'cruce_abajo'

export interface OperandoForm {
  kind: 'ref' | 'const' | 'campo'
  ref?: string
  salida?: string
  valor?: number
  campo?: CampoPrecio
}

export interface FilaCondicion {
  id: string
  op: OpComparador
  izq: OperandoForm
  der: OperandoForm
}

const COMPARADORES: OpComparador[] = ['mayor', 'menor', 'mayor_igual', 'menor_igual', 'cruce_arriba', 'cruce_abajo']

export const ES_COMPARADOR = (op: string): op is OpComparador => (COMPARADORES as string[]).includes(op)

/** Id de fila: sólo es `key` de React, nunca viaja al DSL. */
export const nuevaFilaId = (): string =>
  typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `c${Math.random().toString(36).slice(2)}`

export function operandoDeDsl(op: OperandoDsl): OperandoForm {
  if ('ref' in op) return { kind: 'ref', ref: op.ref, salida: op.salida }
  if ('campo' in op) return { kind: 'campo', campo: op.campo }
  return { kind: 'const', valor: op.const }
}

export function operandoADsl(op: OperandoForm): OperandoDsl {
  if (op.kind === 'const') return { const: op.valor ?? 0 }
  if (op.kind === 'campo') return { campo: op.campo ?? 'cierre' }
  return op.salida ? { ref: op.ref ?? '', salida: op.salida } : { ref: op.ref ?? '' }
}

export interface BloqueEditable {
  combinador: 'y' | 'o'
  filas: FilaCondicion[]
  /** Condiciones que el editor visual no puede representar y por lo tanto ignoró. > 0 ⇒ no
   * mostrar el editor visual (se perderían al guardar). */
  descartadas: number
}

export function bloqueDeDsl(cond: CondicionDsl | null | undefined): BloqueEditable {
  if (!cond) return { combinador: 'y', filas: [], descartadas: 0 }

  if (cond.op === 'y' || cond.op === 'o') {
    const filas: FilaCondicion[] = []
    let descartadas = 0
    for (const c of cond.condiciones) {
      if (ES_COMPARADOR(c.op) && 'izq' in c && 'der' in c) {
        filas.push({ id: nuevaFilaId(), op: c.op, izq: operandoDeDsl(c.izq), der: operandoDeDsl(c.der) })
      } else {
        descartadas += 1
      }
    }
    return { combinador: cond.op, filas, descartadas }
  }

  if (ES_COMPARADOR(cond.op) && 'izq' in cond && 'der' in cond) {
    return {
      combinador: 'y',
      filas: [{ id: nuevaFilaId(), op: cond.op, izq: operandoDeDsl(cond.izq), der: operandoDeDsl(cond.der) }],
      descartadas: 0,
    }
  }

  // `no` / `entre` / `subiendo` / `bajando` a nivel raíz: nada representable.
  return { combinador: 'y', filas: [], descartadas: 1 }
}

export function bloqueADsl(combinador: 'y' | 'o', filas: FilaCondicion[]): CondicionDsl | null {
  if (filas.length === 0) return null
  const condiciones = filas.map(f => ({ op: f.op, izq: operandoADsl(f.izq), der: operandoADsl(f.der) }) as CondicionDsl)
  if (condiciones.length === 1) return condiciones[0]
  return { op: combinador, condiciones }
}

/** ¿El editor visual puede editar este DSL sin perder condiciones? Deriva de `bloqueDeDsl`, así
 * nunca queda fuera de sync con lo que el editor realmente sabe leer. */
export function esEditableVisual(dsl: EstrategiaDsl): boolean {
  const entrada = bloqueDeDsl(dsl.entrada)
  const salida = bloqueDeDsl(dsl.salida ?? null)
  return entrada.descartadas === 0 && salida.descartadas === 0 && entrada.filas.length > 0
}

/** Primer sufijo libre para un id de indicador, respecto de los ids ya presentes. Evita que
 * importar un DSL con `id:"sma1"` y después agregar un SMA por la UI regenere `sma1` (el backend
 * respondería "id duplicado", o `compilar` pisaría la serie en silencio). */
export function nuevoIdIndicador(tipo: string, existentes: string[]): string {
  const base = tipo.toLowerCase().slice(0, 3) || 'ind'
  const usados = new Set(existentes)
  for (let i = 1; ; i++) {
    const candidato = `${base}${i}`
    if (!usados.has(candidato)) return candidato
  }
}
