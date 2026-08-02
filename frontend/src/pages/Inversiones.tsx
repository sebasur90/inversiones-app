import { useState } from 'react'
import { Alert, Button, Card, Col, Row, Select, Spin, Tabs, Typography, message, Modal, List, Badge, Tag } from 'antd'
import { SyncOutlined, ExclamationCircleOutlined, CheckCircleOutlined } from '@ant-design/icons'
import { useInversiones } from '../hooks/useInversiones'
import InversionesKpis from '../components/inversiones/InversionesKpis'
import ComparacionInversionChart from '../components/inversiones/ComparacionInversionChart'
import ExposicionGrid from '../components/inversiones/ExposicionGrid'
import MovimientosInversionTabla from '../components/inversiones/MovimientosInversionTabla'
import RendimientoPorTickerTabla from '../components/inversiones/RendimientoPorTickerTabla'
import TickerDetalleDrawer from '../components/inversiones/TickerDetalleDrawer'
import ObjetivoInversionPanel from '../components/inversiones/ObjetivoInversionPanel'
import type { RendimientoPorTickerItem, SyncErrorItem } from '../api'

const { Title, Text } = Typography

export default function Inversiones() {
  const {
    carteras,
    carteraSeleccionada,
    setCarteraSeleccionada,
    monedaSeleccionada,
    setMonedaSeleccionada,
    resumen,
    exposicion,
    movimientos,
    rendimientoPorTicker,
    loading,
    syncing,
    error,
    sincronizar,
    sinDatos,
  } = useInversiones()

  const [activeTab, setActiveTab] = useState('resumen')
  const [tickerFiltro, setTickerFiltro] = useState<string | null>(null)
  const [tickerDrawer, setTickerDrawer] = useState<RendimientoPorTickerItem | null>(null)
  const [erroresModal, setErroresModal] = useState<SyncErrorItem[]>([])
  const [advertenciasModal, setAdvertenciasModal] = useState<SyncErrorItem[]>([])
  const [resumenSync, setResumenSync] = useState<string>('')

  const verMovimientosDeTicker = (ticker: string) => {
    setTickerFiltro(ticker)
    setActiveTab('resumen')
    setTickerDrawer(null)
  }

  const handleSync = async () => {
    try {
      const resultado = await sincronizar()
      const advertencias = resultado.errores.filter(e => e.motivo.startsWith('Advertencia:'))
      const errores = resultado.errores.filter(e => !e.motivo.startsWith('Advertencia:'))
      const resumenTexto = `${resultado.movimientos} movimientos, ${resultado.instrumentos} instrumentos, ${resultado.precios} precios, ${resultado.indices_mercado} fechas con CER/MEP`
      setResumenSync(resumenTexto)
      setErroresModal(errores)
      setAdvertenciasModal(advertencias)

      if (errores.length > 0) {
        Modal.warning({
          title: `Sincronización completada con ${errores.length} fila${errores.length > 1 ? 's' : ''} inválida${errores.length > 1 ? 's' : ''}`,
          width: 800,
          content: (
            <div style={{ marginTop: 16 }}>
              <Text>
                Se cargaron: <strong>{resumenTexto}</strong>
              </Text>
              <div style={{ marginTop: 16 }}>
                <Text strong style={{ display: 'block', marginBottom: 8 }}>Filas con errores:</Text>
                <List
                  size="small"
                  dataSource={errores}
                  renderItem={(item) => (
                    <List.Item>
                      <Badge status="error" />
                      <Text>
                        <strong>Fila {item.fila}:</strong> {item.motivo}
                      </Text>
                    </List.Item>
                  )}
                />
              </div>
              {advertencias.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <Text strong style={{ display: 'block', marginBottom: 8 }}>Advertencias:</Text>
                  <List
                    size="small"
                    dataSource={advertencias}
                    renderItem={(item) => (
                      <List.Item>
                        <Badge status="warning" />
                        <Text>{item.motivo}</Text>
                      </List.Item>
                    )}
                  />
                </div>
              )}
            </div>
          ),
        })
      } else if (advertencias.length > 0) {
        Modal.info({
          title: 'Sincronización completada',
          width: 600,
          content: (
            <div style={{ marginTop: 16 }}>
              <Text>
                Se cargaron: <strong>{resumenTexto}</strong>
              </Text>
              <div style={{ marginTop: 16 }}>
                <Text strong style={{ display: 'block', marginBottom: 8 }}>Advertencias:</Text>
                <List
                  size="small"
                  dataSource={advertencias}
                  renderItem={(item) => (
                    <List.Item>
                      <Badge status="warning" />
                      <Text>{item.motivo}</Text>
                    </List.Item>
                  )}
                />
              </div>
            </div>
          ),
        })
      } else {
        message.success(`Sincronizado: ${resumenTexto}.`)
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detail || 'Error al sincronizar el Google Sheet')
    }
  }

  const carteraOptions = [
    { value: '', label: 'Consolidado' },
    ...carteras.map(c => ({ value: c.nombre, label: c.nombre })),
  ]

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <Title level={3} style={{ margin: 0, color: '#c9d1d9' }}>Inversiones</Title>
          {!sinDatos && (
            <>
              <Select
                value={carteraSeleccionada ?? ''}
                onChange={v => setCarteraSeleccionada(v || null)}
                options={carteraOptions}
                style={{ width: 200 }}
              />
              <Select
                value={monedaSeleccionada}
                onChange={v => setMonedaSeleccionada(v as 'USD' | 'ARS')}
                options={[
                  { value: 'USD', label: 'USD' },
                  { value: 'ARS', label: 'ARS' },
                ]}
                style={{ width: 100 }}
              />
            </>
          )}
        </div>
        <Button type="primary" icon={<SyncOutlined spin={syncing} />} loading={syncing} onClick={handleSync}>
          Sincronizar Sheet
        </Button>
      </div>

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />}

      {sinDatos ? (
        <Card style={{ background: '#161b22', border: '1px solid #30363d', textAlign: 'center', padding: 40 }}>
          <Text style={{ fontSize: 15, color: '#c9d1d9' }}>
            Sincronizá tu Google Sheet para empezar
          </Text>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">
              Todavía no hay movimientos de inversión importados. Usá el botón "Sincronizar Sheet" para traer los datos.
            </Text>
          </div>
        </Card>
      ) : loading ? (
        <div style={{ textAlign: 'center', paddingTop: 80 }}><Spin size="large" /></div>
      ) : (
        <>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: 'resumen',
                label: 'Resumen',
                children: (
                  <>
                    <InversionesKpis resumen={resumen} moneda={monedaSeleccionada} />

                    <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                      <Col xs={24}>
                        <ComparacionInversionChart resumen={resumen} />
                      </Col>
                    </Row>

                    <div style={{ marginBottom: 16 }}>
                      <ExposicionGrid ejes={exposicion.ejes} moneda={monedaSeleccionada} />
                    </div>

                    <MovimientosInversionTabla movimientos={movimientos} tickerSeleccionado={tickerFiltro} />
                  </>
                ),
              },
              {
                key: 'ticker',
                label: 'Análisis por Ticker',
                children: (
                  <RendimientoPorTickerTabla
                    items={rendimientoPorTicker}
                    cartera={carteraSeleccionada}
                    onSelectTicker={setTickerDrawer}
                    moneda={monedaSeleccionada}
                  />
                ),
              },
              {
                key: 'objetivo',
                label: 'Objetivo',
                disabled: carteraSeleccionada === null,
                children: (
                  <ObjetivoInversionPanel cartera={carteraSeleccionada} />
                ),
              },
            ]}
          />

          <TickerDetalleDrawer
            item={tickerDrawer}
            movimientos={movimientos}
            open={tickerDrawer != null}
            onClose={() => setTickerDrawer(null)}
            onVerMovimientos={verMovimientosDeTicker}
            moneda={monedaSeleccionada}
          />
        </>
      )}
    </div>
  )
}
