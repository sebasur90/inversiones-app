import { useState } from 'react'
import Card from '../ui/Card'
import Segmented from '../ui/Segmented'
import Button from '../ui/Button'
import { EscenarioSimulacionItem, EscenarioParamsIn } from '../../api'
import FormHelp from '../../help/components/FormHelp'
import { ESCENARIO_PARAM_LIMITS } from '../../help/errors/escenarioLimits'

interface EscenarioConfigPanelProps {
  escenario: EscenarioSimulacionItem
  index: number
  onChangePreset: (tipo: string) => void
  onChangeParam: (campo: string, valor: any) => void
  onSave: () => void
  /** Tickers en cartera, para los overrides de variación por instrumento. */
  tickersDisponibles?: { ticker: string; nombre: string }[]
}

function VariacionPorInstrumento({
  overrides,
  porDefecto,
  tickers,
  onChange,
}: {
  overrides: Record<string, number>
  porDefecto: number
  tickers: { ticker: string; nombre: string }[]
  onChange: (next: Record<string, number>) => void
}) {
  const [abierto, setAbierto] = useState(false)
  // B14: texto crudo por ticker mientras se edita (permite tipear "-" antes del dígito en un
  // input controlado). Se sincroniza con `overrides` cuando el texto parsea a un número
  // completo, y al blur.
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const nOverrides = Object.keys(overrides).length

  if (tickers.length === 0) return null

  const NUM_COMPLETO = /^-?\d+(\.\d+)?$/

  const valorMostrado = (ticker: string) =>
    drafts[ticker] ?? (overrides[ticker] !== undefined ? String(overrides[ticker]) : '')

  const aplicar = (ticker: string, n: number | null) => {
    const next = { ...overrides }
    if (n === null) delete next[ticker]
    else next[ticker] = n
    if (JSON.stringify(next) !== JSON.stringify(overrides)) onChange(next)
  }

  const onInputTicker = (ticker: string, raw: string) => {
    setDrafts(d => ({ ...d, [ticker]: raw }))
    const t = raw.trim()
    if (t === '') aplicar(ticker, null)
    else if (NUM_COMPLETO.test(t)) aplicar(ticker, parseFloat(t))
  }

  const onBlurTicker = (ticker: string) => {
    const t = (drafts[ticker] ?? '').trim()
    if (t !== '' && !Number.isNaN(parseFloat(t))) aplicar(ticker, parseFloat(t))
    else if (t === '') aplicar(ticker, null)
    setDrafts(d => {
      const c = { ...d }
      delete c[ticker]
      return c
    })
  }

  const limpiar = () => {
    setDrafts({})
    onChange({})
  }

  return (
    <div>
      <button
        onClick={() => setAbierto(v => !v)}
        className="text-xs text-app-text-secondary hover:text-app-text"
      >
        {abierto ? '▼' : '▶'} Variación por instrumento{nOverrides > 0 ? ` (${nOverrides})` : ''}
      </button>
      {abierto && (
        <div className="mt-2 space-y-1.5">
          <div className="text-label text-app-text-faint">
            Variación anual % por ticker. Vacío = usa la var. default ({porDefecto}%).
          </div>
          {tickers.map(t => (
            <div key={t.ticker} className="flex items-center gap-2">
              <span className="text-label text-app-text flex-1 min-w-0 truncate" title={t.nombre}>
                <span className="font-semibold">{t.ticker}</span>
              </span>
              <input
                type="text"
                inputMode="decimal"
                value={valorMostrado(t.ticker)}
                placeholder={String(porDefecto)}
                onChange={e => onInputTicker(t.ticker, e.target.value)}
                onBlur={() => onBlurTicker(t.ticker)}
                className="w-24 h-8 rounded-lg bg-app-surface-2 border border-app-border px-2 text-xs focus:border-app-gold/60 tabular-nums"
              />
            </div>
          ))}
          {nOverrides > 0 && (
            <button
              onClick={limpiar}
              className="text-label text-app-text-secondary hover:text-app-coral"
            >
              Limpiar overrides
            </button>
          )}
        </div>
      )}
    </div>
  )
}

const PRESETS = ['base', 'alcista', 'bajista', 'crisis', 'personalizado']
const MODOS_DIVIDENDOS = ['reinvertir_total', 'reinvertir_parcial', 'retirar']

