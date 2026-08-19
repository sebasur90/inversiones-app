import { useState, useEffect, useMemo } from 'react'
import dayjs from 'dayjs'
import {
  resolverAporteMensual,
  resolverFechaAlcanzable,
  resolverTasaNecesaria,
  type ParametrosSimulacion,
  type ResultadoSolverAporte,
  type ResultadoSolverFecha,
  type ResultadoSolverTasa,
} from '../../utils/proyeccion'
import { formatUSD, formatPct } from '../../utils'
import Card from '../ui/Card'
import Segmented from '../ui/Segmented'
import FormHelp from '../../help/components/FormHelp'
import InfoTooltip from '../../help/components/InfoTooltip'

type SolverMode = 'aporte' | 'fecha' | 'tasa'

interface SimuladorInversoProps {
  objetivoMontoCargado: number
  objetivoFechaLimiteCargada: string
  valorInicialCargado: number
  aporteMensualCargado: number
  tasaBaseCargada: number
  tasaBaseSource: 'configuracion' | 'historico' | 'fallback'
}

interface FormState {
  objetivo: number
  fechaObjetivo: string
  patrimonioInicial: number
  aporteMensual: number
  crecimientoAporteAnual: number
  rentabilidadAnual: number
}

interface Resultado {
  aporte?: ResultadoSolverAporte
  fecha?: ResultadoSolverFecha
  tasa?: ResultadoSolverTasa
}

function mensajeMotivo(motivo?: string): string {
  switch (motivo) {
    case 'sin_tiempo':
      return 'La fecha es pasada o hoy'
    case 'nunca':
      return 'Imposible alcanzar con estos parámetros'
    case 'fuera_de_rango':
      return 'Rentabilidad requerida fuera de rango'
    case 'ya_alcanzable_con_minimo':
      return 'Ya alcanzable al mínimo esperado'
    default:
      return 'No disponible'
  }
}

