import { useEffect, useMemo, useState } from 'react'
import { useInversionesContext } from '../context/InversionesContext'
import { formatARS, formatUSD } from '../utils'
import {
  getConfiguracionCartera,
  simularRebalanceo,
  type ConfiguracionCartera,
  type ModoSimulacion,
  type RebalanceoSimulacionOut,
} from '../api'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import EmptyState from '../components/ui/EmptyState'
import InfoTooltip from '../help/components/InfoTooltip'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import { Icon } from '../components/icons/Icons'
import RebalanceoRow from '../components/inversiones/RebalanceoRow'
import PropuestaRebalanceoRow from '../components/inversiones/PropuestaRebalanceoRow'

const MODO_OPCIONES: { value: ModoSimulacion; label: string }[] = [
  { value: 'completo', label: 'Rebalanceo completo' },
  { value: 'solo_aportes', label: 'Solo nuevos aportes' },
]

export default function Rebalanceo() {
  const { carteraSeleccionada, rebalanceo, monedaSeleccionada, loading } = useInversionesContext()
  const [ejeActivo, setEjeActivo] = useState<string | null>(null)
  const esARS = monedaSeleccionada === 'ARS'
  const formatMoneda = esARS ? formatARS : formatUSD

  const [configuracion, setConfiguracion] = useState<ConfiguracionCartera | null>(null)

  const [simuladorAbierto, setSimuladorAbierto] = useState(false)
  const [modo, setModo] = useState<ModoSimulacion>('completo')
  const [aporteInput, setAporteInput] = useState('')
  const [tasaInput, setTasaInput] = useState('')
  const [simResultado, setSimResultado] = useState<RebalanceoSimulacionOut | null>(null)
  const [simLoading, setSimLoading] = useState(false)
  const [simError, setSimError] = useState<string | null>(null)

  const eje = useMemo(() => {
    if (rebalanceo.ejes.length === 0) return null
    return rebalanceo.ejes.find(e => e.eje === ejeActivo) ?? rebalanceo.ejes[0]
  }, [rebalanceo.ejes, ejeActivo])

  useEffect(() => {
    let cancelado = false
    getConfiguracionCartera(carteraSeleccionada)
      .then(data => {
        if (!cancelado) setConfiguracion(data)
      })
      .catch(() => {
        if (!cancelado) setConfiguracion(null)
      })
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada])

  useEffect(() => {
    setSimResultado(null)
    setSimError(null)
  }, [eje?.eje, carteraSeleccionada])

  const toleranciaPp = configuracion?.tolerancia ?? 2

  const handleSimular = () => {
    if (!eje) return
    setSimLoading(true)
    setSimError(null)
    const aporte = Number(aporteInput.replace(',', '.')) || 0
    const tasa = tasaInput.trim() === '' ? null : Number(tasaInput.replace(',', '.'))
    simularRebalanceo(carteraSeleccionada, { eje: eje.eje, modo, aporte_usd: aporte, tasa_comision_pct: tasa })
      .then(data => {
        setSimResultado(data)
        if (tasaInput.trim() === '') setTasaInput(String(data.tasa_comision_pct))
      })
      .catch(() => setSimError('No se pudo simular el rebalanceo. Intentá de nuevo.'))
      .finally(() => setSimLoading(false))
  }

  const necesarios = simResultado?.items.filter(it => it.necesidad === 'necesario' && it.accion !== 'mantener') ?? []
  const opcionales = simResultado?.items.filter(it => it.necesidad === 'opcional' && it.accion !== 'mantener') ?? []

  return (
    <div className="pb-4">
      <ScreenHeader title="Balance de Cartera" />

      {loading ? (
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      ) : rebalanceo.ejes.length === 0 ? (
        <EmptyState
          title="Sin objetivos de rebalanceo cargados"
          description="Agregá filas a la pestaña 'Rebalanceo' del Sheet y sincronizá para ver el balance de tu cartera."
        />
      ) : (
        <>
          <h3 className="text-[13.5px] font-bold text-app-text mb-2.5">
            <InfoTooltip term="rebalanceo" label="Balance de Cartera" />
          </h3>

          <Segmented
            options={rebalanceo.ejes.map(e => ({ value: e.eje, label: e.eje }))}
            value={eje?.eje ?? rebalanceo.ejes[0].eje}
            onChange={setEjeActivo}
          />

          {eje && (
            <>
              <div className="flex flex-col gap-4 mt-4">
                {eje.items.length === 0 ? (
                  <div className="text-[12px] text-app-text-dim">Sin categorías con objetivo en este eje.</div>
                ) : (
                  eje.items.map(item => (
                    <RebalanceoRow key={item.etiqueta} item={item} moneda={monedaSeleccionada} toleranciaPp={toleranciaPp} />
                  ))
                )}
              </div>

              {eje.sin_objetivo.length > 0 && (
                <>
                  <h3 className="text-[13.5px] font-bold text-app-text mb-2.5 mt-6">Sin objetivo</h3>
                  <div className="flex flex-col gap-2.5">
                    {eje.sin_objetivo.map(item => (
                      <div key={item.etiqueta}>
                        <div className="flex justify-between items-baseline text-[11.5px] mb-1.5">
                          <span className="text-app-text-dim">{item.etiqueta}</span>
                          <span className="font-mono font-bold text-app-text-dim tabular-nums">
                            {formatMoneda(esARS ? item.valor_ars : item.valor_usd)}
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full bg-app-surface-2 overflow-hidden">
                          <div className="h-full rounded-full bg-app-text-faint" style={{ width: `${item.porcentaje}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {eje.items.length > 0 && (
                <div className="mt-6">
                  <Button
                    variant="outline"
                    icon={<Icon name="scale" className="w-4 h-4" />}
                    onClick={() => setSimuladorAbierto(v => !v)}
                    className="w-full"
                  >
                    {simuladorAbierto ? 'Ocultar simulador' : 'Simular rebalanceo'}
                  </Button>

                  {simuladorAbierto && (
                    <Card className="mt-3">
                      <label className="block text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2">Modo</label>
                      <Segmented options={MODO_OPCIONES} value={modo} onChange={setModo} />

                      {modo === 'solo_aportes' && (
                        <div className="mt-3.5">
                          <label className="block text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2">
                            Monto del aporte (USD)
                          </label>
                          <input
                            type="number"
                            min={0}
                            step={10}
                            placeholder="0"
                            value={aporteInput}
                            onChange={e => setAporteInput(e.target.value)}
                            className="w-full h-11 rounded-xl bg-app-surface-2 border border-app-border px-3.5 text-[13.5px] text-app-text outline-none focus:border-app-gold/60 tabular-nums"
                          />
                        </div>
                      )}

                      <div className="mt-3.5">
                        <label className="block text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2">
                          Comisión estimada (%)
                        </label>
                        <input
                          type="number"
                          min={0}
                          step={0.1}
                          placeholder="0"
                          value={tasaInput}
                          onChange={e => setTasaInput(e.target.value)}
                          className="w-full h-11 rounded-xl bg-app-surface-2 border border-app-border px-3.5 text-[13.5px] text-app-text outline-none focus:border-app-gold/60 tabular-nums"
                        />
                        <div className="text-[10px] text-app-text-faint mt-1">
                          Se precarga con el promedio histórico de esta cartera; podés editarla.
                        </div>
                      </div>

                      <Button className="w-full mt-4" loading={simLoading} onClick={handleSimular}>
                        {simLoading ? 'Simulando…' : 'Simular'}
                      </Button>

                      <div className="text-[10.5px] text-app-text-faint text-center mt-2.5">
                        Esto es una simulación: no se registran movimientos reales.
                      </div>

                      {simError && <div className="text-[11.5px] text-app-coral mt-3">{simError}</div>}

                      {simResultado && (
                        <div className="mt-4">
                          <div className="grid grid-cols-3 gap-2 mb-4">
                            <div className="bg-app-surface-2 rounded-[13px] p-2.5">
                              <div className="text-[9px] font-bold uppercase tracking-wide text-app-text-faint mb-1">Comprar</div>
                              <div className="font-mono text-[13px] font-bold text-app-teal tabular-nums">
                                {formatUSD(simResultado.total_a_comprar_usd)}
                              </div>
                            </div>
                            <div className="bg-app-surface-2 rounded-[13px] p-2.5">
                              <div className="text-[9px] font-bold uppercase tracking-wide text-app-text-faint mb-1">Vender</div>
                              <div className="font-mono text-[13px] font-bold text-app-coral tabular-nums">
                                {formatUSD(simResultado.total_a_vender_usd)}
                              </div>
                            </div>
                            <div className="bg-app-surface-2 rounded-[13px] p-2.5">
                              <div className="text-[9px] font-bold uppercase tracking-wide text-app-text-faint mb-1">Comisiones</div>
                              <div className="font-mono text-[13px] font-bold text-app-text tabular-nums">
                                {formatUSD(simResultado.total_comision_estimada_usd)}
                              </div>
                            </div>
                          </div>

                          {simResultado.modo === 'solo_aportes' && simResultado.sobrante_usd > 0.5 && (
                            <div className="text-[11.5px] text-app-text-dim mb-3">
                              Sobrante sin invertir: <span className="font-mono font-bold text-app-text">{formatUSD(simResultado.sobrante_usd)}</span> (alcanzarías los objetivos antes de usar todo el aporte).
                            </div>
                          )}

                          {necesarios.length === 0 && opcionales.length === 0 ? (
                            <div className="text-[12px] text-app-text-dim">No hay cambios sugeridos: la cartera ya está dentro de la tolerancia.</div>
                          ) : (
                            <>
                              {necesarios.length > 0 && (
                                <>
                                  <h3 className="text-[12.5px] font-bold text-app-text mb-1 mt-2">Cambios necesarios</h3>
                                  <div>
                                    {necesarios.map((it, i) => (
                                      <PropuestaRebalanceoRow key={`${it.posicion ?? it.categoria}-${i}`} item={it} />
                                    ))}
                                  </div>
                                </>
                              )}
                              {opcionales.length > 0 && (
                                <>
                                  <h3 className="text-[12.5px] font-bold text-app-text mb-1 mt-4">Cambios opcionales</h3>
                                  <div>
                                    {opcionales.map((it, i) => (
                                      <PropuestaRebalanceoRow key={`${it.posicion ?? it.categoria}-${i}`} item={it} />
                                    ))}
                                  </div>
                                </>
                              )}
                            </>
                          )}
                        </div>
                      )}
                    </Card>
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
