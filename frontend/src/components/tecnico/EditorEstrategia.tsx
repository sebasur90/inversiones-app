import { useEffect, useState } from 'react'
import type { CondicionDsl, EjecucionDsl, EstrategiaDsl, IndicadorDsl, OperandoDsl, RiesgoDsl } from '../../api'
import { ESPEC_POR_TIPO, INDICADORES_UI, claveIndicador, paramsPorDefecto } from './indicadoresConfig'
import Segmented from '../ui/Segmented'
import { Icon } from '../icons/Icons'

type CampoPrecio = 'cierre' | 'apertura' | 'maximo' | 'minimo' | 'volumen'
type OpComparador = 'mayor' | 'menor' | 'mayor_igual' | 'menor_igual' | 'cruce_arriba' | 'cruce_abajo'
const OPERADORES: { value: OpComparador; label: string }[] = [
  { value: 'mayor', label: 'es mayor que' },
  { value: 'menor', label: 'es menor que' },
  { value: 'mayor_igual', label: 'es mayor o igual que' },
  { value: 'menor_igual', label: 'es menor o igual que' },
  { value: 'cruce_arriba', label: 'cruza hacia arriba a' },
  { value: 'cruce_abajo', label: 'cruza hacia abajo a' },
]

interface OperandoForm {
  kind: 'ref' | 'const' | 'campo'
  ref?: string
  salida?: string
  valor?: number
  campo?: CampoPrecio
}

interface FilaCondicion {
  id: string
  op: OpComparador
  izq: OperandoForm
  der: OperandoForm
}

interface IndicadorForm {
  id: string
  tipo: string
  params: Record<string, number>
}

interface EstadoEstrategia {
  indicadores: IndicadorForm[]
  entradaCombinador: 'y' | 'o'
  entrada: FilaCondicion[]
  salidaCombinador: 'y' | 'o'
  salida: FilaCondicion[]
  riesgo: RiesgoDsl
  ejecucion: EjecucionDsl
}

let contador = 0
const nuevoId = (prefijo: string) => `${prefijo}${++contador}`

const OPERANDO_CIERRE: OperandoForm = { kind: 'campo', campo: 'cierre' }
const OPERANDO_CONST_0: OperandoForm = { kind: 'const', valor: 0 }

function estadoVacio(): EstadoEstrategia {
  return {
    indicadores: [],
    entradaCombinador: 'y',
    entrada: [{ id: nuevoId('c'), op: 'mayor', izq: { ...OPERANDO_CIERRE }, der: { ...OPERANDO_CONST_0 } }],
    salidaCombinador: 'y',
    salida: [],
    riesgo: { stop_loss_pct: 8, take_profit_pct: null, trailing_stop_pct: null, max_barras: null },
    ejecucion: { lado: 'long', comision_pct: 0.6, precio_ejecucion: 'cierre', demora_barras: 0 },
  }
}

function operandoDeDsl(op: OperandoDsl): OperandoForm {
  if ('ref' in op) return { kind: 'ref', ref: op.ref, salida: op.salida }
  if ('campo' in op) return { kind: 'campo', campo: op.campo }
  return { kind: 'const', valor: op.const }
}

function operandoADsl(op: OperandoForm): OperandoDsl {
  if (op.kind === 'const') return { const: op.valor ?? 0 }
  if (op.kind === 'campo') return { campo: op.campo ?? 'cierre' }
  return op.salida ? { ref: op.ref ?? '', salida: op.salida } : { ref: op.ref ?? '' }
}

const ES_COMPARADOR = (op: string): op is OpComparador =>
  ['mayor', 'menor', 'mayor_igual', 'menor_igual', 'cruce_arriba', 'cruce_abajo'].includes(op)

function bloqueDeDsl(cond: CondicionDsl | null | undefined): { combinador: 'y' | 'o'; filas: FilaCondicion[] } {
  if (!cond) return { combinador: 'y', filas: [] }
  if (cond.op === 'y' || cond.op === 'o') {
    const filas = cond.condiciones
      .filter((c): c is Extract<CondicionDsl, { izq: OperandoDsl; der: OperandoDsl }> => ES_COMPARADOR(c.op))
      .map(c => ({ id: nuevoId('c'), op: c.op as OpComparador, izq: operandoDeDsl(c.izq), der: operandoDeDsl(c.der) }))
    return { combinador: cond.op, filas }
  }
  if (ES_COMPARADOR(cond.op) && 'izq' in cond && 'der' in cond) {
    return { combinador: 'y', filas: [{ id: nuevoId('c'), op: cond.op, izq: operandoDeDsl(cond.izq), der: operandoDeDsl(cond.der) }] }
  }
  return { combinador: 'y', filas: [] }
}

