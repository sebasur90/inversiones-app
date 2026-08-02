import { useState } from 'react'
import { Button, Popconfirm, Alert, Spin, Empty } from 'antd'
import { EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { useObjetivoInversion } from '../../hooks/useObjetivoInversion'
import ObjetivoInversionModal from './ObjetivoInversionModal'
import AportesHistoricosChart from './AportesHistoricosChart'
import { formatUSD } from '../../utils'
import dayjs from 'dayjs'
import type { ObjetivoInversionPayload } from '../../api'
import { message } from 'antd'

interface Props {
  cartera: string | null
}

export default function ObjetivoInversionPanel({ cartera }: Props) {
  const { objetivo, aportesHistoricos, loading, error, crear, editar, eliminar } = useObjetivoInversion(cartera)
  const [modalOpen, setModalOpen] = useState(false)
  const [editandoObjetivo, setEditandoObjetivo] = useState(false)

  if (!cartera) {
    return <Empty description="Selecciona una cartera para ver el objetivo" />
  }

  const handleCrear = async (payload: ObjetivoInversionPayload) => {
    try {
      await crear(payload)
      message.success('Objetivo creado correctamente')
      setModalOpen(false)
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Error creando objetivo')
    }
  }

  const handleEditar = async (payload: ObjetivoInversionPayload) => {
    try {
      await editar(payload)
      message.success('Objetivo actualizado correctamente')
      setEditandoObjetivo(false)
      setModalOpen(false)
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Error editando objetivo')
    }
  }

  const handleEliminar = async () => {
    try {
      await eliminar()
      message.success('Objetivo eliminado correctamente')
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Error eliminando objetivo')
    }
  }

  if (loading) {
    return <Spin />
  }

  if (error && !objetivo && !aportesHistoricos) {
    return <Alert type="error" message={error} />
  }

  if (!objetivo && !aportesHistoricos) {
    return (
      <Empty
        description="Esta cartera no tiene un objetivo definido"
        style={{ marginTop: 40 }}
      >
        <Button type="primary" onClick={() => {
          setEditandoObjetivo(false)
          setModalOpen(true)
        }}>
          Definir objetivo
        </Button>
      </Empty>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {objetivo ? (
        <>
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 32 }}>{objetivo.icono}</span>
            <div style={{ flex: 1 }}>
              <h2 style={{ margin: 0, color: '#e6edf3', fontSize: 20 }}>{objetivo.nombre}</h2>
              <span style={{ color: '#8b949e', fontSize: 12 }}>
                Fecha límite: {dayjs(objetivo.fecha_limite).format('MMM YYYY')}
              </span>
            </div>
            <Button icon={<EditOutlined />} onClick={() => {
              setEditandoObjetivo(true)
              setModalOpen(true)
            }}>
              Editar
            </Button>
            <Popconfirm
              title="¿Eliminar este objetivo?"
              onConfirm={handleEliminar}
              okText="Eliminar"
              cancelText="Cancelar"
              okButtonProps={{ danger: true }}
            >
              <Button icon={<DeleteOutlined />} danger />
            </Popconfirm>
          </div>

          {/* Métricas */}
          <div style={{ display: 'flex', gap: 12 }}>
            <MetricaCard
              label="Monto objetivo"
              value={formatUSD(objetivo.monto_usd)}
              success={objetivo.alcanzable}
            />
            <MetricaCard
              label="Valor actual"
              value={formatUSD(objetivo.valor_actual_usd)}
              success={objetivo.alcanzable}
            />
            <MetricaCard
              label="Falta"
              value={formatUSD(objetivo.deficit_usd)}
              success={objetivo.alcanzable}
            />
            <MetricaCard
              label="Fecha límite"
              value={dayjs(objetivo.fecha_limite).format('MMM YYYY')}
              success={objetivo.alcanzable}
            />
          </div>

          {/* Barra de progreso */}
          <div style={{
            background: '#161b22',
            border: '1px solid #30363d',
            borderRadius: 6,
            padding: 12,
          }}>
            <div style={{ marginBottom: 8, display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
              <span style={{ color: '#8b949e' }}>Progreso</span>
              <span style={{ color: '#e6edf3', fontWeight: 600 }}>
                {formatUSD(objetivo.valor_actual_usd)} / {formatUSD(objetivo.monto_usd)}
              </span>
            </div>
            <div style={{
              background: '#0d1117',
              borderRadius: 4,
              height: 8,
              overflow: 'hidden',
            }}>
              <div style={{
                height: '100%',
                width: `${Math.min((objetivo.valor_actual_usd / objetivo.monto_usd) * 100, 100)}%`,
                background: objetivo.alcanzable ? '#3fb950' : '#f85149',
                transition: 'width 0.3s',
              }} />
            </div>
          </div>

          {/* Banner de estado */}
          {objetivo.meses_restantes === 0 ? (
            <Alert
              type="error"
              message="⏰ La fecha límite ya pasó."
              showIcon={false}
            />
          ) : objetivo.alcanzable ? (
            <Alert
              type="success"
              message={
                <>
                  ✅ Al ritmo actual (<strong>${objetivo.aporte_mensual_promedio_usd.toLocaleString('es-AR')}/mes</strong>), proyectás <strong>{formatUSD(objetivo.proyeccion_usd)}</strong> para {dayjs(objetivo.fecha_limite).format('MMM YYYY')}.
                </>
              }
              showIcon={false}
            />
          ) : (
            <Alert
              type="error"
              message={
                <>
                  🔴 No llegás: proyectás <strong>{formatUSD(objetivo.proyeccion_usd)}</strong>, te faltarían <strong>{formatUSD(objetivo.deficit_usd)}</strong>. Necesitarías aportar <strong>${objetivo.aporte_mensual_necesario_usd?.toLocaleString('es-AR')}/mes</strong> en vez de <strong>${objetivo.aporte_mensual_promedio_usd.toLocaleString('es-AR')}/mes</strong> actuales.
                </>
              }
              showIcon={false}
            />
          )}
        </>
      ) : null}

      {/* Gráfico de aportes */}
      {aportesHistoricos && (
        <AportesHistoricosChart
          aportesHistoricos={aportesHistoricos}
          montoObjetivo={objetivo?.monto_usd}
        />
      )}

      {/* Modal */}
      <ObjetivoInversionModal
        open={modalOpen}
        objetivo={editandoObjetivo ? objetivo : null}
        onGuardar={editandoObjetivo ? handleEditar : handleCrear}
        onCancelar={() => {
          setModalOpen(false)
          setEditandoObjetivo(false)
        }}
      />
    </div>
  )
}

function MetricaCard({ label, value, success }: { label: string; value: string; success?: boolean }) {
  const borderColor = success === undefined ? '#30363d' : success ? '#3fb950' : '#f85149'
  return (
    <div
      style={{
        flex: 1,
        background: '#161b22',
        border: `1px solid ${borderColor}`,
        borderRadius: 6,
        padding: '10px 14px',
        textAlign: 'center',
      }}
    >
      <div style={{ color: '#8b949e', fontSize: 11 }}>{label}</div>
      <div style={{ color: '#e6edf3', fontSize: 15, fontWeight: 600, marginTop: 2 }}>{value}</div>
    </div>
  )
}
