import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { agregarAWatchlist, getAnalisisDecision, type AnalisisDecision as Analisis, type DimensionEval, type EscenarioEntrada } from '../../api'
import { qk } from '../../api/queryClient'
import { useInversionesContext } from '../../context/InversionesContext'
import ScreenHeader from '../../components/layout/ScreenHeader'
import Card from '../../components/ui/Card'
import Button from '../../components/ui/Button'
import Modal from '../../components/ui/Modal'
import Chip from '../../components/ui/Chip'
import QueryBoundary from '../../components/ui/QueryBoundary'
import { SkeletonCard } from '../../components/ui/Skeleton'
import EmptyState from '../../components/ui/EmptyState'
import SelectorInstrumento from '../../components/inversiones/SelectorInstrumento'
import DiagnosticoCard from '../../components/valuacion/DiagnosticoCard'
import ValorRazonable from '../../components/valuacion/ValorRazonable'
import InfoTooltip from '../../help/components/InfoTooltip'
import { parseApiError } from '../../help/errors/apiErrors'
import ErrorBanner from '../../help/components/ErrorBanner'
import SimuladorDecision from '../../components/decisiones/SimuladorDecision'
import GuardarDecision from '../../components/decisiones/GuardarDecision'
import {
  Banderas, BarraDimension, Conclusion, ConclusionBadge, DetalleDimension, Fuentes, Lista, Observaciones, Orden, Seccion,
  num, pct, precio,
} from '../../components/decisiones/comun'

const MAX_ALTERNATIVAS = 6

