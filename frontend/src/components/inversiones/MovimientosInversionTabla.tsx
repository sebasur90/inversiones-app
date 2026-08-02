import { useEffect, useMemo, useState } from 'react'
import { Card, Input, Select, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { MovimientoInversion } from '../../api'
import { formatUSD } from '../../utils'

const TIPO_LABELS: Record<string, string> = {
  compra: 'Compra',
  venta: 'Venta',
  dividendo: 'Dividendo',
  cupon: 'Cupón',
  amortizacion: 'Amortización',
}

const TIPO_COLORS: Record<string, string> = {
  compra: 'red',
  venta: 'green',
  dividendo: 'blue',
  cupon: 'blue',
  amortizacion: 'purple',
}

export default function MovimientosInversionTabla({ movimientos, tickerSeleccionado }: {
  movimientos: MovimientoInversion[]
  tickerSeleccionado?: string | null
}) {
  const [ticker, setTicker] = useState<string | undefined>()
  const [tipo, setTipo] = useState<string | undefined>()
  const [busqueda, setBusqueda] = useState('')

  useEffect(() => {
    if (tickerSeleccionado) setTicker(tickerSeleccionado)
  }, [tickerSeleccionado])

  const tickers = useMemo(
    () => Array.from(new Set(movimientos.map(m => m.ticker))).sort(),
    [movimientos],
  )

  const filtrados = useMemo(() => movimientos.filter(m =>
    (!ticker || m.ticker === ticker)
    && (!tipo || m.tipo_movimiento === tipo)
    && (!busqueda || m.ticker.toLowerCase().includes(busqueda.toLowerCase()) || m.cartera.toLowerCase().includes(busqueda.toLowerCase())),
  ), [movimientos, ticker, tipo, busqueda])

  const columns: ColumnsType<MovimientoInversion> = [
    { title: 'Fecha', dataIndex: 'fecha', width: 100, sorter: (a, b) => a.fecha.localeCompare(b.fecha) },
    { title: 'Cartera', dataIndex: 'cartera', width: 140, ellipsis: true },
    { title: 'Ticker', dataIndex: 'ticker', width: 110 },
    {
      title: 'Tipo',
      dataIndex: 'tipo_movimiento',
      width: 120,
      render: (v: string) => <Tag color={TIPO_COLORS[v] || 'default'}>{TIPO_LABELS[v] || v}</Tag>,
    },
    { title: 'Cantidad', dataIndex: 'cantidad', width: 100, align: 'right', render: v => v ?? '—' },
    {
      title: 'Precio',
      dataIndex: 'precio',
      width: 130,
      align: 'right',
      render: (v: number, row) => row.moneda === 'USD' ? formatUSD(v) : `$${v.toLocaleString('es-AR')}`,
    },
    { title: 'Moneda', dataIndex: 'moneda', width: 80 },
    { title: 'Comisión', dataIndex: 'comision', width: 100, align: 'right', render: v => v ? Number(v).toLocaleString('es-AR') : '—' },
  ]

  return (
    <Card
      title="Movimientos"
      size="small"
      style={{ background: '#161b22', border: '1px solid #30363d' }}
      styles={{ header: { color: '#c9d1d9', borderBottom: '1px solid #30363d' } }}
    >
      <Space wrap style={{ marginBottom: 12 }}>
        <Select
          placeholder="Ticker"
          allowClear
          value={ticker}
          style={{ width: 140 }}
          options={tickers.map(t => ({ value: t, label: t }))}
          onChange={setTicker}
        />
        <Select
          placeholder="Tipo"
          allowClear
          style={{ width: 160 }}
          options={Object.entries(TIPO_LABELS).map(([value, label]) => ({ value, label }))}
          onChange={setTipo}
        />
        <Input
          placeholder="Buscar cartera/ticker..."
          style={{ width: 220 }}
          allowClear
          onChange={e => setBusqueda(e.target.value)}
        />
      </Space>
      <Table
        dataSource={filtrados}
        columns={columns}
        rowKey="id"
        size="small"
        scroll={{ x: 800 }}
        pagination={{ pageSize: 20, showTotal: t => `${t} movimientos` }}
      />
    </Card>
  )
}
