import { Card, Col, Row, Typography, Alert, Tooltip } from 'antd'
import { ArrowUpOutlined, ArrowDownOutlined, WalletOutlined, BankOutlined, LineChartOutlined, ThunderboltOutlined, PercentageOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import type { InversionesResumen } from '../../api'
import { formatUSD, formatARS, formatPctRatio, TIPO_COLORS } from '../../utils'

const { Text } = Typography

const KPI_TOOLTIPS = {
  valor_actual: 'Valoración actual del portafolio a precio de mercado de hoy',
  total_invertido: 'Suma neta de todas las inversiones realizadas (compras menos ventas)',
  rendimiento_simple: 'Ganancia porcentual: (Valor actual + Ingresos - Total invertido) / Total invertido',
  xirr: 'Tasa interna de retorno anualizada. Considera el timing de cada flujo de dinero',
  twr: 'Rendimiento ponderado por tiempo. Mide retorno eliminando el efecto del timing de aportes',
}

function KpiCard({ title, icon, primary, secondary, deltaColor, tooltip }: {
  title: string; icon: React.ReactNode; primary: React.ReactNode; secondary?: React.ReactNode; deltaColor?: string; tooltip?: string
}) {
  return (
    <Card size="small" style={{ background: '#161b22', border: '1px solid #30363d', height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#8b949e' }}>
        <span style={{ fontSize: 13 }}>{icon}</span>
        <Text type="secondary" style={{ fontSize: 12 }}>{title}</Text>
        {tooltip && (
          <Tooltip title={tooltip} overlayStyle={{ maxWidth: 280 }}>
            <QuestionCircleOutlined style={{ fontSize: 11, color: '#6e7681', cursor: 'help' }} />
          </Tooltip>
        )}
      </div>
      <div style={{ fontSize: 24, fontWeight: 600, color: deltaColor ?? '#c9d1d9', marginTop: 6, lineHeight: 1.2 }}>
        {primary}
      </div>
      {secondary && <div style={{ fontSize: 11, color: '#8b949e', marginTop: 2 }}>{secondary}</div>}
    </Card>
  )
}

function deltaColorFor(value: number | null): string | undefined {
  if (value == null) return undefined
  if (value > 0) return TIPO_COLORS.ingreso
  if (value < 0) return TIPO_COLORS.egreso
  return TIPO_COLORS.neutro
}

function deltaIcon(value: number | null) {
  if (value == null || value === 0) return null
  return value > 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />
}

function DeltaValue({ value, extra }: { value: number | null; extra?: string }) {
  return (
    <span style={{ color: deltaColorFor(value) }}>
      {deltaIcon(value)} {formatPctRatio(value)}{extra ?? ''}
    </span>
  )
}

function RendimientoSecondary({ real }: { real: number | null }) {
  if (real == null) return <span>real: N/A</span>
  return <span>real: <DeltaValue value={real} /></span>
}

export default function InversionesKpis({ resumen, moneda = 'USD' }: { resumen: InversionesResumen | null; moneda?: 'USD' | 'ARS' }) {
  const esARS = moneda === 'ARS'

  const rendimiento = esARS ? resumen?.rendimiento_simple_ars ?? null : resumen?.rendimiento_simple_usd ?? null
  const xirr = esARS ? resumen?.xirr_ars ?? null : resumen?.xirr_usd ?? null
  const twr = esARS ? resumen?.twr_ars ?? null : resumen?.twr_usd ?? null

  return (
    <div style={{ marginBottom: 24 }}>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={5}>
          <KpiCard
            title="Valor actual"
            icon={<WalletOutlined />}
            primary={esARS ? formatARS(resumen?.valor_actual_ars ?? null) : formatUSD(resumen?.valor_actual_usd ?? null)}
            secondary={!esARS ? formatARS(resumen?.valor_actual_ars ?? null) : undefined}
            tooltip={KPI_TOOLTIPS.valor_actual}
          />
        </Col>
        <Col xs={24} sm={12} lg={5}>
          <KpiCard
            title="Total invertido"
            icon={<BankOutlined />}
            primary={esARS ? formatARS(resumen?.total_invertido_ars ?? null) : formatUSD(resumen?.total_invertido_usd ?? null)}
            tooltip={KPI_TOOLTIPS.total_invertido}
          />
        </Col>
        <Col xs={24} sm={12} lg={5}>
          <KpiCard
            title="Rendimiento simple"
            icon={<PercentageOutlined />}
            primary={!resumen ? '—' : <DeltaValue value={rendimiento} />}
            deltaColor={resumen ? deltaColorFor(rendimiento) : undefined}
            secondary={resumen && esARS ? <RendimientoSecondary real={resumen.rendimiento_simple_ars_real} /> : undefined}
            tooltip={KPI_TOOLTIPS.rendimiento_simple}
          />
        </Col>
        <Col xs={24} sm={12} lg={5}>
          <KpiCard
            title="XIRR (anualizado)"
            icon={<ThunderboltOutlined />}
            primary={!resumen ? '—' : <DeltaValue value={xirr} />}
            deltaColor={resumen ? deltaColorFor(xirr) : undefined}
            secondary={resumen && esARS ? <RendimientoSecondary real={resumen.xirr_ars_real} /> : undefined}
            tooltip={KPI_TOOLTIPS.xirr}
          />
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <KpiCard
            title="TWR"
            icon={<LineChartOutlined />}
            primary={!resumen ? '—' : <DeltaValue value={twr} />}
            deltaColor={resumen ? deltaColorFor(twr) : undefined}
            secondary={resumen && esARS ? <RendimientoSecondary real={resumen.twr_ars_real} /> : undefined}
            tooltip={KPI_TOOLTIPS.twr}
          />
        </Col>
      </Row>
      {resumen?.tiene_precios_desactualizados && (
        <Alert
          style={{ marginTop: 12 }}
          type="warning"
          showIcon
          message="Algunos precios usados tienen más de 45 días de antigüedad — los cálculos son aproximados."
        />
      )}
    </div>
  )
}