/** Análisis completo de un activo con tus preferencias. Resumen primero; cada sección se abre a pedido. */
export default function AnalisisDecision() {
  const { ticker = '' } = useParams()
  const navigate = useNavigate()
  const { carteraSeleccionada } = useInversionesContext()
  const [con, setCon] = useState<string[]>([])
  const [guardarAbierto, setGuardarAbierto] = useState(false)
  const t = ticker.toUpperCase()
  const q = useQuery({
    queryKey: qk.de('decision-analisis', t, carteraSeleccionada, con.join(',')),
    queryFn: () => getAnalisisDecision(t, { cartera: carteraSeleccionada, con }),
  })
  const a = q.data

  return (
    <div className="pb-4">
      <ScreenHeader title={`Analizar ${t}`} onBack={() => navigate(-1)} />
      <QueryBoundary isLoading={q.isLoading} error={q.error} onRetry={() => void q.refetch()}
                     fallback={<div className="flex flex-col gap-3"><SkeletonCard lineas={6} /><SkeletonCard lineas={4} /></div>}>
        {a && a.estado !== 'ok' && <EmptyState ilustracion="lupa" title="No se puede analizar" description={a.mensaje} />}
        {a && a.estado === 'ok' && a.evaluacion && (
          <div className="flex flex-col gap-3">
            <Encabezado a={a} />
            <Resumen a={a} onGuardar={() => setGuardarAbierto(true)} />
            <Seccion titulo="Datos y fecha de actualización" resumen={<ResumenFuentes a={a} />}>
              <Fuentes fuentes={a.fuentes} />
              {Object.entries(a.secciones).filter(([, s]) => s.estado !== 'ok').map(([k, s]) => (
                <p key={k} className="text-label text-app-warn">{k}: {s.motivo}</p>
              ))}
              <p className="text-label text-app-text-faint">
                Reglas: evaluación v{a.versiones.evaluacion}, diagnóstico v{a.versiones.diagnostico}, comparador v{a.versiones.comparador ?? '—'},
                valor razonable v{a.versiones.valor_razonable ?? '—'}, escenarios v{a.versiones.escenarios}.
              </p>
            </Seccion>
            <Seccion titulo="Fortalezas y debilidades" abiertaInicial>
              <div><div className="text-label font-bold uppercase text-app-pos mb-1">A favor</div><Lista items={a.fortalezas} vacio="Sin factores a favor con los datos disponibles." /></div>
              <div><div className="text-label font-bold uppercase text-app-neg mb-1">En contra</div><Lista items={a.debilidades} vacio="Sin factores en contra con los datos disponibles." /></div>
            </Seccion>
            <Seccion titulo="Fundamentales" termino="decisiones_fundamentales" resumen={<BarraDimension d={dim(a, 'fundamentales')} compacta />}>
              <DetalleDimension d={dim(a, 'fundamentales')} />
              {a.diagnostico && <DiagnosticoCard diagnostico={a.diagnostico} fechaDato={a.fuentes[0]?.fecha ?? null} />}
            </Seccion>
            <Seccion titulo="Valoración" termino="decisiones_valoracion" resumen={<BarraDimension d={dim(a, 'valoracion')} compacta />}
                     estado={a.secciones.valor_razonable}>
              <DetalleDimension d={dim(a, 'valoracion')} />
              {a.valor_razonable?.estado === 'ok' && (
                <div className="grid grid-cols-3 gap-2">
                  {a.valor_razonable.escenarios.map(e => (
                    <div key={e.clave} className="rounded-xl bg-app-surface-2 p-2 text-center">
                      <div className="text-label text-app-text-faint">{e.nombre}</div>
                      <div className="text-caption font-mono tabular-nums text-app-text">{precio(e.valor, a.valor_razonable!.moneda)}</div>
                    </div>
                  ))}
                </div>
              )}
              <ValorRazonable ticker={a.ticker} />
            </Seccion>
            <Tecnico a={a} />
            <Seccion titulo="Riesgos" termino="decisiones_riesgo" resumen={<BarraDimension d={dim(a, 'riesgo')} compacta />}>
              <DetalleDimension d={dim(a, 'riesgo')} />
              <Banderas banderas={a.evaluacion.banderas} />
              <div>
                <div className="text-label font-bold uppercase text-app-text-faint mb-1 flex items-center gap-1">Encaje con tu cartera <InfoTooltip term="decisiones_encaje" label="" /></div>
                <DetalleDimension d={dim(a, 'encaje')} />
                {a.encaje && !a.encaje.sin_cartera && <Observaciones items={a.encaje.observaciones} />}
              </div>
            </Seccion>
            <Alternativas a={a} con={con} setCon={setCon} />
            <Escenarios a={a} />
            {a.conclusion && (
              <Seccion titulo="Conclusión" termino="decisiones_conclusion" abiertaInicial
                       resumen={<ConclusionBadge tipo={a.conclusion.tipo} titulo={a.conclusion.titulo} />}>
                <Conclusion c={a.conclusion} />
              </Seccion>
            )}
            <SimuladorDecision iniciales={[{ ticker: a.ticker, monto: String(Math.round(a.encaje?.monto_ref_usd ?? 1000)) }]} />
            <Button onClick={() => setGuardarAbierto(true)}>Guardar decisión</Button>
            <GuardarDecision abierto={guardarAbierto} onClose={() => setGuardarAbierto(false)} modo="oportunidad" ticker={a.ticker}
                             cartera={carteraSeleccionada} con={con} alternativas={(a.alternativas?.items ?? []).map(x => x.ticker)} />
          </div>
        )}
      </QueryBoundary>
    </div>
  )
}

function dim(a: Analisis, clave: string): DimensionEval {
  return a.evaluacion!.dimensiones.find(d => d.clave === clave)!
}

function Encabezado({ a }: { a: Analisis }) {
  const c = a.clasificacion
  return (
    <div>
      <div className="text-title font-bold text-app-text">{a.ticker} <span className="text-body font-normal text-app-text-dim">{a.nombre}</span></div>
      <div className="text-label text-app-text-faint">
        {[c.tipo, c.sector, c.industria, c.pais].filter(Boolean).join(' · ')} · análisis del {a.fecha_analisis}
        {a.cartera ? ` · cartera ${a.cartera}` : ' · consolidado'}
      </div>
    </div>
  )
}

