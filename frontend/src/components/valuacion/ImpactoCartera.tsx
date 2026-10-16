import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { simularImpactoCompra, type ImpactoCompra, type ImpactoEje, type ImpactoObservacion } from '../../api'
import { useInversionesContext } from '../../context/InversionesContext'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import Card from '../ui/Card'
import Button from '../ui/Button'
import Segmented from '../ui/Segmented'
import Semaforo from '../ui/Semaforo'
import InfoTooltip from '../../help/components/InfoTooltip'
import ErrorBanner from '../../help/components/ErrorBanner'
import { parseApiError } from '../../help/errors/apiErrors'
import { Icon } from '../icons/Icons'

const ATAJOS = [500, 1000, 5000]
const FILAS_VISIBLES = 6

/** Los pesos son proporciones de la cartera, no importes: no pasan por el modo privacidad (igual que en Exposición). */
const pct = (v: number) => `${v.toLocaleString('es-AR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`
const pp = (v: number) => `${v > 0.05 ? '+' : v < -0.05 ? '−' : ''}${Math.abs(v).toLocaleString('es-AR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`
const veces = (v: number | null) => (v == null ? '—' : v.toLocaleString('es-AR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }))

function Observacion({ o }: { o: ImpactoObservacion }) {
  return (
    <li className="flex flex-col gap-0.5">
      <div className="flex items-start gap-2">
        {o.nivel === 'info'
          ? <span className="text-label font-semibold text-app-text-faint shrink-0 mt-0.5 w-14">Dato</span>
          : <Semaforo className="shrink-0 mt-0.5 w-14" nivel={o.nivel === 'revisar' ? 'riesgo' : 'atencion'} etiqueta={o.nivel === 'revisar' ? 'Revisar' : 'Atención'} />}
        <span className="text-caption text-app-text">{o.texto}</span>
      </div>
      {o.regla && <span className="text-label text-app-text-faint pl-16">{o.regla}</span>}
    </li>
  )
}

function TablaEje({ eje }: { eje: ImpactoEje }) {
  const [todas, setTodas] = useState(false)
  const filas = todas ? eje.items : eje.items.filter((f, i) => i < FILAS_VISIBLES || f.afectada)
  const ocultas = eje.items.length - filas.length
  return (
    <div>
      <div className="overflow-x-auto -mx-4 px-4">
        <table className="text-caption w-full">
          <thead>
            <tr className="text-label text-app-text-faint">
              <th className="text-left font-semibold pb-1 pr-3">{eje.eje}</th>
              <th className="text-right font-semibold px-2 pb-1">Antes</th>
              <th className="text-right font-semibold px-2 pb-1">Después</th>
              <th className="text-right font-semibold pl-2 pb-1">Cambio (pp)</th>
            </tr>
          </thead>
          <tbody>
            {filas.map(f => (
              <tr key={f.etiqueta} className={`border-t border-app-border ${f.afectada ? 'bg-app-accent-soft' : ''}`}>
                <td className="py-1.5 pr-3">
                  <div className={`${f.afectada ? 'font-bold text-app-accent' : 'text-app-text'} ${f.residual ? 'italic text-app-text-dim' : ''}`}>
                    {f.etiqueta}{f.afectada ? ' ◂' : ''}
                  </div>
                  {f.tickers.length > 1 && <div className="text-label text-app-text-faint">{f.tickers.join(' + ')}: un solo emisor</div>}
                </td>
                <td className="text-right px-2 py-1.5 font-mono whitespace-nowrap">{pct(f.antes_pct)}</td>
                <td className="text-right px-2 py-1.5 font-mono whitespace-nowrap font-semibold">{pct(f.despues_pct)}</td>
                <td className="text-right pl-2 py-1.5 font-mono whitespace-nowrap text-app-text-dim">{pp(f.delta_pp)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {ocultas > 0 && <button onClick={() => setTodas(true)} className="text-caption font-bold text-app-accent mt-1">Ver {ocultas} más</button>}
      {eje.eje === 'Emisor' && (
        <p className="text-label text-app-text-faint mt-1.5">
          Emisores equivalentes: {veces(eje.antes.n_efectivo)} → {veces(eje.despues.n_efectivo)}. Cuanto más alto, más repartida la cartera.
        </p>
      )}
    </div>
  )
}

/**
 * "¿Cómo cambiaría mi cartera?": simula sumar un monto en dólares del ticker de la ficha y muestra los
 * pesos antes y después por emisor, sector, país, región y tipo. Sólo calcula: no guarda nada, no estima
 * precio ni cantidad y no es una recomendación.
 */
export default function ImpactoCartera({ ticker }: { ticker: string }) {
  const { carteraSeleccionada } = useInversionesContext()
  const { monto: formatUSD } = useFormatoFijo('USD')
  const [abierto, setAbierto] = useState(false)
  const [texto, setTexto] = useState('')
  const [ejeActivo, setEjeActivo] = useState('Emisor')

  const monto = Number(texto.replace(/\./g, '').replace(',', '.'))
  const valido = texto.trim() !== '' && Number.isFinite(monto) && monto > 0

  const simular = useMutation({
    mutationFn: () => simularImpactoCompra(carteraSeleccionada, { ticker, monto_usd: monto }),
    onSuccess: () => setEjeActivo('Emisor'),
  })
  const r: ImpactoCompra | undefined = simular.data
  const eje = r?.ejes.find(e => e.eje === ejeActivo) ?? r?.ejes[0]
  const filaEmisor = r?.ejes.find(e => e.eje === 'Emisor')?.items.find(f => f.afectada)

  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <div className="text-strong font-bold text-app-text flex items-center gap-1">
          ¿Cómo cambiaría mi cartera? <InfoTooltip term="impacto_cartera_que_es" label="" />
        </div>
        <button onClick={() => setAbierto(v => !v)} className="text-caption font-bold text-app-accent" aria-expanded={abierto}>
          {abierto ? 'Cerrar' : 'Simular'}
        </button>
      </div>
      {!abierto && (
        <p className="text-caption text-app-text-dim mt-1">
          Indicá un monto en dólares y mirá cuánto pesaría este emisor y cómo se movería tu mezcla por sector, país y región. Sólo simula: no guarda nada.
        </p>
      )}

      {abierto && (
        <div className="mt-3 flex flex-col gap-4">
          <div>
            <label htmlFor={`impacto-monto-${ticker}`} className="text-label font-bold uppercase tracking-wide text-app-text-faint">
              Monto a sumar de {ticker} (USD)
            </label>
            <div className="flex gap-2 mt-1">
              <input
                id={`impacto-monto-${ticker}`} inputMode="decimal" value={texto} onChange={e => setTexto(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && valido) simular.mutate() }}
                placeholder="Ej.: 1000"
                className="flex-1 min-w-0 h-11 px-3 rounded-xl bg-app-surface-2 border border-app-border text-body text-app-text"
              />
              <Button onClick={() => simular.mutate()} loading={simular.isPending} disabled={!valido}>Ver impacto</Button>
            </div>
            <div className="flex gap-1.5 mt-1.5">
              {ATAJOS.map(a => (
                <button key={a} onClick={() => setTexto(String(a))} className="text-caption font-semibold px-2.5 py-1 rounded-lg bg-app-surface-2 text-app-text-dim">
                  {a.toLocaleString('es-AR')}
                </button>
              ))}
            </div>
            <p className="text-label text-app-text-faint mt-1.5">
              Sobre: {carteraSeleccionada ?? 'todas tus carteras (consolidado)'}.
            </p>
          </div>

          {simular.error && <ErrorBanner error={parseApiError(simular.error)} />}

          {r && eje && (
            <div className="flex flex-col gap-4">
              {filaEmisor && (
                <p className="text-body text-app-text">
                  Con {formatUSD(r.monto_usd)} de {r.emisor}, este emisor pasaría de{' '}
                  <span className="font-mono font-bold">{pct(filaEmisor.antes_pct)}</span> a{' '}
                  <span className="font-mono font-bold">{pct(filaEmisor.despues_pct)}</span> de tu cartera.
                </p>
              )}
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-xl bg-app-surface-2 p-3">
                  <div className="text-label font-bold uppercase tracking-wide text-app-text-faint">Cartera hoy</div>
                  <div className="text-strong font-bold font-mono text-app-text">{formatUSD(r.total.antes_usd)}</div>
                </div>
                <div className="rounded-xl bg-app-surface-2 p-3">
                  <div className="text-label font-bold uppercase tracking-wide text-app-text-faint">Con el monto</div>
                  <div className="text-strong font-bold font-mono text-app-text">{formatUSD(r.total.despues_usd)}</div>
                </div>
              </div>

              {r.observaciones.length > 0 && (
                <ul className="flex flex-col gap-2">
                  {r.observaciones.map(o => <Observacion key={o.texto} o={o} />)}
                </ul>
              )}

              <div className="flex flex-col gap-2">
                <Segmented
                  options={r.ejes.map(e => ({ value: e.eje, label: e.eje === 'Tipo de instrumento' ? 'Tipo' : e.eje }))}
                  value={eje.eje} onChange={setEjeActivo}
                />
                <TablaEje key={eje.eje} eje={eje} />
              </div>

              {(r.notas.length > 0 || Object.values(r.avisos).some(l => l.length > 0)) && (
                <div className="flex flex-col gap-1">
                  {r.notas.map(n => (
                    <div key={n} className="flex gap-1.5 items-start text-caption text-app-warn">
                      <Icon name="alert" className="w-3.5 h-3.5 mt-0.5 shrink-0" /> <span>{n}</span>
                    </div>
                  ))}
                  {r.avisos.aproximadas?.length > 0 && (
                    <div className="text-label text-app-text-faint">Valuadas al costo por falta de cotización: {r.avisos.aproximadas.join(', ')}.</div>
                  )}
                  {r.avisos.sin_valuar?.length > 0 && (
                    <div className="text-label text-app-text-faint">Sin cotización ni costo (no suman): {r.avisos.sin_valuar.join(', ')}.</div>
                  )}
                </div>
              )}

              <p className="text-label text-app-text-faint text-center">
                Es una simulación de pesos con la cartera de hoy; no estima precio ni cantidad y no es una recomendación de compra o venta.
              </p>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
