import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { getComparador, type AlternativaComparador } from '../../api'
import { qk } from '../../api/queryClient'
import Card from '../ui/Card'
import Modal from '../ui/Modal'
import Button from '../ui/Button'
import QueryBoundary from '../ui/QueryBoundary'
import InfoTooltip from '../../help/components/InfoTooltip'
import SelectorInstrumento from '../inversiones/SelectorInstrumento'
import FuerzaRelativaChart from '../charts/FuerzaRelativaChart'
import { Icon } from '../icons/Icons'
import { ComparabilidadBadge, formatTamano } from './comun'
import TablaComparativa from './TablaComparativa'
import ConclusionComparativa from './ConclusionComparativa'

const MAX_ALTERNATIVAS = 6   // el mismo tope que el backend (`comparador_engine.MAX_ALTERNATIVAS`)

const TONO_CRITERIO = {
  favorable: 'bg-app-pos', neutro: 'bg-app-warn', desfavorable: 'bg-app-neg', sin_dato: 'bg-app-text-faint',
} as const

/** Por qué una alternativa es (o no) comparable: cada criterio con su estado y su texto. */
function FilaAlternativa({ a, accion }: { a: AlternativaComparador; accion: React.ReactNode }) {
  const [abierta, setAbierta] = useState(false)
  return (
    <div className="border-b border-app-border last:border-b-0 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <button onClick={() => setAbierta(v => !v)} className="min-w-0 flex-1 text-left" aria-expanded={abierta}>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span className="text-body font-bold font-mono text-app-text">{a.ticker_base}</span>
            <ComparabilidadBadge nivel={a.nivel} />
            {a.a_mano && <span className="text-label text-app-accent">· a mano</span>}
            {a.origen === 'sugerida' && !a.en_grupo && <span className="text-label text-app-text-faint">· fuera de tu grupo</span>}
          </div>
          <div className="text-label text-app-text-faint truncate">
            {a.nombre ?? '—'} · {formatTamano(a.tamano_usd)}{a.region ? ` · ${a.region}` : ''}
          </div>
        </button>
        {accion}
      </div>
      {abierta && (
        <div className="mt-2 flex flex-col gap-1.5">
          <div className="text-caption text-app-text-dim">{a.resumen}</div>
          <ul className="flex flex-col gap-1">
            {a.criterios.map(c => (
              <li key={c.clave} className="text-caption text-app-text-dim flex gap-1.5 items-start">
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 mt-1.5 ${TONO_CRITERIO[c.estado]}`} aria-hidden="true" />
                <span><span className="text-app-text font-semibold">{c.nombre}:</span> {c.texto}</span>
              </li>
            ))}
          </ul>
          {a.notas.map(n => <div key={n} className="text-label text-app-accent">{n}</div>)}
        </div>
      )}
    </div>
  )
}

/**
 * "¿Qué compraría en su lugar?": el instrumento contra alternativas comparables, incluso de afuera de su
 * grupo de pares. La consulta arma el universo completo, así que sólo corre cuando se abre la tarjeta.
 * `con` es la elección del usuario (null = su grupo de pares); no se guarda: el grupo persistente se
 * edita en "Pares".
 */
export default function ComparadorAlternativas({ ticker }: { ticker: string }) {
  const [abierto, setAbierto] = useState(false)
  const [con, setCon] = useState<string[] | null>(null)
  const [buscando, setBuscando] = useState(false)

  const query = useQuery({
    queryKey: qk.de('valuacion-comparador', ticker, (con ?? []).join(',')),
    queryFn: () => getComparador(ticker, con ?? []),
    enabled: abierto,
    placeholderData: keepPreviousData,
  })
  const c = query.data
  const seleccion = c?.seleccion ?? []
  const lleno = seleccion.length >= MAX_ALTERNATIVAS

  const sumar = (t: string) => setCon([...seleccion, t.toUpperCase()].slice(0, MAX_ALTERNATIVAS))
  const quitar = (t: string) => {
    const resto = seleccion.filter(x => x !== t)
    setCon(resto.length ? resto : null)
  }

  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <div className="text-strong font-bold text-app-text flex items-center gap-1">
          ¿Qué compraría en su lugar? <InfoTooltip term="comparador_que_es" label="" />
        </div>
        <button onClick={() => setAbierto(v => !v)} className="text-caption font-bold text-app-accent" aria-expanded={abierto}>
          {abierto ? 'Cerrar' : 'Comparar'}
        </button>
      </div>
      {!abierto && (
        <p className="text-caption text-app-text-dim mt-1">
          Compará este instrumento con alternativas comparables, incluso de afuera de su grupo de pares, con una conclusión
          que explica por qué podría merecer un múltiplo mayor o menor.
        </p>
      )}

      {abierto && (
        <div className="mt-3">
          <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
            {c && (
              <div className="flex flex-col gap-4">
                {c.estado === 'sin_datos' ? (
                  <p className="text-caption text-app-text-dim">{c.mensaje}</p>
                ) : (
                  <>
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <div className="text-label font-bold uppercase tracking-wide text-app-text-faint flex items-center gap-1">
                          Se compara contra ({seleccion.length}) <InfoTooltip term="comparador_comparabilidad" label="" />
                        </div>
                        {c.elegido_por_usuario && (
                          <button onClick={() => setCon(null)} className="text-caption font-bold text-app-accent">Volver a mi grupo de pares</button>
                        )}
                      </div>
                      {!c.elegido_por_usuario && (
                        <p className="text-label text-app-text-faint mb-1">Sin elegir, se usa tu grupo de pares (hasta 4, los más comparables).</p>
                      )}
                      {c.alternativas.length === 0 && <p className="text-caption text-app-text-dim">Todavía no hay alternativas elegidas.</p>}
                      {c.alternativas.map(a => (
                        <FilaAlternativa key={a.ticker_base} a={a} accion={
                          <button onClick={() => quitar(a.ticker_base)} aria-label={`Quitar ${a.ticker_base}`} className="p-1.5 shrink-0">
                            <Icon name="close" className="w-4 h-4 text-app-text-dim" />
                          </button>
                        } />
                      ))}
                    </div>

                    {c.estado === 'insuficiente' && (
                      <div className="flex gap-1.5 items-start text-caption text-app-warn">
                        <Icon name="alert" className="w-3.5 h-3.5 mt-0.5 shrink-0" /> <span>{c.mensaje} <InfoTooltip term="comparador_minimo" label="" /></span>
                      </div>
                    )}

                    {c.sugeridas.length > 0 && !lleno && (
                      <div>
                        <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">Sugeridas</div>
                        {c.sugeridas.map(a => (
                          <FilaAlternativa key={a.ticker_base} a={a} accion={
                            <button
                              onClick={() => sumar(a.ticker_base)}
                              className="flex items-center gap-1 text-caption font-bold text-app-accent shrink-0 p-1.5"
                              aria-label={`Sumar ${a.ticker_base}`}
                            >
                              <Icon name="plus" className="w-3.5 h-3.5" /> Sumar
                            </button>
                          } />
                        ))}
                      </div>
                    )}

                    <Button variant="outline" icon={<Icon name="search" className="w-4 h-4" />} disabled={lleno} onClick={() => setBuscando(true)}>
                      {lleno ? `Máximo ${MAX_ALTERNATIVAS} alternativas` : 'Buscar otra alternativa'}
                    </Button>

                    {c.rechazadas.length > 0 && (
                      <details>
                        <summary className="text-caption font-bold text-app-text-dim cursor-pointer">No entran en la comparación ({c.rechazadas.length})</summary>
                        <ul className="flex flex-col gap-1.5 mt-1.5">
                          {c.rechazadas.map(r => (
                            <li key={r.ticker_base} className="text-caption text-app-text-dim">
                              <span className="font-mono font-bold text-app-text">{r.ticker_base}</span> — {r.motivo}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}

                    {c.tabla && c.tabla.filas.length > 0 && <TablaComparativa tabla={c.tabla} />}
                    {c.conclusion && <ConclusionComparativa c={c} />}

                    {c.fuerza_relativa.length > 1 && seleccion.length > 0 && (
                      <div>
                        <div className="text-strong font-bold text-app-text mb-2">Precio vs. las alternativas</div>
                        <FuerzaRelativaChart key={seleccion.join(',')} puntos={c.fuerza_relativa} ticker={c.ticker_base} pares={seleccion} />
                      </div>
                    )}
                  </>
                )}
                <p className="text-label text-app-text-faint text-center">
                  Es un análisis relativo para encontrar candidatos para mirar; no es una recomendación de compra o venta.
                </p>
              </div>
            )}
          </QueryBoundary>
        </div>
      )}

      <Modal open={buscando} onClose={() => setBuscando(false)} title="Buscar una alternativa">
        <SelectorInstrumento
          yaSeguidos={new Set([ticker.toUpperCase(), ...seleccion])}
          etiquetaYaElegido="Ya está"
          onElegir={inst => { sumar(inst.simbolo); setBuscando(false) }}
        />
      </Modal>
    </Card>
  )
}