function Resumen({ a, onGuardar }: { a: Analisis; onGuardar: () => void }) {
  const ev = a.evaluacion!
  return (
    <Card>
      <div className="text-label font-bold uppercase text-app-text-faint mb-2">Resumen</div>
      <Orden evaluacion={ev} />
      <div className="flex flex-col gap-1.5 mt-3">
        {ev.dimensiones.map(d => <BarraDimension key={d.clave} d={d} />)}
      </div>
      {ev.banderas.length > 0 && (
        <div className="mt-3">
          <div className="text-label font-bold uppercase text-app-text-faint mb-1 flex items-center gap-1">Banderas <InfoTooltip term="decisiones_banderas" label="" /></div>
          <Banderas banderas={ev.banderas} />
        </div>
      )}
      {a.conclusion && <div className="mt-3"><ConclusionBadge tipo={a.conclusion.tipo} titulo={a.conclusion.titulo} /></div>}
      {a.resumen.length > 0 && <div className="mt-2"><Lista items={a.resumen.map(f => f.texto)} /></div>}
      <div className="flex gap-2 mt-3">
        <Button variant="outline" onClick={onGuardar}>Guardar decisión</Button>
      </div>
    </Card>
  )
}

function ResumenFuentes({ a }: { a: Analisis }) {
  const viejas = a.fuentes.filter(f => f.estado !== 'ok')
  return (
    <p className="text-caption text-app-text-dim">
      Fundamentales del {a.fuentes[0]?.fecha ?? '—'}.{' '}
      {viejas.length ? `${viejas.length} fuente(s) faltan o están desactualizadas.` : 'Todas las fuentes al día.'}
    </p>
  )
}

function Tecnico({ a }: { a: Analisis }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const agregar = useMutation({
    mutationFn: () => agregarAWatchlist({ ticker: a.ticker }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.watchlist })
      void queryClient.invalidateQueries({ queryKey: qk.de('decision-analisis') })
    },
  })
  const tec = a.tecnico
  return (
    <Seccion titulo="Análisis técnico" termino="decisiones_tecnico" resumen={<BarraDimension d={dim(a, 'tecnico')} compacta />}>
      <DetalleDimension d={dim(a, 'tecnico')} />
      {tec ? (
        <ul className="text-caption text-app-text flex flex-col gap-0.5">
          <li>Último cierre: {precio(tec.ultimo_cierre, tec.moneda)} ({tec.fecha}, serie {tec.variante}).</li>
          {tec.soporte && <li>Soporte: {precio(tec.soporte.precio, tec.moneda)} ({num(tec.soporte.distancia_pct, 1)} %, {tec.soporte.toques} toques).</li>}
          {tec.resistencia && <li>Resistencia: {precio(tec.resistencia.precio, tec.moneda)} ({num(tec.resistencia.distancia_pct, 1)} %).</li>}
          {tec.atr != null && <li className="flex items-center gap-1">ATR(14): {precio(tec.atr, tec.moneda)} <InfoTooltip term="decisiones_atr" label="" /></li>}
        </ul>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-caption text-app-text-dim">Sin serie diaria: el técnico se calcula para activos de tu cartera o tu watchlist.</p>
          <Button variant="outline" onClick={() => agregar.mutate()} loading={agregar.isPending}>Agregar a la watchlist</Button>
          {agregar.isSuccess && <p className="text-label text-app-text-faint">Agregado. La serie se baja en el próximo refresco de precios.</p>}
          {agregar.error && <ErrorBanner error={parseApiError(agregar.error)} />}
        </div>
      )}
      {tec && <Button variant="ghost" onClick={() => navigate(`/analisis-tecnico?ticker=${encodeURIComponent(a.ticker)}`)}>Abrir el gráfico</Button>}
    </Seccion>
  )
}

