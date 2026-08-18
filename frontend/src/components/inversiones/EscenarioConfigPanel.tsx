import { useState } from 'react'
import Card from '../ui/Card'
import Segmented from '../ui/Segmented'
import Button from '../ui/Button'
import { EscenarioSimulacionItem, EscenarioParamsIn } from '../../api'

interface EscenarioConfigPanelProps {
  escenario: EscenarioSimulacionItem
  index: number
  onChangePreset: (tipo: string) => void
  onChangeParam: (campo: string, valor: any) => void
  onSave: () => void
}

const PRESETS = ['base', 'alcista', 'bajista', 'crisis', 'personalizado']
const MODOS_DIVIDENDOS = ['reinvertir_total', 'reinvertir_parcial', 'retirar']

export default function EscenarioConfigPanel({
  escenario,
  index,
  onChangePreset,
  onChangeParam,
  onSave,
}: EscenarioConfigPanelProps) {
  const [mostrarAvanzado, setMostrarAvanzado] = useState(false)
  const params = escenario.parametros || {
    horizonte_meses: 60,
    variacion_dolar_pct: 0,
    variacion_por_instrumento: {},
    variacion_por_defecto_pct: 0,
    aporte_mensual_usd: 0,
    crecimiento_aporte_anual_pct: 0,
    retiro_mensual_usd: 0,
    modo_dividendos: 'reinvertir_total',
    dividend_yield_anual_pct: 0,
    pct_dividendo_reinvertido: null,
    comision_pct: 0,
    inflacion_anual_pct: null,
  } as EscenarioParamsIn

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    // TBD: update nombre en escenario
  }

  return (
    <Card className="p-3 bg-app-surface border border-app-border">
      {/* Header con preset selector */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <input
            type="text"
            placeholder={`Escenario ${index + 1}`}
            value={escenario.nombre || escenario.tipo_preset}
            onChange={handleNameChange}
            className="text-sm font-medium bg-transparent border-0 px-0 py-0 focus:outline-none text-app-text"
          />
          <span className="text-xs text-app-text-secondary">#{index + 1}</span>
        </div>

        {/* Selector de preset */}
        <Segmented
          value={escenario.tipo_preset}
          options={[
            { label: 'Base', value: 'base' },
            { label: 'Alcista', value: 'alcista' },
            { label: 'Bajista', value: 'bajista' },
            { label: 'Crisis', value: 'crisis' },
            { label: 'Custom', value: 'personalizado' },
          ]}
          onChange={(val) => onChangePreset(val)}
        />
      </div>

      {/* Parámetros principales (siempre visibles) */}
      <div className="mt-4 grid grid-cols-2 gap-2">
        {/* Horizonte */}
        <div>
          <label className="text-xs font-medium text-app-text-secondary uppercase">Horizonte</label>
          <input
            type="number"
            value={params.horizonte_meses}
            onChange={(e) => onChangeParam('horizonte_meses', parseInt(e.target.value) || 0)}
            className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
            disabled={escenario.tipo_preset !== 'personalizado'}
          />
          <div className="text-[10px] text-app-text-secondary mt-0.5">meses</div>
        </div>

        {/* Variación dólar */}
        <div>
          <label className="text-xs font-medium text-app-text-secondary uppercase">Dólar</label>
          <input
            type="number"
            step="0.1"
            value={params.variacion_dolar_pct}
            onChange={(e) => onChangeParam('variacion_dolar_pct', parseFloat(e.target.value) || 0)}
            className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
            disabled={escenario.tipo_preset !== 'personalizado'}
          />
          <div className="text-[10px] text-app-text-secondary mt-0.5">%</div>
        </div>

        {/* Variación por defecto */}
        <div>
          <label className="text-xs font-medium text-app-text-secondary uppercase">Var. Default</label>
          <input
            type="number"
            step="0.1"
            value={params.variacion_por_defecto_pct}
            onChange={(e) => onChangeParam('variacion_por_defecto_pct', parseFloat(e.target.value) || 0)}
            className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
            disabled={escenario.tipo_preset !== 'personalizado'}
          />
          <div className="text-[10px] text-app-text-secondary mt-0.5">% anual</div>
        </div>

        {/* Aporte mensual */}
        <div>
          <label className="text-xs font-medium text-app-text-secondary uppercase">Aporte</label>
          <input
            type="number"
            step="10"
            value={params.aporte_mensual_usd}
            onChange={(e) => onChangeParam('aporte_mensual_usd', parseFloat(e.target.value) || 0)}
            className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
            disabled={escenario.tipo_preset !== 'personalizado'}
          />
          <div className="text-[10px] text-app-text-secondary mt-0.5">USD/mes</div>
        </div>

        {/* Dividend yield */}
        <div>
          <label className="text-xs font-medium text-app-text-secondary uppercase">Dividend</label>
          <input
            type="number"
            step="0.1"
            value={params.dividend_yield_anual_pct}
            onChange={(e) => onChangeParam('dividend_yield_anual_pct', parseFloat(e.target.value) || 0)}
            className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
            disabled={escenario.tipo_preset !== 'personalizado'}
          />
          <div className="text-[10px] text-app-text-secondary mt-0.5">% anual</div>
        </div>

        {/* Modo dividendos */}
        <div>
          <label className="text-xs font-medium text-app-text-secondary uppercase">Modo Div.</label>
          <select
            value={params.modo_dividendos}
            onChange={(e) => onChangeParam('modo_dividendos', e.target.value)}
            className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60"
            disabled={escenario.tipo_preset !== 'personalizado'}
          >
            {MODOS_DIVIDENDOS.map(modo => (
              <option key={modo} value={modo}>{modo}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Avanzado (colapsable) */}
      <div className="mt-3">
        <button
          onClick={() => setMostrarAvanzado(!mostrarAvanzado)}
          className="text-xs text-app-text-secondary hover:text-app-text"
        >
          {mostrarAvanzado ? '▼ Menos' : '▶ Más opciones'}
        </button>

        {mostrarAvanzado && (
          <div className="mt-3 grid grid-cols-2 gap-2 pt-3 border-t border-app-border">
            {/* Retiro mensual */}
            <div>
              <label className="text-xs font-medium text-app-text-secondary uppercase">Retiro</label>
              <input
                type="number"
                step="10"
                value={params.retiro_mensual_usd}
                onChange={(e) => onChangeParam('retiro_mensual_usd', parseFloat(e.target.value) || 0)}
                className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
                disabled={escenario.tipo_preset !== 'personalizado'}
              />
              <div className="text-[10px] text-app-text-secondary mt-0.5">USD/mes</div>
            </div>

            {/* Crecimiento aporte */}
            <div>
              <label className="text-xs font-medium text-app-text-secondary uppercase">Crec. Aporte</label>
              <input
                type="number"
                step="0.1"
                value={params.crecimiento_aporte_anual_pct}
                onChange={(e) => onChangeParam('crecimiento_aporte_anual_pct', parseFloat(e.target.value) || 0)}
                className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
                disabled={escenario.tipo_preset !== 'personalizado'}
              />
              <div className="text-[10px] text-app-text-secondary mt-0.5">% anual</div>
            </div>

            {/* Comisión */}
            <div>
              <label className="text-xs font-medium text-app-text-secondary uppercase">Comisión</label>
              <input
                type="number"
                step="0.01"
                value={params.comision_pct}
                onChange={(e) => onChangeParam('comision_pct', parseFloat(e.target.value) || 0)}
                className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
                disabled={escenario.tipo_preset !== 'personalizado'}
              />
              <div className="text-[10px] text-app-text-secondary mt-0.5">%</div>
            </div>

            {/* Inflación */}
            <div>
              <label className="text-xs font-medium text-app-text-secondary uppercase">Inflación</label>
              <input
                type="number"
                step="0.1"
                value={params.inflacion_anual_pct || ''}
                onChange={(e) => onChangeParam('inflacion_anual_pct', e.target.value ? parseFloat(e.target.value) : null)}
                className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
                disabled={escenario.tipo_preset !== 'personalizado'}
                placeholder="Opcional"
              />
              <div className="text-[10px] text-app-text-secondary mt-0.5">% anual</div>
            </div>
          </div>
        )}
      </div>

      {/* Botón guardar */}
      <div className="mt-3 pt-3 border-t border-app-border">
        <Button
          onClick={onSave}
          className="w-full text-xs py-2"
          variant="outline"
        >
          Guardar escenario
        </Button>
      </div>
    </Card>
  )
}
