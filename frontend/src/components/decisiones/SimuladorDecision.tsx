import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { simularDecision, type SimulacionDecision } from '../../api'
import { useInversionesContext } from '../../context/InversionesContext'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'
import { parseApiError } from '../../help/errors/apiErrors'
import ErrorBanner from '../../help/components/ErrorBanner'
import InfoTooltip from '../../help/components/InfoTooltip'
import Button from '../ui/Button'
import Card from '../ui/Card'
import Segmented from '../ui/Segmented'
import { Lista, Observaciones, num } from './comun'

export interface OperacionSimulada { ticker: string; monto: string }

/**
 * Simulador de decisiones: una o varias operaciones hipotéticas en USD (positivo suma, negativo reduce) y cómo
 * quedaría la cartera. No guarda nada ni toca movimientos: para eso está el flujo de carga de la planilla.
 */
export default function SimuladorDecision({ iniciales, titulo = 'Simular el impacto en tu cartera' }: {
  iniciales: OperacionSimulada[]; titulo?: string
}) {
  const { carteraSeleccionada } = useInversionesContext()
  const fmt = useFormatoFijo('USD')
  const [ops, setOps] = useState<OperacionSimulada[]>(iniciales)
  const [eje, setEje] = useState('Emisor')
  const validas = ops
    .map(o => ({ ticker: o.ticker.trim().toUpperCase(), monto_usd: Number(o.monto.replace(/\./g, '').replace(',', '.')) }))
    .filter(o => o.ticker && Number.isFinite(o.monto_usd) && o.monto_usd !== 0)
  const sim = useMutation({ mutationFn: () => simularDecision(carteraSeleccionada, validas) })
  const r: SimulacionDecision | undefined = sim.data
  const ejeActual = r?.ejes.find(e => e.eje === eje) ?? r?.ejes[0]

  const cambiar = (i: number, campo: keyof OperacionSimulada, v: string) =>
    setOps(prev => prev.map((o, j) => (j === i ? { ...o, [campo]: v } : o)))

  return (
    <Card>
      <div className="text-strong font-bold text-app-text flex items-center gap-1">
        {titulo} <InfoTooltip term="decisiones_simulador" label="" />
      </div>
      <p className="text-label text-app-text-dim mt-0.5">
        Montos en USD: positivo suma, negativo reduce una tenencia. Lo que se libera y no se reasigna queda como liquidez.
        {carteraSeleccionada ? ` Cartera: ${carteraSeleccionada}.` : ' Consolidado.'} Sólo simula: no guarda nada.
      </p>
      <div className="flex flex-col gap-2 mt-3">
        {ops.map((o, i) => (
          <div key={i} className="flex gap-2">
            <input aria-label="Ticker" value={o.ticker} onChange={e => cambiar(i, 'ticker', e.target.value)} placeholder="Ticker"
                   className="w-24 h-11 px-3 rounded-xl bg-app-surface-2 border border-app-border text-body text-app-text uppercase" />
            <input aria-label="Monto en USD" inputMode="decimal" value={o.monto} onChange={e => cambiar(i, 'monto', e.target.value)}
                   placeholder="Ej.: -500" className="flex-1 min-w-0 h-11 px-3 rounded-xl bg-app-surface-2 border border-app-border text-body text-app-text" />
            {ops.length > 1 && (
              <button type="button" onClick={() => setOps(prev => prev.filter((_, j) => j !== i))}
                      className="text-caption text-app-text-dim px-2" aria-label="Quitar operación">✕</button>
            )}
          </div>
        ))}
        <div className="flex gap-2">
          {ops.length < 8 && (
            <Button variant="outline" onClick={() => setOps(prev => [...prev, { ticker: '', monto: '' }])}>+ operación</Button>
          )}
          <Button onClick={() => sim.mutate()} loading={sim.isPending} disabled={!validas.length}>Simular</Button>
        </div>
      </div>

      {sim.error && <div className="mt-3"><ErrorBanner error={parseApiError(sim.error)} /></div>}

      {r && (
        <div className="mt-4 flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-2 text-caption">
            <div className="rounded-xl bg-app-surface-2 p-2.5">
              <div className="text-label text-app-text-faint">Total antes</div>
              <div className="font-mono tabular-nums text-app-text">{fmt.monto(r.total.antes_usd)}</div>
            </div>
            <div className="rounded-xl bg-app-surface-2 p-2.5">
              <div className="text-label text-app-text-faint">Total después</div>
              <div className="font-mono tabular-nums text-app-text">{fmt.monto(r.total.despues_usd)}</div>
            </div>
          </div>
          {r.liquidez_usd > 0 && <p className="text-caption text-app-text">Liquidez simulada: {fmt.monto(r.liquidez_usd)}.</p>}
          {r.ventas.map(v => (
            <p key={v.ticker} className="text-caption text-app-text">
              Reducir {v.ticker}: {fmt.monto(v.monto_usd)}
              {v.cantidad_estimada != null && ` (≈ ${num(v.cantidad_estimada, 2)} unidades)`}
              {v.resultado_estimado_usd != null && `, resultado estimado ${fmt.montoConSigno(v.resultado_estimado_usd)}`}.
            </p>
          ))}
          {r.comision_estimada_usd != null && (
            <p className="text-caption text-app-text">Comisión estimada: {fmt.monto(r.comision_estimada_usd)} (tasa {num(r.tasa_comision_pct, 2)} %).</p>
          )}
          <Observaciones items={r.observaciones} />
          <Segmented options={r.ejes.map(e => ({ value: e.eje, label: e.eje }))} value={ejeActual?.eje ?? 'Emisor'} onChange={setEje} />
          {ejeActual && (
            <div className="overflow-x-auto -mx-4 px-4">
              <table className="text-caption w-full">
                <thead>
                  <tr className="text-label text-app-text-faint">
                    <th className="text-left font-semibold pb-1 pr-3">{ejeActual.eje}</th>
                    <th className="text-right font-semibold px-2 pb-1">Antes</th>
                    <th className="text-right font-semibold px-2 pb-1">Después</th>
                    <th className="text-right font-semibold pl-2 pb-1">Cambio (pp)</th>
                  </tr>
                </thead>
                <tbody>
                  {ejeActual.items.map(f => (
                    <tr key={f.etiqueta} className={`border-t border-app-border ${f.afectada ? 'bg-app-accent-soft' : ''}`}>
                      <td className="py-1.5 pr-3 text-app-text">{f.etiqueta}</td>
                      <td className="text-right px-2 font-mono tabular-nums">{num(f.antes_pct, 1)} %</td>
                      <td className="text-right px-2 font-mono tabular-nums">{num(f.despues_pct, 1)} %</td>
                      <td className="text-right pl-2 font-mono tabular-nums">{f.delta_pp > 0 ? '+' : ''}{num(f.delta_pp, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {r.rebalanceo.length > 0 && (
            <div>
              <div className="text-label font-bold uppercase text-app-text-faint mb-1">Distancia a tus objetivos de Rebalanceo</div>
              <ul className="flex flex-col gap-0.5 text-caption text-app-text">
                {r.rebalanceo.map(x => (
                  <li key={x.eje}>{x.eje}: {num(x.desvio_antes_pp, 1)} → {num(x.desvio_despues_pp, 1)} puntos de desvío</li>
                ))}
              </ul>
            </div>
          )}
          <div className="grid gap-2">
            <div><div className="text-label font-bold uppercase text-app-text-faint">Exacto con los datos actuales</div><Lista items={r.exacto} /></div>
            <div><div className="text-label font-bold uppercase text-app-text-faint">Supuestos</div><Lista items={r.supuestos} /></div>
            {r.notas.length > 0 && <Lista items={r.notas} />}
          </div>
        </div>
      )}
    </Card>
  )
}
