import { useMemo, useState } from 'react'
import { Button, Card, Empty, Input, Table, Typography } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import type { RendimientoPorTickerItem } from '../../api'
import { formatARS, formatPctRatio, formatUSD, TIPO_COLORS } from '../../utils'

const { Text } = Typography

function colorRendimiento(value: number | null): string {
  if (value == null || value === 0) return TIPO_COLORS.neutro
  return value > 0 ? TIPO_COLORS.ingreso : TIPO_COLORS.egreso
}

function celdaRendimiento(value: number | null) {
  if (value == null) return <Text type="secondary">—</Text>
  const color = colorRendimiento(value)
  const icono = value > 0 ? '↑' : value < 0 ? '↓' : ''
  return <span style={{ color }}>{icono} {formatPctRatio(value)}</span>
}

function formatCantidad(value: number): string {
  return value.toLocaleString('es-AR', { maximumFractionDigits: 8 })
}

function formatPrecio(value: number): string {
  return value.toLocaleString('es-AR', { maximumFractionDigits: 6 })
}

function exportarCSV(items: RendimientoPorTickerItem[], cartera: string | null) {
  const headers = [
    'Ticker', 'Nombre', 'Cantidad Actual', 'Precio Promedio', 'Precio Actual',
    'Rendimiento USD %', 'Rendimiento ARS %', 'Rendimiento ARS Real %',
    'Valor Invertido (USD)', 'Valor Actual (USD)', 'Valor Invertido (ARS)', 'Valor Actual (ARS)',
  ]
  const rows = items.map(it => [
    it.ticker, it.nombre, it.cantidad_actual, it.precio_promedio, it.precio_actual,
    it.rendimiento_simple_usd != null ? (it.rendimiento_simple_usd * 100).toFixed(2) : '',
    it.rendimiento_simple_ars != null ? (it.rendimiento_simple_ars * 100).toFixed(2) : '',
    it.rendimiento_simple_ars_real != null ? (it.rendimiento_simple_ars_real * 100).toFixed(2) : '',
    it.valor_invertido_usd, it.valor_actual_usd, it.valor_invertido_ars, it.valor_actual_ars,
  ])
  const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const fecha = new Date().toISOString().slice(0, 10)
  a.download = `inversiones-rendimiento-${cartera || 'consolidado'}-${fecha}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export default function RendimientoPorTickerTabla({ items, cartera, onSelectTicker, moneda = 'USD' }: {
  items: RendimientoPorTickerItem[]
  cartera: string | null
  onSelectTicker: (item: RendimientoPorTickerItem) => void
  moneda?: 'USD' | 'ARS'
}) {
  const esARS = moneda === 'ARS'
  const [busqueda, setBusqueda] = useState('')

  const filtrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase()
    if (!q) return items
    return items.filter(it => it.ticker.toLowerCase().includes(q) || it.nombre.toLowerCase().includes(q))
  }, [items, busqueda])

  const columns: ColumnsType<RendimientoPorTickerItem> = [
    {
      title: 'Ticker',
      dataIndex: 'ticker',
      width: 100,
      fixed: 'left',
      sorter: (a, b) => a.ticker.localeCompare(b.ticker),
      render: (v: string) => <a>{v}</a>,
    },
    {
      title: 'Cantidad Actual',
      dataIndex: 'cantidad_actual',
      width: 130,
      align: 'right',
      sorter: (a, b) => a.cantidad_actual - b.cantidad_actual,
      render: formatCantidad,
    },
    {
      title: 'Precio Promedio',
      dataIndex: 'precio_promedio',
      width: 130,
      align: 'right',
      responsive: ['lg'],
      sorter: (a, b) => a.precio_promedio - b.precio_promedio,
      render: formatPrecio,
    },
    {
      title: 'Precio Actual',
      dataIndex: 'precio_actual',
      width: 120,
      align: 'right',
      responsive: ['md'],
      sorter: (a, b) => a.precio_actual - b.precio_actual,
      render: formatPrecio,
    },
    {
      title: 'Rendimiento USD %',
      dataIndex: 'rendimiento_simple_usd',
      width: 140,
      align: 'right',
      sorter: (a, b) => (a.rendimiento_simple_usd ?? 0) - (b.rendimiento_simple_usd ?? 0),
      render: celdaRendimiento,
    },
    {
      title: 'Rendimiento ARS %',
      dataIndex: 'rendimiento_simple_ars',
      width: 140,
      align: 'right',
      responsive: ['md'],
      sorter: (a, b) => (a.rendimiento_simple_ars ?? 0) - (b.rendimiento_simple_ars ?? 0),
      render: celdaRendimiento,
    },
    {
      title: 'Rendimiento ARS Real %',
      dataIndex: 'rendimiento_simple_ars_real',
      width: 150,
      align: 'right',
      responsive: ['lg'],
      sorter: (a, b) => (a.rendimiento_simple_ars_real ?? 0) - (b.rendimiento_simple_ars_real ?? 0),
      render: celdaRendimiento,
    },
    {
      title: `Valor Invertido (${moneda})`,
      dataIndex: esARS ? 'valor_invertido_ars' : 'valor_invertido_usd',
      width: 150,
      align: 'right',
      responsive: ['md'],
      sorter: (a, b) => (esARS ? a.valor_invertido_ars - b.valor_invertido_ars : a.valor_invertido_usd - b.valor_invertido_usd),
      render: (v: number) => (esARS ? formatARS(v) : formatUSD(v)),
    },
    {
      title: `Valor Actual (${moneda})`,
      dataIndex: esARS ? 'valor_actual_ars' : 'valor_actual_usd',
      width: 150,
      align: 'right',
      defaultSortOrder: 'descend',
      sorter: (a, b) => (esARS ? a.valor_actual_ars - b.valor_actual_ars : a.valor_actual_usd - b.valor_actual_usd),
      render: (v: number) => (esARS ? formatARS(v) : formatUSD(v)),
    },
  ]

  return (
    <Card
      title="Análisis por Ticker"
      size="small"
      style={{ background: '#161b22', border: '1px solid #30363d' }}
      styles={{ header: { color: '#c9d1d9', borderBottom: '1px solid #30363d' } }}
      extra={
        <Button
          icon={<DownloadOutlined />}
          onClick={() => exportarCSV(filtrados, cartera)}
          disabled={filtrados.length === 0}
        >
          Exportar
        </Button>
      }
    >
      <Input
        placeholder="Buscar ticker o nombre..."
        allowClear
        style={{ width: 260, marginBottom: 12 }}
        onChange={e => setBusqueda(e.target.value)}
      />
      {items.length === 0 ? (
        <Empty description="No hay posiciones activas" />
      ) : (
        <Table
          dataSource={filtrados}
          columns={columns}
          rowKey="ticker"
          size="small"
          scroll={{ x: 900 }}
          pagination={{ pageSize: 20, showTotal: t => `${t} posiciones activas` }}
          onRow={item => ({
            onClick: () => onSelectTicker(item),
            tabIndex: 0,
            style: { cursor: 'pointer' },
            onKeyDown: e => { if (e.key === 'Enter') onSelectTicker(item) },
          })}
        />
      )}
    </Card>
  )
}
