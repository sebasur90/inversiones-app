import { useState, useEffect } from 'react'
import { Modal, Form, Input, InputNumber, DatePicker } from 'antd'
import dayjs from 'dayjs'
import type { ObjetivoInversion, ObjetivoInversionPayload } from '../../api'

const EMOJIS = ['🎯', '🚗', '🪑', '🏠', '✈️', '💻', '📱', '🎓', '🏖️', '💰', '🛒', '🏋️', '🎸', '📷', '🚀']

interface Props {
  open: boolean
  objetivo: ObjetivoInversion | null  // null = crear
  onGuardar: (payload: ObjetivoInversionPayload) => Promise<void>
  onCancelar: () => void
}

export default function ObjetivoInversionModal({
  open,
  objetivo,
  onGuardar,
  onCancelar,
}: Props) {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [selectedIcon, setSelectedIcon] = useState<string>('🎯')

  useEffect(() => {
    if (open) {
      const initialIcon = objetivo?.icono ?? '🎯'
      form.setFieldsValue(
        objetivo
          ? {
              nombre: objetivo.nombre,
              icono: initialIcon,
              monto_usd: objetivo.monto_usd,
              fecha_limite: dayjs(objetivo.fecha_limite),
            }
          : { icono: initialIcon },
      )
      setSelectedIcon(initialIcon)
    }
  }, [open, objetivo, form])

  const handleOk = async () => {
    const values = await form.validateFields()
    setLoading(true)
    try {
      await onGuardar({
        nombre: values.nombre,
        icono: values.icono ?? '🎯',
        monto_usd: values.monto_usd,
        fecha_limite: (values.fecha_limite as dayjs.Dayjs).format('YYYY-MM-DD'),
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      open={open}
      title={objetivo ? 'Editar objetivo de inversión' : 'Nuevo objetivo de inversión'}
      onOk={handleOk}
      onCancel={onCancelar}
      okText="Guardar"
      cancelText="Cancelar"
      confirmLoading={loading}
      width={480}
    >
      <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
        {/* Selector de emoji */}
        <Form.Item name="icono" label="Ícono">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {EMOJIS.map(e => (
              <span
                key={e}
                onClick={() => {
                  form.setFieldValue('icono', e)
                  setSelectedIcon(e)
                }}
                style={{
                  fontSize: 22,
                  cursor: 'pointer',
                  padding: '2px 6px',
                  borderRadius: 6,
                  background: selectedIcon === e ? '#1d3557' : 'transparent',
                  border: selectedIcon === e ? '1px solid #58a6ff' : '1px solid transparent',
                }}
              >
                {e}
              </span>
            ))}
          </div>
        </Form.Item>

        <Form.Item name="nombre" label="Nombre" rules={[{ required: true, message: 'Ingresá un nombre' }]}>
          <Input placeholder="ej: Fondo de emergencia" />
        </Form.Item>

        <div style={{ display: 'flex', gap: 12 }}>
          <Form.Item
            name="monto_usd"
            label="Monto (USD)"
            style={{ flex: 1 }}
            rules={[{ required: true, message: 'Requerido' }]}
          >
            <InputNumber min={1} style={{ width: '100%' }} prefix="USD" />
          </Form.Item>

          <Form.Item
            name="fecha_limite"
            label="Fecha límite"
            style={{ flex: 1 }}
            rules={[{ required: true, message: 'Requerido' }]}
          >
            <DatePicker picker="month" style={{ width: '100%' }} format="MMM YYYY" />
          </Form.Item>
        </div>
      </Form>
    </Modal>
  )
}
