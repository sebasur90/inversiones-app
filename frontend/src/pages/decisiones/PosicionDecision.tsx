import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { getDecisiones, getPosicionDecision, type OpcionPosicion, type PosicionDecision as Posicion } from '../../api'
import { qk } from '../../api/queryClient'
import { useInversionesContext } from '../../context/InversionesContext'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import ScreenHeader from '../../components/layout/ScreenHeader'
import Card from '../../components/ui/Card'
import Button from '../../components/ui/Button'
import QueryBoundary from '../../components/ui/QueryBoundary'
import { SkeletonCard } from '../../components/ui/Skeleton'
import EmptyState from '../../components/ui/EmptyState'
import InfoTooltip from '../../help/components/InfoTooltip'
import SimuladorDecision from '../../components/decisiones/SimuladorDecision'
import GuardarDecision from '../../components/decisiones/GuardarDecision'
import { Banderas, BarraDimension, ConclusionBadge, Lista, Observaciones, Orden, Seccion, num, precio } from '../../components/decisiones/comun'
import { FilaDecision } from '../CentroDecisiones'

const BALANCE: Record<OpcionPosicion['balance'], string> = {
  mas_a_favor: 'Más evidencia a favor', mas_en_contra: 'Más evidencia en contra', mixta: 'Evidencia mixta',
}

/** Mantener, aumentar, reducir o salir de una posición: evidencia, efecto en la cartera y alternativas. */
export default function PosicionDecision() {
  const { ticker = '' } = useParams()
  const navigate = useNavigate()
  const { carteraSeleccionada } = useInversionesContext()
  const fmt = useFormatoFijo('USD')
  const [guardar, setGuardar] = useState<string | null>(null)
  const t = ticker.toUpperCase()
  const q = useQuery({ queryKey: qk.de('decision-posicion', t, carteraSeleccionada), queryFn: () => getPosicionDecision(t, carteraSeleccionada) })
  const historial = useQuery({ queryKey: qk.de('decisiones', t), queryFn: () => getDecisiones({ ticker: t }) })
  const p = q.data

  return (
    <div className="pb-4">
      <ScreenHeader title={`Posición ${t}`} onBack={() => navigate(-1)} />
      <QueryBoundary isLoading={q.isLoading} error={q.error} onRetry={() => void q.refetch()} fallback={<SkeletonCard lineas={6} />}>
        {p && (
          <div className="flex flex-col gap-3">
            <Situacion p={p} />
            <Card>
              <div className="text-label font-bold uppercase text-app-text-faint mb-2">Lo que dice el análisis hoy</div>
              {p.analisis.evaluacion && (
                <>
                  <Orden evaluacion={p.analisis.evaluacion} />
                  <div className="flex flex-col gap-1.5 mt-3">{p.analisis.evaluacion.dimensiones.map(d => <BarraDimension key={d.clave} d={d} />)}</div>
                  <div className="mt-2"><Banderas banderas={p.analisis.evaluacion.banderas} /></div>
                </>
              )}
              {p.analisis.conclusion && <div className="mt-2"><ConclusionBadge tipo={p.analisis.conclusion.tipo} titulo={p.analisis.conclusion.titulo} /></div>}
              <Button variant="ghost" onClick={() => navigate(`/decisiones/analisis/${encodeURIComponent(p.ticker)}`)}>Ver el análisis completo</Button>
            </Card>
            <Tesis p={p} />
            <div className="text-strong font-bold text-app-text flex items-center gap-1 px-0.5">Opciones <InfoTooltip term="decisiones_posicion" label="" /></div>
            {p.opciones.map(o => <TarjetaOpcion key={o.clave} o={o} onGuardar={() => setGuardar(o.clave)} />)}
            {p.invalidacion_cumplida.length > 0 && (
              <Card><div className="text-caption font-bold text-app-warn">Condición de invalidación cumplida</div><Lista items={p.invalidacion_cumplida} /></Card>
            )}
            <Seccion titulo="Mantener frente a reasignar" termino="decisiones_simulador" abiertaInicial
                     resumen={<p className="text-caption text-app-text-dim">{p.reasignaciones.length} alternativas simuladas.</p>}>
              {p.liquidez && (
                <div>
                  <div className="text-caption font-bold text-app-text">{p.liquidez.texto}</div>
                  <p className="text-label text-app-text-dim">Liquidez simulada: {fmt.monto(p.liquidez.simulacion.liquidez_usd)}.</p>
                  <Observaciones items={p.liquidez.simulacion.observaciones} />
                </div>
              )}
              {p.reasignaciones.map(r => (
                <div key={r.destino} className="border-t border-app-border pt-2">
                  <div className="text-caption font-bold text-app-text">
                    Pasar la mitad a {r.destino} {r.orden_destino != null && <span className="font-normal text-app-text-dim">(orden {num(r.orden_destino)})</span>}
                  </div>
                  <p className="text-label text-app-text-dim">Monto simulado: {fmt.monto(r.monto_usd)}.</p>
                  <Observaciones items={r.simulacion.observaciones} />
                </div>
              ))}
              {!p.reasignaciones.length && <p className="text-caption text-app-text-dim">No hay alternativas comparables para simular una reasignación.</p>}
              <p className="text-label text-app-text-faint">Un rendimiento pasado mejor no garantiza uno futuro mejor. Impuestos no calculados.</p>
            </Seccion>
            <SimuladorDecision titulo="Simular otra combinación"
                               iniciales={[{ ticker: p.ticker, monto: String(-Math.round((p.situacion.valor_actual_usd ?? 0) / 2)) }]} />
            {(historial.data?.length ?? 0) > 0 && (
              <Card>
                <div className="text-strong font-bold text-app-text mb-2">Decisiones sobre {p.ticker}</div>
                <div className="flex flex-col divide-y divide-app-border">
                  {historial.data!.map(d => <FilaDecision key={d.id} d={d} onAbrir={() => navigate(`/decisiones/${d.id}`)} />)}
                </div>
              </Card>
            )}
            <GuardarDecision abierto={guardar != null} onClose={() => setGuardar(null)} modo="posicion" ticker={p.ticker}
                             cartera={carteraSeleccionada} con={[]} accionInicial={guardar ?? undefined}
                             alternativas={p.reasignaciones.map(r => r.destino)} key={guardar ?? 'x'} />
          </div>
        )}
        {!p && !q.isLoading && !q.error && <EmptyState ilustracion="lupa" title="Sin datos" />}
      </QueryBoundary>
    </div>
  )
}