function bloqueADsl(combinador: 'y' | 'o', filas: FilaCondicion[]): CondicionDsl | null {
  if (filas.length === 0) return null
  const condiciones = filas.map(f => ({ op: f.op, izq: operandoADsl(f.izq), der: operandoADsl(f.der) }) as CondicionDsl)
  if (condiciones.length === 1) return condiciones[0]
  return { op: combinador, condiciones }
}

export function dslDeEstado(estado: EstadoEstrategia): EstrategiaDsl {
  const indicadores: IndicadorDsl[] = estado.indicadores.map(i => ({ id: i.id, tipo: i.tipo, params: i.params }))
  return {
    version: 1,
    indicadores,
    entrada: bloqueADsl(estado.entradaCombinador, estado.entrada) ?? { op: 'y', condiciones: [] },
    salida: bloqueADsl(estado.salidaCombinador, estado.salida),
    riesgo: estado.riesgo,
    ejecucion: estado.ejecucion,
  }
}

function estadoDeDsl(dsl: EstrategiaDsl): EstadoEstrategia {
  const entradaB = bloqueDeDsl(dsl.entrada)
  const salidaB = bloqueDeDsl(dsl.salida ?? null)
  return {
    indicadores: dsl.indicadores.map(i => ({ id: i.id, tipo: i.tipo, params: i.params })),
    entradaCombinador: entradaB.combinador,
    entrada: entradaB.filas.length ? entradaB.filas : [{ id: nuevoId('c'), op: 'mayor', izq: { ...OPERANDO_CIERRE }, der: { ...OPERANDO_CONST_0 } }],
    salidaCombinador: salidaB.combinador,
    salida: salidaB.filas,
    riesgo: dsl.riesgo,
    ejecucion: dsl.ejecucion,
  }
}

function opcionesOperando(indicadores: IndicadorForm[]): { grupo: string; value: string; label: string }[] {
  const opciones: { grupo: string; value: string; label: string }[] = []
  for (const ind of indicadores) {
    const espec = ESPEC_POR_TIPO[ind.tipo]
    if (!espec) continue
    if (espec.destino !== 'precio' && espec.destino !== 'volumen' && espec.tipo !== 'RSI' && espec.tipo !== 'MACD' && espec.tipo !== 'ESTOCASTICO' && espec.tipo !== 'ATR') continue
    // multi-salida: una opción por salida declarada en el registro del backend
    const salidas: Record<string, string[]> = {
      MACD: ['macd', 'senal', 'histograma'],
      BOLLINGER: ['media', 'superior', 'inferior', 'ancho_pct', 'pctb'],
      ESTOCASTICO: ['k', 'd'],
    }
    const lista = salidas[ind.tipo]
    if (lista) {
      for (const s of lista) opciones.push({ grupo: 'Indicadores', value: `ref:${ind.id}:${s}`, label: `${ind.id} (${s})` })
    } else {
      opciones.push({ grupo: 'Indicadores', value: `ref:${ind.id}:`, label: ind.id })
    }
  }
  const campos: { campo: CampoPrecio; label: string }[] = [
    { campo: 'cierre', label: 'Precio de cierre' },
    { campo: 'apertura', label: 'Precio de apertura' },
    { campo: 'maximo', label: 'Precio máximo' },
    { campo: 'minimo', label: 'Precio mínimo' },
    { campo: 'volumen', label: 'Volumen' },
  ]
  for (const c of campos) opciones.push({ grupo: 'Precio', value: `campo:${c.campo}`, label: c.label })
  opciones.push({ grupo: 'Valor', value: 'const', label: 'Valor fijo' })
  return opciones
}

function operandoAOpcionValue(op: OperandoForm): string {
  if (op.kind === 'ref') return `ref:${op.ref}:${op.salida ?? ''}`
  if (op.kind === 'campo') return `campo:${op.campo}`
  return 'const'
}

function opcionValueAOperando(value: string, valorConstPrevio: number): OperandoForm {
  if (value === 'const') return { kind: 'const', valor: valorConstPrevio }
  if (value.startsWith('campo:')) return { kind: 'campo', campo: value.slice('campo:'.length) as CampoPrecio }
  const [, ref, salida] = value.split(':')
  return { kind: 'ref', ref, salida: salida || undefined }
}

