import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInversionesContext } from '../context/InversionesContext'
import { getVencimientos, type VencimientoItem, type VencimientoAnioItem } from '../api'
import { formatARS, formatUSD } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import VencimientoRow from '../components/inversiones/VencimientoRow'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import InfoTooltip from '../help/components/InfoTooltip'

function ResumenPorAnio({
  porAnio,
  esARS,
}: {
  porAnio: VencimientoAnioItem[]
  esARS: boolean
}) {
  const fmt = esARS ? formatARS : formatUSD
  const maxPct = Math.max(
    0.0001,
    ...porAnio.map(a => (esARS ? a.pct_cartera_ars : a.pct_cartera_usd) ?? 0),
  )

  return (
    <Card>
      <div className="flex items-center gap-2 mb-2.5">
        <span className="text-[12px] font-semibold text-app-text">% de la cartera que vence por año</span>
        <InfoTooltip term="vencimientos_por_anio" />
      </div>
      <div className="flex flex-col gap-2">
        {porAnio.map(a => {
          const pct = (esARS ? a.pct_cartera_ars : a.pct_cartera_usd) ?? 0
          const valor = esARS ? a.valor_ars : a.valor_usd
          return (
            <div key={a.anio}>
              <div className="flex items-baseline justify-between text-[11.5px]">
                <span className="font-semibold text-app-text tabular-nums">{a.anio}</span>
                <span className="text-app-text-dim tabular-nums">
                  {(pct * 100).toFixed(1)}% · {fmt(valor)}
                </span>
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-app-surface-2 overflow-hidden">
                <div
                  className="h-full rounded-full bg-app-teal"
                  style={{ width: `${Math.max(3, (pct / maxPct) * 100)}%` }}
                />
              </div>
              {a.instrumentos_sin_valuar > 0 && (
                <div className="text-[9.5px] text-app-text-faint mt-0.5">
                  {a.instrumentos_sin_valuar} sin cotización cargada (no suman al %)
                </div>
              )}
            </div>
          )
        })}
      </div>
    </Card>
  )
}

export default function Vencimientos() {
  const navigate = useNavigate()
  const { carteraSeleccionada, monedaSeleccionada, syncVersion } = useInversionesContext()
  const [items, setItems] = useState<VencimientoItem[]>([])
  const [porAnio, setPorAnio] = useState<VencimientoAnioItem[]>([])
  const [loading, setLoading] = useState(true)

  const esARS = monedaSeleccionada === 'ARS'

  useEffect(() => {
    let cancelado = false
    setLoading(true)
    getVencimientos(carteraSeleccionada)
      .then(data => {
        if (cancelado) return
        setItems(data.items)
        setPorAnio(data.por_anio)
      })
      .catch(() => {
        if (cancelado) return
        setItems([])
        setPorAnio([])
      })
      .finally(() => {
        if (!cancelado) setLoading(false)
      })
    return () => {
      cancelado = true
    }
  }, [carteraSeleccionada, syncVersion])

  return (
    <div className="pb-4">
      <ScreenHeader title="Vencimientos" onBack={() => navigate(-1)} />

      <div className="px-4 mb-4 pt-2">
        <div className="text-[12px] text-app-text-dim space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-app-text">Días restantes</span>
            <InfoTooltip term="vencimientos_dias_restantes" />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-app-text">Fecha de vencimiento</span>
            <InfoTooltip term="vencimientos_fecha_vencimiento" />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-app-text">Valor actual</span>
            <InfoTooltip term="vencimientos_valor_actual" />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-app-text">Paridad · TIR al vto. · Duration</span>
            <InfoTooltip term="vencimientos_paridad" />
            <InfoTooltip term="vencimientos_tir" />
            <InfoTooltip term="vencimientos_duration" />
            <InfoTooltip term="vencimientos_inferido" />
          </div>
        </div>
      </div>

      {loading ? (
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      ) : items.length === 0 ? (
        <EmptyState title="Sin vencimientos" description="No hay instrumentos con fecha de vencimiento en esta cartera." />
      ) : (
        <div className="px-4 flex flex-col gap-4">
          {porAnio.length > 0 && <ResumenPorAnio porAnio={porAnio} esARS={esARS} />}

          <div>
            <div className="flex items-center gap-2 mb-1 text-[11px] font-bold uppercase tracking-wide text-app-text-dim">
              Instrumentos
              <InfoTooltip term="vencimientos_inferido" />
            </div>
            {items.map(item => (
              <VencimientoRow key={item.ticker} item={item} moneda={monedaSeleccionada} />
            ))}
            <div className="text-[10px] text-app-text-faint mt-2">
              Paridad, TIR al vencimiento y duration son estimaciones sobre el cronograma de
              cobros inferido de tu historial (mismo motor que Flujo de caja proyectado), no un
              cronograma oficial.
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