function Situacion({ p }: { p: Posicion }) {
  const fmt = useFormatoFijo('USD')
  const s = p.situacion
  const fila = (k: string, v: string) => (
    <><span className="text-app-text-faint">{k}</span><span className="text-right font-mono tabular-nums text-app-text">{v}</span></>
  )
  return (
    <Card>
      <div className="text-title font-bold text-app-text">{p.ticker} <span className="text-body font-normal text-app-text-dim">{p.nombre}</span></div>
      <div className="text-label text-app-text-faint mb-2">{p.cartera ? `Cartera ${p.cartera}` : 'Consolidado'}</div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-caption">
        {fila('Cantidad', num(s.cantidad, 2))}
        {fila('Precio actual', `${precio(s.precio_actual, s.moneda)}${s.fecha_precio ? ` (${s.fecha_precio})` : ''}`)}
        {fila('Valor de mercado', fmt.monto(s.valor_actual_usd))}
        {fila('Costo de la tenencia', fmt.monto(s.valor_invertido_usd))}
        {fila('No realizado', fmt.montoConSigno(s.no_realizado_usd))}
        {fila('Realizado', fmt.montoConSigno(s.realizado_usd))}
        {fila('Dividendos y cupones', fmt.monto(s.ingresos_usd))}
        {fila('Peso del ticker', s.peso_ticker_pct != null ? `${num(s.peso_ticker_pct, 1)} %` : '—')}
        {fila('Peso del emisor', `${num(s.peso_emisor_pct, 1)} % (atención desde ${num(s.umbral_atencion_pct, 0)} %)`)}
      </div>
      {s.valuado_al_costo && <p className="text-label text-app-warn mt-1">Sin cotización: valuada al costo.</p>}
      <p className="text-label text-app-text-faint mt-2">{s.nota_resultado}</p>
    </Card>
  )
}

function Tesis({ p }: { p: Posicion }) {
  if (!p.tesis.existe) {
    return <Card><p className="text-caption text-app-text-dim">No hay una decisión guardada sobre este activo: guardala para poder comparar tu tesis con lo que pase después.</p></Card>
  }
  return (
    <Card>
      <div className="text-caption font-bold text-app-text">Tesis original {p.tesis.deteriorada ? <span className="text-app-warn">· se deterioró</span> : <span className="text-app-pos">· sin deterioro grande</span>}</div>
      <ul className="text-caption text-app-text mt-1 flex flex-col gap-0.5">
        {p.tesis.cambios.map(c => <li key={c.nombre}>{c.nombre}: {num(c.antes)} → {num(c.ahora)} ({c.delta > 0 ? '+' : ''}{num(c.delta, 1)})</li>)}
      </ul>
      {p.tesis.banderas_nuevas.length > 0 && <div className="mt-1"><Banderas banderas={p.tesis.banderas_nuevas} /></div>}
    </Card>
  )
}

function TarjetaOpcion({ o, onGuardar }: { o: OpcionPosicion; onGuardar: () => void }) {
  const fmt = useFormatoFijo('USD')
  const c = o.cambio_en_cartera
  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <span className="text-strong font-bold text-app-text">{o.nombre}</span>
        <span className="text-label text-app-text-dim">{BALANCE[o.balance]}</span>
      </div>
      <div className="grid gap-2 mt-2">
        <div><div className="text-label font-bold uppercase text-app-pos">A favor</div><Lista items={o.a_favor} vacio="Nada a favor con los datos disponibles." /></div>
        <div><div className="text-label font-bold uppercase text-app-neg">En contra</div><Lista items={o.en_contra} vacio="Nada en contra con los datos disponibles." /></div>
        {c && (
          <div>
            <div className="text-label font-bold uppercase text-app-text-faint">Cómo quedaría la cartera</div>
            <p className="text-caption text-app-text">
              Peso del emisor: {num(c.peso_antes_pct, 1)} % → {num(c.peso_despues_pct, 1)} %
              {c.liquidez_usd > 0 ? `; liquidez ${fmt.monto(c.liquidez_usd)}` : ''}
              {c.venta?.resultado_estimado_usd != null ? `; resultado estimado ${fmt.montoConSigno(c.venta.resultado_estimado_usd)}` : ''}.
            </p>
            {c.observaciones.length > 0 && <Observaciones items={c.observaciones} />}
          </div>
        )}
        <div><div className="text-label font-bold uppercase text-app-text-faint">Condiciones</div><Lista items={o.condiciones} /></div>
        <div><div className="text-label font-bold uppercase text-app-text-faint">Lo invalidaría</div><Lista items={o.invalidaria} /></div>
      </div>
      <div className="mt-2"><Button variant="outline" onClick={onGuardar}>Registrar «{o.nombre}»</Button></div>
    </Card>
  )
}
