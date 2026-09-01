import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { useInversionesContext } from '../context/InversionesContext'
import { getComisiones, type ComisionPeriodoItem } from '../api'
import { qk } from '../api/queryClient'
import { CHART_COLORS, formatARS, formatUSD } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Segmented from '../components/ui/Segmented'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import BotonExportarCsv from '../components/ui/BotonExportarCsv'
import SkeletonPantalla from '../components/ui/Skeleton'
import QueryBoundary from '../components/ui/QueryBoundary'

type Desglose = 'cartera' | 'ticker' | 'mes' | 'anio'

function BarrasDesglose({
  items,
  formatMoneda,
}: {
  items: { etiqueta: string; valor: number }[]
  formatMoneda: (v: number) => string
}) {
  const total = items.reduce((acc, i) => acc + i.valor, 0)
  if (total <= 0) {
    return <div className="text-center py-10 text-app-text-dim text-caption">Sin comisiones para este desglose</div>
  }
  return (
    <div className="flex flex-col gap-2.5">
      {items.map((item, i) => (
        <div key={item.etiqueta}>
          <div className="flex justify-between items-baseline text-caption mb-1.5">
            <span className="text-app-text">{item.etiqueta}</span>
            <span className="font-mono font-bold text-app-text tabular-nums">{formatMoneda(item.valor)}</span>
          </div>
          <div className="h-1.5 rounded-full bg-app-surface-2 overflow-hidden">
            <div
              className="h-full rounded-full"
              style={{ width: `${(item.valor / total) * 100}%`, background: CHART_COLORS[i % CHART_COLORS.length] }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

function PeriodoChart({ items, esARS }: { items: ComisionPeriodoItem[]; esARS: boolean }) {
  if (items.length === 0) {
    return <div className="text-center py-10 text-app-text-dim text-caption">Sin comisiones para este período</div>
  }
  const clave = esARS ? 'total_ars' : 'total_usd'
  const formatMoneda = esARS ? formatARS : formatUSD
  const prefijo = esARS ? '$' : 'U$S'
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={items} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#223028" />
        <XAxis dataKey="periodo" stroke="#8ca39b" tick={{ fontSize: 10, fill: '#8ca39b' }} />
        <YAxis stroke="#8ca39b" tick={{ fontSize: 10, fill: '#8ca39b' }} width={56} tickFormatter={v => `${prefijo} ${v}`} />
        <Tooltip
          contentStyle={{ background: '#17221e', border: '1px solid #223028', borderRadius: 10, fontSize: 12 }}
          labelStyle={{ color: '#edf2ef' }}
          formatter={(v: number) => [formatMoneda(v), 'Comisión']}
          cursor={{ fill: 'rgba(255,255,255,0.04)' }}
        />
        <Bar dataKey={clave} fill="#d8b14a" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export default function Comisiones() {
  const navigate = useNavigate()
  const { carteraSeleccionada, monedaSeleccionada } = useInversionesContext()
  // null = todavía no eligió: se usa el desglose por defecto según lo que traiga la respuesta.
  const [desgloseElegido, setDesglose] = useState<Desglose | null>(null)

  const comisionesQuery = useQuery({
    queryKey: qk.de('comisiones', carteraSeleccionada),
    queryFn: () => getComisiones(carteraSeleccionada),
  })
  const datos = comisionesQuery.data ?? null

  const hayPorCartera = (datos?.por_cartera.length ?? 0) > 0
  const desglose: Desglose = desgloseElegido ?? (hayPorCartera ? 'cartera' : 'ticker')

  const esARS = monedaSeleccionada === 'ARS'
  const formatMoneda = esARS ? formatARS : formatUSD

  if (comisionesQuery.isLoading || comisionesQuery.error) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Comisiones" onBack={() => navigate(-1)} />
        <QueryBoundary
          isLoading={comisionesQuery.isLoading}
          error={comisionesQuery.error}
          onRetry={() => void comisionesQuery.refetch()}
          fallback={<SkeletonPantalla />}
        >
          {null}
        </QueryBoundary>
      </div>
    )
  }

  if (!datos || datos.movimientos_con_comision === 0) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Comisiones" onBack={() => navigate(-1)} />
        <EmptyState title="Sin comisiones registradas" description="No hay movimientos con comisión en esta cartera." />
      </div>
    )
  }

  const opciones: { value: Desglose; label: string }[] = [
    ...(datos.por_cartera.length > 0 ? [{ value: 'cartera' as Desglose, label: 'Cartera' }] : []),
    { value: 'ticker', label: 'Ticker' },
    { value: 'mes', label: 'Mensual' },
    { value: 'anio', label: 'Anual' },
  ]

  return (
    <div className="pb-4">
      <ScreenHeader title="Comisiones" onBack={() => navigate(-1)} />

      <Card className="mb-4">
        <div className="text-label font-bold uppercase tracking-wide text-app-text-faint mb-1">Total pagado</div>
        <div className="font-mono text-metric-lg font-bold text-app-text tabular-nums">
          {formatMoneda(esARS ? datos.total_ars : datos.total_usd)}
        </div>
        <div className="text-label text-app-text-dim mt-1">
          {datos.movimientos_con_comision} movimiento{datos.movimientos_con_comision !== 1 ? 's' : ''} con comisión
        </div>
      </Card>

      <div className="flex items-center justify-between gap-3 mb-3">
        <Segmented options={opciones} value={desglose} onChange={setDesglose} />
        <BotonExportarCsv
          nombre={`comisiones-${carteraSeleccionada || 'consolidado'}`}
          encabezados={['Desglose', 'Etiqueta', 'Total USD', 'Total ARS']}
          filas={() => [
            ...datos.por_cartera.map(i => ['Cartera', i.etiqueta, i.total_usd, i.total_ars]),
            ...datos.por_ticker.map(i => ['Ticker', i.ticker, i.total_usd, i.total_ars]),
            ...datos.por_mes.map(i => ['Mes', i.periodo, i.total_usd, i.total_ars]),
            ...datos.por_anio.map(i => ['Año', i.periodo, i.total_usd, i.total_ars]),
          ]}
        />
      </div>

      {desglose === 'cartera' && (
        <BarrasDesglose
          items={datos.por_cartera.map(i => ({ etiqueta: i.etiqueta, valor: esARS ? i.total_ars : i.total_usd }))}
          formatMoneda={formatMoneda}
        />
      )}
      {desglose === 'ticker' && (
        <BarrasDesglose
          items={datos.por_ticker.map(i => ({ etiqueta: i.ticker, valor: esARS ? i.total_ars : i.total_usd }))}
          formatMoneda={formatMoneda}
        />
      )}
      {desglose === 'mes' && <PeriodoChart items={datos.por_mes} esARS={esARS} />}
      {desglose === 'anio' && <PeriodoChart items={datos.por_anio} esARS={esARS} />}
    </div>
  )
}