export default function EscenarioConfigPanel({
  escenario,
  index,
  onChangePreset,
  onChangeParam,
  onSave,
  tickersDisponibles = [],
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
          <FormHelp term="escenario_horizonte" label="Horizonte" fieldKey="horizonte_meses" />
          <input
            type="number"
            value={params.horizonte_meses}
            min={ESCENARIO_PARAM_LIMITS.horizonte_meses.min}
            max={ESCENARIO_PARAM_LIMITS.horizonte_meses.max}
            onChange={(e) => onChangeParam('horizonte_meses', parseInt(e.target.value) || 0)}
            className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
          />
        </div>

        {/* Variación dólar */}
        <div>
          <FormHelp term="escenario_variacion_dolar" label="Dólar" fieldKey="variacion_dolar_pct" />
          <input
            type="number"
            step="0.1"
            min={ESCENARIO_PARAM_LIMITS.variacion_dolar_pct.min}
            max={ESCENARIO_PARAM_LIMITS.variacion_dolar_pct.max}
            value={params.variacion_dolar_pct}
            onChange={(e) => onChangeParam('variacion_dolar_pct', parseFloat(e.target.value) || 0)}
            className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
          />
        </div>

        {/* Variación por defecto */}
        <div>
          <FormHelp term="escenario_variacion_default" label="Var. Default" fieldKey="variacion_por_defecto_pct" />
          <input
            type="number"
            step="0.1"
            min={ESCENARIO_PARAM_LIMITS.variacion_por_defecto_pct.min}
            max={ESCENARIO_PARAM_LIMITS.variacion_por_defecto_pct.max}
            value={params.variacion_por_defecto_pct}
            onChange={(e) => onChangeParam('variacion_por_defecto_pct', parseFloat(e.target.value) || 0)}
            className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
          />
        </div>

        {/* Aporte mensual */}
        <div>
          <FormHelp term="escenario_aporte_mensual" label="Aporte" fieldKey="aporte_mensual_usd" />
          <input
            type="number"
            step="10"
            min={ESCENARIO_PARAM_LIMITS.aporte_mensual_usd.min}
            value={params.aporte_mensual_usd}
            onChange={(e) => onChangeParam('aporte_mensual_usd', parseFloat(e.target.value) || 0)}
            className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
          />
        </div>

        {/* Dividend yield */}
        <div>
          <FormHelp term="escenario_dividend_yield" label="Dividend" fieldKey="dividend_yield_anual_pct" />
          <input
            type="number"
            step="0.1"
            min={ESCENARIO_PARAM_LIMITS.dividend_yield_anual_pct.min}
            max={ESCENARIO_PARAM_LIMITS.dividend_yield_anual_pct.max}
            value={params.dividend_yield_anual_pct}
            onChange={(e) => onChangeParam('dividend_yield_anual_pct', parseFloat(e.target.value) || 0)}
            className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
          />
        </div>

        {/* Modo dividendos */}
        <div>
          <label className="text-xs font-semibold text-app-text mb-2">Modo Div.</label>
          <select
            value={params.modo_dividendos}
            onChange={(e) => onChangeParam('modo_dividendos', e.target.value)}
            className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60"
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
          <div className="mt-3 space-y-3 pt-3 border-t border-app-border">
            <div className="grid grid-cols-2 gap-2">
              {/* Retiro mensual */}
              <div>
                <FormHelp term="escenario_retiro_mensual" label="Retiro" fieldKey="retiro_mensual_usd" />
                <input
                  type="number"
                  step="10"
                  min={ESCENARIO_PARAM_LIMITS.retiro_mensual_usd.min}
                  value={params.retiro_mensual_usd}
                  onChange={(e) => onChangeParam('retiro_mensual_usd', parseFloat(e.target.value) || 0)}
                  className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
                      />
              </div>

              {/* Crecimiento aporte */}
              <div>
                <FormHelp term="escenario_crecimiento_aporte" label="Crec. Aporte" fieldKey="crecimiento_aporte_anual_pct" />
                <input
                  type="number"
                  step="0.1"
                  min={ESCENARIO_PARAM_LIMITS.crecimiento_aporte_anual_pct.min}
                  max={ESCENARIO_PARAM_LIMITS.crecimiento_aporte_anual_pct.max}
                  value={params.crecimiento_aporte_anual_pct}
                  onChange={(e) => onChangeParam('crecimiento_aporte_anual_pct', parseFloat(e.target.value) || 0)}
                  className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
                      />
              </div>

              {/* Comisión */}
              <div>
                <FormHelp term="escenario_comision" label="Comisión" fieldKey="comision_pct" />
                <input
                  type="number"
                  step="0.01"
                  min={ESCENARIO_PARAM_LIMITS.comision_pct.min}
                  max={ESCENARIO_PARAM_LIMITS.comision_pct.max}
                  value={params.comision_pct}
                  onChange={(e) => onChangeParam('comision_pct', parseFloat(e.target.value) || 0)}
                  className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
                      />
              </div>

              {/* Inflación */}
              <div>
                <FormHelp term="escenario_inflacion" label="Inflación" />
                <input
                  type="number"
                  step="0.1"
                  min={ESCENARIO_PARAM_LIMITS.inflacion_anual_pct.min}
                  max={ESCENARIO_PARAM_LIMITS.inflacion_anual_pct.max}
                  value={params.inflacion_anual_pct || ''}
                  onChange={(e) => onChangeParam('inflacion_anual_pct', e.target.value ? parseFloat(e.target.value) : null)}
                  className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
                        placeholder="Opcional"
                />
              </div>
            </div>

            {/* Variación por instrumento (overrides por ticker) */}
            <VariacionPorInstrumento
              overrides={params.variacion_por_instrumento || {}}
              porDefecto={params.variacion_por_defecto_pct ?? 0}
              tickers={tickersDisponibles}
              onChange={next => onChangeParam('variacion_por_instrumento', next)}
            />

            {/* Porcentaje dividendo reinvertido (solo si modo = reinvertir_parcial) */}
            {params.modo_dividendos === 'reinvertir_parcial' && (
              <div>
                <FormHelp term="escenario_pct_dividendo_reinvertido" label="% Dividendo reinvertido" fieldKey="pct_dividendo_reinvertido" />
                <input
                  type="number"
                  step="0.1"
                  min={ESCENARIO_PARAM_LIMITS.pct_dividendo_reinvertido.min}
                  max={ESCENARIO_PARAM_LIMITS.pct_dividendo_reinvertido.max}
                  value={params.pct_dividendo_reinvertido ?? ''}
                  onChange={(e) => onChangeParam('pct_dividendo_reinvertido', e.target.value ? parseFloat(e.target.value) : null)}
                  className="w-full h-9 rounded-lg bg-app-surface-2 border border-app-border px-2.5 text-xs focus:border-app-gold/60 tabular-nums"
                      />
              </div>
            )}
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
