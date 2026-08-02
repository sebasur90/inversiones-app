import { useMemo } from 'react'
import { Button, Descriptions, Drawer, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { MovimientoInversion, RendimientoPorTickerItem } from '../../api'
import { formatARS, formatPctRatio, formatUSD, TIPO_COLORS } from '../../utils'

const { Title, Text } = Typography

const TIPO_LABELS: Record<string, string> = {
  compra: 'Compra',
  venta: 'Venta',
  dividendo: 'Dividendo',
  cupon: 'Cupón',
  amortizacion: 'Amortización',
}

const TIPO_TAG_COLORS: Record<string, string> = {
  compra: 'red',
  venta: 'green',
  dividendo: 'blue',
  cupon: 'blue',
  amortizacion: 'purple',
}

function useDrawerWidth() {
  if (typeof window === 'undefined') return '50%'
  const w = window.innerWidth
  if (w < 576) return '90%'
  if (w < 992) return '60%'
  return '50%'
}

export default function TickerDetalleDrawer({ item, movimientos, open, onClose, onVerMovimientos, moneda = 'USD' }: {
  item: RendimientoPorTickerItem | null
  movimientos: MovimientoInversion[]
  open: boolean
  onClose: () => void
  onVerMovimientos: (ticker: string) => void
  moneda?: 'USD' | 'ARS'
}) {
  const esARS = moneda === 'ARS'
  const movimientosTicker = useMemo(
    () => item
      ? movimientos
        .filter(m => m.ticker === item.ticker)
        .sort((a, b) => b.fecha.localeCompare(a.fecha))
      : [],
    [movimientos, item],
  )

  const totales = useMemo(() => {
    let comprada = 0
    let vendida = 0
    let montoComprado = 0
    for (const m of movimientosTicker) {
      const cantidad = m.cantidad ?? 0
      if (m.tipo_movimiento === 'compra') {
        comprada += cantidad
        montoComprado += cantidad * m.precio
      } else if (m.tipo_movimiento === 'venta' || m.tipo_movimiento === 'amortizacion') {
        vendida += cantidad
      }
    }
    return {
      comprada,
      vendida,
      promedioCompra: comprada > 0 ? montoComprado / comprada : null,
    }
  }, [movimientosTicker])

  const columns: ColumnsType<MovimientoInversion> = [
    { title: 'Fecha', dataIndex: 'fecha', width: 100 },
    {
      title: 'Tipo',
      dataIndex: 'tipo_movimiento',
      width: 110,
      render: (v: string) => <Tag color={TIPO_TAG_COLORS[v] || 'default'}>{TIPO_LABELS[v] || v}</Tag>,
    },
    { title: 'Cantidad', dataIndex: 'cantidad', width: 90, align: 'right', render: v => v ?? '—' },
    { title: 'Precio', dataIndex: 'precio', width: 100, align: 'right', render: (v: number) => v.toLocaleString('es-AR', { maximumFractionDigits: 6 }) },
    { title: 'Comisión', dataIndex: 'comision', width: 90, align: 'right', render: v => v ? Number(v).toLocaleString('es-AR') : '—' },
    { title: 'Moneda', dataIndex: 'moneda', width: 70 },
  ]

  if (!item) return null

  const valorInvertido = esARS ? item.valor_invertido_ars : item.valor_invertido_usd
  const valorActual = esARS ? item.valor_actual_ars : item.valor_actual_usd
  const rendimiento = esARS ? item.rendimiento_simple_ars : item.rendimiento_simple_usd
  const formatMoneda = esARS ? formatARS : formatUSD
  const pnlAbsoluto = valorActual - valorInvertido
  const colorPnl = pnlAbsoluto > 0 ? TIPO_COLORS.ingreso : pnlAbsoluto < 0 ? TIPO_COLORS.egreso : TIPO_COLORS.neutro
  const iconoPnl = pnlAbsoluto > 0 ? '↑' : pnlAbsoluto < 0 ? '↓' : ''

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={useDrawerWidth()}
      styles={{
        content: { background: '#161b22' },
        header: { background: '#161b22', borderBottom: '1px solid #30363d' },
        body: { background: '#161b22' },
      }}
      title={
        <div>
          <Title level={4} style={{ margin: 0, color: '#c9d1d9' }}>{item.ticker}</Title>
          <Text type="secondary">{item.nombre}</Text>
        </div>
      }
    >
      <Descriptions
        size="small"
        column={2}
        style={{ marginBottom: 20 }}
        items={[
          { key: 'tipo', label: 'Tipo', children: item.tipo_instrumento },
          { key: 'mercado', label: 'Mercado', children: item.mercado },
          { key: 'moneda', label: 'Moneda del instrumento', children: item.moneda },
          ...(item.sector ? [{ key: 'sector', label: 'Sector', children: item.sector }] : []),
          ...(item.pais ? [{ key: 'pais', label: 'País', children: item.pais }] : []),
        ]}
      />

      <Title level={5} style={{ color: '#c9d1d9' }}>Resumen de posición</Title>
      <Descriptions
        size="small"
        column={2}
        bordered
        style={{ marginBottom: 24 }}
        items={[
          { key: 'cantidad', label: 'Cantidad actual', children: item.cantidad_actual.toLocaleString('es-AR', { maximumFractionDigits: 8 }) },
          { key: 'precio_prom', label: 'Precio promedio', children: item.precio_promedio.toLocaleString('es-AR', { maximumFractionDigits: 6 }) },
          { key: 'precio_actual', label: 'Precio actual', children: item.precio_actual.toLocaleString('es-AR', { maximumFractionDigits: 6 }) },
          { key: 'valor_invertido', label: `Valor invertido (${moneda})`, children: formatMoneda(valorInvertido) },
          { key: 'valor_actual', label: `Valor actual (${moneda})`, children: formatMoneda(valorActual) },
          {
            key: 'pnl',
            label: `P&L (${moneda})`,
            children: (
              <span style={{ color: colorPnl, fontWeight: 600 }}>
                {iconoPnl} {formatMoneda(pnlAbsoluto)} ({formatPctRatio(rendimiento)})
              </span>
            ),
          },
        ]}
      />

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <Title level={5} style={{ color: '#c9d1d9', margin: 0 }}>Timeline de movimientos</Title>
        <Button size="small" onClick={() => onVerMovimientos(item.ticker)}>
          Ver todos los movimientos de este ticker
        </Button>
      </div>
      <Table
        dataSource={movimientosTicker}
        columns={columns}
        rowKey="id"
        size="small"
        pagination={{ pageSize: 10 }}
        scroll={{ x: 600 }}
        summary={() => (
          <Table.Summary fixed>
            <Table.Summary.Row>
              <Table.Summary.Cell index={0} colSpan={2}>Totales</Table.Summary.Cell>
              <Table.Summary.Cell index={1} align="right">
                +{totales.comprada.toLocaleString('es-AR', { maximumFractionDigits: 8 })} / -{totales.vendida.toLocaleString('es-AR', { maximumFractionDigits: 8 })}
              </Table.Summary.Cell>
              <Table.Summary.Cell index={2} align="right">
                {totales.promedioCompra != null ? totales.promedioCompra.toLocaleString('es-AR', { maximumFractionDigits: 6 }) : '—'}
              </Table.Summary.Cell>
              <Table.Summary.Cell index={3} colSpan={2} />
            </Table.Summary.Row>
          </Table.Summary>
        )}
      />
    </Drawer>
  )
}
