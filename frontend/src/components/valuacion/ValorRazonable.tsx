import { useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getValorRazonable, guardarSupuestosValor, restablecerSupuestosValor,
  type EscenarioClave, type EscenarioValor, type MetodoValor, type SupuestosValor, type ValorRazonable as ValorRazonableData,
} from '../../api'
import { qk } from '../../api/queryClient'
import Card from '../ui/Card'
import Button from '../ui/Button'
import QueryBoundary from '../ui/QueryBoundary'
import InfoTooltip from '../../help/components/InfoTooltip'
import ErrorBanner from '../../help/components/ErrorBanner'
import { parseApiError } from '../../help/errors/apiErrors'
import { Icon } from '../icons/Icons'
import { OrigenTag, formatMetrica } from './comun'

const ESCENARIOS: EscenarioClave[] = ['pesimista', 'base', 'optimista']

/** Precios de mercado (no importes de la cartera): no pasan por el modo privacidad. */
function precioTexto(v: number | null | undefined, moneda: string | null): string {
  if (v == null) return '—'
  return `${v.toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}${moneda ? ` ${moneda}` : ''}`
}

function pctTexto(v: number | null | undefined, conSigno = false): string {
  if (v == null) return '—'
  const t = (v * 100).toLocaleString('es-AR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
  return `${conSigno && v > 0 ? '+' : ''}${t} %`
}

const ESTADO_METODO: Record<MetodoValor['estado'], { palabra: string; clase: string }> = {
  usado: { palabra: 'Usado', clase: 'text-app-pos' },
  no_aplica: { palabra: 'No aplica', clase: 'text-app-text-faint' },
  falta: { palabra: 'Falta dato', clase: 'text-app-warn' },
  inestable: { palabra: 'Inestable', clase: 'text-app-warn' },
  excluido: { palabra: 'Excluido', clase: 'text-app-text-dim' },
}

const CONFIANZA: Record<ValorRazonableData['confianza'], string> = {
  alta: 'Confianza alta', media: 'Confianza media', baja: 'Confianza baja', sin_datos: 'Sin datos',
}

/** El precio de hoy sobre la recta del rango pesimista–optimista. La palabra dice lo mismo que la posición. */
function BarraRango({ v }: { v: ValorRazonableData }) {
  const esc = (c: EscenarioClave) => v.escenarios.find(e => e.clave === c)!
  const [pes, base, opt] = ESCENARIOS.map(c => esc(c).valor)
  const precio = v.precio ?? base
  const minimo = Math.min(pes, precio)
  const maximo = Math.max(opt, precio)
  const margen = (maximo - minimo) * 0.12 || 1
  const desde = minimo - margen
  const ancho = maximo + margen - desde
  const pos = (x: number) => `${((x - desde) / ancho) * 100}%`
  return (
    <div>
      <div className="relative h-8" role="img" aria-label={`Rango de ${precioTexto(pes, v.moneda)} a ${precioTexto(opt, v.moneda)}; precio actual ${precioTexto(v.precio, v.moneda)}`}>
        <div className="absolute top-1/2 -translate-y-1/2 h-2 rounded-full bg-app-surface-2 inset-x-0" />
        <div className="absolute top-1/2 -translate-y-1/2 h-2 rounded-full bg-app-accent-soft" style={{ left: pos(pes), width: `calc(${pos(opt)} - ${pos(pes)})` }} />
        <div className="absolute top-1/2 -translate-y-1/2 w-0.5 h-4 bg-app-accent -translate-x-1/2" style={{ left: pos(base) }} />
        <div className="absolute top-0 bottom-0 w-0.5 bg-app-text -translate-x-1/2" style={{ left: pos(precio) }} />
      </div>
      <div className="flex justify-between text-label text-app-text-faint mt-1 gap-2">
        <span>Pesimista {precioTexto(pes, null)}</span>
        <span>Base {precioTexto(base, null)}</span>
        <span>Optimista {precioTexto(opt, null)}</span>
      </div>
      <div className="text-caption text-app-text mt-1">
        <span className="inline-block w-0.5 h-3 bg-app-text align-middle mr-1.5" aria-hidden="true" />
        Precio actual: <span className="font-mono font-bold">{precioTexto(v.precio, v.moneda)}</span>
      </div>
    </div>
  )
}

/** Margen de seguridad y potencial, lado a lado, con la diferencia dicha en palabras. */
function MargenYPotencial({ e, moneda, precio }: { e: EscenarioValor; moneda: string | null; precio: number | null }) {
  return (
    <div>
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-xl bg-app-surface-2 p-3">
          <div className="text-label font-bold uppercase tracking-wide text-app-text-faint flex items-center gap-1">
            Margen de seguridad <InfoTooltip term="valor_razonable_margen" label="" />
          </div>
          <div className="text-metric font-bold font-mono text-app-text mt-0.5">{pctTexto(e.margen_seguridad)}</div>
          <div className="text-label text-app-text-faint">del valor ({precioTexto(e.valor, moneda)}) es colchón</div>
        </div>
        <div className="rounded-xl bg-app-surface-2 p-3">
          <div className="text-label font-bold uppercase tracking-wide text-app-text-faint">Potencial</div>
          <div className="text-metric font-bold font-mono text-app-text mt-0.5">{pctTexto(e.potencial, true)}</div>
          <div className="text-label text-app-text-faint">
            {e.potencial != null && e.potencial >= 0 ? 'lo que subiría' : 'lo que bajaría'} desde {precioTexto(precio, moneda)} hasta el valor base
          </div>
        </div>
      </div>
      <p className="text-label text-app-text-faint mt-1.5">
        Son dos medidas de la misma brecha: el margen la mide contra el valor y el potencial contra el precio. No se restan ni se comparan entre sí.
      </p>
    </div>
  )
}

function FilaMetodo({ m, moneda }: { m: MetodoValor; moneda: string | null }) {
  const e = ESTADO_METODO[m.estado]
  const veces = (x: number | null | undefined) => (x == null ? '—' : formatMetrica(x, 'x'))
  return (
    <>
      <tr className="border-t border-app-border">
        <td className="sticky left-0 bg-app-surface pr-3 py-1.5 align-top">
          <div className="font-semibold text-app-text">{m.nombre}</div>
          <div className="flex gap-1 mt-0.5 flex-wrap">
            <OrigenTag origen={m.origen} />
            {!m.decide && <span className="text-label text-app-text-faint">sólo apoya</span>}
            {m.manual && <span className="text-label text-app-accent">fijado por vos</span>}
          </div>
        </td>
        <td className="text-right px-2 py-1.5 font-mono whitespace-nowrap">{veces(m.multiplo_propio)}</td>
        <td className="text-right px-2 py-1.5 font-mono whitespace-nowrap">{veces(m.referencias.base)}</td>
        <td className="text-right px-2 py-1.5 font-mono whitespace-nowrap">
          {m.valores.base != null ? precioTexto(m.valores.base, null) : '—'}
        </td>
        <td className={`text-right pl-2 py-1.5 font-semibold whitespace-nowrap ${e.clase}`}>{e.palabra}</td>
      </tr>
      {m.motivo && (
        <tr>
          <td colSpan={5} className="pb-1.5 text-label text-app-text-faint whitespace-normal min-w-[260px]">{m.motivo}{m.estado === 'inestable' && m.valores.base != null ? ` (${precioTexto(m.valores.base, moneda)})` : ''}</td>
        </tr>
      )}
    </>
  )
}

/** Ajuste general, métodos excluidos y múltiplo manual. Todo opcional; vacío = mediana de los pares. */
function EditorSupuestos({ v, ticker, onGuardado }: { v: ValorRazonableData; ticker: string; onGuardado: (nuevo: ValorRazonableData) => void }) {
  const [ajuste, setAjuste] = useState(String(v.supuestos.ajuste_pct || ''))
  const [excluir, setExcluir] = useState<string[]>(v.supuestos.excluir)
  const [manuales, setManuales] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(v.supuestos.multiplos).map(([k, x]) => [k, String(x)])),
  )
  const editables = v.metodos.filter(m => m.estado !== 'no_aplica')

  const armar = (): SupuestosValor => ({
    ajuste_pct: ajuste.trim() === '' ? 0 : Number(ajuste.replace(',', '.')),
    excluir,
    multiplos: Object.fromEntries(
      Object.entries(manuales).filter(([k, x]) => x.trim() !== '' && !excluir.includes(k)).map(([k, x]) => [k, Number(x.replace(',', '.'))]),
    ),
  })
  const guardar = useMutation({ mutationFn: () => guardarSupuestosValor(ticker, armar()), onSuccess: onGuardado })
  const restablecer = useMutation({
    mutationFn: () => restablecerSupuestosValor(ticker),
    onSuccess: nuevo => { setAjuste(''); setExcluir([]); setManuales({}); onGuardado(nuevo) },
  })
  const ajusteInvalido = ajuste.trim() !== '' && Number.isNaN(Number(ajuste.replace(',', '.')))

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-app-border p-3">
      <p className="text-caption text-app-text-dim">
        Tus supuestos cambian el resultado. Sin tocar nada, el valor sale de la mediana de los pares. <InfoTooltip term="valor_razonable_supuestos" label="" />
      </p>
      <label className="flex flex-col gap-1">
        <span className="text-label font-bold uppercase tracking-wide text-app-text-faint">Ajuste general sobre los múltiplos de referencia (%)</span>
        <input
          inputMode="decimal" value={ajuste} onChange={e => setAjuste(e.target.value)} placeholder="0 (ej.: -10 = descuento del 10 %)"
          className="w-full h-10 px-3 rounded-xl bg-app-surface-2 border border-app-border text-body text-app-text"
        />
      </label>
      <div className="flex flex-col gap-2">
        <span className="text-label font-bold uppercase tracking-wide text-app-text-faint">Por método</span>
        {editables.map(m => {
          const fuera = excluir.includes(m.clave)
          return (
            <div key={m.clave} className="flex items-center gap-2">
              <label className="flex items-center gap-1.5 flex-1 min-w-0 text-caption text-app-text">
                <input
                  type="checkbox" checked={!fuera}
                  onChange={() => setExcluir(x => (fuera ? x.filter(c => c !== m.clave) : [...x, m.clave]))}
                />
                <span className="truncate">{m.nombre}</span>
              </label>
              <input
                inputMode="decimal" disabled={fuera} aria-label={`Múltiplo fijo de ${m.nombre}`}
                value={manuales[m.clave] ?? ''} onChange={e => setManuales(x => ({ ...x, [m.clave]: e.target.value }))}
                placeholder={m.referencias.base != null ? `pares: ${m.referencias.base.toFixed(1)}x` : 'múltiplo fijo'}
                className="w-32 h-9 px-2 rounded-xl bg-app-surface-2 border border-app-border text-caption text-app-text disabled:opacity-50"
              />
            </div>
          )
        })}
      </div>
      {(guardar.error || restablecer.error) && <ErrorBanner error={parseApiError(guardar.error ?? restablecer.error)} />}
      <div className="grid grid-cols-2 gap-2">
        <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={ajusteInvalido}>Aplicar</Button>
        <Button variant="outline" onClick={() => restablecer.mutate()} loading={restablecer.isPending} disabled={v.supuestos.por_defecto}>Restablecer</Button>
      </div>
    </div>
  )
}

