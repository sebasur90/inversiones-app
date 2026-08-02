import { Card, Col, Row } from 'antd'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts'
import type { ExposicionEje, ExposicionItem } from '../../api'
import { CHART_COLORS, formatUSD, formatARS } from '../../utils'

function bucketizeTop10(items: ExposicionItem[], moneda: 'USD' | 'ARS'): ExposicionItem[] {
  if (items.length <= 10) return items
  const top = items.slice(0, 10)
  const resto = items.slice(10)
  const valueKey = moneda === 'ARS' ? 'valor_ars' : 'valor_usd'
  const otros: ExposicionItem = {
    etiqueta: 'Otros',
    valor_usd: resto.reduce((acc, i) => acc + i.valor_usd, 0),
    valor_ars: resto.reduce((acc, i) => acc + i.valor_ars, 0),
    porcentaje: resto.reduce((acc, i) => acc + i.porcentaje, 0),
  }
  return [...top, otros]
}

function EjeCard({ eje, moneda = 'USD' }: { eje: ExposicionEje; moneda?: 'USD' | 'ARS' }) {
  const esARS = moneda === 'ARS'
  const valueKey = esARS ? 'valor_ars' : 'valor_usd'
  const formatter = esARS ? formatARS : formatUSD
  const items = eje.eje === 'Ticker' ? bucketizeTop10(eje.items, moneda) : eje.items

  return (
    <Card
      title={`Exposición: ${eje.eje}`}
      size="small"
      style={{ background: '#161b22', border: '1px solid #30363d' }}
      styles={{ header: { color: '#c9d1d9', borderBottom: '1px solid #30363d' } }}
    >
      <ResponsiveContainer width="100%" height={240}>
        <PieChart>
          <Pie
            data={items}
            dataKey={valueKey}
            nameKey="etiqueta"
            cx="50%"
            cy="50%"
            outerRadius={80}
            label={({ porcentaje }) => `${porcentaje.toFixed(0)}%`}
            labelLine={false}
          >
            {items.map((_, i) => (
              <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ background: '#21262d', border: '1px solid #30363d', borderRadius: 8 }}
            formatter={(v: number, name: string) => [formatter(v), name]}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
        </PieChart>
      </ResponsiveContainer>
    </Card>
  )
}

export default function ExposicionGrid({ ejes, moneda = 'USD' }: { ejes: ExposicionEje[]; moneda?: 'USD' | 'ARS' }) {
  if (ejes.length === 0) return null
  return (
    <Row gutter={[16, 16]}>
      {ejes.map(eje => (
        <Col xs={24} md={12} key={eje.eje}>
          <EjeCard eje={eje} moneda={moneda} />
        </Col>
      ))}
    </Row>
  )
}
