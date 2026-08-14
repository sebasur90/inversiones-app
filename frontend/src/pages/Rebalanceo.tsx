import { useMemo, useState } from 'react'
import { useInversionesContext } from '../context/InversionesContext'
import { formatARS, formatUSD } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import EmptyState from '../components/ui/EmptyState'
import InfoTerm from '../components/ui/InfoTerm'
import RebalanceoRow from '../components/inversiones/RebalanceoRow'

export default function Rebalanceo() {
  const { rebalanceo, monedaSeleccionada, loading } = useInversionesContext()
  const [ejeActivo, setEjeActivo] = useState<string | null>(null)
  const esARS = monedaSeleccionada === 'ARS'
  const formatMoneda = esARS ? formatARS : formatUSD

  const eje = useMemo(() => {
    if (rebalanceo.ejes.length === 0) return null
    return rebalanceo.ejes.find(e => e.eje === ejeActivo) ?? rebalanceo.ejes[0]
  }, [rebalanceo.ejes, ejeActivo])

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
            <InfoTerm term="rebalanceo" label="Balance de Cartera" />
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
                  eje.items.map(item => <RebalanceoRow key={item.etiqueta} item={item} moneda={monedaSeleccionada} />)
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
            </>
          )}
        </>
      )}
    </div>
  )
}