function Alternativas({ a, con, setCon }: { a: Analisis; con: string[]; setCon: (c: string[]) => void }) {
  const [editar, setEditar] = useState(false)
  const alt = a.alternativas
  const obj = alt?.objetivo_en_grupo
  const filas = obj ? [{ ticker: obj.ticker, nombre: a.nombre, evaluacion: obj.evaluacion, comparabilidad: 'el activo', diferencias: [] as { texto: string }[] }, ...(alt?.items ?? [])] : []
  return (
    <Seccion titulo="Comparación con alternativas" termino="decisiones_alternativas" estado={a.secciones.alternativas}
             resumen={<p className="text-caption text-app-text-dim">{alt?.items.length ? `${alt.items.length} alternativas: ${alt.items.map(x => x.ticker).join(', ')}.` : alt?.mensaje || 'Sin alternativas comparables.'}</p>}>
      {filas.length > 0 ? (
        <div className="overflow-x-auto -mx-4 px-4">
          <table className="text-caption w-full">
            <thead>
              <tr className="text-label text-app-text-faint">
                <th className="text-left font-semibold pb-1 pr-2">Activo</th>
                <th className="text-right font-semibold px-1 pb-1">Orden</th>
                {['Fund.', 'Val.', 'Riesgo', 'Técn.', 'Encaje'].map(h => <th key={h} className="text-right font-semibold px-1 pb-1">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {filas.map(f => (
                <tr key={f.ticker} className={`border-t border-app-border ${f.ticker === obj?.ticker ? 'bg-app-accent-soft' : ''}`}>
                  <td className="py-1.5 pr-2">
                    <div className="font-semibold text-app-text">{f.ticker}</div>
                    <div className="text-label text-app-text-faint">{f.comparabilidad}</div>
                  </td>
                  <td className="text-right px-1 font-mono tabular-nums font-bold">{f.evaluacion.orden.puntaje != null ? num(f.evaluacion.orden.puntaje) : '—'}</td>
                  {f.evaluacion.dimensiones.map(d => (
                    <td key={d.clave} className="text-right px-1 font-mono tabular-nums text-app-text-dim">{d.puntaje != null ? num(d.puntaje) : d.estado === 'no_aplica' ? 'n/a' : '—'}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="text-caption text-app-text-dim">{alt?.mensaje || 'No hay alternativas comparables suficientes.'}</p>}
      {(alt?.items ?? []).map(x => x.diferencias.length > 0 && (
        <div key={x.ticker}>
          <div className="text-label font-bold text-app-text">{x.ticker} frente a {a.ticker_base}</div>
          <Lista items={x.diferencias.map(d => d.texto)} />
          {x.evaluacion.banderas.length > 0 && <p className="text-label text-app-warn">⚠ {x.evaluacion.banderas.map(b => b.texto).join(' · ')}</p>}
        </div>
      ))}
      {alt?.metodo && <p className="text-label text-app-text-faint">Método: {alt.metodo}. Robustez (ganador por enfoque): {Object.entries(alt.robustez).map(([k, v]) => `${k} ${v ?? '—'}`).join(', ')}.</p>}
      {alt?.advertencias_fechas.map(w => <p key={w} className="text-label text-app-warn">⚠ {w}</p>)}
      {alt?.excluidas.map(e => <p key={e.ticker} className="text-label text-app-text-faint">{e.ticker}: {e.motivo}</p>)}
      {(a.comparador?.rechazadas ?? []).length > 0 && (
        <details className="text-label text-app-text-faint">
          <summary className="cursor-pointer">Descartadas por no ser comparables</summary>
          <ul className="mt-1">{a.comparador!.rechazadas.map(r => <li key={r.ticker}>{r.ticker}: {r.motivo}</li>)}</ul>
        </details>
      )}
      <div className="flex flex-wrap gap-1.5 items-center">
        {con.map(c => <Chip key={c} onRemove={() => setCon(con.filter(x => x !== c))}>{c}</Chip>)}
        <Button variant="outline" onClick={() => setEditar(true)}>{con.length ? 'Cambiar alternativas' : 'Elegir alternativas'}</Button>
        {con.length > 0 && <Button variant="ghost" onClick={() => setCon([])}>Volver a las automáticas</Button>}
      </div>
      <Modal open={editar} onClose={() => setEditar(false)} title="Elegir alternativas">
        <p className="text-caption text-app-text-dim mb-2">Hasta {MAX_ALTERNATIVAS}. Las no comparables (otro modelo de negocio, ETF frente a empresa) se descartan con su motivo.</p>
        <SelectorInstrumento
          onElegir={i => { if (con.length < MAX_ALTERNATIVAS && !con.includes(i.simbolo)) setCon([...con, i.simbolo]) }}
          yaSeguidos={new Set(con)} deshabilitado={con.length >= MAX_ALTERNATIVAS} etiquetaYaElegido="Elegida"
        />
      </Modal>
    </Seccion>
  )
}

function Escenarios({ a }: { a: Analisis }) {
  const e = a.escenarios
  return (
    <Seccion titulo="Escenarios de entrada" termino="decisiones_escenarios" estado={a.secciones.escenarios}
             resumen={<p className="text-caption text-app-text-dim">{e?.estado === 'ok' ? `Precio de referencia ${precio(e.precio, e.moneda)} (${e.fecha_precio ?? 'sin fecha'}).` : e?.mensaje}</p>}>
      {e?.estado === 'ok' ? (
        <>
          <p className="text-label text-app-text-faint">{e.salvedad} Horizonte de evaluación: {e.horizonte_meses} meses.</p>
          {e.escenarios.map(x => <TarjetaEscenario key={x.clave} e={x} moneda={e.moneda} />)}
          <details className="text-label text-app-text-faint"><summary className="cursor-pointer">Fórmula del potencial</summary><p className="mt-1">{e.regla_potencial}</p></details>
        </>
      ) : <p className="text-caption text-app-text-dim">{e?.mensaje}</p>}
    </Seccion>
  )
}

function TarjetaEscenario({ e, moneda }: { e: EscenarioEntrada; moneda: string | null }) {
  return (
    <div className={`rounded-xl border p-3 ${e.disponible ? 'border-app-border bg-app-surface-2' : 'border-dashed border-app-border opacity-70'}`}>
      <div className="text-caption font-bold text-app-text">{e.nombre}</div>
      <p className="text-caption text-app-text mt-0.5">{e.disponible ? e.condicion : 'No disponible.'}</p>
      {e.fundamento && <p className="text-label text-app-text-faint">{e.fundamento}</p>}
      {e.precio_entrada != null && (
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 mt-2 text-label">
          <span className="text-app-text-faint">Entrada</span><span className="text-right font-mono tabular-nums">{precio(e.precio_entrada, moneda)}</span>
          <span className="text-app-text-faint flex items-center gap-1">Invalidación <InfoTooltip term="decisiones_invalidacion" label="" /></span>
          <span className="text-right font-mono tabular-nums">{precio(e.invalidacion, moneda)} ({pct(e.riesgo_pct, 1, true)})</span>
          <span className="text-app-text-faint">Desfavorable / base / favorable</span>
          <span className="text-right font-mono tabular-nums">{pct(e.desfavorable_pct, 0, true)} / {pct(e.base_pct, 0, true)} / {pct(e.favorable_pct, 0, true)}</span>
          <span className="text-app-text-faint">Comisión ida y vuelta</span><span className="text-right font-mono tabular-nums">{pct(e.comision_pct, 2)}</span>
        </div>
      )}
      {e.tramos.length > 0 && <p className="text-label text-app-text-faint mt-1">Tramos: {e.tramos.map(t => precio(t.precio, moneda)).join(' · ')}</p>}
      {e.faltantes.length > 0 && <p className="text-label text-app-text-faint mt-1">Falta: {e.faltantes.join('; ')}.</p>}
      {e.incertidumbres.length > 0 && <p className="text-label text-app-text-faint">Incertidumbre: {e.incertidumbres.join('; ')}.</p>}
    </div>
  )
}
