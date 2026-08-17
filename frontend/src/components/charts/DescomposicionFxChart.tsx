import React from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, Cell, ResponsiveContainer } from 'recharts'
import { formatPctRatio } from '../../utils'

interface DescomposicionFxChartProps {
  retornoTotalArs: number | null
  retornoActivo: number | null
  efectoFx: number | null
  esARS: boolean
}

export default function DescomposicionFxChart({
  retornoTotalArs,
  retornoActivo,
  efectoFx,
  esARS,
}: DescomposicionFxChartProps) {
  if (retornoTotalArs === null || retornoActivo === null || efectoFx === null) {
    return null
  }

  const data = [
    {
      name: 'Retorno total',
      valor: retornoTotalArs,
      fill: '#4fd1ae',
    },
    {
      name: 'Efecto FX',
      valor: efectoFx,
      fill: '#e2665a',
    },
    {
      name: 'Retorno activos',
      valor: retornoActivo,
      fill: '#4fd1ae',
    },
  ]

  const renderCustomLabel = (props: any) => {
    const { x, y, width, value } = props
    if (value === null || value === undefined) return <></>
    const isNegative = value < 0
    const yPos = isNegative ? y + 20 : y - 10
    return (
      <text
        x={x + width / 2}
        y={yPos}
        fill="#a8a8a8"
        textAnchor="middle"
        fontSize={12}
        fontWeight="bold"
      >
        {formatPctRatio(value)}
      </text>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data}>
        <XAxis
          dataKey="name"
          tick={{ fill: '#8ca39b', fontSize: 12 }}
          axisLine={{ stroke: '#223028' }}
          tickLine={{ stroke: '#223028' }}
        />
        <YAxis
          tick={{ fill: '#8ca39b', fontSize: 12 }}
          axisLine={{ stroke: '#223028' }}
          tickLine={{ stroke: '#223028' }}
          tickFormatter={formatPctRatio}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#17221e',
            border: '1px solid #223028',
            borderRadius: '4px',
            color: '#a8a8a8',
          }}
          labelStyle={{ color: '#a8a8a8' }}
          formatter={(value: number) => formatPctRatio(value)}
        />
        <Bar dataKey="valor" radius={4} label={renderCustomLabel}>
          {data.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.fill} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
