import { useEffect, useState } from 'react'
import dayjs from 'dayjs'
import { useInversionesContext } from '../context/InversionesContext'
import { useObjetivoInversion } from '../hooks/useObjetivoInversion'
import { formatUSD, calcularProyeccionConInteres } from '../utils'
import ScreenHeader from '../components/layout/ScreenHeader'
import Card from '../components/ui/Card'
import EmptyState from '../components/ui/EmptyState'
import AportesChart from '../components/charts/AportesChart'
import { Icon } from '../components/icons/Icons'

export default function Objetivo() {
  const { carteras, carteraSeleccionada, setCarteraSeleccionada } = useInversionesContext()
  const { objetivo, aportesHistoricos, loading } = useObjetivoInversion(carteraSeleccionada)
  const [tasaInput, setTasaInput] = useState('')

  useEffect(() => {
    if (!carteraSeleccionada) return
    const stored = localStorage.getItem(`objetivo-tasa-${carteraSeleccionada}`)
    setTasaInput(stored ?? '')
  }, [carteraSeleccionada])

  const handleTasaChange = (value: string) => {
    setTasaInput(value)
    if (carteraSeleccionada) {
      localStorage.setItem(`objetivo-tasa-${carteraSeleccionada}`, value)
    }
  }

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

  const progreso = objetivo ? Math.min((objetivo.valor_actual_usd / objetivo.monto_usd) * 100, 100) : 0
  const tasaAnualPct = Number(tasaInput.replace(',', '.')) || 0
  const proyeccion = objetivo
    ? calcularProyeccionConInteres(
        objetivo.valor_actual_usd,
        objetivo.monto_usd,
        objetivo.meses_restantes,
        objetivo.aporte_mensual_promedio_usd,
        objetivo.aporte_mensual_necesario_usd,
        tasaAnualPct
      )
    : null

  return (
    <div className="pb-4">
      <ScreenHeader title="Objetivo" />

      {loading ? (
        <div className="py-20 text-center text-app-text-dim text-[13px]">Cargando…</div>
      ) : !objetivo ? (
        <EmptyState
          title="Esta cartera no tiene un objetivo definido"
          description={`Agregá una fila para "${carteraSeleccionada}" en la pestaña "Objetivos" del Sheet (Cartera, Nombre, Fecha Límite, Monto USD) y sincronizá con el botón de arriba.`}
        />
      ) : (
        <>
          <div className="flex items-center gap-3 mb-4">
            <div className="w-[46px] h-[46px] rounded-2xl bg-app-gold-soft flex items-center justify-center text-[21px] shrink-0">{objetivo.icono}</div>
            <div className="flex-1 min-w-0">
              <div className="font-display text-[18px] font-semibold text-app-text truncate">{objetivo.nombre}</div>
              <div className="text-[11.5px] text-app-text-dim">Meta al {dayjs(objetivo.fecha_limite).format('MMM YYYY')} · cartera {carteraSeleccionada}</div>
            </div>
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

          <h3 className="text-[13.5px] font-bold text-app-text mb-2.5 flex items-center gap-1.5">
            <Icon name="trend" className="w-3.5 h-3.5 text-app-gold" />
            Simulador con interés
          </h3>
          <Card>
            <label className="block text-[11px] font-bold uppercase tracking-wide text-app-text-dim mb-2">
              Tasa anual esperada (%)
            </label>
            <input
              type="number"
              min={0}
              step={0.5}
              placeholder="0"
              value={tasaInput}
              onChange={e => handleTasaChange(e.target.value)}
              className="w-full h-11 rounded-xl bg-app-surface-2 border border-app-border px-3.5 text-[13.5px] text-app-text outline-none focus:border-app-gold/60 tabular-nums"
            />

            {proyeccion && tasaAnualPct > 0 && (
              <div className="grid grid-cols-2 gap-2 mt-3.5">
                <div className="bg-app-surface-2 rounded-[13px] p-2.5">
                  <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">Necesario/mes con interés</div>
                  <div className="font-mono text-[15px] font-bold text-app-text tabular-nums">
                    {proyeccion.aporteMensualNecesarioConInteres != null ? formatUSD(proyeccion.aporteMensualNecesarioConInteres) : '—'}
                  </div>
                  {proyeccion.ahorroAporteMensualUsd != null && proyeccion.ahorroAporteMensualUsd > 0.5 && (
                    <div className="text-[10.5px] text-app-teal font-semibold mt-1">
                      {formatUSD(proyeccion.ahorroAporteMensualUsd)} menos/mes
                    </div>
                  )}
                </div>
                <div className="bg-app-surface-2 rounded-[13px] p-2.5">
                  <div className="text-[9.5px] font-bold uppercase tracking-wide text-app-text-faint mb-1">Meses al ritmo actual</div>
                  <div className="font-mono text-[15px] font-bold text-app-text tabular-nums">
                    {proyeccion.mesesNecesariosConInteres != null ? `${proyeccion.mesesNecesariosConInteres.toFixed(1)} m` : '—'}
                  </div>
                  {proyeccion.mesesAhorrados != null && proyeccion.mesesAhorrados > 0.05 && (
                    <div className="text-[10.5px] text-app-teal font-semibold mt-1">
                      {proyeccion.mesesAhorrados.toFixed(1)} meses menos
                    </div>
                  )}
                </div>
              </div>
            )}
          </Card>

          <h3 className="text-[13.5px] font-bold text-app-text mb-2.5 mt-3.5">Aportes históricos</h3>
          <Card>
            <AportesChart aportesHistoricos={aportesHistoricos} montoObjetivo={objetivo.monto_usd} />
          </Card>
        </>
      )}
    </div>
  )
}