export default function SimuladorInverso({
  objetivoMontoCargado,
  objetivoFechaLimiteCargada,
  valorInicialCargado,
  aporteMensualCargado,
  tasaBaseCargada,
  tasaBaseSource,
}: SimuladorInversoProps) {
  const [mode, setMode] = useState<SolverMode>('aporte')
  const [form, setForm] = useState<FormState>({
    objetivo: objetivoMontoCargado,
    fechaObjetivo: objetivoFechaLimiteCargada,
    patrimonioInicial: valorInicialCargado,
    aporteMensual: aporteMensualCargado,
    crecimientoAporteAnual: 0,
    rentabilidadAnual: tasaBaseCargada,
  })

  // Actualizar cuando cambian los valores cargados (p.ej., al cambiar de cartera)
  useEffect(() => {
    setForm({
      objetivo: objetivoMontoCargado,
      fechaObjetivo: objetivoFechaLimiteCargada,
      patrimonioInicial: valorInicialCargado,
      aporteMensual: aporteMensualCargado,
      crecimientoAporteAnual: 0,
      rentabilidadAnual: tasaBaseCargada,
    })
  }, [
    objetivoMontoCargado,
    objetivoFechaLimiteCargada,
    valorInicialCargado,
    aporteMensualCargado,
    tasaBaseCargada,
  ])

  // Calcular meses restantes
  const hoy = dayjs()
  const fechaFin = dayjs(form.fechaObjetivo)
  const mesesRestantes = Math.max(0, Math.ceil(fechaFin.diff(hoy, 'month', true)))

  // Resolver según el modo activo
  const resultado: Resultado = useMemo(() => {
    const baseParams: Omit<ParametrosSimulacion, 'tasaAnualPct' | 'aporteMensualUsd'> = {
      valorInicialUsd: form.patrimonioInicial,
      crecimientoAporteAnualPct: form.crecimientoAporteAnual,
    }

    const result: Resultado = {}

    if (mode === 'aporte') {
      result.aporte = resolverAporteMensual(form.objetivo, mesesRestantes, {
        ...baseParams,
        tasaAnualPct: form.rentabilidadAnual,
      })
    } else if (mode === 'fecha') {
      result.fecha = resolverFechaAlcanzable(
        form.objetivo,
        {
          valorInicialUsd: form.patrimonioInicial,
          aporteMensualUsd: form.aporteMensual,
          crecimientoAporteAnualPct: form.crecimientoAporteAnual,
          tasaAnualPct: form.rentabilidadAnual,
        },
        1200,
        hoy.toDate()
      )
    } else if (mode === 'tasa') {
      result.tasa = resolverTasaNecesaria(form.objetivo, mesesRestantes, {
        ...baseParams,
        aporteMensualUsd: form.aporteMensual,
      })
    }

    return result
  }, [mode, form, mesesRestantes, hoy])

  const handleFormChange = (field: keyof FormState, value: any) => {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  return (
    <div>
      <h3 className="text-[13.5px] font-bold text-app-text mb-2.5 flex items-center gap-1.5">
        🔄 Simulador inverso
      </h3>

      <Card>
        <div className="mb-4">
          <label className="block text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2 flex items-center gap-1.5">
            ¿Qué querés resolver?
            <InfoTooltip term="objetivo_modo_solver" />
          </label>
          <Segmented<SolverMode>
            value={mode}
            onChange={setMode}
            options={[
              { value: 'aporte', label: 'Aporte requerido' },
              { value: 'fecha', label: 'Fecha alcanzable' },
              { value: 'tasa', label: 'Rentabilidad necesaria' },
            ]}
          />
        </div>

        {/* Grid de inputs */}
        <div className="grid grid-cols-2 gap-2 mb-4">
          {/* Objetivo USD */}
          <div>
            <FormHelp term="objetivo_monto" label="Objetivo (USD)" />
            <input
              type="number"
              min={0}
              value={form.objetivo}
              onChange={e => handleFormChange('objetivo', parseFloat(e.target.value) || 0)}
              className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-[12px] text-app-text outline-none focus:border-app-gold/60 tabular-nums"
            />
          </div>

          {/* Fecha objetivo */}
          <div>
            <FormHelp term="objetivo_fecha_limite" label="Fecha objetivo" />
            <input
              type="date"
              value={form.fechaObjetivo}
              onChange={e => handleFormChange('fechaObjetivo', e.target.value)}
              className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-[12px] text-app-text outline-none focus:border-app-gold/60"
            />
          </div>

          {/* Patrimonio inicial */}
          <div>
            <FormHelp term="objetivo_patrimonio_inicial" label="Patrimonio inicial (USD)" />
            <input
              type="number"
              min={0}
              value={form.patrimonioInicial}
              onChange={e => handleFormChange('patrimonioInicial', parseFloat(e.target.value) || 0)}
              className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-[12px] text-app-text outline-none focus:border-app-gold/60 tabular-nums"
            />
          </div>

          {/* Aporte mensual */}
          <div>
            <FormHelp term="objetivo_aporte_mensual" label="Aporte mensual (USD)" />
            <input
              type="number"
              min={0}
              step={10}
              value={form.aporteMensual}
              onChange={e => handleFormChange('aporteMensual', parseFloat(e.target.value) || 0)}
              disabled={mode === 'aporte'}
              className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-[12px] text-app-text outline-none focus:border-app-gold/60 tabular-nums disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>

          {/* Crecimiento del aporte anual */}
          <div>
            <label className="block text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">
              Crec. aporte anual (%)
            </label>
            <input
              type="number"
              min={-100}
              step={0.5}
              value={form.crecimientoAporteAnual}
              onChange={e => handleFormChange('crecimientoAporteAnual', parseFloat(e.target.value) || 0)}
              className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-[12px] text-app-text outline-none focus:border-app-gold/60 tabular-nums"
            />
          </div>

          {/* Rentabilidad anual */}
          <div>
            <FormHelp term="objetivo_rentabilidad_anual" label="Rentabilidad anual (%)" />
            <input
              type="number"
              min={-90}
              step={0.5}
              value={form.rentabilidadAnual}
              onChange={e => handleFormChange('rentabilidadAnual', parseFloat(e.target.value) || 0)}
              disabled={mode === 'tasa'}
              className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-[12px] text-app-text outline-none focus:border-app-gold/60 tabular-nums disabled:opacity-50 disabled:cursor-not-allowed"
            />
            {mode !== 'tasa' && (
              <div className="text-[8px] text-app-text-faint mt-0.5">
                Fuente: {tasaBaseSource}
              </div>
            )}
          </div>
        </div>

        {/* Resultado */}
        <div className="bg-app-surface-2 rounded-lg p-3 mt-4">
          {mode === 'aporte' && resultado.aporte ? (
            <div>
              <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">
                Aporte mensual requerido
              </div>
              {resultado.aporte.aporteMensualUsd != null ? (
                <div>
                  <div className="font-mono text-[16px] font-bold text-app-text tabular-nums">
                    {formatUSD(resultado.aporte.aporteMensualUsd)}
                  </div>
                  <div className="text-[9px] text-app-text-dim mt-1">
                    Para alcanzar {formatUSD(form.objetivo)} en {mesesRestantes} meses
                  </div>
                </div>
              ) : (
                <div className={`font-mono text-[14px] font-semibold tabular-nums ${resultado.aporte.motivo ? 'text-app-coral' : 'text-app-text'}`}>
                  {resultado.aporte.motivo ? mensajeMotivo(resultado.aporte.motivo) : '—'}
                </div>
              )}
            </div>
          ) : mode === 'fecha' && resultado.fecha ? (
            <div>
              <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">
                Fecha de alcance
              </div>
              {resultado.fecha.fecha ? (
                <div>
                  <div className="font-mono text-[16px] font-bold text-app-text tabular-nums">
                    {dayjs(resultado.fecha.fecha).format('MMM DD, YYYY')}
                  </div>
                  <div className="text-[9px] text-app-text-dim mt-1">
                    En {resultado.fecha.meses} meses ({resultado.fecha.meses && resultado.fecha.meses > mesesRestantes ? 'después' : 'antes'} del límite)
                  </div>
                </div>
              ) : (
                <div className={`font-mono text-[14px] font-semibold tabular-nums ${resultado.fecha.motivo ? 'text-app-coral' : 'text-app-text'}`}>
                  {resultado.fecha.motivo ? mensajeMotivo(resultado.fecha.motivo) : '—'}
                </div>
              )}
            </div>
          ) : mode === 'tasa' && resultado.tasa ? (
            <div>
              <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">
                Rentabilidad anual requerida
              </div>
              {resultado.tasa.tasaAnualPct != null ? (
                <div>
                  <div className="font-mono text-[16px] font-bold text-app-text tabular-nums">
                    {formatPct(resultado.tasa.tasaAnualPct)}
                  </div>
                  <div className="text-[9px] text-app-text-dim mt-1">
                    Para alcanzar {formatUSD(form.objetivo)} en {mesesRestantes} meses
                  </div>
                </div>
              ) : (
                <div className={`font-mono text-[14px] font-semibold tabular-nums ${resultado.tasa.motivo ? 'text-app-coral' : 'text-app-text'}`}>
                  {resultado.tasa.motivo ? mensajeMotivo(resultado.tasa.motivo) : '—'}
                </div>
              )}
            </div>
          ) : null}
        </div>
      </Card>
    </div>
  )
}