function OperandoSelector({
  operando, indicadores, onChange,
}: {
  operando: OperandoForm
  indicadores: IndicadorForm[]
  onChange: (op: OperandoForm) => void
}) {
  const opciones = opcionesOperando(indicadores)
  const value = operandoAOpcionValue(operando)
  return (
    <div className="flex items-center gap-1.5">
      <select
        value={value}
        onChange={e => onChange(opcionValueAOperando(e.target.value, operando.valor ?? 0))}
        className="bg-app-surface-2 border border-app-border rounded-lg px-2 py-1.5 text-caption text-app-text max-w-[9.5rem] truncate"
      >
        {opciones.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {operando.kind === 'const' && (
        <input
          type="number" value={operando.valor ?? 0}
          onChange={e => onChange({ kind: 'const', valor: Number(e.target.value) })}
          className="w-16 bg-app-surface-2 border border-app-border rounded-lg px-2 py-1.5 font-mono text-caption text-app-text"
        />
      )}
    </div>
  )
}

function BloqueCondiciones({
  titulo, combinador, filas, indicadores, onCambiarCombinador, onCambiarFilas,
}: {
  titulo: string
  combinador: 'y' | 'o'
  filas: FilaCondicion[]
  indicadores: IndicadorForm[]
  onCambiarCombinador: (c: 'y' | 'o') => void
  onCambiarFilas: (filas: FilaCondicion[]) => void
}) {
  return (
    <div className="bg-app-surface border border-app-border rounded-2xl p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="font-semibold text-caption text-app-text">{titulo}</div>
        {filas.length > 1 && (
          <Segmented
            options={[{ value: 'y', label: 'Y (todas)' }, { value: 'o', label: 'O (alguna)' }]}
            value={combinador}
            onChange={onCambiarCombinador}
          />
        )}
      </div>
      <div className="flex flex-col gap-2">
        {filas.map((fila, i) => (
          <div key={fila.id} className="flex items-center gap-1.5 flex-wrap">
            <OperandoSelector
              operando={fila.izq} indicadores={indicadores}
              onChange={op => onCambiarFilas(filas.map(f => f.id === fila.id ? { ...f, izq: op } : f))}
            />
            <select
              value={fila.op}
              onChange={e => onCambiarFilas(filas.map(f => f.id === fila.id ? { ...f, op: e.target.value as OpComparador } : f))}
              className="bg-app-surface-2 border border-app-border rounded-lg px-2 py-1.5 text-caption text-app-text"
            >
              {OPERADORES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <OperandoSelector
              operando={fila.der} indicadores={indicadores}
              onChange={op => onCambiarFilas(filas.map(f => f.id === fila.id ? { ...f, der: op } : f))}
            />
            <button
              onClick={() => onCambiarFilas(filas.filter(f => f.id !== fila.id))}
              className="text-app-text-faint shrink-0 ml-auto" aria-label="Quitar condición"
            >
              <Icon name="trash" className="w-3.5 h-3.5" />
            </button>
            {i < filas.length - 1 && <div className="w-full text-label text-app-text-faint uppercase">{combinador === 'y' ? 'y' : 'o'}</div>}
          </div>
        ))}
      </div>
      <button
        onClick={() => onCambiarFilas([...filas, { id: nuevoId('c'), op: 'mayor', izq: { ...OPERANDO_CIERRE }, der: { ...OPERANDO_CONST_0 } }])}
        className="mt-2 inline-flex items-center gap-1 text-label font-semibold text-app-gold"
      >
        <Icon name="plus" className="w-3 h-3" /> Agregar condición
      </button>
    </div>
  )
}

export default function EditorEstrategia({
  dslInicial, onCambiar, erroresValidacion,
}: {
  dslInicial: EstrategiaDsl
  onCambiar: (dsl: EstrategiaDsl) => void
  erroresValidacion?: string[]
}) {
  // `estado` es la única fuente de verdad mientras el editor está montado. Al elegir otro preset o
  // cargar una estrategia guardada, el padre re-monta este componente vía `key`, y el estado se
  // re-inicializa desde `dslInicial`. No re-sincronizamos con `dslInicial` en cada render: onCambiar
  // ya emite el DSL editado hacia arriba y hacerlo generaría un bucle infinito de renders.
  const [estado, setEstado] = useState<EstadoEstrategia>(() => estadoDeDsl(dslInicial))

  useEffect(() => {
    onCambiar(dslDeEstado(estado))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estado])

  function agregarIndicador(tipo: string) {
    const id = nuevoId(tipo.toLowerCase().slice(0, 3))
    setEstado(s => ({ ...s, indicadores: [...s.indicadores, { id, tipo, params: paramsPorDefecto(tipo) }] }))
  }

  function quitarIndicador(id: string) {
    setEstado(s => ({ ...s, indicadores: s.indicadores.filter(i => i.id !== id) }))
  }

  function cambiarParamIndicador(id: string, nombre: string, valor: number) {
    setEstado(s => ({
      ...s,
      indicadores: s.indicadores.map(i => i.id === id ? { ...i, params: { ...i.params, [nombre]: valor } } : i),
    }))
  }

  return (
    <div className="flex flex-col gap-3">
      {erroresValidacion && erroresValidacion.length > 0 && (
        <div className="bg-app-coral-soft border border-app-coral/40 rounded-xl px-3 py-2 text-caption text-app-coral">
          {erroresValidacion.map((e, i) => <div key={i}>{e}</div>)}
        </div>
      )}

      <div>
        <div className="font-semibold text-caption text-app-text mb-1.5">Indicadores</div>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {estado.indicadores.map(ind => (
            <div key={ind.id} className="flex items-center gap-1 bg-app-surface-2 border border-app-border rounded-lg px-2 py-1">
              <span className="font-mono text-label text-app-text">{ind.id} = {claveIndicador(ind.tipo, ind.params)}</span>
              {ESPEC_POR_TIPO[ind.tipo]?.params.map(p => (
                <input
                  key={p.nombre} type="number" min={p.min} max={p.max} step={p.step ?? 1}
                  value={ind.params[p.nombre] ?? p.default}
                  onChange={e => cambiarParamIndicador(ind.id, p.nombre, Number(e.target.value))}
                  className="w-12 bg-app-surface border border-app-border rounded px-1 font-mono text-label text-app-text"
                />
              ))}
              <button onClick={() => quitarIndicador(ind.id)} aria-label="Quitar indicador" className="text-app-text-faint">
                <Icon name="trash" className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {INDICADORES_UI.map(e => (
            <button
              key={e.tipo} onClick={() => agregarIndicador(e.tipo)}
              className="text-label font-semibold px-2 py-1 rounded-lg border border-app-border text-app-text-dim bg-app-surface"
            >
              + {e.label}
            </button>
          ))}
        </div>
      </div>

      <BloqueCondiciones
        titulo="Compra (entrada)" combinador={estado.entradaCombinador} filas={estado.entrada}
        indicadores={estado.indicadores}
        onCambiarCombinador={c => setEstado(s => ({ ...s, entradaCombinador: c }))}
        onCambiarFilas={filas => setEstado(s => ({ ...s, entrada: filas }))}
      />

      <BloqueCondiciones
        titulo="Venta (salida, opcional)" combinador={estado.salidaCombinador} filas={estado.salida}
        indicadores={estado.indicadores}
        onCambiarCombinador={c => setEstado(s => ({ ...s, salidaCombinador: c }))}
        onCambiarFilas={filas => setEstado(s => ({ ...s, salida: filas }))}
      />

      <div className="bg-app-surface border border-app-border rounded-2xl p-3">
        <div className="font-semibold text-caption text-app-text mb-2">Riesgo</div>
        <div className="grid grid-cols-2 gap-2">
          {([
            ['stop_loss_pct', 'Stop loss %'],
            ['take_profit_pct', 'Take profit %'],
            ['trailing_stop_pct', 'Trailing stop %'],
            ['max_barras', 'Máx. barras en posición'],
          ] as const).map(([campo, label]) => (
            <label key={campo} className="flex flex-col gap-1 text-label text-app-text-dim">
              {label}
              <input
                type="number"
                value={estado.riesgo[campo] ?? ''}
                onChange={e => setEstado(s => ({
                  ...s,
                  riesgo: { ...s.riesgo, [campo]: e.target.value === '' ? null : Number(e.target.value) },
                }))}
                placeholder="—"
                className="bg-app-surface-2 border border-app-border rounded-lg px-2 py-1.5 font-mono text-caption text-app-text"
              />
            </label>
          ))}
        </div>
      </div>

      <div className="bg-app-surface border border-app-border rounded-2xl p-3">
        <div className="font-semibold text-caption text-app-text mb-2">Ejecución</div>
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-label text-app-text-dim">
            Comisión por lado (%)
            <input
              type="number" min={0} max={5} step={0.1} value={estado.ejecucion.comision_pct}
              onChange={e => setEstado(s => ({ ...s, ejecucion: { ...s.ejecucion, comision_pct: Number(e.target.value) } }))}
              className="w-24 bg-app-surface-2 border border-app-border rounded-lg px-2 py-1.5 font-mono text-caption text-app-text"
            />
          </label>
          <div>
            <div className="text-label text-app-text-dim mb-1">Precio de ejecución</div>
            <Segmented
              options={[
                { value: 'cierre', label: 'Cierre' },
                { value: 'apertura_siguiente', label: 'Apertura siguiente (sin lookahead)' },
              ]}
              value={estado.ejecucion.precio_ejecucion}
              onChange={v => setEstado(s => ({
                ...s,
                ejecucion: { ...s.ejecucion, precio_ejecucion: v, demora_barras: v === 'apertura_siguiente' ? 1 : 0 },
              }))}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
