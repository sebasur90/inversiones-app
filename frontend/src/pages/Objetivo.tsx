import { useState } from 'react'
import dayjs from 'dayjs'
import { useInversionesContext } from '../context/InversionesContext'
import { useObjetivoInversion } from '../hooks/useObjetivoInversion'
import type { ObjetivoInversionPayload } from '../api'
import { formatUSD } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Button from '../components/ui/Button'
import IconButton from '../components/ui/IconButton'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import AportesChart from '../components/charts/AportesChart'
import ObjetivoModal from '../components/inversiones/ObjetivoModal'
import { Icon } from '../components/icons/Icons'

export default function Objetivo() {
  const { carteras, carteraSeleccionada, setCarteraSeleccionada, showToast } = useInversionesContext()
  const { objetivo, aportesHistoricos, loading, crear, editar, eliminar } = useObjetivoInversion(carteraSeleccionada)
  const [modalOpen, setModalOpen] = useState(false)
  const [editando, setEditando] = useState(false)

  if (!carteraSeleccionada) {
    return (
      <div className="pb-4">
        <ScreenHeader title="Objetivo" />
        <EmptyState
          title="Elegí una cartera"
          description="Los objetivos se definen por cartera, no aplican al Consolidado."
        />
        <div className="flex flex-col gap-1.5 px-4">
          {carteras.map(c => (
            <button
              key={c.nombre}
              onClick={() => setCarteraSeleccionada(c.nombre)}
              className="text-left px-3.5 py-3 rounded-xl text-[13.5px] font-semibold text-app-text bg-app-surface border border-app-border"
            >
              {c.nombre}
            </button>
          ))}
        </div>
      </div>
    )
  }

  const handleCrear = async (payload: ObjetivoInversionPayload) => {
    try {
      await crear(payload)
      showToast('Objetivo creado correctamente')
      setModalOpen(false)
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Error creando objetivo', 'error')
    }
  }

  const handleEditar = async (payload: ObjetivoInversionPayload) => {
    try {
      await editar(payload)
      showToast('Objetivo actualizado correctamente')
      setEditando(false)
      setModalOpen(false)
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Error editando objetivo', 'error')
    }
  }

  const handleEliminar = async () => {
    if (!window.confirm('¿Eliminar este objetivo?')) return
    try {
      await eliminar()
      showToast('Objetivo eliminado correctamente')
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Error eliminando objetivo', 'error')
    }
  }

  const progreso = objetivo ? Math.min((objetivo.valor_actual_usd / objetivo.monto_usd) * 100, 100) : 0

  return (
    <div className="pb-4">
      <ScreenHeader title="Objetivo" />

      {loading ? (
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      ) : !objetivo ? (
        <EmptyState
          title="Esta cartera no tiene un objetivo definido"
          action={
            <Button
              onClick={() => {
                setEditando(false)
                setModalOpen(true)
              }}
            >
              Definir objetivo
            </Button>
          }
        />
      ) : (
        <>
          <div className="flex items-center gap-3 mb-4">
            <div className="w-[46px] h-[46px] rounded-2xl bg-app-gold-soft flex items-center justify-center text-[21px] shrink-0">{objetivo.icono}</div>
            <div className="flex-1 min-w-0">
              <div className="font-display text-[18px] font-semibold text-app-text truncate">{objetivo.nombre}</div>
              <div className="text-[11.5px] text-app-text-dim">Meta al {dayjs(objetivo.fecha_limite).format('MMM YYYY')} · cartera {carteraSeleccionada}</div>
            </div>
            <IconButton
              onClick={() => {
                setEditando(true)
                setModalOpen(true)
              }}
              aria-label="Editar objetivo"
            >
              <Icon name="edit" className="w-4 h-4" />
            </IconButton>
            <IconButton onClick={handleEliminar} aria-label="Eliminar objetivo" tone="danger">
              <Icon name="trash" className="w-4 h-4" />
            </IconButton>
          </div>

          <Card>
            <div className="flex items-center gap-5">
              <div
                className="relative w-[130px] h-[130px] rounded-full shrink-0"
                style={{ background: `conic-gradient(${objetivo.alcanzable ? '#d8b14a' : '#e2665a'} 0% ${progreso}%, #223028 ${progreso}% 100%)` }}
              >
                <div className="absolute inset-3.5 rounded-full bg-app-surface flex flex-col items-center justify-center">
                  <b className="font-mono text-[21px] text-app-text tabular-nums">{progreso.toFixed(0)}%</b>
                  <span className="text-[9px] text-app-text-dim mt-0.5">completado</span>
                </div>
              </div>
              <div className="flex-1 flex flex-col gap-2.5 min-w-0">
                <div>
                  <b className="font-mono text-[14px] text-app-text tabular-nums block">
                    {formatUSD(objetivo.valor_actual_usd)}
                  </b>
                  <span className="text-[10px] uppercase tracking-wide text-app-text-dim">de {formatUSD(objetivo.monto_usd)}</span>
                </div>
                <div>
                  <b className="font-mono text-[14px] text-app-text tabular-nums block">{objetivo.meses_restantes} meses</b>
                  <span className="text-[10px] uppercase tracking-wide text-app-text-dim">Restantes</span>
                </div>
                <span className={`inline-flex items-center gap-1.5 font-bold text-[11px] px-2.5 py-1.5 rounded-lg w-fit ${objetivo.alcanzable ? 'bg-app-teal-soft text-app-teal' : 'bg-app-coral-soft text-app-coral'}`}>
                  <Icon name={objetivo.alcanzable ? 'up' : 'down'} className="w-3 h-3" />
                  {objetivo.meses_restantes === 0 ? 'Fecha límite vencida' : objetivo.alcanzable ? 'Alcanzable' : 'En riesgo'}
                </span>
              </div>
            </div>
          </Card>

          <div className="grid grid-cols-2 gap-2 my-3.5">
            <div className="bg-app-surface border border-app-border rounded-[13px] p-2.5">
              <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">Aporte prom./mes</div>
              <div className="font-mono text-[15px] font-bold text-app-text tabular-nums">{formatUSD(objetivo.aporte_mensual_promedio_usd)}</div>
            </div>
            <div className="bg-app-surface border border-app-border rounded-[13px] p-2.5">
              <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">Necesario/mes</div>
              <div className={`font-mono text-[15px] font-bold tabular-nums ${objetivo.alcanzable ? 'text-app-text' : 'text-app-coral'}`}>
                {objetivo.aporte_mensual_necesario_usd != null ? formatUSD(objetivo.aporte_mensual_necesario_usd) : '—'}
              </div>
            </div>
          </div>

          <h3 className="text-[13.5px] font-bold text-app-text mb-2.5">Aportes históricos</h3>
          <Card>
            <AportesChart aportesHistoricos={aportesHistoricos} montoObjetivo={objetivo.monto_usd} />
          </Card>
        </>
      )}

      <ObjetivoModal
        open={modalOpen}
        objetivo={editando ? objetivo : null}
        onGuardar={editando ? handleEditar : handleCrear}
        onCancelar={() => {
          setModalOpen(false)
          setEditando(false)
        }}
      />
    </div>
  )
}
