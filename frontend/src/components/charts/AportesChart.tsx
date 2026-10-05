import {
  XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, ComposedChart, Area, Scatter,
} from 'recharts'
import { mesAnioCorto, mesAnioLargo } from '../../utils/fechas'
import type { AportesHistoricosOut } from '../../api'
import { useFormatoFijo } from '../../hooks/useFormatoMoneda'

export default function AportesChart({
  aportesHistoricos,
  montoObjetivo,
}: {
  aportesHistoricos: AportesHistoricosOut | null
  montoObjetivo?: number | null
}) {
  // Con el modo privacidad se tapan el eje, el tooltip y los totales de abajo. La forma de la
  // curva queda: dice lo mismo que el rendimiento en %, que también queda a la vista.
  const { monto, montoConSigno, compactoFino } = useFormatoFijo('USD')

  if (!aportesHistoricos || aportesHistoricos.curva.length === 0) {
    return <div className="text-center py-8 text-app-text-dim text-caption">Sin movimientos en esta cartera</div>
  }

  const data = aportesHistoricos.curva.map(punto => ({ ...punto, mes_label: punto.mes }))
  const acumuladoFinal = data[data.length - 1]?.aportes_netos_acumulados ?? 0
  const rendimientoAcumulado = aportesHistoricos.valor_actual_usd - acumuladoFinal
  const rendimientoPct = acumuladoFinal > 0 ? (rendimientoAcumulado / acumuladoFinal) * 100 : 0

  return (
    <div>
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
          <defs>
            <linearGradient id="aportesFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1c1f2a" />
          <XAxis
            dataKey="mes_label"
            tick={{ fill: '#94a3b8', fontSize: 10 }}
            tickFormatter={v => mesAnioCorto(v)}
            interval="preserveStartEnd"
          />
          <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={v => compactoFino(v as number)} width={42} />
          <Tooltip
            contentStyle={{ background: '#171b26', border: '1px solid #1c1f2a', borderRadius: 10, fontSize: 12 }}
            labelStyle={{ color: '#f8fafc' }}
            labelFormatter={v => mesAnioLargo(v)}
            formatter={(v: number, name: string) => (name === 'aportes_netos_acumulados' ? [monto(v), 'Aportes acumulados'] : [v, name])}
          />
          {montoObjetivo && (
            <ReferenceLine y={montoObjetivo} stroke="#10b981" strokeDasharray="6 3" label={{ value: 'Meta', fill: '#10b981', fontSize: 11 }} />
          )}
          {/* dot={{ r: 0 }} en vez de `false`: con un solo punto en la curva (un único mes con
              movimientos) Recharts ignora `dot={false}` y fuerza igual un punto visible
              (Area.renderDots se llama si `dot || hasSinglePoint`), que queda superpuesto con el
              Scatter de "valor actual". Forzar un dot invisible evita ese punto fantasma. */}
          <Area type="monotone" dataKey="aportes_netos_acumulados" stroke="#3b82f6" strokeWidth={2} fill="url(#aportesFill)" dot={{ r: 0, fillOpacity: 0, strokeOpacity: 0 }} />
          <Scatter
            name="Valor actual (hoy)"
            dataKey="__valor_actual"
            fill="#10b981"
            shape="circle"
            data={[{ __valor_actual: aportesHistoricos.valor_actual_usd, mes_label: data[data.length - 1]?.mes_label || '' }]}
          />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="mt-3 text-label text-app-text-dim space-y-1">
        <div>Últimos aportes netos acumulados: <strong className="text-app-text">{monto(acumuladoFinal)}</strong></div>
        <div>Valor actual (hoy): <strong className="text-app-text">{monto(aportesHistoricos.valor_actual_usd)}</strong></div>
        <div>
          Rendimiento acumulado:{' '}
          <strong className={rendimientoAcumulado >= 0 ? 'text-app-pos' : 'text-app-neg'}>
            {montoConSigno(rendimientoAcumulado)} ({rendimientoPct >= 0 ? '+' : ''}{rendimientoPct.toFixed(1)}%)
          </strong>
        </div>
      </div>
    </div>
  )
}
