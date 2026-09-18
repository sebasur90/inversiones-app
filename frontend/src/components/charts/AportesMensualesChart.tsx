import {
  Bar, Cell, ComposedChart, CartesianGrid, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import dayjs from 'dayjs'
import type { AporteMesItem } from '../../api'
import { formatUSD } from '../../utils'

const COLOR_APORTE = '#10b981' // app-pos
const COLOR_RETIRO = '#ef4444' // app-neg
const COLOR_MOVIL = '#3b82f6'
const COLOR_REFERENCIA = '#94a3b8'

function ejeK(v: number): string {
  const abs = Math.abs(v)
  const txt = abs >= 1000 ? `${(abs / 1000).toFixed(abs >= 10000 ? 0 : 1)}k` : `${abs}`
  return `${v < 0 ? '-' : ''}$${txt}`
}

function TooltipMes({ active, payload }: { active?: boolean; payload?: { payload: AporteMesItem }[] }) {
  const item = payload?.[0]?.payload
  if (!active || !item) return null
  return (
    <div className="bg-app-surface border border-app-surface-2 rounded-[10px] px-3 py-2 text-caption">
      <div className="text-app-text font-semibold mb-1">
        {dayjs(`${item.mes}-01`).format('MMMM YYYY')}
        {item.en_curso ? ' (en curso)' : ''}
      </div>
      <div className="flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: item.neto_usd < 0 ? COLOR_RETIRO : COLOR_APORTE }} />
        <span className="text-app-text-dim">Aporte neto</span>
        <span className="font-mono tabular-nums text-app-text ml-auto pl-3">{formatUSD(item.neto_usd)}</span>
      </div>
      <div className="text-app-text-faint pl-3.5">
        compras {formatUSD(item.compras_usd)} · salidas {formatUSD(item.salidas_usd)}
      </div>
      {item.promedio_movil_3_usd != null && (
        <div className="flex items-center gap-1.5 mt-1">
          <span className="w-2 h-0.5 shrink-0" style={{ background: COLOR_MOVIL }} />
          <span className="text-app-text-dim">Promedio móvil 3m</span>
          <span className="font-mono tabular-nums text-app-text ml-auto pl-3">{formatUSD(item.promedio_movil_3_usd)}</span>
        </div>
      )}
    </div>
  )
}

/** Aporte neto por mes (barras, verde aporte / rojo retiro) + promedio móvil de 3 meses (línea).
 *  Un solo eje en USD; el mes en curso va atenuado porque está incompleto. */
export default function AportesMensualesChart({
  serie,
  promedio12,
}: {
  serie: AporteMesItem[]
  promedio12: number | null
}) {
  const data = serie.filter(s => !s.futuro)
  if (data.length === 0) return null

  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1c1f2a" vertical={false} />
        <XAxis
          dataKey="mes"
          stroke="#94a3b8"
          tick={{ fontSize: 10, fill: '#94a3b8' }}
          tickFormatter={v => dayjs(`${v}-01`).format('MMM YY')}
          interval="preserveStartEnd"
          minTickGap={24}
        />
        <YAxis stroke="#94a3b8" tick={{ fontSize: 10, fill: '#94a3b8' }} width={48} tickFormatter={v => ejeK(v as number)} />
        <Tooltip cursor={{ fill: 'rgba(255,255,255,0.04)' }} content={<TooltipMes />} />
        <Legend
          verticalAlign="top"
          height={24}
          iconSize={10}
          wrapperStyle={{ fontSize: 11, color: '#94a3b8' }}
          formatter={value => (value === 'neto_usd' ? 'Aporte neto del mes' : 'Promedio móvil 3 meses')}
        />
        <ReferenceLine y={0} stroke="#2a2f3d" />
        {promedio12 != null && (
          <ReferenceLine
            y={promedio12}
            stroke={COLOR_REFERENCIA}
            strokeDasharray="4 4"
            label={{ value: 'Prom. 12m', fill: COLOR_REFERENCIA, fontSize: 10, position: 'insideTopLeft' }}
          />
        )}
        <Bar dataKey="neto_usd" fill={COLOR_APORTE} radius={[4, 4, 0, 0]} maxBarSize={28}>
          {data.map(item => (
            <Cell
              key={item.mes}
              fill={item.neto_usd < 0 ? COLOR_RETIRO : COLOR_APORTE}
              fillOpacity={item.en_curso ? 0.45 : 0.9}
            />
          ))}
        </Bar>
        <Line
          type="monotone"
          dataKey="promedio_movil_3_usd"
          stroke={COLOR_MOVIL}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4 }}
          connectNulls={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