/**
 * Valor razonable y escenarios con los múltiplos de los pares, con el margen de seguridad separado del
 * potencial. La consulta arma el universo completo, así que sólo corre cuando se abre la tarjeta.
 */
export default function ValorRazonable({ ticker }: { ticker: string }) {
  const [abierto, setAbierto] = useState(false)
  const [editando, setEditando] = useState(false)
  const queryClient = useQueryClient()
  const clave = qk.de('valuacion-valor', ticker)

  const query = useQuery({ queryKey: clave, queryFn: () => getValorRazonable(ticker), enabled: abierto, placeholderData: keepPreviousData })
  const v = query.data
  const base = v?.escenarios.find(e => e.clave === 'base')

  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <div className="text-strong font-bold text-app-text flex items-center gap-1">
          Valor razonable <InfoTooltip term="valor_razonable_que_es" label="" />
        </div>
        <button onClick={() => setAbierto(x => !x)} className="text-caption font-bold text-app-accent" aria-expanded={abierto}>
          {abierto ? 'Cerrar' : 'Calcular'}
        </button>
      </div>
      {!abierto && (
        <p className="text-caption text-app-text-dim mt-1">
          A qué precio cotizaría con los múltiplos que hoy pagan sus pares: tres escenarios, con el margen de seguridad separado del
          potencial y los supuestos a la vista.
        </p>
      )}

      {abierto && (
        <div className="mt-3">
          <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
            {v && (
              <div className="flex flex-col gap-4">
                {v.estado === 'ok' && base ? (
                  <>
                    <div>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-1">
                        <span className="text-label font-bold uppercase tracking-wide text-app-text-faint flex items-center gap-1">
                          Rango de valor <InfoTooltip term="valor_razonable_escenarios" label="" />
                        </span>
                        <span className={`text-label font-semibold ${v.confianza === 'baja' ? 'text-app-warn' : 'text-app-text-dim'}`}>
                          · {CONFIANZA[v.confianza]}
                        </span>
                      </div>
                      <BarraRango v={v} />
                    </div>
                    <p className="text-body text-app-text">{v.lectura_texto}</p>
                    <MargenYPotencial e={base} moneda={v.moneda} precio={v.precio} />
                    {v.convergen === false && (
                      <div className="flex gap-1.5 items-start text-caption text-app-warn">
                        <Icon name="alert" className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                        <span>Los métodos no convergen: dan valores muy distintos entre sí ({v.dispersion?.toFixed(1).replace('.', ',')} veces). Tomá el rango como orientativo.</span>
                      </div>
                    )}
                    <details>
                      <summary className="text-caption font-bold text-app-text-dim cursor-pointer">Cómo se decidió</summary>
                      <p className="text-caption text-app-text-dim mt-1.5">{v.regla_lectura}.</p>
                      <p className="text-caption text-app-text-dim mt-1.5">{v.regla_confianza}.</p>
                    </details>
                  </>
                ) : (
                  <div className="flex gap-1.5 items-start text-caption text-app-warn">
                    <Icon name="alert" className="w-3.5 h-3.5 mt-0.5 shrink-0" /> <span>{v.mensaje}</span>
                  </div>
                )}

                {v.metodos.length > 0 && (
                  <div>
                    <div className="text-strong font-bold text-app-text mb-1">Métodos ({v.n_pares} pares con datos)</div>
                    <div className="overflow-x-auto -mx-4 px-4">
                      <table className="text-caption w-full">
                        <thead>
                          <tr className="text-label text-app-text-faint">
                            <th className="sticky left-0 bg-app-surface text-left font-semibold pr-3 pb-1">Método</th>
                            <th className="text-right font-semibold px-2 pb-1">Propio</th>
                            <th className="text-right font-semibold px-2 pb-1">Pares</th>
                            <th className="text-right font-semibold px-2 pb-1">Valor</th>
                            <th className="text-right font-semibold pl-2 pb-1">Estado</th>
                          </tr>
                        </thead>
                        <tbody>{v.metodos.map(m => <FilaMetodo key={m.clave} m={m} moneda={v.moneda} />)}</tbody>
                      </table>
                    </div>
                  </div>
                )}

                {v.faltantes.length > 0 && (
                  <div>
                    <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">Qué falta</div>
                    <ul className="flex flex-col gap-1">
                      {v.faltantes.map(f => <li key={f} className="text-caption text-app-text-dim">· {f}</li>)}
                    </ul>
                  </div>
                )}

                {v.estado !== 'no_aplica' && v.estado !== 'sin_datos' && (
                  editando
                    ? <EditorSupuestos v={v} ticker={ticker} onGuardado={nuevo => { queryClient.setQueryData(clave, nuevo); setEditando(false) }} />
                    : (
                      <Button variant="outline" onClick={() => setEditando(true)}>
                        {v.supuestos.por_defecto ? 'Editar supuestos' : 'Editar supuestos (hay cambios tuyos)'}
                      </Button>
                    )
                )}

                {v.analistas && (
                  <div className="rounded-xl border border-app-border p-3">
                    <div className="text-label font-bold uppercase tracking-wide text-app-text-faint flex items-center gap-1">
                      Referencia: estimación de analistas (Yahoo) <InfoTooltip term="valor_razonable_analistas" label="" />
                    </div>
                    <div className="text-caption text-app-text mt-1">
                      Precio objetivo promedio <span className="font-mono font-bold">{precioTexto(v.analistas.media, v.moneda)}</span>
                      {v.analistas.minimo != null && v.analistas.maximo != null && (
                        <> (entre {precioTexto(v.analistas.minimo, null)} y {precioTexto(v.analistas.maximo, null)})</>
                      )}
                      {v.analistas.n != null && <> · {v.analistas.n} analistas</>}
                    </div>
                    <div className="text-label text-app-text-faint">No entra en el valor razonable: sólo sirve para contrastar.</div>
                  </div>
                )}

                <details>
                  <summary className="text-caption font-bold text-app-text-dim cursor-pointer">Límites de este cálculo</summary>
                  <ul className="flex flex-col gap-1 mt-1.5">
                    {[v.salvedad, ...v.limites].map(t => <li key={t} className="text-caption text-app-text-dim">· {t}</li>)}
                  </ul>
                </details>
                <p className="text-label text-app-text-faint text-center">
                  Es una estimación relativa a sus pares para ordenar ideas; no es una recomendación de compra o venta.
                </p>
              </div>
            )}
          </QueryBoundary>
        </div>
      )}
    </Card>
  )
}
